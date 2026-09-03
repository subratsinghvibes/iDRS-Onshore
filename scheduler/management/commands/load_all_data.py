"""
Django management command to populate ALL data into PostgreSQL from the
fixture files exported from the source SQLite database.

Usage:
    python manage.py load_all_data
    python manage.py load_all_data --skip-large    # skip MPI and AuthorizedUser (fast test run)
    python manage.py load_all_data --only SECTION  # load one section (see --help)

Fixture load order (respects FK dependencies):
    01  CompanyCode               (location master — required by all norms)
    02  ExternalAppSetting        (app-level config)
    03  LocationSpecFactor        → CompanyCode
    04  DailyDrillingRate         → CompanyCode
    05  DrillingBenchmark         → CompanyCode
    06  RigBuildingNorm           → CompanyCode
    07  RigBuildingAdjustment     → CompanyCode
    08  CompletionTestingNorm     → CompanyCode
    09  AdditionalTest            → CompanyCode
    10  CoringNorm                → CompanyCode
    11  CasingNorm                → CompanyCode
    12  HermeticalTestingNorm     → CompanyCode
    13  OperationNorm             → CompanyCode
    14  VideoTutorial             (standalone, no user FK)
    15  MasterPersonnelInfo       (31 MB — ~24k rows, skip with --skip-large)
    16  AuthorizedUser            (9 MB  — ~24k rows, skip with --skip-large)
    17  Schedule                  → CompanyCode (created_by nullable)
    18  WellBasket                → CompanyCode (created_by nullable)

Notes:
    - UserProfile is NOT loaded (requires matching auth.User objects first).
      Create users via `python manage.py createsuperuser`, then assign
      profiles via Django Admin.
    - VideoTutorial DB records are loaded but the actual video files are NOT
      included in fixtures. Re-upload videos via Admin after deployment.
    - LoginAttempt and UserActivity are audit logs — deliberately excluded.
    - Run `python manage.py migrate` BEFORE this command.
"""

import os
import sys
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command


# ── Fixture file registry ─────────────────────────────────────────────────────
# Each entry: (fixture_filename, human_label, is_large, section_tag)
FIXTURES = [
    ('01_companycode.json',          'CompanyCode (28 records)',          False, 'reference'),
    ('02_externalappsetting.json',   'ExternalAppSetting (1 record)',     False, 'reference'),
    ('03_locationspecfactor.json',   'LocationSpecFactor (15 records)',   False, 'norms'),
    ('04_dailydrillingrate.json',    'DailyDrillingRate (138 records)',   False, 'norms'),
    ('05_drillingbenchmark.json',    'DrillingBenchmark (72 records)',    False, 'norms'),
    ('06_rigbuildingnorm.json',      'RigBuildingNorm (40 records)',      False, 'norms'),
    ('07_rigbuildingadjustment.json','RigBuildingAdjustment (29 records)',False, 'norms'),
    ('08_completiontestingnorm.json','CompletionTestingNorm (21 records)',False, 'norms'),
    ('09_additionaltest.json',       'AdditionalTest (59 records)',       False, 'norms'),
    ('10_coringnorm.json',           'CoringNorm (13 records)',           False, 'norms'),
    ('11_casingnorm.json',           'CasingNorm (13 records)',           False, 'norms'),
    ('12_hermeticaltestingnorm.json','HermeticalTestingNorm (11 records)',False, 'norms'),
    ('13_operationnorm.json',        'OperationNorm (21 records)',        False, 'norms'),
    ('14_videotutorial.json',        'VideoTutorial (4 records)',         False, 'misc'),
    ('15_masterpersonnelinfo.json',  'MasterPersonnelInfo (~24k records)',True,  'large'),
    ('16_authorizeduser.json',       'AuthorizedUser (~24k records)',     True,  'large'),
    ('17_schedule.json',             'Schedule (1 record)',               False, 'misc'),
    ('18_wellbasket.json',           'WellBasket (1 record)',             False, 'misc'),
]
# ─────────────────────────────────────────────────────────────────────────────


def find_fixtures_dir():
    """Locate the fixtures/ directory relative to manage.py (project root)."""
    # Try BASE_DIR / fixtures
    base = Path(os.getcwd())
    candidate = base / 'fixtures'
    if candidate.is_dir():
        return candidate
    # Walk up two levels
    for parent in [base.parent, base.parent.parent]:
        candidate = parent / 'fixtures'
        if candidate.is_dir():
            return candidate
    return None


class Command(BaseCommand):
    help = 'Load ALL iDRS data fixtures into PostgreSQL in FK-safe order'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-large',
            action='store_true',
            help='Skip large fixtures (MasterPersonnelInfo + AuthorizedUser)',
        )
        parser.add_argument(
            '--only',
            type=str,
            choices=['reference', 'norms', 'large', 'misc'],
            help='Load only one section: reference | norms | large | misc',
        )
        parser.add_argument(
            '--fixtures-dir',
            type=str,
            default=None,
            help='Explicit path to fixtures/ directory (auto-detected if not set)',
        )

    def handle(self, *args, **options):
        skip_large = options['skip_large']
        only_section = options.get('only')
        fixtures_dir_arg = options.get('fixtures_dir')

        # ── Locate fixtures directory ─────────────────────────────────────────
        if fixtures_dir_arg:
            fixtures_dir = Path(fixtures_dir_arg)
        else:
            fixtures_dir = find_fixtures_dir()

        if not fixtures_dir or not fixtures_dir.is_dir():
            raise CommandError(
                f'Cannot find fixtures/ directory.\n'
                f'  Tried: {Path(os.getcwd()) / "fixtures"}\n'
                f'  Run from the project root (where manage.py is) or pass '
                f'--fixtures-dir=<path>'
            )

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n=== iDRS Data Loader ==='
        ))
        self.stdout.write(f'  Fixtures directory : {fixtures_dir}')
        if skip_large:
            self.stdout.write(self.style.WARNING('  --skip-large: will skip MPI and AuthorizedUser'))
        if only_section:
            self.stdout.write(self.style.WARNING(f'  --only {only_section}: loading that section only'))
        self.stdout.write('')

        # ── Verify all needed files exist before starting ─────────────────────
        missing = []
        for fname, label, is_large, section in FIXTURES:
            if skip_large and is_large:
                continue
            if only_section and section != only_section:
                continue
            fpath = fixtures_dir / fname
            if not fpath.exists():
                missing.append(str(fpath))

        if missing:
            raise CommandError(
                'The following fixture files are missing:\n' +
                '\n'.join(f'  {f}' for f in missing) +
                '\n\nEnsure the fixtures/ folder was copied to the VM alongside the code.'
            )

        # ── Load each fixture in order ────────────────────────────────────────
        total = len([f for f, _, il, sec in FIXTURES
                     if not (skip_large and il)
                     and not (only_section and sec != only_section)])
        loaded = 0
        errors = []

        for fname, label, is_large, section in FIXTURES:
            if skip_large and is_large:
                self.stdout.write(f'  [SKIP] {label}')
                continue
            if only_section and section != only_section:
                continue

            loaded += 1
            fpath = str(fixtures_dir / fname)
            self.stdout.write(f'  [{loaded:02d}/{total:02d}] Loading {label}...')

            try:
                call_command(
                    'loaddata',
                    fpath,
                    verbosity=0,
                    ignore=False,
                )
                self.stdout.write(self.style.SUCCESS(f'         ✓ done'))
            except Exception as exc:
                msg = str(exc)
                errors.append((label, msg))
                self.stdout.write(self.style.ERROR(f'         ✗ FAILED: {msg[:120]}'))
                # Continue loading remaining fixtures even if one fails
                self.stdout.write(self.style.WARNING('           Continuing with remaining fixtures...'))

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write('')
        if errors:
            self.stdout.write(self.style.WARNING(
                f'Completed with {len(errors)} error(s):'
            ))
            for label, msg in errors:
                self.stdout.write(self.style.ERROR(f'  ✗ {label}: {msg[:200]}'))
            self.stdout.write('')
            self.stdout.write(
                'Common causes:\n'
                '  - Duplicate key: data already exists → safe to ignore if re-running\n'
                '  - FK violation : load the parent fixture first\n'
                '  - Missing file : check fixtures/ folder was copied correctly\n'
            )
        else:
            self.stdout.write(self.style.SUCCESS('All fixtures loaded successfully!'))

        self.stdout.write(self.style.MIGRATE_HEADING('\nPost-load checklist:'))
        self.stdout.write(
            '  1. python manage.py createsuperuser\n'
            '  2. python manage.py collectstatic --noinput\n'
            '  3. Start server: Install Windows\\start_server.bat\n'
            '  4. Log in at http://10.212.64.16:8011/admin\n'
            '  5. Re-upload any video tutorials via Admin → Video Tutorials\n'
            '     (video files are not in fixtures — only DB metadata)\n'
        )

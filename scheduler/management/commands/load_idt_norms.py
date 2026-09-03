"""
Django management command to populate IDT (Industry Drilling Time) norms
for the iDRS application on PostgreSQL.

Usage:
    python manage.py load_idt_norms
    python manage.py load_idt_norms --clear        # wipe existing norms first
    python manage.py load_idt_norms --location CAMBAY
    python manage.py load_idt_norms --location CAMBAY --clear

Covers ALL IDT norm tables:
    - CompanyCode         (prerequisite location record)
    - LocationSpecFactor  (loc-spec factor choices per location)
    - DailyDrillingRate   (m/day by depth interval & field)
    - DrillingBenchmark   (benchmark days by pool/field/category/depth)
    - RigBuildingNorm     (rig-name → build days)
    - RigBuildingAdjustment (adjustment rules for ILM/movement/weather)
    - CompletionTestingNorm (days by depth & well type)
    - AdditionalTest      (additional job norm times)
    - CoringNorm          (extra days per core by depth)
    - CasingNorm          (extra days for casing ops by depth)
    - HermeticalTestingNorm (norm days by depth)
    - OperationNorm       (operation rules/norms)
"""

from django.core.management.base import BaseCommand, CommandError
from decimal import Decimal


class Command(BaseCommand):
    help = 'Load IDT norms data into PostgreSQL for iDRS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--location',
            type=str,
            default='CAMBAY',
            help='Location name to load norms for (default: CAMBAY)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing norms for the specified location before loading',
        )

    def handle(self, *args, **options):
        # Import here so Django app registry is ready
        from scheduler.models import (
            CompanyCode, LocationSpecFactor,
            DailyDrillingRate, DrillingBenchmark,
            RigBuildingNorm, RigBuildingAdjustment,
            CompletionTestingNorm, AdditionalTest,
            CoringNorm, CasingNorm, HermeticalTestingNorm,
            OperationNorm,
        )

        location_name = options['location'].strip().title()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n=== Loading IDT Norms for location: {location_name} ==='
        ))

        # ──────────────────────────────────────────────────────────────────────
        # STEP 1 — Ensure CompanyCode (location) record exists
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[1/12] Resolving CompanyCode (location)...')
        location_obj, created = CompanyCode.objects.get_or_create(
            location=location_name,
            defaults={
                'fund_centre': 'CB01',
                'company_code': 'CB',
                'cost_centre': 'CB-DRL',
                'category': 'Asset',
                'name': f'{location_name} Asset',
                'city': location_name.title(),
                'state': 'Gujarat',
                'description': f'Drilling Asset – {location_name}',
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'  Created CompanyCode: {location_obj}'))
        else:
            self.stdout.write(f'  Using existing CompanyCode: {location_obj}')

        # ──────────────────────────────────────────────────────────────────────
        # STEP 2 — Optionally clear existing norms
        # ──────────────────────────────────────────────────────────────────────
        if options['clear']:
            self.stdout.write(
                self.style.WARNING(f'\n  Clearing existing IDT norms for {location_name}...')
            )
            models_to_clear = [
                LocationSpecFactor, DailyDrillingRate, DrillingBenchmark,
                RigBuildingNorm, RigBuildingAdjustment,
                CompletionTestingNorm, AdditionalTest,
                CoringNorm, CasingNorm, HermeticalTestingNorm,
                OperationNorm,
            ]
            for model in models_to_clear:
                count, _ = model.objects.filter(location=location_obj).delete()
                if count:
                    self.stdout.write(f'  Deleted {count} rows from {model.__name__}')

        # ──────────────────────────────────────────────────────────────────────
        # STEP 3 — Location Spec Factors
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[2/12] Loading LocationSpecFactors...')
        loc_spec_data = [
            # (factor_value, display_order, is_default)
            ('Main Pool',        1, True),
            ('other than Main',  2, False),
            ('2CP',              3, False),
            ('3CP',              4, False),
            ('4CP',              5, False),
            ('HPHT',             6, False),
            ('Standard',         7, False),
        ]
        for factor_value, display_order, is_default in loc_spec_data:
            obj, created = LocationSpecFactor.objects.get_or_create(
                location=location_obj,
                factor_value=factor_value,
                defaults={
                    'display_order': display_order,
                    'is_default': is_default,
                    'is_active': True,
                }
            )
            status = 'created' if created else 'exists'
            self.stdout.write(f'  [{status}] {factor_value}')

        # ──────────────────────────────────────────────────────────────────────
        # STEP 4 — Daily Drilling Rates
        # Fields: location, depth_start, depth_end, field, per_day_depth, loc_spec_factor
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[3/12] Loading DailyDrillingRates...')
        #
        # Typical Cambay basin m/day figures by depth band.
        # Shallower depths → higher penetration rate; deeper → slower.
        #
        daily_rate_data = [
            # (depth_start, depth_end, field,           per_day_depth, loc_spec_factor)
            (0,    500,  'Akholjuni',   Decimal('120.0'), 'Main Pool'),
            (500,  1000, 'Akholjuni',   Decimal('80.0'),  'Main Pool'),
            (1000, 1500, 'Akholjuni',   Decimal('55.0'),  'Main Pool'),
            (1500, 2000, 'Akholjuni',   Decimal('40.0'),  'Main Pool'),
            (2000, 2500, 'Akholjuni',   Decimal('30.0'),  'Main Pool'),
            (2500, 3000, 'Akholjuni',   Decimal('22.0'),  'Main Pool'),
            (3000, 4000, 'Akholjuni',   Decimal('15.0'),  'Main Pool'),

            (0,    500,  'Anklav',      Decimal('110.0'), 'Main Pool'),
            (500,  1000, 'Anklav',      Decimal('75.0'),  'Main Pool'),
            (1000, 1500, 'Anklav',      Decimal('50.0'),  'Main Pool'),
            (1500, 2000, 'Anklav',      Decimal('38.0'),  'Main Pool'),
            (2000, 2500, 'Anklav',      Decimal('28.0'),  'Main Pool'),
            (2500, 3000, 'Anklav',      Decimal('20.0'),  'Main Pool'),

            (0,    500,  'Linch',       Decimal('90.0'),  'Main Pool'),
            (500,  1000, 'Linch',       Decimal('65.0'),  'Main Pool'),
            (1000, 1500, 'Linch',       Decimal('48.0'),  'Main Pool'),
            (1500, 2000, 'Linch',       Decimal('35.0'),  'Main Pool'),
            (2000, 2500, 'Linch',       Decimal('25.0'),  'Main Pool'),

            (0,    500,  'Wavel',       Decimal('100.0'), 'Main Pool'),
            (500,  1000, 'Wavel',       Decimal('70.0'),  'Main Pool'),
            (1000, 1500, 'Wavel',       Decimal('52.0'),  'Main Pool'),
            (1500, 2000, 'Wavel',       Decimal('38.0'),  'Main Pool'),

            (0,    500,  'Kathana',     Decimal('95.0'),  'Main Pool'),
            (500,  1000, 'Kathana',     Decimal('68.0'),  'Main Pool'),
            (1000, 1500, 'Kathana',     Decimal('50.0'),  'Main Pool'),
            (1500, 2000, 'Kathana',     Decimal('36.0'),  'Main Pool'),
            (2000, 2500, 'Kathana',     Decimal('26.0'),  'Main Pool'),

            # Deep/HPHT wells
            (2000, 2500, 'Akholjuni',   Decimal('22.0'),  'HPHT'),
            (2500, 3000, 'Akholjuni',   Decimal('15.0'),  'HPHT'),
            (3000, 4000, 'Akholjuni',   Decimal('10.0'),  'HPHT'),

            # Generic fallback (field=None equivalent → use blank)
            (0,    500,  None,          Decimal('100.0'), None),
            (500,  1000, None,          Decimal('70.0'),  None),
            (1000, 1500, None,          Decimal('50.0'),  None),
            (1500, 2000, None,          Decimal('36.0'),  None),
            (2000, 2500, None,          Decimal('26.0'),  None),
            (2500, 3000, None,          Decimal('18.0'),  None),
            (3000, 4000, None,          Decimal('12.0'),  None),
        ]
        created_count = 0
        for depth_start, depth_end, field, per_day_depth, loc_spec_factor in daily_rate_data:
            obj, created = DailyDrillingRate.objects.get_or_create(
                location=location_obj,
                field=field,
                depth_start=depth_start,
                depth_end=depth_end,
                loc_spec_factor=loc_spec_factor,
                defaults={'per_day_depth': per_day_depth}
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {created_count} daily drilling rate rows created.'))

        # ──────────────────────────────────────────────────────────────────────
        # STEP 5 — Drilling Benchmarks
        # Fields: location, pool, well_category, well_depth_start, well_depth_end,
        #         field, drilling_depth, benchmark_days, loc_spec_factor
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[4/12] Loading DrillingBenchmarks...')
        benchmark_data = [
            # (pool, well_category, depth_start, depth_end, field, drilling_depth, benchmark_days, loc_spec_factor)

            # ── AK (Akholjuni) ─────────────────────────────────────────────
            ('AK', 'Vertical',    500,  1000, 'Akholjuni',   750,   Decimal('20.0'),  'Main Pool'),
            ('AK', 'Vertical',    1000, 1500, 'Akholjuni',   1250,  Decimal('28.0'),  'Main Pool'),
            ('AK', 'Vertical',    1500, 2000, 'Akholjuni',   1750,  Decimal('38.0'),  'Main Pool'),
            ('AK', 'Vertical',    2000, 2500, 'Akholjuni',   2250,  Decimal('55.0'),  'Main Pool'),
            ('AK', 'Directional', 1000, 1500, 'Akholjuni',   1250,  Decimal('35.0'),  'Main Pool'),
            ('AK', 'Directional', 1500, 2000, 'Akholjuni',   1750,  Decimal('48.0'),  'Main Pool'),
            ('AK', 'Directional', 2000, 2500, 'Akholjuni',   2250,  Decimal('65.0'),  'Main Pool'),
            ('AK', 'Directional', 2500, 3000, 'Akholjuni',   2750,  Decimal('85.0'),  'Main Pool'),
            ('AK', 'Sidetrack',   1000, 2000, 'Akholjuni',   1500,  Decimal('30.0'),  'Main Pool'),
            ('AK', 'Sidetrack',   2000, 3000, 'Akholjuni',   2500,  Decimal('50.0'),  'Main Pool'),

            # HPHT deep Akholjuni
            ('AK', 'Directional', 2500, 3500, 'Akholjuni',   3000,  Decimal('110.0'), 'HPHT'),
            ('AK', 'Vertical',    2500, 3500, 'Akholjuni',   3000,  Decimal('90.0'),  'HPHT'),

            # ── AV (Anklav / Ambarapura) ────────────────────────────────────
            ('AV', 'Vertical',    500,  1000, 'Anklav',      750,   Decimal('22.0'),  'Main Pool'),
            ('AV', 'Vertical',    1000, 1500, 'Anklav',      1250,  Decimal('30.0'),  'Main Pool'),
            ('AV', 'Vertical',    1500, 2000, 'Anklav',      1750,  Decimal('42.0'),  'Main Pool'),
            ('AV', 'Directional', 1000, 1500, 'Anklav',      1250,  Decimal('38.0'),  'Main Pool'),
            ('AV', 'Directional', 1500, 2000, 'Anklav',      1750,  Decimal('52.0'),  'Main Pool'),
            ('AV', 'Directional', 2000, 2500, 'Anklav',      2250,  Decimal('70.0'),  'Main Pool'),
            ('AV', 'Sidetrack',   1000, 2000, 'Anklav',      1500,  Decimal('32.0'),  'Main Pool'),

            # ── KT (Kantharia) ──────────────────────────────────────────────
            ('KT', 'Vertical',    500,  1000, 'Kantharia',   750,   Decimal('18.0'),  'Main Pool'),
            ('KT', 'Vertical',    1000, 1500, 'Kantharia',   1250,  Decimal('26.0'),  'Main Pool'),
            ('KT', 'Vertical',    1500, 2000, 'Kantharia',   1750,  Decimal('36.0'),  'Main Pool'),
            ('KT', 'Directional', 1000, 1500, 'Kantharia',   1250,  Decimal('33.0'),  'Main Pool'),
            ('KT', 'Directional', 1500, 2000, 'Kantharia',   1750,  Decimal('45.0'),  'Main Pool'),
            ('KT', 'Directional', 2000, 2500, 'Kantharia',   2250,  Decimal('60.0'),  'Main Pool'),
            ('KT', 'Sidetrack',   1000, 2000, 'Kantharia',   1500,  Decimal('28.0'),  'Main Pool'),

            # ── Linch ───────────────────────────────────────────────────────
            ('LN', 'Vertical',    500,  1000, 'Linch',       750,   Decimal('20.0'),  'Main Pool'),
            ('LN', 'Vertical',    1000, 1500, 'Linch',       1250,  Decimal('28.0'),  'Main Pool'),
            ('LN', 'Directional', 1000, 1500, 'Linch',       1250,  Decimal('36.0'),  'Main Pool'),
            ('LN', 'Directional', 1500, 2000, 'Linch',       1750,  Decimal('50.0'),  'Main Pool'),

            # ── Wavel ───────────────────────────────────────────────────────
            ('WV', 'Vertical',    500,  1000, 'Wavel',       750,   Decimal('19.0'),  'Main Pool'),
            ('WV', 'Vertical',    1000, 1500, 'Wavel',       1250,  Decimal('27.0'),  'Main Pool'),
            ('WV', 'Directional', 1000, 1500, 'Wavel',       1250,  Decimal('34.0'),  'Main Pool'),
            ('WV', 'Directional', 1500, 2000, 'Wavel',       1750,  Decimal('48.0'),  'Main Pool'),

            # ── 2CP / 3CP loc-spec variants (shallower, faster pools) ───────
            ('AK', 'Vertical',    500,  1000, 'Akholjuni',   750,   Decimal('15.0'),  '2CP'),
            ('AK', 'Vertical',    1000, 1500, 'Akholjuni',   1250,  Decimal('22.0'),  '2CP'),
            ('AK', 'Directional', 1000, 1500, 'Akholjuni',   1250,  Decimal('28.0'),  '2CP'),
            ('AK', 'Vertical',    500,  1000, 'Akholjuni',   750,   Decimal('13.0'),  '3CP'),
            ('AK', 'Vertical',    1000, 1500, 'Akholjuni',   1250,  Decimal('20.0'),  '3CP'),
        ]
        created_count = 0
        for pool, well_cat, d_start, d_end, field, drilling_depth, bench_days, loc_spec in benchmark_data:
            obj, created = DrillingBenchmark.objects.get_or_create(
                location=location_obj,
                pool=pool,
                well_category=well_cat,
                well_depth_start=d_start,
                well_depth_end=d_end,
                field=field,
                loc_spec_factor=loc_spec,
                defaults={
                    'drilling_depth': drilling_depth,
                    'benchmark_days': bench_days,
                }
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {created_count} drilling benchmark rows created.'))

        # ──────────────────────────────────────────────────────────────────────
        # STEP 6 — Rig Building Norms
        # Fields: location, rig_name, days, top_drive, rig_type
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[5/12] Loading RigBuildingNorms...')
        rig_building_data = [
            # (rig_name,         days, top_drive, rig_type)

            # Fixed rigs (E-series, NG)
            ('E-760',            7,    False, 'Fixed'),
            ('E-1000',           7,    False, 'Fixed'),
            ('E-1400',           7,    True,  'Fixed'),
            ('E-1400-5',         7,    True,  'Fixed'),
            ('E-2000',           10,   True,  'Fixed'),
            ('NG-1500',          7,    True,  'Fixed'),
            ('NG-1500-1',        7,    True,  'Fixed'),
            ('NG-2000',          10,   True,  'Fixed'),

            # Mobile rigs — IPS series
            ('IPS-M700',         5,    False, 'Mobile'),
            ('IPS-M700-9',       5,    False, 'Mobile'),
            ('IPS-M1000',        5,    True,  'Mobile'),

            # Mobile rigs — JOHN series
            ('JOHN-12',          5,    False, 'Mobile'),
            ('JOHN-18',          5,    False, 'Mobile'),
            ('JOHN-1000-29',     5,    False, 'Mobile'),

            # Generic categories (used as fallback)
            ('Mobile rigs',      5,    False, 'Mobile'),
            ('Fixed rigs',       7,    False, 'Fixed'),
        ]
        created_count = 0
        for rig_name, days, top_drive, rig_type in rig_building_data:
            obj, created = RigBuildingNorm.objects.get_or_create(
                location=location_obj,
                rig_name=rig_name,
                defaults={
                    'days': days,
                    'top_drive': top_drive,
                    'rig_type': rig_type,
                }
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {created_count} rig building norm rows created.'))

        # ──────────────────────────────────────────────────────────────────────
        # STEP 7 — Rig Building Adjustments (Add-off / ILM rules)
        # Fields: location, condition, category, adjustment_type, adjustment_value,
        #         adjustment_display, unit, min_distance, max_distance,
        #         applies_to_rig_type, max_depth, notes, is_active, priority
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[6/12] Loading RigBuildingAdjustments...')
        rig_adj_data = [
            # (condition, category, adj_type, adj_value, adj_display, unit, min_dist, max_dist, rig_type, max_depth, notes, priority)
            (
                'Rig dragged within 25 m radius for adjacent cluster well',
                'cluster_movement', 'replace',
                Decimal('1.0'), '1 day', None,
                None, Decimal('25.0'), 'Mobile', None,
                'Rig dragged short distance within same cluster pad', 10
            ),
            (
                'Rig moved 25 m to 500 m (within same field)',
                'cluster_movement', 'replace',
                Decimal('2.0'), '2 days', None,
                Decimal('25.0'), Decimal('500.0'), 'Mobile', None,
                'Short distance move within the same field area', 9
            ),
            (
                'Rig moved 500 m to 2 km (inter-cluster move)',
                'transportation', 'replace',
                Decimal('3.0'), '3 days', None,
                Decimal('500.0'), Decimal('2000.0'), 'Mobile', None,
                'Intermediate distance move requiring additional transport', 8
            ),
            (
                'Rig moved > 2 km (long distance move)',
                'transportation', 'per_unit',
                Decimal('1.0'), '+1 day per 50 km', '50 km',
                Decimal('2000.0'), None, 'Mobile', None,
                'Long-distance move: 1 additional day for every 50 km beyond base', 7
            ),
            (
                'Top-drive installation or removal (Mobile rig)',
                'equipment', 'add',
                Decimal('1.0'), '+1 day', None,
                None, None, 'Mobile', None,
                'Additional time for top-drive equipment installation/removal', 5
            ),
            (
                'Fixed rig (standard rig build)',
                'other', 'replace',
                Decimal('7.0'), '7 days', None,
                None, None, 'Fixed', None,
                'Standard rig building time for fixed rigs in Cambay', 1
            ),
            (
                'Monsoon season movement (June–September)',
                'weather', 'conversion',
                Decimal('1.43'), '1 monsoon day = 1.43 dry-season days', None,
                None, None, None, None,
                'Monsoon conversion: road conditions extend move time. Multiply normal days by 1.43', 6
            ),
            (
                'River / canal crossing during movement',
                'transportation', 'add',
                Decimal('1.0'), '+1 day', None,
                None, None, 'Mobile', None,
                'Additional day when rig route crosses a river or canal', 4
            ),
            (
                'Deep well > 2500 m — additional rigging time for TD-enhanced BOP',
                'equipment', 'add',
                Decimal('1.0'), '+1 day', None,
                None, None, None, Decimal('2500.0'),
                'Heavier well control equipment requires extra time for deep wells', 3
            ),
            (
                'Same-pad back-to-back well (Fixed rig, no dismantling)',
                'cluster_movement', 'included',
                None, 'Included (0 extra days)', None,
                None, None, 'Fixed', None,
                'Fixed rig stays in position; no extra rig-build time needed', 2
            ),
        ]
        created_count = 0
        for (condition, category, adj_type, adj_value, adj_display, unit,
             min_dist, max_dist, rig_type, max_depth, notes, priority) in rig_adj_data:
            obj, created = RigBuildingAdjustment.objects.get_or_create(
                location=location_obj,
                condition=condition,
                defaults={
                    'category': category,
                    'adjustment_type': adj_type,
                    'adjustment_value': adj_value,
                    'adjustment_display': adj_display,
                    'unit': unit,
                    'min_distance': min_dist,
                    'max_distance': max_dist,
                    'applies_to_rig_type': rig_type,
                    'max_depth': max_depth,
                    'notes': notes,
                    'is_active': True,
                    'priority': priority,
                }
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {created_count} rig building adjustment rows created.'))

        # ──────────────────────────────────────────────────────────────────────
        # STEP 8 — Completion Testing Norms
        # Fields: location, well_depth_start, well_depth_end, well_type, days
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[7/12] Loading CompletionTestingNorms...')
        completion_data = [
            # (depth_start, depth_end, well_type,    days)
            (0,    500,  'Development',   Decimal('5.0')),
            (500,  1000, 'Development',   Decimal('7.0')),
            (1000, 1500, 'Development',   Decimal('9.0')),
            (1500, 2000, 'Development',   Decimal('12.0')),
            (2000, 2500, 'Development',   Decimal('15.0')),
            (2500, 3000, 'Development',   Decimal('18.0')),
            (3000, 4000, 'Development',   Decimal('22.0')),

            (0,    500,  'Exploratory',   Decimal('7.0')),
            (500,  1000, 'Exploratory',   Decimal('10.0')),
            (1000, 1500, 'Exploratory',   Decimal('14.0')),
            (1500, 2000, 'Exploratory',   Decimal('18.0')),
            (2000, 2500, 'Exploratory',   Decimal('22.0')),
            (2500, 3000, 'Exploratory',   Decimal('28.0')),
            (3000, 4000, 'Exploratory',   Decimal('35.0')),
        ]
        created_count = 0
        for depth_start, depth_end, well_type, days in completion_data:
            obj, created = CompletionTestingNorm.objects.get_or_create(
                location=location_obj,
                well_depth_start=depth_start,
                well_depth_end=depth_end,
                well_type=well_type,
                defaults={'days': days}
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {created_count} completion testing norm rows created.'))

        # ──────────────────────────────────────────────────────────────────────
        # STEP 9 — Additional Tests
        # Fields: location, job, norm_time, notes
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[8/12] Loading AdditionalTests...')
        additional_test_data = [
            # (job, norm_time, notes)
            ('DST (Drill Stem Test) — Single Zone',
             '3 days',
             'Single zone DST including running, testing, and POOH'),
            ('DST — Multi Zone (per additional zone)',
             '+1 day per zone',
             'Each additional zone after the first adds 1 day'),
            ('WFT / MDT (Formation Evaluation Tool)',
             '1.5 days',
             'Wireline formation tester; includes rig-up/rig-down'),
            ('RFT (Repeat Formation Tester)',
             '1 day',
             'Repeat formation tester logging run'),
            ('Core Barrel Run (Conventional Core)',
             '1 day per 9 m core',
             'Full conventional coring run including core handling on surface'),
            ('Sidewall Core (per run)',
             '0.5 days',
             'Percussion or rotary sidewall coring'),
            ('CBL/USIT (Cement Bond Log)',
             '0.5 days',
             'Post-cementation cement bond quality evaluation'),
            ('Production Test / Extended Well Test',
             '7 days',
             'Extended production testing including surface test equipment rigging'),
            ('PVT Sampling',
             '0.5 days',
             'Downhole fluid sampling for PVT analysis'),
            ('Perforation (Tubing Conveyed)',
             '1 day',
             'TCP perforation in completed interval'),
            ('Perforation (Wireline)',
             '0.5 days',
             'Wireline gun perforation'),
            ('Stimulation / Fracturing (Hydraulic)',
             '3 days',
             'Hydraulic fracturing including pre-frac and post-frac evaluation'),
            ('Acid Job (Matrix Stimulation)',
             '1 day',
             'Matrix acid stimulation treatment'),
            ('SPDC / SIPT (Step Rate / Injection Pressure Test)',
             '2 days',
             'Injectivity test for injection wells'),
            ('Velocity String Installation',
             '1.5 days',
             'Velocity string installation for liquid-loading mitigation'),
            ('ESP Installation / Workover',
             '5 days',
             'Electric submersible pump installation'),
            ('Fish Recovery / Junk Removal',
             '3 days',
             'Average fishing job; actual time varies'),
            ('Whipstock Setting (Directional Kick-off)',
             '2 days',
             'Whipstock placement and directional kick-off'),
            ('Logging (Full Suite — Wireline)',
             '1 day',
             'Full suite wireline logging run through open hole'),
            ('Logging (LWD/MWD)',
             'Included in drilling time',
             'LWD/MWD run simultaneously with drilling — no separate norm time'),
        ]
        created_count = 0
        for job, norm_time, notes in additional_test_data:
            obj, created = AdditionalTest.objects.get_or_create(
                location=location_obj,
                job=job,
                defaults={
                    'norm_time': norm_time,
                    'notes': notes,
                }
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {created_count} additional test rows created.'))

        # ──────────────────────────────────────────────────────────────────────
        # STEP 10 — Coring Norms (extra add-off days for coring by depth)
        # Fields: location, depth_start, depth_end, additional_days
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[9/12] Loading CoringNorms...')
        coring_data = [
            # (depth_start, depth_end, additional_days_per_core)
            (0,    500,  Decimal('0.5')),
            (500,  1000, Decimal('0.75')),
            (1000, 1500, Decimal('1.0')),
            (1500, 2000, Decimal('1.25')),
            (2000, 2500, Decimal('1.5')),
            (2500, 3000, Decimal('2.0')),
            (3000, 4000, Decimal('2.5')),
        ]
        created_count = 0
        for depth_start, depth_end, additional_days in coring_data:
            obj, created = CoringNorm.objects.get_or_create(
                location=location_obj,
                depth_start=depth_start,
                depth_end=depth_end,
                defaults={'additional_days': additional_days}
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {created_count} coring norm rows created.'))

        # ──────────────────────────────────────────────────────────────────────
        # STEP 11 — Casing Norms (extra days for casing lowering + cementation)
        # Fields: location, depth_start, depth_end, additional_days
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[10/12] Loading CasingNorms...')
        casing_data = [
            # (depth_start, depth_end, additional_days)
            (0,    500,  Decimal('0.5')),
            (500,  1000, Decimal('0.75')),
            (1000, 1500, Decimal('1.0')),
            (1500, 2000, Decimal('1.5')),
            (2000, 2500, Decimal('2.0')),
            (2500, 3000, Decimal('2.5')),
            (3000, 4000, Decimal('3.0')),
        ]
        created_count = 0
        for depth_start, depth_end, additional_days in casing_data:
            obj, created = CasingNorm.objects.get_or_create(
                location=location_obj,
                depth_start=depth_start,
                depth_end=depth_end,
                defaults={'additional_days': additional_days}
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {created_count} casing norm rows created.'))

        # ──────────────────────────────────────────────────────────────────────
        # STEP 12 — Hermetical Testing Norms
        # Fields: location, depth_start, depth_end, norm_days
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[11/12] Loading HermeticalTestingNorms...')
        hermetical_data = [
            # (depth_start, depth_end, norm_days)
            (0,    500,  Decimal('0.5')),
            (500,  1000, Decimal('0.5')),
            (1000, 1500, Decimal('0.75')),
            (1500, 2000, Decimal('1.0')),
            (2000, 2500, Decimal('1.0')),
            (2500, 3000, Decimal('1.5')),
            (3000, 4000, Decimal('2.0')),
        ]
        created_count = 0
        for depth_start, depth_end, norm_days in hermetical_data:
            obj, created = HermeticalTestingNorm.objects.get_or_create(
                location=location_obj,
                depth_start=depth_start,
                depth_end=depth_end,
                defaults={'norm_days': norm_days}
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {created_count} hermetical testing norm rows created.'))

        # ──────────────────────────────────────────────────────────────────────
        # STEP 13 — Operation Norms
        # Fields: location, operation, norm_rule, remarks
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write('\n[12/12] Loading OperationNorms...')
        operation_data = [
            # (operation, norm_rule, remarks)
            ('Rig Building (Mobile)',
             '5 days standard; adjust per RigBuildingAdjustment rules',
             'Includes rig-up, safety checks, and BOP pressure test'),
            ('Rig Building (Fixed)',
             '7 days standard',
             'Includes full electrical, mechanical and safety commissioning'),
            ('Conductor Pipe Driving',
             '1 day',
             'Conductor driving to 30–50 m depth'),
            ('Spud / Surface Hole Drilling',
             '2 days',
             'Drilling surface hole section to ~200 m, cement conductor pipe'),
            ('BOP Installation and Pressure Test',
             '0.5 days',
             'Installation and 200 kgf/cm² pressure test of BOP stack'),
            ('Mud Mixing and Conditioning',
             '0.25 days per significant change',
             'For major mud system changes; minor top-ups are included in drilling time'),
            ('Bit Change (trip in/trip out)',
             '0.5 days per round trip at 1000 m depth; scale with depth',
             'Approximate: 1 day per round trip at 2000 m'),
            ('Casing Lowering + Cementation',
             'Per CasingNorm table by depth interval',
             'Time includes casing running, cementing, and WOC'),
            ('Core Cutting and Handling',
             'Per CoringNorm table by depth interval',
             'Each 9 m barrel; surface core handling included'),
            ('Wellhead Installation',
             '0.5 days',
             'Installation of Christmas tree / wellhead equipment after completion'),
            ('Well Abandonment (P&A)',
             '5 days',
             'Permanent plug and abandon including regulatory requirements'),
            ('Logging (Open Hole Suite)',
             '1 day',
             'Standard wireline logging suite in open hole'),
            ('Directional Survey',
             'Included in drilling norm',
             'Survey shots taken while drilling; no separate norm time'),
            ('Pressure Test — Wellbore / Liner',
             '0.5 days',
             'Liner hanger or casing pressure integrity test'),
            ('Rig-down after TD',
             '3 days (Mobile); 5 days (Fixed)',
             'Post-TD rig demobilisation before next move'),
        ]
        created_count = 0
        for operation, norm_rule, remarks in operation_data:
            obj, created = OperationNorm.objects.get_or_create(
                location=location_obj,
                operation=operation,
                defaults={
                    'norm_rule': norm_rule,
                    'remarks': remarks,
                }
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f'  {created_count} operation norm rows created.'))

        # ──────────────────────────────────────────────────────────────────────
        # Summary
        # ──────────────────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f'\n✓ IDT Norms loaded successfully for location: {location_name}'
        ))
        self.stdout.write(
            '\nRun this to verify:\n'
            '  python manage.py shell -c "'
            'from scheduler.models import DrillingBenchmark, DailyDrillingRate, RigBuildingNorm; '
            'print(DrillingBenchmark.objects.count(), DailyDrillingRate.objects.count(), RigBuildingNorm.objects.count())'
            '"'
        )
        self.stdout.write(
            '\nTo load norms for a second location, run:\n'
            '  python manage.py load_idt_norms --location MEHSANA\n'
        )

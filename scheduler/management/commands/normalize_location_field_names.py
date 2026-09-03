"""
Django management command to normalize location and field names to title case
This ensures consistency across the database for fields and locations.

Usage:
    python manage.py normalize_location_field_names
    python manage.py normalize_location_field_names --dry-run  # Preview changes without applying
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from scheduler.models import CompanyCode, Well, StagedWell


class Command(BaseCommand):
    help = 'Normalize location and field_name values to title case for consistency'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying them',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))
        
        # Statistics
        stats = {
            'company_codes_updated': 0,
            'wells_updated': 0,
            'staged_wells_updated': 0,
        }
        
        # Update CompanyCode locations
        self.stdout.write('\nProcessing CompanyCode locations...')
        company_codes = CompanyCode.objects.all()
        for code in company_codes:
            if code.location and code.location != code.location.title():
                old_location = code.location
                new_location = code.location.title()
                self.stdout.write(f'  CompanyCode {code.company_code}: "{old_location}" -> "{new_location}"')
                if not dry_run:
                    code.location = new_location
                    code.save()
                stats['company_codes_updated'] += 1
        
        # Update Well field_names (including soft-deleted)
        self.stdout.write('\nProcessing Well field_names...')
        wells = Well.all_objects.all()  # Include soft-deleted wells
        for well in wells:
            if well.field_name and well.field_name != well.field_name.title():
                old_field = well.field_name
                new_field = well.field_name.title()
                deleted_marker = ' [DELETED]' if well.is_deleted else ''
                self.stdout.write(f'  Well {well.name}{deleted_marker}: "{old_field}" -> "{new_field}"')
                if not dry_run:
                    well.field_name = new_field
                    well.save()
                stats['wells_updated'] += 1
        
        # Update StagedWell field_names
        self.stdout.write('\nProcessing StagedWell field_names...')
        staged_wells = StagedWell.objects.all()
        for well in staged_wells:
            if well.field_name and well.field_name != well.field_name.title():
                old_field = well.field_name
                new_field = well.field_name.title()
                self.stdout.write(f'  StagedWell {well.name}: "{old_field}" -> "{new_field}"')
                if not dry_run:
                    well.field_name = new_field
                    well.save()
                stats['staged_wells_updated'] += 1
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('Summary:'))
        self.stdout.write(f'  CompanyCode locations updated: {stats["company_codes_updated"]}')
        self.stdout.write(f'  Well field_names updated: {stats["wells_updated"]}')
        self.stdout.write(f'  StagedWell field_names updated: {stats["staged_wells_updated"]}')
        self.stdout.write(f'  Total updates: {sum(stats.values())}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No changes were saved'))
            self.stdout.write('Run without --dry-run to apply changes')
        else:
            self.stdout.write(self.style.SUCCESS('\nAll changes have been applied successfully!'))

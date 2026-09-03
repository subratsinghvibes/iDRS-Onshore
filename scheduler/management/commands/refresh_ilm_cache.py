"""
Fast batch ILM cache refresh command.
Computes ilm_days/ilm_note/ilm_rules_applied for all WellPairDistance records
using bulk_update in batches for high performance.
"""
from django.core.management.base import BaseCommand
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Refresh ILM cache fields (ilm_days, ilm_note, ilm_rules_applied) for all WellPairDistance records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Number of records to process per batch (default: 500)'
        )
        parser.add_argument(
            '--location',
            type=str,
            default=None,
            help='Only refresh for this location (company_code or location name)'
        )

    def handle(self, *args, **options):
        from scheduler.models import WellPairDistance, CompanyCode
        from scheduler.views import refresh_ilm_cache_for_location
        from django.db.models import Q

        batch_size = options['batch_size']
        location_filter = options.get('location')

        if location_filter:
            locations = CompanyCode.objects.filter(
                Q(location__iexact=location_filter) | Q(company_code__iexact=location_filter)
            )
            if not locations.exists():
                self.stderr.write(f'Location "{location_filter}" not found')
                return
        else:
            # All locations that have WellPairDistance records
            location_ids = WellPairDistance.objects.values_list('location_id', flat=True).distinct()
            locations = CompanyCode.objects.filter(id__in=location_ids)

        total_locs = locations.count()
        self.stdout.write(f'Refreshing ILM cache for {total_locs} location(s)...')

        total_updated = 0
        for loc in locations:
            count = WellPairDistance.objects.filter(location=loc).count()
            self.stdout.write(f'  {loc.location}: {count} records...')
            updated = refresh_ilm_cache_for_location(loc, batch_size=batch_size)
            self.stdout.write(f'    -> updated {updated} records')
            total_updated += updated

        null_remaining = WellPairDistance.objects.filter(ilm_days__isnull=True).count()
        self.stdout.write(self.style.SUCCESS(
            f'Done! Updated {total_updated} records total. Remaining null: {null_remaining}'
        ))

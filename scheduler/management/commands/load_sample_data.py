from django.core.management.base import BaseCommand
from decimal import Decimal
from datetime import date, timedelta
from scheduler.models import Rig, Well
import random


class Command(BaseCommand):
    help = 'Load sample drilling rig and well data for testing'

    def handle(self, *args, **options):
        self.stdout.write('Creating sample rigs...')
        
        # Create sample rigs
        rigs_data = [
            {
                'name': 'RIG-001',
                'rig_type': 'Mobile',
                'start_date': date.today(),
                'end_date': date.today() + timedelta(days=365),
                'rig_capacity_hp': 2500,
                'daily_cost_inr': Decimal('1875000.00'),  # ~25000 USD
                'drilling_capacity_m': 4572,  # 15000 ft
                'mobilization_time_days': '5 days',
                'maintenance_schedule': 'Monthly',
                'crew_availability': 'OK',
                'hpht_suitability': 'Y',
                'ilm_cost_fixed': Decimal('500000.00'),
                'ilm_cost_per_km': Decimal('1000.00'),
                'ilm_cost_cluster': Decimal('250000.00'),
                'bop_stack': 5000,
                'tds_availability': 'Y',
            },
            {
                'name': 'RIG-002',
                'rig_type': 'Mobile',
                'start_date': date.today(),
                'end_date': date.today() + timedelta(days=300),
                'rig_capacity_hp': 2000,
                'daily_cost_inr': Decimal('1500000.00'),  # ~20000 USD
                'drilling_capacity_m': 3658,  # 12000 ft
                'mobilization_time_days': '3 days',
                'maintenance_schedule': 'Quarterly',
                'crew_availability': 'OK',
                'hpht_suitability': 'N',
                'ilm_cost_fixed': Decimal('400000.00'),
                'ilm_cost_per_km': Decimal('800.00'),
                'ilm_cost_cluster': Decimal('200000.00'),
                'bop_stack': 4000,
                'tds_availability': 'Y',
            },
            {
                'name': 'RIG-003',
                'rig_type': 'Fixed',
                'start_date': date.today() + timedelta(days=30),
                'end_date': date.today() + timedelta(days=400),
                'rig_capacity_hp': 3500,
                'daily_cost_inr': Decimal('2625000.00'),  # ~35000 USD
                'drilling_capacity_m': 6096,  # 20000 ft
                'mobilization_time_days': '10 days',
                'maintenance_schedule': 'Bi-annual',
                'crew_availability': 'OK',
                'hpht_suitability': 'Y',
                'ilm_cost_fixed': Decimal('800000.00'),
                'ilm_cost_per_km': Decimal('1500.00'),
                'ilm_cost_cluster': Decimal('400000.00'),
                'bop_stack': 7000,
                'tds_availability': 'Y',
            },
            {
                'name': 'RIG-004',
                'rig_type': 'Mobile',
                'start_date': date.today(),
                'end_date': date.today() + timedelta(days=250),
                'rig_capacity_hp': 1500,
                'daily_cost_inr': Decimal('1125000.00'),  # ~15000 USD
                'drilling_capacity_m': 2438,  # 8000 ft
                'mobilization_time_days': 'Nil',
                'maintenance_schedule': 'Monthly',
                'crew_availability': 'OK',
                'hpht_suitability': 'N',
                'ilm_cost_fixed': Decimal('300000.00'),
                'ilm_cost_per_km': Decimal('600.00'),
                'ilm_cost_cluster': Decimal('150000.00'),
                'bop_stack': 3000,
                'tds_availability': 'N',
            },
            {
                'name': 'RIG-005',
                'rig_type': 'Mobile',
                'start_date': date.today() + timedelta(days=15),
                'end_date': date.today() + timedelta(days=350),
                'rig_capacity_hp': 3000,
                'daily_cost_inr': Decimal('2100000.00'),  # ~28000 USD
                'drilling_capacity_m': 5486,  # 18000 ft
                'mobilization_time_days': '7 days',
                'maintenance_schedule': 'Quarterly',
                'crew_availability': 'OK',
                'hpht_suitability': 'Y',
                'ilm_cost_fixed': Decimal('600000.00'),
                'ilm_cost_per_km': Decimal('1200.00'),
                'ilm_cost_cluster': Decimal('300000.00'),
                'bop_stack': 6000,
                'tds_availability': 'Y',
            }
        ]
        
        for rig_data in rigs_data:
            rig, created = Rig.objects.get_or_create(
                name=rig_data['name'],
                defaults=rig_data
            )
            if created:
                self.stdout.write(f'Created rig: {rig.name}')
            else:
                self.stdout.write(f'Rig already exists: {rig.name}')
        
        self.stdout.write('Creating sample wells...')
        
        # Create sample wells
        well_types = ['EXP', 'Dev']
        well_profiles = ['DI', 'VE', 'SD']
        priorities = ['HIGH', 'MEDIUM', 'LOW']
        footprints = ['Mobile', 'Fixed']
        
        wells_data = []
        for i in range(1, 21):  # Create 20 wells
            well_data = {
                'sn': i,
                'asset_id': f'ASSET-{i:03d}',
                'name': f'WELL-{i:03d}',
                'well_type': random.choice(well_types),
                'well_profile': random.choice(well_profiles),
                'depth': random.randint(1500, 5500),  # meters
                'rig_capacity_required_hp': random.randint(1500, 3000),
                'drl_days': random.randint(10, 30),
                'pt_days': random.randint(2, 10),
                'duration': random.randint(15, 45),
                'latitude': Decimal(str(round(random.uniform(20.0, 25.0), 6))),
                'longitude': Decimal(str(round(random.uniform(70.0, 75.0), 6))),
                'rtd': date.today() + timedelta(days=random.randint(0, 60)),
                'bop_stack': random.randint(3000, 10000),
                'tds_requirement': random.choice(['Y', 'N']),
                'footprint': random.choice(footprints),
                'preferred_rig': f'RIG-{random.randint(1, 5):03d}' if random.random() > 0.5 else None,
                'expected_potential': f'{random.randint(50, 500)} bpd',
                'priority': random.choice(priorities)
            }
            wells_data.append(well_data)
        
        for well_data in wells_data:
            well, created = Well.objects.get_or_create(
                sn=well_data['sn'],
                defaults=well_data
            )
            if created:
                self.stdout.write(f'Created well: {well.name}')
            else:
                self.stdout.write(f'Well already exists: {well.name}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully loaded sample data: {Rig.objects.count()} rigs, {Well.objects.count()} wells'
            )
        )

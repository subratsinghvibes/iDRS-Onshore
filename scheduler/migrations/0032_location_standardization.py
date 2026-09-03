# Generated migration for location standardization

from django.db import migrations, models
import django.db.models.deletion


def migrate_locations_forward(apps, schema_editor):
    """Convert CharField location values to ForeignKey CompanyCode references"""
    CompanyCode = apps.get_model('scheduler', 'CompanyCode')
    DrillingBenchmark = apps.get_model('scheduler', 'DrillingBenchmark')
    DailyDrillingRate = apps.get_model('scheduler', 'DailyDrillingRate')
    CompletionTestingNorm = apps.get_model('scheduler', 'CompletionTestingNorm')
    
    db_alias = schema_editor.connection.alias
    
    # Build location mapping
    location_map = {}
    for cc in CompanyCode.objects.using(db_alias).all():
        keys = []
        if cc.location:
            keys.append(cc.location.strip().upper())
        if cc.name:
            keys.append(cc.name.strip().upper())
        if cc.company_code:
            keys.append(cc.company_code.strip().upper())
        for key in keys:
            if key and key not in location_map:
                location_map[key] = cc
    
    print(f"\nLocation standardization: Found {len(location_map)} location mappings")
    
    # Helper to find or create CompanyCode for a location string
    def get_company_code(location_str):
        if not location_str:
            return None
        
        key = location_str.strip().upper()
        if key in location_map:
            return location_map[key]
        
        # Try exact match first
        try:
            cc = CompanyCode.objects.using(db_alias).get(location=location_str.strip())
            location_map[key] = cc
            return cc
        except CompanyCode.DoesNotExist:
            pass
        
        # Create new CompanyCode
        cc = CompanyCode.objects.using(db_alias).create(
            location=location_str.strip(),
            fund_centre=f"AUTO_{location_str[:15]}",
            company_code=location_str[:10],
            cost_centre=f"CC_{location_str[:15]}",
            category='Location',
            name=location_str.strip(),
            city='Unknown',
            state='Unknown',
        )
        location_map[key] = cc
        print(f"  Created CompanyCode for: {location_str}")
        return cc
    
    # Migrate DrillingBenchmark
    print("\nMigrating DrillingBenchmark...")
    count = 0
    for obj in DrillingBenchmark.objects.using(db_alias).all():
        if obj.location_temp:
            cc = get_company_code(obj.location_temp)
            if cc:
                obj.location = cc
                obj.save(update_fields=['location'])
                count += 1
    print(f"  Migrated {count} records")
    
    # Migrate DailyDrillingRate
    print("\nMigrating DailyDrillingRate...")
    count = 0
    for obj in DailyDrillingRate.objects.using(db_alias).all():
        if obj.location_temp:
            cc = get_company_code(obj.location_temp)
            if cc:
                obj.location = cc
                obj.save(update_fields=['location'])
                count += 1
    print(f"  Migrated {count} records")
    
    # Migrate CompletionTestingNorm
    print("\nMigrating CompletionTestingNorm...")
    count = 0
    for obj in CompletionTestingNorm.objects.using(db_alias).all():
        if obj.location_temp:
            cc = get_company_code(obj.location_temp)
            if cc:
                obj.location = cc
                obj.save(update_fields=['location'])
                count += 1
    print(f"  Migrated {count} records")


def migrate_locations_reverse(apps, schema_editor):
    """Convert ForeignKey CompanyCode references back to CharField location values"""
    DrillingBenchmark = apps.get_model('scheduler', 'DrillingBenchmark')
    DailyDrillingRate = apps.get_model('scheduler', 'DailyDrillingRate')
    CompletionTestingNorm = apps.get_model('scheduler', 'CompletionTestingNorm')
    
    db_alias = schema_editor.connection.alias
    
    for obj in DrillingBenchmark.objects.using(db_alias).all():
        if obj.location:
            obj.location_temp = obj.location.location or obj.location.name
            obj.save(update_fields=['location_temp'])
    
    for obj in DailyDrillingRate.objects.using(db_alias).all():
        if obj.location:
            obj.location_temp = obj.location.location or obj.location.name
            obj.save(update_fields=['location_temp'])
    
    for obj in CompletionTestingNorm.objects.using(db_alias).all():
        if obj.location:
            obj.location_temp = obj.location.location or obj.location.name
            obj.save(update_fields=['location_temp'])


class Migration(migrations.Migration):

    dependencies = [
        ('scheduler', '0031_alter_rig_location_alter_schedule_location_and_more'),
    ]

    operations = [
        # Step 1: Remove unique_together constraint from DailyDrillingRate first
        migrations.AlterUniqueTogether(
            name='dailydrillingrate',
            unique_together=set(),
        ),
        
        # Step 2: Add temporary CharField columns to store old location data
        migrations.AddField(
            model_name='drillingbenchmark',
            name='location_temp',
            field=models.CharField(max_length=100, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='dailydrillingrate',
            name='location_temp',
            field=models.CharField(max_length=200, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='completiontestingnorm',
            name='location_temp',
            field=models.CharField(max_length=255, null=True, blank=True),
        ),
        
        # Step 3: Copy existing location data to temp columns
        migrations.RunSQL(
            sql=[
                "UPDATE scheduler_drillingbenchmark SET location_temp = location;",
                "UPDATE scheduler_dailydrillingrate SET location_temp = location;",
                "UPDATE scheduler_completiontestingnorm SET location_temp = location;",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        
        # Step 4: Remove old location field
        migrations.RemoveField(
            model_name='drillingbenchmark',
            name='location',
        ),
        migrations.RemoveField(
            model_name='dailydrillingrate',
            name='location',
        ),
        migrations.RemoveField(
            model_name='completiontestingnorm',
            name='location',
        ),
        
        # Step 5: Add new ForeignKey location field  
        migrations.AddField(
            model_name='drillingbenchmark',
            name='location',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='drilling_benchmarks',
                to='scheduler.companycode',
                help_text='Location (Company Code) for this benchmark'
            ),
        ),
        migrations.AddField(
            model_name='dailydrillingrate',
            name='location',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='daily_drilling_rates',
                to='scheduler.companycode',
                help_text='Location (Company Code) for this drilling rate'
            ),
        ),
        migrations.AddField(
            model_name='completiontestingnorm',
            name='location',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='completion_testing_norms',
                to='scheduler.companycode',
                help_text='Location (Company Code) for this completion testing norm'
            ),
        ),
        
        # Step 6: Migrate data from temp CharField to new ForeignKey
        migrations.RunPython(migrate_locations_forward, migrate_locations_reverse),
        
        # Step 7: Remove temporary columns
        migrations.RemoveField(
            model_name='drillingbenchmark',
            name='location_temp',
        ),
        migrations.RemoveField(
            model_name='dailydrillingrate',
            name='location_temp',
        ),
        migrations.RemoveField(
            model_name='completiontestingnorm',
            name='location_temp',
        ),
        
        # Step 8: Re-add unique_together constraint for DailyDrillingRate
        migrations.AlterUniqueTogether(
            name='dailydrillingrate',
            unique_together={('asset_id', 'location', 'depth_start', 'depth_end')},
        ),
    ]

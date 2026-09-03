# Custom migration: Rename casing_deviation_tag to loc_spec_factor

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduler', '0045_add_benchmark_unique_constraint'),
    ]

    operations = [
        # Step 1: Remove old unique_together constraints
        migrations.AlterUniqueTogether(
            name='dailydrillingrate',
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name='drillingbenchmark',
            unique_together=set(),
        ),
        # Step 2: Rename the fields (preserves data)
        migrations.RenameField(
            model_name='dailydrillingrate',
            old_name='casing_deviation_tag',
            new_name='loc_spec_factor',
        ),
        migrations.RenameField(
            model_name='drillingbenchmark',
            old_name='casing_deviation_tag',
            new_name='loc_spec_factor',
        ),
        # Step 3: Update field choices and help text
        migrations.AlterField(
            model_name='dailydrillingrate',
            name='loc_spec_factor',
            field=models.CharField(choices=[('Main Pool', 'Main Pool'), ('other than Main', 'other than Main')], default='Main Pool', help_text='Location-specific factor (Main Pool or other than Main)', max_length=20),
        ),
        migrations.AlterField(
            model_name='drillingbenchmark',
            name='loc_spec_factor',
            field=models.CharField(choices=[('Main Pool', 'Main Pool'), ('other than Main', 'other than Main')], default='Main Pool', help_text='Location-specific factor (Main Pool or other than Main)', max_length=20),
        ),
        # Step 4: Add new unique_together constraints
        migrations.AlterUniqueTogether(
            name='dailydrillingrate',
            unique_together={('location', 'field', 'depth_start', 'depth_end', 'loc_spec_factor')},
        ),
        migrations.AlterUniqueTogether(
            name='drillingbenchmark',
            unique_together={('location', 'pool', 'well_category', 'well_depth_start', 'well_depth_end', 'field', 'loc_spec_factor')},
        ),
    ]

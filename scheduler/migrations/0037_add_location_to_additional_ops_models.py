# Generated migration for adding location field to Additional Ops models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('scheduler', '0036_alter_dailydrillingrate_field'),
    ]

    operations = [
        # Add location field to CoringNorm
        migrations.AddField(
            model_name='coringnorm',
            name='location',
            field=models.ForeignKey(
                blank=True,
                help_text='Location from Company Codes',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='coring_norms',
                to='scheduler.companycode'
            ),
        ),
        # Add location field to CasingNorm
        migrations.AddField(
            model_name='casingnorm',
            name='location',
            field=models.ForeignKey(
                blank=True,
                help_text='Location from Company Codes',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='casing_norms',
                to='scheduler.companycode'
            ),
        ),
        # Add location field to HermeticalTestingNorm
        migrations.AddField(
            model_name='hermeticaltestingnorm',
            name='location',
            field=models.ForeignKey(
                blank=True,
                help_text='Location from Company Codes',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='hermetical_testing_norms',
                to='scheduler.companycode'
            ),
        ),
        # Add location field to OperationNorm
        migrations.AddField(
            model_name='operationnorm',
            name='location',
            field=models.ForeignKey(
                blank=True,
                help_text='Location from Company Codes',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='operation_norms',
                to='scheduler.companycode'
            ),
        ),
        # Update unique_together constraints to include location
        migrations.AlterUniqueTogether(
            name='coringnorm',
            unique_together={('location', 'depth_start', 'depth_end')},
        ),
        migrations.AlterUniqueTogether(
            name='casingnorm',
            unique_together={('location', 'depth_start', 'depth_end')},
        ),
        migrations.AlterUniqueTogether(
            name='hermeticaltestingnorm',
            unique_together={('location', 'depth_start', 'depth_end')},
        ),
        migrations.AlterUniqueTogether(
            name='operationnorm',
            unique_together={('location', 'operation')},
        ),
    ]

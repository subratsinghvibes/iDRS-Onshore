# Generated manually

from django.db import migrations, models
import django.core.validators
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('scheduler', '0016_alter_drillingbenchmark_well_category'),
    ]

    operations = [
        # Delete and recreate the table
        migrations.DeleteModel(
            name='RigBuildingNorm',
        ),
        migrations.CreateModel(
            name='RigBuildingNorm',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('rig_name', models.CharField(help_text='Name of the rig (e.g., E-760, Mobile rigs, IPS-M700)', max_length=100, unique=True)),
                ('days', models.IntegerField(default=0, help_text='Number of days for this rig', validators=[django.core.validators.MinValueValidator(0)])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Rig Building Norm',
                'verbose_name_plural': 'Rig Building Norms',
                'ordering': ['rig_name'],
            },
        ),
    ]

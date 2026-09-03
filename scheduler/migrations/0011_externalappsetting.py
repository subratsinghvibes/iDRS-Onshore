# Generated migration for ExternalAppSetting model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduler', '0010_soft_delete_rig_well'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExternalAppSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Submit Bug/Enhancement', help_text='Display name for the external app button', max_length=100)),
                ('url', models.URLField(default='http://127.0.0.1:8000', help_text='URL to open when the button is clicked')),
                ('enabled', models.BooleanField(default=True, help_text='Enable/disable the external app button')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'External App Setting',
                'verbose_name_plural': 'External App Settings',
            },
        ),
    ]

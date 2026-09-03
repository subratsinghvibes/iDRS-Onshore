from django.db import migrations, models
from django.db.models import Q
import uuid


def _normalize_code(value, max_len=50, fallback='UNKNOWN'):
    if value is None:
        return fallback
    value = str(value).strip()
    if not value:
        return fallback
    return value[:max_len]


def _get_unique_cost(fund_centre, base_cost, CompanyCode):
    cost = base_cost
    suffix = 1
    max_len = 50
    while CompanyCode.objects.filter(fund_centre=fund_centre, cost_centre=cost).exists():
        suffix_str = f"-{suffix}"
        trimmed = base_cost[: max_len - len(suffix_str)]
        cost = f"{trimmed}{suffix_str}"
        suffix += 1
    return cost


def forwards(apps, schema_editor):
    Location = apps.get_model('scheduler', 'Location')
    CompanyCode = apps.get_model('scheduler', 'CompanyCode')
    MasterPersonnelInfo = apps.get_model('scheduler', 'MasterPersonnelInfo')
    UserProfile = apps.get_model('scheduler', 'UserProfile')
    Rig = apps.get_model('scheduler', 'Rig')
    Well = apps.get_model('scheduler', 'Well')
    StagedWell = apps.get_model('scheduler', 'StagedWell')
    Schedule = apps.get_model('scheduler', 'Schedule')

    location_map = {}

    # 1) Promote existing Location records into CompanyCode (centralized locations)
    for loc in Location.objects.all():
        loc_code = (loc.code or '').strip()
        loc_name = (loc.name or '').strip() or loc_code

        existing = CompanyCode.objects.filter(
            Q(location__iexact=loc_code) | Q(company_code__iexact=loc_code) | Q(name__iexact=loc_name)
        ).first()

        if existing:
            updated_fields = []
            if not existing.location and loc_code:
                existing.location = loc_code
                updated_fields.append('location')
            if loc.description and not existing.description:
                existing.description = loc.description
                updated_fields.append('description')
            if existing.is_active is False and loc.is_active is True:
                existing.is_active = True
                updated_fields.append('is_active')
            if updated_fields:
                existing.save(update_fields=updated_fields)
            company_location = existing
        else:
            base_code = _normalize_code(loc_code)
            fund_centre = base_code
            cost_centre = _get_unique_cost(fund_centre, base_code, CompanyCode)
            company_location = CompanyCode.objects.create(
                id=uuid.uuid4(),
                fund_centre=fund_centre,
                company_code=base_code,
                cost_centre=cost_centre,
                category='Location',
                name=loc_name[:255] if loc_name else base_code,
                city='',
                state='',
                location=loc_code or base_code,
                description=loc.description,
                is_active=loc.is_active,
            )

        location_map[str(loc.id)] = company_location.id

    # 2) Ensure unique MPI locations exist in CompanyCode
    mpi_locations = (
        MasterPersonnelInfo.objects
        .exclude(location__isnull=True)
        .exclude(location__exact='')
        .values_list('location', flat=True)
        .distinct()
    )

    for loc_value in mpi_locations:
        loc_value = str(loc_value).strip()
        if not loc_value:
            continue

        exists = CompanyCode.objects.filter(location__iexact=loc_value).exists()
        if exists:
            continue

        base_code = _normalize_code(loc_value)
        fund_centre = base_code
        cost_centre = _get_unique_cost(fund_centre, base_code, CompanyCode)
        CompanyCode.objects.create(
            id=uuid.uuid4(),
            fund_centre=fund_centre,
            company_code=base_code,
            cost_centre=cost_centre,
            category='Location',
            name=loc_value[:255],
            city='',
            state='',
            location=loc_value,
            description=None,
            is_active=True,
        )

    # 3) Migrate FK references to CompanyCode
    for profile in UserProfile.objects.all():
        if profile.location_id:
            profile.company_location_id = location_map.get(str(profile.location_id))
            profile.save(update_fields=['company_location'])

    for rig in Rig.objects.all():
        if rig.location_id:
            rig.company_location_id = location_map.get(str(rig.location_id))
            rig.save(update_fields=['company_location'])

    for well in Well.objects.all():
        if well.location_id:
            well.company_location_id = location_map.get(str(well.location_id))
            well.save(update_fields=['company_location'])

    for staged in StagedWell.objects.all():
        if staged.location_id:
            staged.company_location_id = location_map.get(str(staged.location_id))
            staged.save(update_fields=['company_location'])

    for schedule in Schedule.objects.all():
        if schedule.location_id:
            schedule.company_location_id = location_map.get(str(schedule.location_id))
            schedule.save(update_fields=['company_location'])


def backwards(apps, schema_editor):
    # No-op reverse migration (restoring Location table data is not supported)
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('scheduler', '0029_add_user_field_to_authorizeduser'),
    ]

    operations = [
        migrations.AddField(
            model_name='companycode',
            name='location',
            field=models.CharField(blank=True, help_text='Location/Asset name or code (centralized location field)', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='companycode',
            name='description',
            field=models.TextField(blank=True, help_text='Description of the location', null=True),
        ),
        migrations.AddField(
            model_name='companycode',
            name='is_active',
            field=models.BooleanField(default=True, help_text='Whether this location is currently active'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='company_location',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='users', to='scheduler.companycode'),
        ),
        migrations.AddField(
            model_name='rig',
            name='company_location',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='rigs', to='scheduler.companycode'),
        ),
        migrations.AddField(
            model_name='well',
            name='company_location',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='wells', to='scheduler.companycode'),
        ),
        migrations.AddField(
            model_name='stagedwell',
            name='company_location',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='staged_wells', to='scheduler.companycode'),
        ),
        migrations.AddField(
            model_name='schedule',
            name='company_location',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='schedules', to='scheduler.companycode'),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='userprofile',
            name='location',
        ),
        migrations.RemoveField(
            model_name='rig',
            name='location',
        ),
        migrations.RemoveField(
            model_name='well',
            name='location',
        ),
        migrations.RemoveField(
            model_name='stagedwell',
            name='location',
        ),
        migrations.RemoveField(
            model_name='schedule',
            name='location',
        ),
        migrations.RenameField(
            model_name='userprofile',
            old_name='company_location',
            new_name='location',
        ),
        migrations.RenameField(
            model_name='rig',
            old_name='company_location',
            new_name='location',
        ),
        migrations.RenameField(
            model_name='well',
            old_name='company_location',
            new_name='location',
        ),
        migrations.RenameField(
            model_name='stagedwell',
            old_name='company_location',
            new_name='location',
        ),
        migrations.RenameField(
            model_name='schedule',
            old_name='company_location',
            new_name='location',
        ),
        migrations.DeleteModel(
            name='Location',
        ),
    ]

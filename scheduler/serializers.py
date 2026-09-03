from rest_framework import serializers
from .models import CompanyCode, UserProfile, Rig, Well, Schedule, Assignment, UnassignedWell, StagedWell
from decimal import Decimal


class LocationSerializer(serializers.ModelSerializer):
    """Serializer for centralized locations (CompanyCode)"""
    code = serializers.SerializerMethodField()
    rig_count = serializers.SerializerMethodField()
    well_count = serializers.SerializerMethodField()
    
    class Meta:
        model = CompanyCode
        fields = ['id', 'code', 'name', 'description', 'is_active', 'rig_count', 'well_count', 'created_at']

    def get_code(self, obj):
        return obj.code
    
    def get_rig_count(self, obj):
        return obj.rigs.count()
    
    def get_well_count(self, obj):
        return obj.wells.count()


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for UserProfile model"""
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    location_code = serializers.CharField(source='location.code', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    
    class Meta:
        model = UserProfile
        fields = ['username', 'email', 'location', 'location_code', 'location_name', 'can_view_all_locations']


class RigSerializer(serializers.ModelSerializer):
    duration_days = serializers.ReadOnlyField()
    is_available_now = serializers.ReadOnlyField()
    display_name = serializers.ReadOnlyField()
    location_code = serializers.CharField(source='location.code', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    location_value = serializers.CharField(source='location.location', read_only=True, allow_null=True)
    rig_building_norm_name = serializers.CharField(source='rig_building_norm.rig_name', read_only=True, allow_null=True)
    rig_building_norm_days = serializers.IntegerField(source='rig_building_norm.days', read_only=True, allow_null=True)
    # Soft delete fields
    is_deleted = serializers.BooleanField(read_only=True)
    deleted_at = serializers.DateTimeField(read_only=True)
    
    class Meta:
        model = Rig
        fields = '__all__'
        
    def validate(self, attrs):
        if attrs['start_date'] >= attrs['end_date']:
            raise serializers.ValidationError("End date must be after start date")
        return attrs
    
    def _set_location_from_asset_id(self, validated_data):
        """Auto-set location FK from asset_id (rigs use location name in asset_id)"""
        asset_id = validated_data.get('asset_id')
        if asset_id and not validated_data.get('location'):
            try:
                # For rigs, asset_id contains the location name (e.g., 'CAMBAY')
                location = CompanyCode.objects.get(location__iexact=asset_id)
                validated_data['location'] = location
            except CompanyCode.DoesNotExist:
                pass  # Keep location as None if not found
            except CompanyCode.MultipleObjectsReturned:
                # If multiple, get the first one
                location = CompanyCode.objects.filter(location__iexact=asset_id).first()
                if location:
                    validated_data['location'] = location
        return validated_data
    
    def create(self, validated_data):
        validated_data = self._set_location_from_asset_id(validated_data)
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        validated_data = self._set_location_from_asset_id(validated_data)
        return super().update(instance, validated_data)


class WellSerializer(serializers.ModelSerializer):
    priority_code = serializers.ReadOnlyField()
    has_duration_mismatch = serializers.ReadOnlyField()
    duration_validation_message = serializers.ReadOnlyField()
    display_name = serializers.ReadOnlyField()
    location_code = serializers.CharField(source='location.code', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    location_value = serializers.CharField(source='location.location', read_only=True, allow_null=True)
    # Soft delete fields
    is_deleted = serializers.BooleanField(read_only=True)
    deleted_at = serializers.DateTimeField(read_only=True)
    
    class Meta:
        model = Well
        fields = '__all__'
    
    def _set_location_from_asset_id(self, validated_data):
        """Auto-set location FK from asset_id (wells use company_code in asset_id)"""
        asset_id = validated_data.get('asset_id')
        if asset_id and not validated_data.get('location'):
            try:
                # For wells, asset_id contains the company_code (e.g., 'CBY')
                location = CompanyCode.objects.get(company_code__iexact=asset_id)
                validated_data['location'] = location
            except CompanyCode.DoesNotExist:
                pass  # Keep location as None if not found
            except CompanyCode.MultipleObjectsReturned:
                # If multiple, get the first one
                location = CompanyCode.objects.filter(company_code__iexact=asset_id).first()
                if location:
                    validated_data['location'] = location
        return validated_data
    
    def create(self, validated_data):
        validated_data = self._set_location_from_asset_id(validated_data)
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        validated_data = self._set_location_from_asset_id(validated_data)
        return super().update(instance, validated_data)


class StagedWellSerializer(serializers.ModelSerializer):
    """Serializer for StagedWell model"""
    location_code = serializers.CharField(source='location.code', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    location_value = serializers.CharField(source='location.location', read_only=True, allow_null=True)
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True, allow_null=True)
    completed_by_username = serializers.CharField(source='completed_by.username', read_only=True, allow_null=True)
    is_ready_to_import = serializers.ReadOnlyField()
    missing_fields = serializers.ReadOnlyField()
    
    class Meta:
        model = StagedWell
        fields = '__all__'
        read_only_fields = ['uploaded_by', 'uploaded_at', 'completed_by', 'completed_at', 'imported_at', 'imported_well']


class StagedWellUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating staged well additional fields"""
    
    class Meta:
        model = StagedWell
        fields = [
            'field_name',
            'latitude',
            'longitude',
            'well_profile',
            'rig_capacity_required_hp',
            'drl_days',
            'pt_days',
            'duration',
            'bop_stack',
            'tds_requirement',
            'footprint',
            'preferred_rig',
            'expected_potential'
        ]
    
    def validate_field_name(self, value):
        """Convert field name to title case for consistency"""
        if value:
            return value.title()
        return value


class AssignmentSerializer(serializers.ModelSerializer):
    rig_name = serializers.CharField(source='rig.name', read_only=True)
    well_name = serializers.CharField(source='well.name', read_only=True)
    well_asset = serializers.CharField(source='well.asset_id', read_only=True)
    
    class Meta:
        model = Assignment
        fields = '__all__'


class UnassignedWellSerializer(serializers.ModelSerializer):
    well_name = serializers.CharField(source='well.name', read_only=True)
    well_asset = serializers.CharField(source='well.asset_id', read_only=True)
    
    class Meta:
        model = UnassignedWell
        fields = '__all__'


class ScheduleSerializer(serializers.ModelSerializer):
    assignments = AssignmentSerializer(many=True, read_only=True)
    unassigned_wells = UnassignedWellSerializer(many=True, read_only=True)
    total_cost = serializers.SerializerMethodField()
    parent_schedule_id = serializers.UUIDField(source='parent_schedule.id', read_only=True, allow_null=True)
    parent_schedule_name = serializers.CharField(source='parent_schedule.name', read_only=True, allow_null=True)
    location_code = serializers.CharField(source='location.code', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    is_stale = serializers.SerializerMethodField()
    
    class Meta:
        model = Schedule
        fields = '__all__'
    
    def get_total_cost(self, obj):
        """Calculate total cost from drilling cost and ILM cost"""
        total_drilling = obj.total_drilling_cost or 0
        total_ilm = obj.total_ilm_cost or 0
        return total_drilling + total_ilm

    def get_is_stale(self, obj):
        """Detect stale RUNNING schedules — if running longer than time_limit + buffer, it's likely stale."""
        if obj.status != 'RUNNING':
            return False
        from django.utils import timezone
        elapsed = (timezone.now() - obj.created_at).total_seconds()
        # Allow time_limit + 2 minutes buffer for setup/teardown
        limit = (obj.time_limit_seconds or 600) + 120
        return elapsed > limit

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        is_admin = request and request.user and request.user.is_superuser
        if not is_admin:
            # Hide admin-only fields for non-admin users
            data.pop('optimality_gap_percent', None)
            # Keep schedule_hash for grouping purposes but omit raw display in JS
        return data


class ScheduleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the schedules list page — no nested assignments."""
    total_cost = serializers.SerializerMethodField()
    assignments_count = serializers.IntegerField(read_only=True, default=0)
    parent_schedule_id = serializers.UUIDField(source='parent_schedule.id', read_only=True, allow_null=True)
    parent_schedule_name = serializers.CharField(source='parent_schedule.name', read_only=True, allow_null=True)
    location_code = serializers.CharField(source='location.code', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    is_stale = serializers.SerializerMethodField()

    class Meta:
        model = Schedule
        fields = [
            'id', 'name', 'financial_year', 'status', 'created_at', 'completed_at',
            'total_drilling_cost', 'total_ilm_cost', 'total_cost',
            'project_end_date', 'unassigned_wells_count',
            'solver_status', 'solve_time_seconds', 'optimality_gap_percent',
            'schedule_hash', 'parent_schedule', 'parent_schedule_id', 'parent_schedule_name',
            'branch_type', 'version_number',
            'input_wells_count', 'input_rigs_count', 'time_limit_seconds',
            'location', 'location_code', 'location_name',
            'created_by', 'created_by_username',
            'is_stale', 'assignments_count',
        ]

    def get_total_cost(self, obj):
        total_drilling = obj.total_drilling_cost or 0
        total_ilm = obj.total_ilm_cost or 0
        return total_drilling + total_ilm

    def get_is_stale(self, obj):
        if obj.status != 'RUNNING':
            return False
        from django.utils import timezone
        elapsed = (timezone.now() - obj.created_at).total_seconds()
        limit = (obj.time_limit_seconds or 600) + 120
        return elapsed > limit

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        is_admin = request and request.user and request.user.is_superuser
        if not is_admin:
            data.pop('optimality_gap_percent', None)
        return data


class ScheduleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    financial_year = serializers.CharField(
        max_length=9,
        help_text="Financial Year (e.g., 2024-2025)"
    )
    rig_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of rig UUIDs to include in scheduling"
    )
    well_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of well UUIDs to include in scheduling"
    )
    time_limit_seconds = serializers.IntegerField(
        default=600,
        min_value=10,
        help_text="Maximum solver time in seconds (default 600s = 10 minutes, no upper limit)"
    )


class GanttDataSerializer(serializers.Serializer):
    """Serializer for Gantt chart data"""
    schedule_id = serializers.UUIDField()
    tasks = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of Gantt chart tasks"
    )
    rigs = serializers.ListField(
        child=serializers.CharField(),
        help_text="List of rig names"
    )
    wells = serializers.ListField(
        child=serializers.CharField(),
        help_text="List of well names"
    )
    date_range = serializers.DictField(
        help_text="Start and end dates for the chart"
    )


class AssignmentUpdateSerializer(serializers.Serializer):
    """Serializer for updating assignment dates via drag-and-drop"""
    assignment_id = serializers.UUIDField()
    new_start_date = serializers.DateField()
    new_rig_id = serializers.UUIDField(required=False)
    
    
class BulkDataUploadSerializer(serializers.Serializer):
    """Serializer for bulk data upload via CSV"""
    rigs_file = serializers.FileField(required=False)
    wells_file = serializers.FileField(required=False)
    
    def validate_rigs_file(self, value):
        if value and not value.name.endswith('.csv'):
            raise serializers.ValidationError("Rigs file must be a CSV file")
        return value
    
    def validate_wells_file(self, value):
        if value and not value.name.endswith('.csv'):
            raise serializers.ValidationError("Wells file must be a CSV file")
        return value


class ScheduleStatsSerializer(serializers.Serializer):
    """Serializer for schedule statistics"""
    total_assignments = serializers.IntegerField()
    total_unassigned = serializers.IntegerField()
    total_drilling_cost_cr = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_ilm_cost_cr = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_cost_cr = serializers.DecimalField(max_digits=10, decimal_places=2)
    project_duration_days = serializers.IntegerField()
    rig_utilization = serializers.ListField(
        child=serializers.DictField()
    )
    priority_breakdown = serializers.DictField()
    solver_status = serializers.CharField(allow_null=True, required=False)
    optimality_gap_percent = serializers.FloatField(allow_null=True, required=False)
    schedule_hash = serializers.CharField(allow_null=True, required=False)


class RigUtilizationSerializer(serializers.Serializer):
    """Serializer for rig utilization data"""
    rig_name = serializers.CharField()
    total_available_days = serializers.IntegerField()
    total_assigned_days = serializers.IntegerField()
    utilization_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    wells_assigned = serializers.IntegerField()
    idle_days = serializers.IntegerField()
    drilling_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    ilm_cost = serializers.DecimalField(max_digits=12, decimal_places=2)

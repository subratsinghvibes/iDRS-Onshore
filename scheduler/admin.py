from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import format_html
from django.contrib import messages
from .models import (
    CompanyCode, UserProfile, Rig, Well, Schedule, Assignment, 
    UnassignedWell, ExternalAppSetting, StagedWell,
    DrillingBenchmark, RigBuildingNorm, RigBuildingAdjustment,
    DailyDrillingRate, CoringNorm, CasingNorm, HermeticalTestingNorm, 
    OperationNorm, CompletionTestingNorm, AdditionalTest,
    AuthorizedUser, LoginAttempt, WellPairDistance, LocationSpecFactor,
    VideoTutorial,
    ExecutionSchedule, ExecutionRig, ExecutionWell, ExecutionLog,
)

# Try to import MPI if it exists
try:
    from .models import MasterPersonnelInfo
    HAS_MPI = True
except ImportError:
    HAS_MPI = False



# =============================================================================
# SOFT DELETE ADMIN MIXIN
# =============================================================================

class SoftDeleteAdminMixin:
    """Mixin for admin classes to handle soft-deleted models"""
    
    def get_queryset(self, request):
        """Override to show all objects (including deleted) in admin"""
        # Use all_objects manager to include deleted items
        qs = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs
    
    def get_list_filter(self, request):
        """Add is_deleted to list filters"""
        list_filter = list(super().get_list_filter(request))
        if 'is_deleted' not in list_filter:
            list_filter = ['is_deleted'] + list_filter
        return list_filter
    
    def get_list_display(self, request):
        """Add deletion status to list display"""
        list_display = list(super().get_list_display(request))
        if 'deletion_status' not in list_display:
            list_display.append('deletion_status')
        return list_display
    
    def deletion_status(self, obj):
        """Display deletion status with color coding"""
        if obj.is_deleted:
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">🗑️ DELETED</span>'
            )
        return format_html(
            '<span style="color: #28a745;">✓ Active</span>'
        )
    deletion_status.short_description = 'Status'
    deletion_status.admin_order_field = 'is_deleted'
    
    def get_actions(self, request):
        """Add soft delete and restore actions"""
        actions = super().get_actions(request)
        actions['soft_delete_selected'] = (
            self.soft_delete_selected,
            'soft_delete_selected',
            'Soft delete selected items'
        )
        actions['restore_selected'] = (
            self.restore_selected,
            'restore_selected',
            'Restore selected deleted items'
        )
        return actions
    
    def soft_delete_selected(self, request, queryset):
        """Soft delete selected items"""
        count = 0
        for obj in queryset:
            if not obj.is_deleted:
                obj.soft_delete(user=request.user)
                count += 1
        self.message_user(
            request,
            f'{count} item(s) have been soft-deleted.',
            messages.SUCCESS
        )
    soft_delete_selected.short_description = 'Soft delete selected items'
    
    def restore_selected(self, request, queryset):
        """Restore selected soft-deleted items"""
        count = 0
        for obj in queryset:
            if obj.is_deleted:
                obj.restore()
                count += 1
        self.message_user(
            request,
            f'{count} item(s) have been restored.',
            messages.SUCCESS
        )
    restore_selected.short_description = 'Restore selected deleted items'
    
    def delete_model(self, request, obj):
        """Override delete to use soft delete"""
        obj.soft_delete(user=request.user)
    
    def delete_queryset(self, request, queryset):
        """Override bulk delete to use soft delete"""
        for obj in queryset:
            obj.soft_delete(user=request.user)


# ===== CompanyCode (Location) Admin =====
@admin.register(CompanyCode)
class CompanyCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'company_code', 'name', 'location', 'is_active', 'rig_count', 'well_count', 'user_count', 'created_at']
    list_filter = ['is_active', 'category', 'created_at']
    search_fields = ['company_code', 'name', 'location', 'city', 'state', 'description']
    ordering = ['location', 'company_code', 'name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Company Code Details', {
            'fields': ('fund_centre', 'company_code', 'cost_centre', 'category', 'name')
        }),
        ('Location Details', {
            'fields': ('location', 'description', 'city', 'state', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def rig_count(self, obj):
        return obj.rigs.count()
    rig_count.short_description = 'Rigs'
    
    def well_count(self, obj):
        return obj.wells.count()
    well_count.short_description = 'Wells'
    
    def user_count(self, obj):
        return obj.users.count()
    user_count.short_description = 'Users'


# ===== UserProfile Inline for User Admin =====
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'User Profile (Location Assignment)'
    fk_name = 'user'
    fields = ['location', 'can_view_all_locations']
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'location':
            kwargs['queryset'] = CompanyCode.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ===== Extended User Admin =====
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ['username', 'email', 'first_name', 'last_name', 'get_location', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'profile__location']
    
    def get_location(self, obj):
        if hasattr(obj, 'profile') and obj.profile:
            if obj.profile.can_view_all_locations:
                return "All Locations"
            return obj.profile.location.code if obj.profile.location else "Not Assigned"
        return "No Profile"
    get_location.short_description = 'Location'
    get_location.admin_order_field = 'profile__location'
    
    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)


# Re-register User admin with profile inline
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# ===== UserProfile Admin (standalone) =====
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'location', 'can_view_all_locations', 'created_at']
    list_filter = ['location', 'can_view_all_locations', 'created_at']
    search_fields = ['user__username', 'user__email', 'location__code', 'location__name']
    ordering = ['user__username']
    raw_id_fields = ['user']
    readonly_fields = ['created_at']
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'location')
        }),
        ('Permissions', {
            'fields': ('can_view_all_locations',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )


# ===== External App Setting Admin (singleton) =====
@admin.register(ExternalAppSetting)
class ExternalAppSettingAdmin(admin.ModelAdmin):
    """Admin for External App Setting - Singleton pattern"""
    
    list_display = ['name', 'url', 'enabled', 'updated_at']
    fields = ['name', 'url', 'secret_key', 'enabled']
    
    def has_add_permission(self, request):
        """Only allow one instance"""
        return not ExternalAppSetting.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion"""
        return False
    
    def changelist_view(self, request, extra_context=None):
        """Redirect to change view if setting exists"""
        if ExternalAppSetting.objects.exists():
            obj = ExternalAppSetting.objects.first()
            from django.shortcuts import redirect
            from django.urls import reverse
            return redirect(reverse('admin:scheduler_externalappsetting_change', args=[obj.pk]))
        return super().changelist_view(request, extra_context)


@admin.register(Rig)
class RigAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = [
        'name', 'location', 'rig_type', 'start_date', 'end_date', 'rig_capacity_hp',
        'drilling_capacity_m', 'daily_cost_inr', 'crew_availability', 'is_available_now'
    ]
    list_filter = ['location', 'rig_type', 'crew_availability', 'hpht_suitability', 'tds_availability']
    search_fields = ['name', 'rig_type', 'location__code', 'location__name']
    date_hierarchy = 'start_date'
    ordering = ['is_deleted', 'name']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'location', 'asset_id', 'rig_type', 'start_date', 'end_date')
        }),
        ('Capabilities', {
            'fields': ('rig_capacity_hp', 'drilling_capacity_m', 'bop_stack', 'tds_availability', 'hpht_suitability')
        }),
        ('Costs', {
            'fields': ('daily_cost_inr', 'ilm_cost_fixed', 'ilm_cost_per_km', 'ilm_cost_cluster')
        }),
        ('Operations', {
            'fields': ('mobilization_time_days', 'maintenance_schedule', 'crew_availability')
        }),
        ('Deletion Status', {
            'fields': ('is_deleted', 'deleted_at', 'deleted_by'),
            'classes': ('collapse',),
            'description': 'Soft delete information. If deleted, item will not appear in new schedules.'
        }),
    )
    readonly_fields = ['is_deleted', 'deleted_at', 'deleted_by']
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'location':
            kwargs['queryset'] = Location.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Well)
class WellAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = [
        'name', 'location', 'asset_id', 'well_type', 'priority', 'depth',
        'rig_capacity_required_hp', 'duration', 'rtd', 'footprint'
    ]
    list_filter = ['location', 'well_type', 'well_profile', 'priority', 'footprint', 'tds_requirement']
    search_fields = ['name', 'asset_id', 'location__code', 'location__name']
    date_hierarchy = 'rtd'
    ordering = ['is_deleted', 'sn']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('sn', 'location', 'asset_id', 'name', 'well_type', 'well_profile', 'priority')
        }),
        ('Technical Specifications', {
            'fields': ('depth', 'rig_capacity_required_hp', 'bop_stack', 'tds_requirement', 'footprint')
        }),
        ('Schedule', {
            'fields': ('drl_days', 'pt_days', 'duration', 'rtd')
        }),
        ('GPS Coordinates', {
            'fields': ('latitude', 'longitude')
        }),
        ('Optional', {
            'fields': ('preferred_rig', 'expected_potential'),
            'classes': ('collapse',)
        }),
        ('Deletion Status', {
            'fields': ('is_deleted', 'deleted_at', 'deleted_by'),
            'classes': ('collapse',),
            'description': 'Soft delete information. If deleted, item will not appear in new schedules.'
        }),
    )
    readonly_fields = ['is_deleted', 'deleted_at', 'deleted_by']
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'location':
            kwargs['queryset'] = Location.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(StagedWell)
class StagedWellAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'location', 'asset_id', 'well_type', 'status', 'depth', 
        'rtd', 'uploaded_by', 'uploaded_at', 'is_ready_status'
    ]
    list_filter = ['location', 'status', 'well_type', 'priority', 'uploaded_at']
    search_fields = ['name', 'asset_id', 'location__code', 'location__name']
    date_hierarchy = 'uploaded_at'
    ordering = ['-uploaded_at']
    
    fieldsets = (
        ('Basic Information (From CSV)', {
            'fields': ('location', 'asset_id', 'name', 'well_type', 'depth', 'priority')
        }),
        ('GPS Coordinates', {
            'fields': ('latitude', 'longitude')
        }),
        ('Schedule', {
            'fields': ('rtd',)
        }),
        ('Additional Fields (To Be Completed)', {
            'fields': (
                'well_profile', 'rig_capacity_required_hp', 'drl_days', 
                'pt_days', 'duration', 'bop_stack', 'tds_requirement', 
                'footprint', 'preferred_rig', 'expected_potential'
            ),
            'description': 'These fields need to be completed before finalizing the well.'
        }),
        ('Status & Metadata', {
            'fields': (
                'status', 'uploaded_by', 'uploaded_at', 
                'completed_by', 'completed_at', 'imported_at', 'imported_well'
            ),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = [
        'uploaded_by', 'uploaded_at', 'completed_by', 
        'completed_at', 'imported_at', 'imported_well'
    ]
    
    def is_ready_status(self, obj):
        """Display ready status with color coding"""
        if obj.is_ready_to_import:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✓ Ready</span>'
            )
        return format_html(
            '<span style="color: #dc3545;">✗ Incomplete ({} fields)</span>',
            len(obj.missing_fields)
        )
    is_ready_status.short_description = 'Ready to Import'
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'location':
            kwargs['queryset'] = Location.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(WellPairDistance)
class WellPairDistanceAdmin(admin.ModelAdmin):
    """Admin for Well Pair Distance (ILM Cost calculation)"""
    list_display = [
        'location', 'rig', 'well_1', 'well_2', 'distance_km', 'created_at'
    ]
    list_filter = ['location', 'rig']
    search_fields = ['well_1__name', 'well_2__name', 'rig__name', 'location__company_code']
    ordering = ['location', 'rig', 'well_1', 'well_2']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Location & Rig', {
            'fields': ('location', 'rig')
        }),
        ('Well Pair', {
            'fields': ('well_1', 'well_2')
        }),
        ('Distance', {
            'fields': ('distance_km',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'location', 'financial_year', 'status', 'created_at', 'completed_at', 
        'unassigned_wells_count', 'solver_status', 'solve_time_seconds'
    ]
    list_filter = ['location', 'status', 'solver_status', 'financial_year', 'created_at']
    search_fields = ['name', 'location__code', 'location__name']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    readonly_fields = [
        'created_at', 'updated_at', 'completed_at', 'total_drilling_cost',
        'total_ilm_cost', 'project_end_date', 'unassigned_wells_count',
        'solver_status', 'solve_time_seconds'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'location', 'financial_year', 'status')
        }),
        ('Results', {
            'fields': (
                'total_drilling_cost', 'total_ilm_cost', 'project_end_date',
                'unassigned_wells_count', 'solver_status', 'solve_time_seconds'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'location':
            kwargs['queryset'] = Location.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = [
        'get_rig_name', 'get_well_name', 'well_start_date', 'well_end_date',
        'sequence_order', 'get_schedule_name', 'drilling_cost'
    ]
    list_filter = [
        'schedule__status', 'rig__rig_type', 'well__priority', 'well__well_type',
        'rtd_check', 'hp_check', 'depth_check'
    ]
    search_fields = ['rig__name', 'well__name', 'schedule__name']
    date_hierarchy = 'well_start_date'
    ordering = ['schedule', 'rig__name', 'sequence_order']
    
    def get_rig_name(self, obj):
        return obj.rig.name
    get_rig_name.short_description = 'Rig'
    get_rig_name.admin_order_field = 'rig__name'
    
    def get_well_name(self, obj):
        return obj.well.name
    get_well_name.short_description = 'Well'
    get_well_name.admin_order_field = 'well__name'
    
    def get_schedule_name(self, obj):
        return obj.schedule.name
    get_schedule_name.short_description = 'Schedule'
    get_schedule_name.admin_order_field = 'schedule__name'
    
    fieldsets = (
        ('Assignment', {
            'fields': ('schedule', 'rig', 'well', 'sequence_order')
        }),
        ('Dates', {
            'fields': ('well_start_date', 'well_end_date')
        }),
        ('Validation Checks', {
            'fields': (
                'rtd_check', 'well_start_check', 'well_end_check',
                'depth_check', 'hp_check', 'bop_check', 'tds_check', 'rig_type_check'
            ),
            'classes': ('collapse',)
        }),
        ('Costs', {
            'fields': ('drilling_cost', 'ilm_cost'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UnassignedWell)
class UnassignedWellAdmin(admin.ModelAdmin):
    list_display = ['get_well_name', 'get_schedule_name', 'get_well_priority', 'reason', 'created_at']
    list_filter = ['schedule__status', 'well__priority', 'well__well_type']
    search_fields = ['well__name', 'schedule__name', 'reason']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    def get_well_name(self, obj):
        return obj.well.name
    get_well_name.short_description = 'Well'
    get_well_name.admin_order_field = 'well__name'
    
    def get_schedule_name(self, obj):
        return obj.schedule.name
    get_schedule_name.short_description = 'Schedule'
    get_schedule_name.admin_order_field = 'schedule__name'
    
    def get_well_priority(self, obj):
        return obj.well.priority
    get_well_priority.short_description = 'Priority'
    get_well_priority.admin_order_field = 'well__priority'


# Customize admin site headers
admin.site.site_header = "Intelligent Drilling Rig Scheduler"
admin.site.site_title = "iDRS Admin"
admin.site.index_title = "Welcome to iDRS Administration"


# =============================================================================
# BENCHMARK AND RIG NORMS ADMIN
# =============================================================================

@admin.register(DrillingBenchmark)
class DrillingBenchmarkAdmin(admin.ModelAdmin):
    """Admin interface for Drilling Benchmarks"""
    list_display = ['location', 'pool', 'well_category', 'field', 'well_depth_start', 'well_depth_end', 'drilling_depth', 'benchmark_days', 'loc_spec_factor']
    list_filter = ['location', 'pool', 'well_category', 'loc_spec_factor']
    search_fields = ['location', 'pool', 'field']
    ordering = ['location', 'pool', 'well_category', 'field']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Location & Pool', {
            'fields': ('location', 'pool', 'field', 'well_category')
        }),
        ('Depth Information', {
            'fields': ('well_depth_start', 'well_depth_end', 'drilling_depth')
        }),
        ('Benchmark Data', {
            'fields': ('benchmark_days', 'loc_spec_factor')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']


@admin.register(RigBuildingNorm)
class RigBuildingNormAdmin(admin.ModelAdmin):
    """Admin interface for Rig Building Norms"""
    list_display = ['rig_name', 'days', 'top_drive', 'rig_type', 'created_at', 'updated_at']
    search_fields = ['rig_name', 'rig_type']
    list_filter = ['rig_type', 'top_drive']
    ordering = ['rig_name']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Rig Information', {
            'fields': ('rig_name', 'days', 'top_drive', 'rig_type')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']


@admin.register(RigBuildingAdjustment)
class RigBuildingAdjustmentAdmin(admin.ModelAdmin):
    """Admin interface for Rig Building Adjustments"""
    list_display = ['condition', 'category', 'adjustment_display', 'adjustment_type', 'is_active', 'priority', 'updated_at']
    search_fields = ['condition', 'notes']
    list_filter = ['category', 'adjustment_type', 'is_active', 'applies_to_rig_type']
    ordering = ['category', 'priority', 'condition']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Rule Definition', {
            'fields': ('condition', 'category', 'adjustment_type', 'adjustment_value', 'adjustment_display', 'unit', 'notes')
        }),
        ('Lookup Parameters', {
            'fields': ('min_distance', 'max_distance', 'applies_to_rig_type', 'max_depth'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'priority')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']

@admin.register(DailyDrillingRate)
class DailyDrillingRateAdmin(admin.ModelAdmin):
    """Admin interface for Daily Drilling Rates"""
    list_display = ['location', 'field', 'depth_start', 'depth_end', 'per_day_depth', 'loc_spec_factor', 'updated_at']
    search_fields = ['location__location', 'field']
    list_filter = ['location', 'loc_spec_factor']
    ordering = ['location', 'field', 'depth_start']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Location & Depth', {
            'fields': ('location', 'field', 'depth_start', 'depth_end')
        }),
        ('Rate', {
            'fields': ('per_day_depth', 'loc_spec_factor')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']


@admin.register(CoringNorm)
class CoringNormAdmin(admin.ModelAdmin):
    """Admin interface for Coring Norms"""
    list_display = ['depth_start', 'depth_end', 'additional_days', 'updated_at']
    ordering = ['depth_start']
    
    fieldsets = (
        ('Depth Range', {
            'fields': ('depth_start', 'depth_end')
        }),
        ('Norm Time', {
            'fields': ('additional_days',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']


@admin.register(CasingNorm)
class CasingNormAdmin(admin.ModelAdmin):
    """Admin interface for Casing Norms"""
    list_display = ['depth_start', 'depth_end', 'additional_days', 'updated_at']
    ordering = ['depth_start']
    
    fieldsets = (
        ('Depth Range', {
            'fields': ('depth_start', 'depth_end')
        }),
        ('Norm Time', {
            'fields': ('additional_days',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']


@admin.register(HermeticalTestingNorm)
class HermeticalTestingNormAdmin(admin.ModelAdmin):
    """Admin interface for Hermetical Testing Norms"""
    list_display = ['depth_start', 'depth_end', 'norm_days', 'updated_at']
    ordering = ['depth_start']
    
    fieldsets = (
        ('Depth Range', {
            'fields': ('depth_start', 'depth_end')
        }),
        ('Norm Time', {
            'fields': ('norm_days',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']


@admin.register(OperationNorm)
class OperationNormAdmin(admin.ModelAdmin):
    """Admin interface for Operation Norms"""
    list_display = ['operation', 'norm_rule', 'updated_at']
    search_fields = ['operation', 'norm_rule', 'remarks']
    ordering = ['operation']
    
    fieldsets = (
        ('Operation Details', {
            'fields': ('operation', 'norm_rule', 'remarks')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
@admin.register(CompletionTestingNorm)
class CompletionTestingNormAdmin(admin.ModelAdmin):
    list_display = ['location', 'well_depth_start', 'well_depth_end', 'well_type', 'days', 'updated_at']
    list_filter = ['location', 'well_type']
    search_fields = ['location']
    ordering = ['location', 'well_depth_start', 'well_type']
    fieldsets = (
        ('Location & Well Type', {'fields': ('location', 'well_type')}),
        ('Depth Interval', {'fields': ('well_depth_start', 'well_depth_end')}),
        ('Norm', {'fields': ('days',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    readonly_fields = ['created_at', 'updated_at']


@admin.register(AdditionalTest)
class AdditionalTestAdmin(admin.ModelAdmin):
    list_display = ['job', 'norm_time', 'notes', 'updated_at']
    search_fields = ['job', 'norm_time', 'notes']
    ordering = ['job']
    fieldsets = (
        ('Test Information', {'fields': ('job', 'norm_time', 'notes')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    readonly_fields = ['created_at', 'updated_at']


@admin.register(LocationSpecFactor)
class LocationSpecFactorAdmin(admin.ModelAdmin):
    """Admin interface for Location-Specific Factors"""
    list_display = ['location', 'factor_value', 'display_order', 'is_default', 'is_active', 'updated_at']
    list_filter = ['location', 'is_active', 'is_default']
    search_fields = ['location__location', 'factor_value']
    ordering = ['location', 'display_order', 'factor_value']
    
    fieldsets = (
        ('Factor Information', {
            'fields': ('location', 'factor_value', 'display_order')
        }),
        ('Status', {
            'fields': ('is_default', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']


# =============================================================================
# LDAP AUTHENTICATION ADMIN
# =============================================================================

@admin.register(AuthorizedUser)
class AuthorizedUserAdmin(admin.ModelAdmin):
    """Admin interface for managing authorized users who can log in via LDAP"""
    list_display = ['cpf_no', 'name', 'role', 'assigned_location', 'is_active', 'django_user_link', 'last_login_display', 'created_at']
    list_filter = ['role', 'is_active', 'created_at']
    search_fields = ['cpf_no', 'name', 'email']
    ordering = ['cpf_no']
    
    fieldsets = (
        ('User Information', {
            'fields': ('cpf_no', 'name', 'email')
        }),
        ('Role & Access', {
            'fields': ('role', 'assigned_location', 'is_active')
        }),
        ('Activity', {
            'fields': ('last_login', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['last_login', 'created_at', 'updated_at']
    
    def last_login_display(self, obj):
        """Display last login with better formatting"""
        if obj.last_login:
            return format_html(
                '<span style="color: green;">{}</span>',
                obj.last_login.strftime('%Y-%m-%d %H:%M:%S')
            )
        return format_html('<span style="color: gray;">Never</span>')
    last_login_display.short_description = 'Last Login'
    
    def django_user_link(self, obj):
        """Display link to the linked Django user"""
        if obj.user:
            return format_html(
                '<a href="/admin/auth/user/{}/change/" target="_blank">{}</a>',
                obj.user.id,
                obj.user.username
            )
        return format_html('<span style="color: gray;">Not linked</span>')
    django_user_link.short_description = 'Django User'
    
    actions = ['activate_users', 'deactivate_users', 'make_admin', 'make_L1', 'make_user']
    
    def activate_users(self, request, queryset):
        """Activate selected users"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} user(s) activated.', messages.SUCCESS)
    activate_users.short_description = "Activate selected users"
    
    def deactivate_users(self, request, queryset):
        """Deactivate selected users"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} user(s) deactivated.', messages.WARNING)
    deactivate_users.short_description = "Deactivate selected users"
    
    def make_admin(self, request, queryset):
        """Change role to Admin and sync Django user permissions"""
        from .models import UserProfile
        count = 0
        for auth_user in queryset:
            auth_user.role = 'admin'
            auth_user.save()
            # Sync Django User permissions
            if auth_user.user:
                auth_user.user.is_staff = True
                auth_user.user.is_superuser = True
                auth_user.user.save()
                # Update UserProfile
                profile, _ = UserProfile.objects.get_or_create(user=auth_user.user)
                profile.can_view_all_locations = True
                profile.location = None
                profile.save()
            count += 1
        self.message_user(request, f'{count} user(s) set to Admin role with full permissions.', messages.SUCCESS)
    make_admin.short_description = "Set role to Admin"
    
    def make_L1(self, request, queryset):
        """Change role to L1 and sync Django user permissions"""
        from .models import UserProfile
        count = 0
        for auth_user in queryset:
            auth_user.role = 'L1'
            auth_user.save()
            # Sync Django User permissions (L1 has is_staff but not is_superuser)
            if auth_user.user:
                auth_user.user.is_staff = True
                auth_user.user.is_superuser = False
                auth_user.user.save()
                # Update UserProfile - L1 can view all locations
                profile, _ = UserProfile.objects.get_or_create(user=auth_user.user)
                profile.can_view_all_locations = True
                profile.location = None
                profile.save()
            count += 1
        self.message_user(request, f'{count} user(s) set to L1 role with all-locations access.', messages.SUCCESS)
    make_L1.short_description = "Set role to L1"
    
    def make_user(self, request, queryset):
        """Change role to User and sync Django user permissions"""
        from .models import UserProfile, CompanyCode
        count = 0
        for auth_user in queryset:
            auth_user.role = 'user'
            auth_user.save()
            # Sync Django User permissions (regular user has no staff/superuser)
            if auth_user.user:
                auth_user.user.is_staff = False
                auth_user.user.is_superuser = False
                auth_user.user.save()
                # Update UserProfile - restricted to assigned location
                profile, _ = UserProfile.objects.get_or_create(user=auth_user.user)
                profile.can_view_all_locations = False
                # Try to set location from assigned_location if available
                if auth_user.assigned_location:
                    from django.db.models import Q
                    company_code = CompanyCode.objects.filter(
                        Q(location__icontains=auth_user.assigned_location) |
                        Q(company_code__icontains=auth_user.assigned_location),
                        is_active=True
                    ).first()
                    if company_code:
                        profile.location = company_code
                profile.save()
            count += 1
        self.message_user(request, f'{count} user(s) set to User role with location restrictions.', messages.SUCCESS)
    make_user.short_description = "Set role to User"


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Admin interface for viewing login attempts (security monitoring)"""
    list_display = ['username', 'status_display', 'ip_address', 'attempted_at', 'user_link']
    list_filter = ['status', 'attempted_at']
    search_fields = ['username', 'ip_address', 'user_agent']
    ordering = ['-attempted_at']
    date_hierarchy = 'attempted_at'
    
    fieldsets = (
        ('Login Information', {
            'fields': ('username', 'status', 'user')
        }),
        ('Request Details', {
            'fields': ('ip_address', 'user_agent')
        }),
        ('Error Details', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('attempted_at',)
        }),
    )
    
    readonly_fields = ['username', 'status', 'ip_address', 'user_agent', 'error_message', 'attempted_at', 'user']
    
    def status_display(self, obj):
        """Display status with color coding"""
        if obj.status == 'success':
            color = 'green'
        elif obj.status.startswith('failed'):
            color = 'red'
        else:
            color = 'orange'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    def user_link(self, obj):
        """Link to associated Django user if exists"""
        if obj.user:
            return format_html(
                '<a href="/admin/auth/user/{}/change/">{}</a>',
                obj.user.id,
                obj.user.username
            )
        return format_html('<span style="color: gray;">—</span>')
    user_link.short_description = 'Django User'
    
    def has_add_permission(self, request):
        """Disable manual addition - login attempts are auto-created"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Make login attempts read-only"""
        return False


# Register MPI admin only if the model exists
if HAS_MPI:
    @admin.register(MasterPersonnelInfo)
    class MasterPersonnelInfoAdmin(admin.ModelAdmin):
        """Admin interface for viewing all MPI personnel"""
        list_display = ['cpf_no', 'name', 'location', 'org_unit', 'designation', 'updated_at']
        list_filter = ['location', 'org_unit']
        search_fields = ['cpf_no', 'name', 'location', 'designation']
        ordering = ['cpf_no']
        
        readonly_fields = ['created_at', 'updated_at']
        
        fieldsets = (
            ('Basic Information', {
                'fields': ('cpf_no', 'name', 'mobile_no')
            }),
            ('Work Details', {
                'fields': ('location', 'org_unit', 'designation', 'position_text', 'personal_area')
            }),
            ('Organization', {
                'fields': ('group_1', 'group_2', 'org_new', 'org_unit_text'),
                'classes': ('collapse',)
            }),
            ('Dates', {
                'fields': ('dob', 'dor', 'doj_ongc', 'date_of_retirement'),
                'classes': ('collapse',)
            }),
            ('Additional', {
                'fields': ('sector', 'state_deployed', 'home_state', 'gender_key'),
                'classes': ('collapse',)
            }),
            ('Timestamps', {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            }),
        )
        
        def has_add_permission(self, request):
            """Disable manual addition - MPI is imported from CSV"""
            return False



@admin.register(VideoTutorial)
class VideoTutorialAdmin(admin.ModelAdmin):
    """Admin interface for Video Tutorials"""
    
    list_display = ['title', 'category', 'processing_status_display', 'file_sizes_display', 
                    'duration_minutes', 'view_count', 'is_active', 'uploaded_by', 'created_at']
    list_filter = ['category', 'is_active', 'processing_status', 'created_at']
    search_fields = ['title', 'description']
    ordering = ['category', 'order', 'title']
    readonly_fields = ['processing_status', 'processing_error', 'original_size_mb', 
                      'optimized_size_mb', 'compressed_size_mb', 'view_count', 
                      'created_at', 'updated_at']
    
    fieldsets = (
        ('Video Information', {
            'fields': ('title', 'description', 'category', 'duration_minutes', 'order')
        }),
        ('Files', {
            'fields': ('video_file', 'thumbnail')
        }),
        ('Processing Status', {
            'fields': ('processing_status', 'processing_error', 'original_size_mb', 
                      'optimized_size_mb', 'compressed_size_mb'),
            'classes': ('collapse',)
        }),
        ('Processed Files (Auto-generated)', {
            'fields': ('optimized_video', 'compressed_video'),
            'classes': ('collapse',),
            'description': 'These files are automatically generated when you upload a video.'
        }),
        ('Status', {
            'fields': ('is_active', 'view_count')
        }),
        ('Metadata', {
            'fields': ('uploaded_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def processing_status_display(self, obj):
        """Display processing status with color coding."""
        status_colors = {
            'pending': 'orange',
            'processing': 'blue',
            'completed': 'green',
            'failed': 'red',
        }
        color = status_colors.get(obj.processing_status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_processing_status_display()
        )
    processing_status_display.short_description = 'Processing'
    
    def file_sizes_display(self, obj):
        """Display file sizes in a compact format."""
        if obj.processing_status == 'completed':
            reduction = 0
            if obj.original_size_mb > 0 and obj.compressed_size_mb > 0:
                reduction = int((1 - obj.compressed_size_mb / obj.original_size_mb) * 100)
            return format_html(
                '<span title="Original: {}MB, Optimized: {}MB, Compressed: {}MB">'
                '{}MB → {}MB <span style="color: green;">({}% smaller)</span></span>',
                obj.original_size_mb,
                obj.optimized_size_mb,
                obj.compressed_size_mb,
                obj.original_size_mb,
                obj.compressed_size_mb,
                reduction
            )
        elif obj.original_size_mb > 0:
            return f"{obj.original_size_mb}MB"
        return "-"
    file_sizes_display.short_description = 'File Size'
    
    def save_model(self, request, obj, form, change):
        """Set uploaded_by to current user if not set and trigger video processing"""
        if not obj.uploaded_by:
            obj.uploaded_by = request.user
        
        # Check if video file was changed
        video_changed = 'video_file' in form.changed_data if form.changed_data else not change
        
        super().save_model(request, obj, form, change)
        
        # Trigger video processing if video was uploaded/changed
        if video_changed and obj.video_file:
            from .video_processing import process_video_for_streaming, is_ffmpeg_available
            from django.contrib import messages
            import threading
            
            if is_ffmpeg_available():
                # Process video in background thread to not block admin
                def process_video():
                    try:
                        process_video_for_streaming(obj)
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).error(f"Video processing failed: {e}")
                
                thread = threading.Thread(target=process_video, daemon=True)
                thread.start()
                
                messages.info(
                    request,
                    f"Video '{obj.title}' is being processed for optimal streaming. "
                    "This may take a few minutes. Refresh the page to see the status."
                )
            else:
                messages.warning(
                    request,
                    "FFmpeg is not installed. Video will stream but may not be optimized. "
                    "Install FFmpeg for better streaming performance."
                )
                obj.processing_status = 'completed'
                obj.processing_error = 'FFmpeg not available'
                obj.save(update_fields=['processing_status', 'processing_error'])
    
    actions = ['process_videos_action']
    
    @admin.action(description="Process selected videos for streaming optimization")
    def process_videos_action(self, request, queryset):
        """Admin action to process selected videos."""
        from .video_processing import process_video_for_streaming, is_ffmpeg_available
        from django.contrib import messages
        import threading
        
        if not is_ffmpeg_available():
            messages.error(request, "FFmpeg is not installed. Cannot process videos.")
            return
        
        count = queryset.count()
        
        def process_videos():
            for tutorial in queryset:
                try:
                    process_video_for_streaming(tutorial)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Video processing failed: {e}")
        
        thread = threading.Thread(target=process_videos, daemon=True)
        thread.start()
        
        messages.success(
            request, 
            f"Started processing {count} video(s). This may take several minutes."
        )


# =============================================================================
# SCHEDULE EXECUTION MODULE (SEM) ADMIN
# =============================================================================

class ExecutionWellInline(admin.TabularInline):
    model = ExecutionWell
    extra = 0
    readonly_fields = ('well', 'rig', 'status', 'is_locked', 'planned_start_date', 'planned_end_date',
                        'actual_start_date', 'actual_end_date', 'sequence_order')
    fields = ('well', 'rig', 'status', 'is_locked', 'planned_start_date', 'planned_end_date',
              'actual_start_date', 'actual_end_date', 'sequence_order')


@admin.register(ExecutionSchedule)
class ExecutionScheduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_schedule', 'status', 'financial_year',
                    'total_wells', 'locked_wells_count', 'progress_percentage',
                    'optimization_runs', 'created_at')
    list_filter = ('status', 'financial_year')
    search_fields = ('name', 'source_schedule__name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [ExecutionWellInline]


@admin.register(ExecutionRig)
class ExecutionRigAdmin(admin.ModelAdmin):
    list_display = ('execution_schedule', 'rig', 'is_active', 'added_at', 'removed_at')
    list_filter = ('is_active',)
    search_fields = ('rig__name', 'execution_schedule__name')


@admin.register(ExecutionWell)
class ExecutionWellAdmin(admin.ModelAdmin):
    list_display = ('well', 'rig', 'execution_schedule', 'status', 'is_locked',
                    'planned_start_date', 'planned_end_date',
                    'actual_start_date', 'actual_end_date', 'delay_days')
    list_filter = ('status', 'is_locked')
    search_fields = ('well__name', 'rig__name', 'execution_schedule__name')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(ExecutionLog)
class ExecutionLogAdmin(admin.ModelAdmin):
    list_display = ('execution_schedule', 'action', 'description', 'performed_by', 'created_at')
    list_filter = ('action',)
    search_fields = ('description', 'execution_schedule__name')
    readonly_fields = ('id', 'created_at')

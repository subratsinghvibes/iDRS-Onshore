from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
import uuid
from datetime import date


# =============================================================================
# SOFT DELETE MANAGERS
# =============================================================================

class ActiveManager(models.Manager):
    """Manager that returns only non-deleted (active) objects"""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Manager that returns all objects including deleted ones"""
    def get_queryset(self):
        return super().get_queryset()


class SoftDeleteMixin(models.Model):
    """Mixin to add soft-delete functionality to models"""
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Soft delete flag. If True, this record is considered deleted."
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the record was soft-deleted"
    )
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_deleted',
        help_text="User who deleted this record"
    )
    
    class Meta:
        abstract = True
    
    def soft_delete(self, user=None):
        """Soft delete the record"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])
    
    def restore(self):
        """Restore a soft-deleted record"""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])


class UserProfile(models.Model):
    """Extended user profile with location assignment"""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        help_text="Location (Company Code) this user belongs to. If empty, user can see all locations (admin)."
    )
    can_view_all_locations = models.BooleanField(
        default=False,
        help_text="If True, user can view data from all locations (like an admin)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
    
    def __str__(self):
        location_str = self.location.code if self.location else "All Locations"
        return f"{self.user.username} - {location_str}"
    
    def get_accessible_locations(self):
        """Get all locations this user can access"""
        if self.can_view_all_locations or self.user.is_superuser:
            return CompanyCode.objects.filter(is_active=True)
        elif self.location:
            return CompanyCode.objects.filter(id=self.location.id, is_active=True)
        return CompanyCode.objects.none()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create UserProfile when a User is created"""
    if created:
        profile = UserProfile.objects.create(user=instance)
        
        # Try to set default location from MPI based on username (CPF)
        try:
            from .models import MasterPersonnelInfo, CompanyCode
            mpi = MasterPersonnelInfo.objects.filter(cpf_no=instance.username).first()
            if mpi and mpi.location:
                # Try to find matching CompanyCode object
                company_code = CompanyCode.objects.filter(
                    models.Q(location__icontains=mpi.location) |
                    models.Q(company_code__icontains=mpi.location) |
                    models.Q(name__icontains=mpi.location),
                    is_active=True
                ).first()
                if company_code:
                    profile.location = company_code
                    profile.save(update_fields=['location'])
        except Exception as e:
            # Don't fail if we can't set location
            pass


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Automatically save UserProfile when User is saved"""
    if hasattr(instance, 'profile'):
        instance.profile.save()


def get_current_financial_year():
    """Get current financial year in YYYY-YYYY format (April to March)"""
    today = date.today()
    if today.month >= 4:  # April to March cycle
        start_year = today.year
        end_year = today.year + 1
    else:
        start_year = today.year - 1
        end_year = today.year
    return f"{start_year}-{end_year}"


def get_financial_year_choices():
    """Generate financial year choices for dropdown (current + 2 previous + 2 future)"""
    current_fy = get_current_financial_year()
    current_start_year = int(current_fy.split('-')[0])
    
    choices = []
    for i in range(-2, 3):  # 2 years back to 2 years forward
        start_year = current_start_year + i
        end_year = start_year + 1
        fy = f"{start_year}-{end_year}"
        choices.append((fy, f"FY {fy}"))
    
    return choices


def parse_financial_year(fy_string: str) -> tuple:
    """
    Parse a financial year string and return the start and end dates.
    
    Financial Year in India runs from April 1 to March 31.
    For example, FY "2024-2025" means:
    - Start: April 1, 2024
    - End: March 31, 2025
    
    Args:
        fy_string: Financial year string in format "YYYY-YYYY" (e.g., "2024-2025")
        
    Returns:
        tuple: (start_date, end_date) as date objects
        
    Raises:
        ValueError: If the FY string format is invalid
    """
    if not fy_string or '-' not in fy_string:
        raise ValueError(f"Invalid financial year format: {fy_string}. Expected format: YYYY-YYYY")
    
    parts = fy_string.split('-')
    if len(parts) != 2:
        raise ValueError(f"Invalid financial year format: {fy_string}. Expected format: YYYY-YYYY")
    
    try:
        start_year = int(parts[0])
        end_year = int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid year values in financial year: {fy_string}")
    
    # Validate that end_year is start_year + 1
    if end_year != start_year + 1:
        raise ValueError(f"Financial year end year must be start year + 1: {fy_string}")
    
    # FY starts on April 1 of start_year and ends on March 31 of end_year
    fy_start_date = date(start_year, 4, 1)  # April 1
    fy_end_date = date(end_year, 3, 31)      # March 31
    
    return (fy_start_date, fy_end_date)


class Rig(SoftDeleteMixin, models.Model):
    """Model representing a drilling rig"""
    
    RIG_TYPES = [
        ('Mobile', 'Mobile'),
        ('Fixed', 'Fixed'),
    ]
    
    YES_NO_CHOICES = [
        ('Y', 'Yes'),
        ('N', 'No'),
    ]
    
    AVAILABILITY_CHOICES = [
        ('OK', 'OK'),
        ('NOT_OK', 'Not OK'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True, help_text="Rig identifier (e.g., JOHN-1000-29)")
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rigs',
        help_text="Location (Company Code) where this rig is assigned"
    )
    asset_id = models.CharField(max_length=50, help_text="Asset/Location identifier (legacy field)", blank=True, null=True)
    rig_type = models.CharField(max_length=10, choices=RIG_TYPES)
    start_date = models.DateField(help_text="Rig availability start date")
    end_date = models.DateField(help_text="Rig availability end date")
    rig_capacity_hp = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Rig capacity in horsepower"
    )
    daily_cost_inr = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Daily cost in INR"
    )
    drilling_capacity_m = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Maximum drilling depth in meters"
    )
    mobilization_time_days = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="Time required for mobilization (e.g., 'Nil', '5 days')"
    )
    maintenance_schedule = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Maintenance schedule information"
    )
    crew_availability = models.CharField(
        max_length=10,
        choices=AVAILABILITY_CHOICES,
        default='OK'
    )
    hpht_suitability = models.CharField(
        max_length=1,
        choices=YES_NO_CHOICES,
        default='N',
        help_text="High Pressure High Temperature suitability"
    )
    ilm_cost_fixed = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Inter Location Movement fixed cost"
    )
    ilm_cost_per_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text="ILM cost per kilometer"
    )
    ilm_cost_cluster = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text="ILM cost for cluster operations"
    )
    bop_stack = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="BOP Stack capacity"
    )
    tds_availability = models.CharField(
        max_length=1,
        choices=YES_NO_CHOICES,
        default='Y',
        help_text="Top Drive System availability"
    )
    rig_building_norm = models.ForeignKey(
        'RigBuildingNorm',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rigs',
        help_text="Associated rig building norm for this rig"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Managers
    objects = ActiveManager()  # Default: returns only active (non-deleted) rigs
    all_objects = AllObjectsManager()  # Returns all rigs including deleted
    
    class Meta:
        ordering = ['name']
        verbose_name = "Drilling Rig"
        verbose_name_plural = "Drilling Rigs"
    
    def __str__(self):
        status = " [DELETED]" if self.is_deleted else ""
        return f"{self.name} ({self.rig_type}){status}"
    
    @property
    def display_name(self):
        """Return clean name without version suffix for display"""
        import re
        # Remove version suffix like _v20251218_143025
        clean_name = re.sub(r'_v\d{8}_\d{6}$', '', self.name)
        return clean_name
    
    @property
    def duration_days(self):
        """Calculate rig availability duration in days"""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0
    
    @property
    def is_available_now(self):
        """Check if rig is currently available"""
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date


class Well(SoftDeleteMixin, models.Model):
    """Model representing a well to be drilled"""
    
    WELL_TYPES = [
        ('EXP', 'Exploration'),
        ('Dev', 'Development'),
    ]
    
    WELL_PROFILES = [
        ('DI', 'Directional'),
        ('VE', 'Vertical'),
        ('SD', 'Sidetrack'),
    ]
    
    PRIORITY_CHOICES = [
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    ]
    
    FOOTPRINT_CHOICES = [
        ('Mobile', 'Mobile'),
        ('Fixed', 'Fixed'),
    ]
    
    YES_NO_CHOICES = [
        ('Y', 'Yes'),
        ('N', 'No'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sn = models.IntegerField(unique=True, help_text="Serial number")
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wells',
        help_text="Location (Company Code) where this well is located"
    )
    asset_id = models.CharField(max_length=50, help_text="Asset identifier (legacy field)")
    name = models.CharField(max_length=50, help_text="Well name")
    field_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Field name - used for benchmark lookup",
        db_index=True
    )
    well_type = models.CharField(max_length=3, choices=WELL_TYPES)
    well_profile = models.CharField(max_length=2, choices=WELL_PROFILES)
    depth = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Well depth in meters"
    )
    rig_capacity_required_hp = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Required rig capacity in HP"
    )
    drl_days = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Drilling days required"
    )
    pt_days = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Post-drilling testing days"
    )
    duration = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Total duration in days"
    )
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        help_text="GPS latitude"
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        help_text="GPS longitude"
    )
    rtd = models.DateField(help_text="Ready To Drill date")
    bop_stack = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Required BOP Stack capacity"
    )
    tds_requirement = models.CharField(
        max_length=1,
        choices=YES_NO_CHOICES,
        help_text="Top Drive System requirement"
    )
    footprint = models.CharField(
        max_length=10,
        choices=FOOTPRINT_CHOICES,
        help_text="Required rig footprint type"
    )
    preferred_rig = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Preferred rig for this well"
    )
    expected_potential = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Expected well potential"
    )
    priority = models.CharField(
        max_length=6,
        choices=PRIORITY_CHOICES,
        default='MEDIUM'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Managers
    objects = ActiveManager()  # Default: returns only active (non-deleted) wells
    all_objects = AllObjectsManager()  # Returns all wells including deleted
    
    class Meta:
        ordering = ['sn']
        verbose_name = "Well"
        verbose_name_plural = "Wells"
    
    def __str__(self):
        status = " [DELETED]" if self.is_deleted else ""
        return f"{self.name} ({self.asset_id}){status}"
    
    def save(self, *args, **kwargs):
        """Override save to convert field_name to title case for consistency"""
        if self.field_name:
            self.field_name = self.field_name.title()
        super().save(*args, **kwargs)
    
    @property
    def display_name(self):
        """Return clean name without version suffix for display"""
        import re
        # Remove version suffix like _v20251218_143025
        clean_name = re.sub(r'_v\d{8}_\d{6}$', '', self.name)
        return clean_name    
    @property
    def priority_code(self):
        """Get numeric priority code for optimization"""
        priority_map = {"HIGH": 1, "MEDIUM": 2, "LOW": 3}
        return priority_map.get(self.priority, 2)
    
    @property
    def has_duration_mismatch(self):
        """Check if duration doesn't match drilling days + testing days"""
        return (self.drl_days + self.pt_days) != self.duration
    
    @property
    def duration_validation_message(self):
        """Get validation message for duration mismatch"""
        if self.has_duration_mismatch:
            expected = self.drl_days + self.pt_days
            return f"Duration ({self.duration}) should equal DRL_DAYS ({self.drl_days}) + PT_DAYS ({self.pt_days}) = {expected}"
        return None


class WellPairDistance(models.Model):
    """
    Model to store pre-calculated distances between well pairs for ILM cost calculation.
    Distances are calculated using Haversine formula based on GPS coordinates.
    One entry per unique well pair per rig location.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.CASCADE,
        related_name='well_pair_distances',
        help_text="Location (Company Code) for this distance calculation"
    )
    rig = models.ForeignKey(
        Rig,
        on_delete=models.CASCADE,
        related_name='well_pair_distances',
        help_text="Rig associated with these wells"
    )
    well_1 = models.ForeignKey(
        Well,
        on_delete=models.CASCADE,
        related_name='distances_as_well_1',
        help_text="First well in the pair"
    )
    well_2 = models.ForeignKey(
        Well,
        on_delete=models.CASCADE,
        related_name='distances_as_well_2',
        help_text="Second well in the pair"
    )
    distance_km = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Distance between wells in metres"
    )
    # Pre-computed ILM fields (cached to avoid recalculating on every request)
    ilm_days = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Pre-computed ILM days based on adjustment rules"
    )
    ilm_note = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Note about ILM calculation"
    )
    ilm_rules_applied = models.JSONField(
        default=list,
        blank=True,
        help_text="JSON list of rules applied during ILM calculation"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Well Pair Distance"
        verbose_name_plural = "Well Pair Distances"
        # Ensure unique well pair per rig (well_1 and well_2 order matters for lookup)
        unique_together = ['rig', 'well_1', 'well_2']
        ordering = ['location__company_code', 'rig__name', 'well_1__name', 'well_2__name']

    def __str__(self):
        return f"{self.rig.name}: {self.well_1.name} ↔ {self.well_2.name} = {self.distance_km} m"

    @staticmethod
    def haversine_distance(lat1, lon1, lat2, lon2):
        """
        Calculate the great circle distance between two points on earth (in metres).
        Uses the Haversine formula.
        """
        from math import radians, cos, sin, asin, sqrt
        
        # Convert to float for calculation
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        # Earth's radius in kilometres (6371 km) * 1000 to get metres
        r = 6371000
        
        return round(c * r, 2)

    @classmethod
    def calculate_and_store_distances(cls, well, rig=None):
        """
        Calculate and store distances between the given well and all other wells
        in the same location. Optionally filter by rig.
        
        Args:
            well: The Well object to calculate distances for
            rig: Optional Rig object to associate distances with
        
        Returns:
            Number of distance records created/updated
            
        Note on data structure:
            - Wells have asset_id = company_code (e.g., 'CBY')
            - Rigs have asset_id = location name (e.g., 'CAMBAY')
            - Both may have location FK set, or use legacy asset_id field
        """
        from itertools import combinations
        from django.db.models import Q
        
        # Determine the location for the well
        location = well.location
        if not location and well.asset_id:
            # Try to find location by matching asset_id to company_code
            try:
                location = CompanyCode.objects.get(company_code=well.asset_id)
            except CompanyCode.DoesNotExist:
                pass
        
        if not location:
            return 0
        
        # Get all wells in the same location (excluding the given well)
        # Match by location FK OR asset_id matching company_code
        location_wells = Well.objects.filter(
            Q(location=location) | Q(asset_id=location.company_code),
            is_deleted=False
        ).exclude(id=well.id)
        
        # Get all rigs in the same location
        # Match by location FK OR asset_id matching location name
        if rig:
            rigs = [rig]
        else:
            rigs = list(Rig.objects.filter(
                Q(location=location) | Q(asset_id=location.location),
                is_deleted=False
            ))
        
        count = 0
        for r in rigs:
            for other_well in location_wells:
                # Skip if coordinates are missing
                if not all([well.latitude, well.longitude, other_well.latitude, other_well.longitude]):
                    continue
                
                distance = cls.haversine_distance(
                    well.latitude, well.longitude,
                    other_well.latitude, other_well.longitude
                )
                
                # Store both directions (well_1 -> well_2 and well_2 -> well_1)
                for w1, w2 in [(well, other_well), (other_well, well)]:
                    cls.objects.update_or_create(
                        rig=r,
                        well_1=w1,
                        well_2=w2,
                        defaults={
                            'location': location,
                            'distance_km': distance
                        }
                    )
                    count += 1
        
        return count

    @classmethod
    def recalculate_all_for_location(cls, location):
        """
        Recalculate all well pair distances for a given location.
        Clears existing records and recreates them.
        Also pre-computes ILM days for each pair.
        
        Args:
            location: CompanyCode object
        
        Returns:
            Number of distance records created
        
        Note on data structure:
            - Wells have asset_id = company_code (e.g., 'CBY')
            - Rigs have asset_id = location name (e.g., 'CAMBAY')
            - Both may have location FK set, or use legacy asset_id field
        """
        from django.db.models import Q
        
        # Get all wells for the location
        # Wells: location FK OR asset_id matches company_code
        wells = list(Well.objects.filter(
            Q(location=location) | Q(asset_id=location.company_code),
            is_deleted=False
        ))
        
        # Get all rigs for the location
        # Rigs: location FK OR asset_id matches location name
        rigs = list(Rig.objects.filter(
            Q(location=location) | Q(asset_id=location.location),
            is_deleted=False
        ).select_related('rig_building_norm'))
        
        # Clear existing records for this location
        cls.objects.filter(location=location).delete()
        
        count = 0
        from itertools import combinations
        
        # Import ILM calculation function (lazy to avoid circular imports)
        calculate_ilm = None
        prefetched_adjustments = None
        try:
            from scheduler.views import calculate_ilm_days
            calculate_ilm = calculate_ilm_days
            # Pre-fetch adjustment rules once for the entire location
            from scheduler.models import RigBuildingAdjustment
            prefetched_adjustments = list(RigBuildingAdjustment.objects.filter(
                location=location,
                is_active=True
            ).order_by('-priority', 'category'))
        except ImportError:
            pass
        
        for rig in rigs:
            norm_days = rig.rig_building_norm.days if rig.rig_building_norm else None
            
            for well_1, well_2 in combinations(wells, 2):
                # Skip if coordinates are missing
                if not all([well_1.latitude, well_1.longitude, well_2.latitude, well_2.longitude]):
                    continue
                
                distance = cls.haversine_distance(
                    well_1.latitude, well_1.longitude,
                    well_2.latitude, well_2.longitude
                )
                
                # Pre-compute ILM days during creation
                ilm_days_val = None
                ilm_note_val = ''
                ilm_rules_val = []
                if calculate_ilm and norm_days is not None:
                    try:
                        ilm_result = calculate_ilm(rig, float(distance), location, norm_days,
                                                   prefetched_adjustments=prefetched_adjustments)
                        ilm_days_val = ilm_result.get('ilm_days')
                        ilm_note_val = ilm_result.get('note', '')
                        ilm_rules_val = ilm_result.get('applied_rules', [])
                    except Exception:
                        pass
                
                # Store both directions
                for w1, w2 in [(well_1, well_2), (well_2, well_1)]:
                    cls.objects.create(
                        location=location,
                        rig=rig,
                        well_1=w1,
                        well_2=w2,
                        distance_km=distance,
                        ilm_days=ilm_days_val,
                        ilm_note=ilm_note_val,
                        ilm_rules_applied=ilm_rules_val
                    )
                    count += 1
        
        return count


# =============================================================================
# BACKGROUND ILM AUTO-POPULATION SIGNALS
# =============================================================================
# These signals fire when a Well or Rig is saved and trigger background
# incremental updates of WellPairDistance + ILM fields without blocking the UI.
# Uses PostgreSQL's concurrent connection support for parallel background work.

import threading
import logging as _logging
_ilm_signal_logger = _logging.getLogger(__name__)

# Track pending recalculations to avoid duplicate threads per location
_pending_ilm_recalc = set()
_pending_lock = threading.Lock()

# Serialize ILM background writes to avoid SQLite "database is locked" errors
_ilm_write_lock = threading.Lock()


def _compute_and_store_ilm(location, records_to_update):
    """
    Compute ILM fields for given WellPairDistance records and bulk_update them.
    Used in background threads — pre-fetches adjustments to avoid N+1 queries.
    """
    try:
        from scheduler.views import calculate_ilm_days
        from scheduler.models import RigBuildingAdjustment, WellPairDistance

        # Pre-fetch all adjustment rules for this location once
        prefetched_adjustments = list(RigBuildingAdjustment.objects.filter(
            location=location, is_active=True
        ).order_by('-priority', 'category'))

        to_update = []
        for d in records_to_update:
            norm_days = d.rig.rig_building_norm.days if d.rig.rig_building_norm else None
            ilm_result = calculate_ilm_days(
                d.rig, float(d.distance_km), location, norm_days,
                prefetched_adjustments=prefetched_adjustments
            )
            d.ilm_days = ilm_result.get('ilm_days')
            d.ilm_note = ilm_result.get('note', '')
            d.ilm_rules_applied = ilm_result.get('applied_rules', [])
            to_update.append(d)

        if to_update:
            WellPairDistance.objects.bulk_update(
                to_update, ['ilm_days', 'ilm_note', 'ilm_rules_applied'], batch_size=500
            )
    except Exception as e:
        _ilm_signal_logger.error(f'[ILM Background] Error computing ILM: {e}')


def _background_add_well_pairs(well_id, location_id):
    """
    Background thread: add/refresh WellPairDistance records for a specific well
    across all rigs at its location.
    Uses _ilm_write_lock to serialize SQLite writes across concurrent threads.
    """
    from django.db import connections
    with _ilm_write_lock:
        try:
            from scheduler.models import Well, Rig, WellPairDistance, CompanyCode
            from scheduler.views import calculate_ilm_days
            from scheduler.models import RigBuildingAdjustment
            from itertools import combinations
            from django.db.models import Q

            location = CompanyCode.objects.get(id=location_id)
            well = Well.objects.get(id=well_id)

            if not all([well.latitude, well.longitude]):
                _ilm_signal_logger.info(f'[ILM Background] Skipping {well.name} - no coordinates')
                return

            # Get all other wells in this location with coordinates
            other_wells = list(Well.objects.filter(
                Q(location=location) | Q(asset_id=location.company_code),
                is_deleted=False
            ).exclude(id=well_id).filter(
                latitude__isnull=False, longitude__isnull=False
            ))

            # Get all rigs in this location
            rigs = list(Rig.objects.filter(
                Q(location=location) | Q(asset_id=location.location),
                is_deleted=False
            ).select_related('rig_building_norm'))

            if not other_wells or not rigs:
                _ilm_signal_logger.info(f'[ILM Background] No pairs to create for {well.name}')
                return

            # Pre-fetch adjustment rules
            prefetched_adjustments = list(RigBuildingAdjustment.objects.filter(
                location=location, is_active=True
            ).order_by('-priority', 'category'))

            # Delete existing pairs for this well (both directions)
            WellPairDistance.objects.filter(
                location=location, rig__in=rigs
            ).filter(Q(well_1=well) | Q(well_2=well)).delete()

            # Create new pairs
            new_records = []
            for rig in rigs:
                norm_days = rig.rig_building_norm.days if rig.rig_building_norm else None
                for other_well in other_wells:
                    distance = WellPairDistance.haversine_distance(
                        well.latitude, well.longitude,
                        other_well.latitude, other_well.longitude
                    )
                    ilm_result_fwd = calculate_ilm_days(rig, float(distance), location, norm_days,
                                                        prefetched_adjustments=prefetched_adjustments)
                    ilm_result_rev = ilm_result_fwd  # Symmetric

                    # Both directions
                    new_records.append(WellPairDistance(
                        location=location, rig=rig, well_1=well, well_2=other_well,
                        distance_km=distance,
                        ilm_days=ilm_result_fwd.get('ilm_days'),
                        ilm_note=ilm_result_fwd.get('note', ''),
                        ilm_rules_applied=ilm_result_fwd.get('applied_rules', [])
                    ))
                    new_records.append(WellPairDistance(
                        location=location, rig=rig, well_1=other_well, well_2=well,
                        distance_km=distance,
                        ilm_days=ilm_result_rev.get('ilm_days'),
                        ilm_note=ilm_result_rev.get('note', ''),
                        ilm_rules_applied=ilm_result_rev.get('applied_rules', [])
                    ))

            if new_records:
                WellPairDistance.objects.bulk_create(new_records, ignore_conflicts=True, batch_size=500)
                _ilm_signal_logger.info(
                    f'[ILM Background] Added {len(new_records)} WellPairDistance records for {well.name}'
                )

        except Exception as e:
            _ilm_signal_logger.error(f'[ILM Background] Error adding well pairs for {well_id}: {e}')
        finally:
            try:
                connections['default'].close()
            except Exception:
                pass


def _background_add_rig_pairs(rig_id, location_id):
    """
    Background thread: add WellPairDistance records for a newly added rig,
    or refresh ILM fields only if only the norm changed.
    Uses _ilm_write_lock to serialize SQLite writes across concurrent threads.
    """
    from django.db import connections
    with _ilm_write_lock:
        try:
            from scheduler.models import Rig, Well, WellPairDistance, CompanyCode, RigBuildingAdjustment
            from scheduler.views import calculate_ilm_days
            from itertools import combinations
            from django.db.models import Q

            location = CompanyCode.objects.get(id=location_id)
            rig = Rig.objects.get(id=rig_id)

            # Pre-fetch adjustments
            prefetched_adjustments = list(RigBuildingAdjustment.objects.filter(
                location=location, is_active=True
            ).order_by('-priority', 'category'))

            # Existing records for this rig
            existing = WellPairDistance.objects.filter(location=location, rig=rig).select_related(
                'well_1', 'well_2'
            )

            if existing.exists():
                # Refresh ILM cache for this rig (norm likely changed)
                norm_days = rig.rig_building_norm.days if rig.rig_building_norm else None
                batch = list(existing.select_related('rig', 'rig__rig_building_norm'))
                to_update = []
                for d in batch:
                    ilm_result = calculate_ilm_days(
                        rig, float(d.distance_km), location, norm_days,
                        prefetched_adjustments=prefetched_adjustments
                    )
                    d.ilm_days = ilm_result.get('ilm_days')
                    d.ilm_note = ilm_result.get('note', '')
                    d.ilm_rules_applied = ilm_result.get('applied_rules', [])
                    to_update.append(d)
                WellPairDistance.objects.bulk_update(
                    to_update, ['ilm_days', 'ilm_note', 'ilm_rules_applied'], batch_size=500
                )
                _ilm_signal_logger.info(
                    f'[ILM Background] Refreshed {len(to_update)} ILM records for rig {rig.name}'
                )
            else:
                # New rig — create pairs for all well combinations
                wells = list(Well.objects.filter(
                    Q(location=location) | Q(asset_id=location.company_code),
                    is_deleted=False
                ).filter(latitude__isnull=False, longitude__isnull=False))

                norm_days = rig.rig_building_norm.days if rig.rig_building_norm else None
                new_records = []
                for well_1, well_2 in combinations(wells, 2):
                    distance = WellPairDistance.haversine_distance(
                        well_1.latitude, well_1.longitude,
                        well_2.latitude, well_2.longitude
                    )
                    ilm_result = calculate_ilm_days(rig, float(distance), location, norm_days,
                                                    prefetched_adjustments=prefetched_adjustments)
                    for w1, w2 in [(well_1, well_2), (well_2, well_1)]:
                        new_records.append(WellPairDistance(
                            location=location, rig=rig, well_1=w1, well_2=w2,
                            distance_km=distance,
                            ilm_days=ilm_result.get('ilm_days'),
                            ilm_note=ilm_result.get('note', ''),
                            ilm_rules_applied=ilm_result.get('applied_rules', [])
                        ))

                if new_records:
                    WellPairDistance.objects.bulk_create(new_records, ignore_conflicts=True, batch_size=500)
                    _ilm_signal_logger.info(
                        f'[ILM Background] Created {len(new_records)} WellPairDistance records for rig {rig.name}'
                    )

        except Exception as e:
            _ilm_signal_logger.error(f'[ILM Background] Error processing rig {rig_id}: {e}')
        finally:
            try:
                connections['default'].close()
            except Exception:
                pass


@receiver(post_save, sender=Well)
def well_saved_trigger_ilm(sender, instance, created, raw, **kwargs):
    """Trigger background ILM pair creation/refresh when a Well is saved.
    Uses transaction.on_commit() to ensure the well is visible to the background thread."""
    if raw:
        # Skip during loaddata / fixture loading
        return
    if instance.is_deleted:
        return
    if not instance.location:
        return
    if not all([instance.latitude, instance.longitude]):
        return  # Only process wells with coordinates

    well_id = str(instance.id)
    location_id = str(instance.location_id)
    well_name = instance.name

    def _start_background():
        t = threading.Thread(
            target=_background_add_well_pairs,
            args=(well_id, location_id),
            daemon=True,
            name=f'ilm-well-{well_name}'
        )
        t.start()
        _ilm_signal_logger.info(f'[ILM Background] Started pair update for well {well_name}')

    from django.db import transaction as txn
    txn.on_commit(_start_background)


@receiver(post_save, sender=Rig)
def rig_saved_trigger_ilm(sender, instance, created, raw, **kwargs):
    """Trigger background ILM pair creation/refresh when a Rig is saved.
    Uses transaction.on_commit() to ensure the rig is visible to the background thread."""
    if raw:
        return
    if instance.is_deleted:
        return
    if not instance.location:
        return

    rig_id = str(instance.id)
    location_id = str(instance.location_id)
    rig_name = instance.name

    def _start_background():
        t = threading.Thread(
            target=_background_add_rig_pairs,
            args=(rig_id, location_id),
            daemon=True,
            name=f'ilm-rig-{rig_name}'
        )
        t.start()
        _ilm_signal_logger.info(f'[ILM Background] Started ILM update for rig {rig_name}')

    from django.db import transaction as txn
    txn.on_commit(_start_background)


class StagedWell(models.Model):
    """Model representing wells in staging area awaiting field completion before final import"""
    
    WELL_TYPES = [
        ('EXP', 'Exploration'),
        ('Dev', 'Development'),
    ]
    
    WELL_PROFILES = [
        ('DI', 'Directional'),
        ('VE', 'Vertical'),
        ('SD', 'Sidetrack'),
    ]
    
    PRIORITY_CHOICES = [
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    ]
    
    FOOTPRINT_CHOICES = [
        ('Mobile', 'Mobile'),
        ('Fixed', 'Fixed'),
    ]
    
    YES_NO_CHOICES = [
        ('Y', 'Yes'),
        ('N', 'No'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending Completion'),
        ('COMPLETED', 'Ready to Import'),
        ('IMPORTED', 'Imported to Wells'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Fields from CSV upload
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staged_wells',
        help_text="Location (Company Code) where this well is located"
    )
    asset_id = models.CharField(max_length=50, help_text="Asset identifier")
    name = models.CharField(max_length=50, help_text="Well name")
    field_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Field name - used for benchmark lookup",
        db_index=True
    )
    well_type = models.CharField(max_length=3, choices=WELL_TYPES)
    depth = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Well depth in meters"
    )
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        blank=True,
        null=True,
        help_text="GPS latitude - can be filled manually if missing from CSV"
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        blank=True,
        null=True,
        help_text="GPS longitude - can be filled manually if missing from CSV"
    )
    rtd = models.DateField(
        null=True,
        blank=True,
        help_text="Ready To Drill date - can be blank on upload, set later"
    )
    priority = models.CharField(
        max_length=6,
        choices=PRIORITY_CHOICES,
        default='MEDIUM'
    )
    
    # Fields to be filled by user through form (required before import)
    well_profile = models.CharField(
        max_length=2, 
        choices=WELL_PROFILES,
        blank=True,
        null=True,
        help_text="Well profile type - to be completed by user"
    )
    rig_capacity_required_hp = models.IntegerField(
        validators=[MinValueValidator(1)],
        blank=True,
        null=True,
        help_text="Required rig capacity in HP - to be completed by user"
    )
    drl_days = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
        help_text="Drilling days required - to be completed by user"
    )
    pt_days = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
        help_text="Post-drilling testing days - to be completed by user"
    )
    duration = models.IntegerField(
        validators=[MinValueValidator(1)],
        blank=True,
        null=True,
        help_text="Total duration in days - to be completed by user"
    )
    bop_stack = models.IntegerField(
        validators=[MinValueValidator(1)],
        blank=True,
        null=True,
        help_text="Required BOP Stack capacity - to be completed by user"
    )
    tds_requirement = models.CharField(
        max_length=1,
        choices=YES_NO_CHOICES,
        blank=True,
        null=True,
        help_text="Top Drive System requirement - to be completed by user"
    )
    footprint = models.CharField(
        max_length=10,
        choices=FOOTPRINT_CHOICES,
        blank=True,
        null=True,
        help_text="Required rig footprint type - to be completed by user"
    )
    preferred_rig = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Preferred rig for this well - to be completed by user"
    )
    expected_potential = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Expected well potential - to be completed by user"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING',
        help_text="Current status of staged well"
    )
    
    # Metadata
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_staged_wells',
        help_text="User who uploaded this well"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    completed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_staged_wells',
        help_text="User who completed the additional fields"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    
    # Basket association - well can belong to multiple baskets
    baskets = models.ManyToManyField(
        'WellBasket',
        blank=True,
        related_name='staged_wells',
        help_text="Baskets this well belongs to"
    )
    
    imported_well = models.ForeignKey(
        'Well',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staged_source',
        help_text="The final Well record created from this staged well"
    )
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = "Staged Well"
        verbose_name_plural = "Staged Wells"
    
    def __str__(self):
        return f"{self.name} ({self.asset_id}) - {self.status}"
    
    @property
    def is_ready_to_import(self):
        """Check if all required fields are filled"""
        required_fields = [
            self.location,
            self.latitude,
            self.longitude,
            self.well_profile,
            self.rig_capacity_required_hp,
            self.drl_days,
            self.pt_days,
            self.duration,
            self.bop_stack,
            self.tds_requirement,
            self.footprint,
            self.rtd,
        ]
        return all(field is not None for field in required_fields)
    
    @property
    def missing_fields(self):
        """Return list of missing required fields"""
        fields = []
        if not self.location:
            fields.append('Location')
        if self.latitude is None:
            fields.append('Latitude')
        if self.longitude is None:
            fields.append('Longitude')
        if not self.well_profile:
            fields.append('Well Profile')
        if not self.rig_capacity_required_hp:
            fields.append('Rig Capacity Required (HP)')
        if not self.drl_days:
            fields.append('DRL Days')
        if not self.pt_days:
            fields.append('PT Days')
        if not self.duration:
            fields.append('Duration')
        if not self.bop_stack:
            fields.append('BOP Stack')
        if not self.tds_requirement:
            fields.append('TDS Requirement')
        if not self.footprint:
            fields.append('Footprint')
        if self.rtd is None:
            fields.append('RTD Date')
        return fields
    
    def save(self, *args, **kwargs):
        """Override save to convert field_name to title case for consistency"""
        if self.field_name:
            self.field_name = self.field_name.title()
        super().save(*args, **kwargs)


class WellBasket(models.Model):
    """
    Model representing a basket/subset of staged wells for batch processing.
    Users can create baskets to group related wells for planning purposes.
    A staged well can belong to multiple baskets simultaneously.
    """
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('FINALIZED', 'Finalized'),
        ('ARCHIVED', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100,
        help_text="Name/description for this basket"
    )
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.CASCADE,
        related_name='well_baskets',
        help_text="Location (Company Code) this basket belongs to"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description or notes for this basket"
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='ACTIVE',
        help_text="Current status of the basket"
    )
    
    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_baskets',
        help_text="User who created this basket"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Well Basket"
        verbose_name_plural = "Well Baskets"
    
    def __str__(self):
        return f"{self.name} ({self.location.code if self.location else 'No Location'}) - {self.well_count} wells"
    
    @property
    def well_count(self):
        """Return count of wells in this basket"""
        return self.staged_wells.count()
    
    @property
    def wells_summary(self):
        """Return summary of wells by status"""
        wells = self.staged_wells.all()
        return {
            'total': wells.count(),
            'pending': wells.filter(status='PENDING').count(),
            'completed': wells.filter(status='COMPLETED').count(),
            'imported': wells.filter(status='IMPORTED').count(),
        }


class Schedule(models.Model):
    """Model representing a scheduling session/run"""
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, help_text="Schedule name/description")
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedules',
        help_text="Location (Company Code) this schedule belongs to"
    )
    financial_year = models.CharField(
        max_length=9,
        default=get_current_financial_year,
        help_text="Financial Year (e.g., 2024-2025, 2025-2026)",
        db_index=True
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_schedules',
        help_text="User who created this schedule"
    )
    
    # Optimization results
    total_drilling_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total drilling cost in INR"
    )
    total_ilm_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total ILM cost in INR"
    )
    project_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Calculated project completion date"
    )
    unassigned_wells_count = models.IntegerField(
        default=0,
        help_text="Number of wells that couldn't be assigned"
    )
    solver_status = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="OR-Tools solver status"
    )
    solve_time_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Time taken to solve in seconds"
    )
    optimality_gap_percent = models.FloatField(
        null=True,
        blank=True,
        help_text="Optimality gap in percent. 0% = proven optimal. Small % = near-optimal."
    )
    schedule_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="SHA-256 fingerprint of assignments (rig, well, start, end). Used to verify determinism."
    )

    # Parent-child relationship for branching
    parent_schedule = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='child_schedules',
        help_text="Parent schedule if this is derived from another schedule"
    )
    branch_type = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Type of branching: 'reschedule', 'add_well', 'delete_well', etc."
    )
    version_number = models.IntegerField(
        default=1,
        help_text="Version number within the schedule family"
    )
    
    # Input metadata (stored at creation time for display while running/queued)
    input_wells_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of wells submitted for optimization"
    )
    input_rigs_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of rigs submitted for optimization"
    )
    time_limit_seconds = models.IntegerField(
        null=True,
        blank=True,
        help_text="Solver time limit in seconds as requested by user"
    )
    
    def get_root_schedule(self):
        """Get the root/original schedule in the family"""
        current = self
        while current.parent_schedule:
            current = current.parent_schedule
        return current
    
    def get_base_name(self):
        """Get the base name without version suffixes"""
        root = self.get_root_schedule()
        # Remove any existing version suffixes like " v2", " (v3)", etc.
        base_name = root.name
        import re
        # Remove patterns like " v2", " (v3)", " - v4", etc.
        base_name = re.sub(r'\s*[-\(]?\s*v\d+\s*\)?$', '', base_name)
        return base_name
    
    def get_display_name(self):
        """Get a clean display name with proper versioning"""
        base_name = self.get_base_name()
        if self.version_number == 1:
            return base_name
        else:
            return f"{base_name} v{self.version_number}"
    
    def get_next_version_number(self):
        """Get the next version number for a child schedule"""
        root = self.get_root_schedule()
        
        # Get ALL schedules in the family tree recursively
        def get_all_descendants(schedule_id):
            """Recursively get all descendants of a schedule"""
            descendants = set([schedule_id])
            children = Schedule.objects.filter(parent_schedule_id=schedule_id).values_list('id', flat=True)
            for child_id in children:
                descendants.update(get_all_descendants(child_id))
            return descendants
        
        all_family_ids = get_all_descendants(root.id)
        
        # Get max version from entire family
        from django.db import models as db_models
        family_schedules = Schedule.objects.filter(id__in=all_family_ids)
        max_version = family_schedules.aggregate(
            max_version=models.Max('version_number')
        )['max_version'] or 0
        return max_version + 1
    
    def get_unique_asset_ids(self):
        """Get unique asset IDs from all wells in this schedule's assignments"""
        return self.assignments.values_list('well__asset_id', flat=True).distinct().order_by('well__asset_id')
    
    @property
    def total_cost(self):
        """Calculate total cost (drilling + ILM)"""
        drilling_cost = self.total_drilling_cost or Decimal('0')
        ilm_cost = self.total_ilm_cost or Decimal('0')
        return drilling_cost + ilm_cost
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Schedule"
        verbose_name_plural = "Schedules"
    
    def __str__(self):
        display_name = self.get_display_name()
        return f"{display_name} - FY{self.financial_year} ({self.status})"


class ScheduleRig(models.Model):
    """Model to track which rigs were selected for a schedule"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.CASCADE,
        related_name='selected_rigs'
    )
    rig = models.ForeignKey(
        Rig,
        on_delete=models.PROTECT,  # Prevent hard deletion if rig is in any schedule
        related_name='selected_schedules'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['schedule', 'rig']
        verbose_name = "Schedule Rig"
        verbose_name_plural = "Schedule Rigs"
    
    def __str__(self):
        return f"{self.schedule.name} - {self.rig.name}"


class ScheduleWell(models.Model):
    """Model to track which wells were selected for a schedule"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.CASCADE,
        related_name='selected_wells'
    )
    well = models.ForeignKey(
        Well,
        on_delete=models.PROTECT,  # Prevent hard deletion if well is in any schedule
        related_name='selected_schedules'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['schedule', 'well']
        verbose_name = "Schedule Well"
        verbose_name_plural = "Schedule Wells"
    
    def __str__(self):
        return f"{self.schedule.name} - {self.well.name}"


class Assignment(models.Model):
    """Model representing a rig-well assignment"""
    
    CHECK_STATUSES = [
        ('OK', 'OK'),
        ('NOK', 'Not OK'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    rig = models.ForeignKey(
        Rig,
        on_delete=models.PROTECT,  # Prevent hard deletion if rig has assignments
        related_name='assignments'
    )
    well = models.ForeignKey(
        Well,
        on_delete=models.PROTECT,  # Prevent hard deletion if well has assignments
        related_name='assignments'
    )
    
    # Calculated schedule dates (current optimized dates)
    well_start_date = models.DateField(help_text="Calculated well start date")
    well_end_date = models.DateField(help_text="Calculated well end date")
    
    # Original planned dates (preserved when actual dates are locked)
    original_planned_start = models.DateField(
        null=True,
        blank=True,
        help_text="Original planned start date before actual dates were locked"
    )
    original_planned_end = models.DateField(
        null=True,
        blank=True,
        help_text="Original planned end date before actual dates were locked"
    )
    
    # Actual dates (when work actually started/ended)
    actual_start_date = models.DateField(
        null=True, 
        blank=True, 
        help_text="Actual date when drilling started for this well"
    )
    actual_end_date = models.DateField(
        null=True, 
        blank=True, 
        help_text="Actual date when drilling completed for this well"
    )
    
    # Validation checks
    rtd_check = models.CharField(
        max_length=3,
        choices=CHECK_STATUSES,
        help_text="RTD date validation"
    )
    well_start_check = models.CharField(
        max_length=3,
        choices=CHECK_STATUSES,
        help_text="Well start date validation"
    )
    well_end_check = models.CharField(
        max_length=3,
        choices=CHECK_STATUSES,
        help_text="Well end date validation"
    )
    depth_check = models.CharField(
        max_length=3,
        choices=CHECK_STATUSES,
        help_text="Depth capability check"
    )
    hp_check = models.CharField(
        max_length=3,
        choices=CHECK_STATUSES,
        help_text="Horsepower check"
    )
    bop_check = models.CharField(
        max_length=3,
        choices=CHECK_STATUSES,
        help_text="BOP stack check"
    )
    tds_check = models.CharField(
        max_length=3,
        choices=CHECK_STATUSES,
        help_text="TDS availability check"
    )
    rig_type_check = models.CharField(
        max_length=3,
        choices=CHECK_STATUSES,
        help_text="Rig type compatibility check"
    )
    
    # Costs
    drilling_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Drilling cost for this assignment"
    )
    ilm_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="ILM cost to reach this well"
    )
    ilm_days = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=Decimal('0.0'),
        help_text="ILM days to reach this well from previous well"
    )
    
    # Order in sequence for the rig
    sequence_order = models.IntegerField(
        help_text="Order of this well in the rig's sequence"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['rig__name', 'sequence_order']
        unique_together = ['schedule', 'well']  # Each well can only be assigned once per schedule
        verbose_name = "Assignment"
        verbose_name_plural = "Assignments"
    
    def __str__(self):
        return f"{self.rig.name} -> {self.well.name} (Order: {self.sequence_order})"


class UnassignedWell(models.Model):
    """Model to track wells that couldn't be assigned in a schedule"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.CASCADE,
        related_name='unassigned_wells'
    )
    well = models.ForeignKey(
        Well,
        on_delete=models.CASCADE,
        related_name='unassigned_schedules'
    )
    reason = models.TextField(
        help_text="Reason why the well couldn't be assigned"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['well__sn']
        unique_together = ['schedule', 'well']
        verbose_name = "Unassigned Well"
        verbose_name_plural = "Unassigned Wells"
    
    def __str__(self):
        return f"Unassigned: {self.well.name} in {self.schedule.name}"


class ExternalAppSetting(models.Model):
    """Model for configuring external app link in sidebar"""
    
    name = models.CharField(
        max_length=100, 
        default='Submit Bug/Enhancement',
        help_text='Display name for the external app button'
    )
    url = models.URLField(
        default='http://127.0.0.1:8000',
        help_text='URL to open when the button is clicked'
    )
    secret_key = models.CharField(
        max_length=255,
        default='iDRS_secret_key_12345',
        help_text='Secret key for HMAC signature generation. MUST match AppSense configuration.'
    )
    enabled = models.BooleanField(
        default=True,
        help_text='Enable/disable the external app button'
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "External App Setting"
        verbose_name_plural = "External App Settings"
    
    def __str__(self):
        return f"{self.name} - {self.url}"
    
    @classmethod
    def get_setting(cls):
        """Get or create the external app setting (singleton pattern)"""
        obj, created = cls.objects.get_or_create(
            id=1,
            defaults={
                'name': 'Submit Bug/Enhancement',
                'url': 'http://127.0.0.1:8000',
                'secret_key': 'iDRS_secret_key_12345',
                'enabled': True
            }
        )
        return obj


class DrillingBenchmark(models.Model):
    """Model to store drilling benchmark data for auto-calculation of DRL_DAYS"""
    
    WELL_CATEGORY_CHOICES = [
        ('Directional', 'Directional'),
        ('Vertical', 'Vertical'),
        ('Sidetrack', 'Sidetrack'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='drilling_benchmarks',
        help_text="Location (Company Code) for this benchmark"
    )
    pool = models.CharField(
        max_length=100, 
        default='AK',
        help_text="Pool name (e.g., AK, AV, KT)"
    )
    well_category = models.CharField(
        max_length=50, 
        choices=WELL_CATEGORY_CHOICES,
        default='Directional',
        help_text="Category of well"
    )
    well_depth_start = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Well depth start in meters"
    )
    well_depth_end = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Well depth end in meters"
    )
    field = models.CharField(
        max_length=100,
        help_text="Field name",
        db_index=True
    )
    drilling_depth = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Representative drilling depth in meters"
    )
    benchmark_days = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Benchmark drilling days"
    )
    loc_spec_factor = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Location-specific factor (dynamically managed via Location Spec Factors)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['location', 'pool', 'well_category', 'field']
        unique_together = ['location', 'pool', 'well_category', 'well_depth_start', 'well_depth_end', 'field', 'loc_spec_factor']
        verbose_name = "Drilling Benchmark"
        verbose_name_plural = "Drilling Benchmarks"
    
    def __str__(self):
        location_str = self.location.location if self.location else 'No Location'
        return f"{location_str} - {self.pool} - {self.field} - {self.well_category}"


class DailyDrillingRate(models.Model):
    """Model to store daily drilling rates by location, field and depth"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='daily_drilling_rates_location',
        help_text="Location from CompanyCode (e.g., CAMBAY, MEHSANA)"
    )
    depth_start = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Start depth in meters"
    )
    depth_end = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="End depth in meters"
    )
    field = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Field/Sector name (free text, e.g., Akholjuni, Anklav)"
    )
    per_day_depth = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Meters drilled per day"
    )
    loc_spec_factor = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Location-specific factor (dynamically managed via Location Spec Factors)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['location', 'field', 'depth_start']
        unique_together = ['location', 'field', 'depth_start', 'depth_end', 'loc_spec_factor']
    
    def __str__(self):
        location_str = self.location.location if self.location else 'N/A'
        field_str = self.field.location if self.field else 'N/A'
        return f"{location_str} - {field_str} ({self.depth_start}-{self.depth_end}m): {self.per_day_depth}m/day"


class CoringNorm(models.Model):
    """Model to store additional norm time for coring operations"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coring_norms',
        help_text="Location from Company Codes"
    )
    depth_start = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Start depth in meters"
    )
    depth_end = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="End depth in meters"
    )
    additional_days = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Additional norm time in days for one core"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['depth_start']
        unique_together = ['location', 'depth_start', 'depth_end']
    
    def __str__(self):
        return f"{self.depth_start}-{self.depth_end}m: {self.additional_days} days"


class CasingNorm(models.Model):
    """Model to store additional norm time for casing operations"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='casing_norms',
        help_text="Location from Company Codes"
    )
    depth_start = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Start depth in meters"
    )
    depth_end = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="End depth in meters"
    )
    additional_days = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Additional norm time in days for casing lowering + cementation"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['depth_start']
        unique_together = ['location', 'depth_start', 'depth_end']
    
    def __str__(self):
        return f"{self.depth_start}-{self.depth_end}m: {self.additional_days} days"


class HermeticalTestingNorm(models.Model):
    """Model to store norm time for hermetical testing"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hermetical_testing_norms',
        help_text="Location from Company Codes"
    )
    depth_start = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Start depth in meters"
    )
    depth_end = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="End depth in meters"
    )
    norm_days = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Norm time in days for hermetical testing"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['depth_start']
        unique_together = ['location', 'depth_start', 'depth_end']
    
    def __str__(self):
        return f"{self.depth_start}-{self.depth_end}m: {self.norm_days} days"


class OperationNorm(models.Model):
    """Model to store norm rules for various operations"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operation_norms',
        help_text="Location from Company Codes"
    )
    operation = models.CharField(
        max_length=200,
        help_text="Name of the operation"
    )
    norm_rule = models.CharField(
        max_length=200,
        help_text="Norm or rule for the operation"
    )
    remarks = models.TextField(
        blank=True,
        help_text="Additional remarks or notes"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['operation']
        unique_together = ['location', 'operation']
    
    def __str__(self):
        return f"{self.operation}: {self.norm_rule}"


class RigBuildingNorm(models.Model):
    """Model to store rig building norms - simple rig name to days mapping"""
    
    RIG_TYPE_CHOICES = [
        ('Fixed', 'Fixed'),
        ('Mobile', 'Mobile'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rig_building_norms',
        help_text="Location (Company Code) for this rig building norm"
    )
    rig_name = models.CharField(
        max_length=100,
        help_text="Name of the rig (e.g., E-760, Mobile rigs, IPS-M700)"
    )
    days = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of days for this rig"
    )
    top_drive = models.BooleanField(
        default=False,
        help_text="Whether this rig has top drive capability"
    )
    rig_type = models.CharField(
        max_length=20,
        choices=RIG_TYPE_CHOICES,
        default='Fixed',
        help_text="Type of rig (Fixed or Mobile)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['location', 'rig_name']
        unique_together = ['location', 'rig_name']
        verbose_name = "Rig Building Norm"
        verbose_name_plural = "Rig Building Norms"
    
    def __str__(self):
        location_str = self.location.location if self.location else 'No Location'
        return f"{location_str} - {self.rig_name} - {self.days} days"


class RigBuildingAdjustment(models.Model):
    """
    Model to store rig building adjustment rules for various scenarios.
    These rules are used during scheduling to calculate ILM cost and time adjustments
    based on conditions like distance, rig type, transportation, monsoon period, etc.
    """
    
    ADJUSTMENT_TYPE_CHOICES = [
        ('replace', 'Replace Base Norm'),      # Replaces the base rig building days
        ('add', 'Add to Base Norm'),           # Adds days to base norm (e.g., +1 day, +2 days)
        ('included', 'Included (No Extra)'),   # No additional days needed
        ('per_unit', 'Per Unit Addition'),     # Add days per unit (e.g., +1 day per 50 km)
        ('conversion', 'Conversion Rule'),     # Conversion factor (e.g., 1 monsoon day = 0.7 dry days)
        ('conditional', 'Conditional Rule'),   # Apply only when certain conditions are met
    ]
    
    CATEGORY_CHOICES = [
        ('cluster_movement', 'Cluster Movement'),
        ('transportation', 'Transportation'),
        ('equipment', 'Equipment Related'),
        ('weather', 'Weather/Monsoon'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rig_building_adjustments',
        help_text="Location (Company Code) for this adjustment rule"
    )
    
    condition = models.CharField(
        max_length=500,
        help_text="Description of the condition/scenario (e.g., 'Rig dragged within 25m radius for adjacent well')"
    )
    
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='other',
        help_text="Category of this adjustment rule"
    )
    
    adjustment_type = models.CharField(
        max_length=20,
        choices=ADJUSTMENT_TYPE_CHOICES,
        default='add',
        help_text="How this adjustment is applied"
    )
    
    adjustment_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Numeric value for the adjustment (days, conversion factor, etc.)"
    )
    
    adjustment_display = models.CharField(
        max_length=100,
        help_text="Human-readable adjustment display (e.g., '+1 day', '2 days', '0.7 ratio')"
    )
    
    unit = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Unit for per-unit adjustments (e.g., '50 km')"
    )
    
    # Lookup parameters for matching during scheduling
    min_distance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum distance in meters for distance-based rules"
    )
    
    max_distance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum distance in meters for distance-based rules"
    )
    
    applies_to_rig_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Rig type this rule applies to (Mobile, Fixed, Type-I, or blank for all)"
    )
    
    max_depth = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum well depth in meters for depth-based rules"
    )
    
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes or clarifications"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this rule is currently active"
    )
    
    priority = models.IntegerField(
        default=0,
        help_text="Priority for rule application (higher = applied first)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['location', 'category', 'priority', 'condition']
        verbose_name = "Rig Building Adjustment"
        verbose_name_plural = "Rig Building Adjustments"
    
    def __str__(self):
        location_str = self.location.location if self.location else 'General'
        return f"{location_str} - {self.condition} ({self.adjustment_display})"


class CompletionTestingNorm(models.Model):
    """
    Model for completion testing norms based on location, depth interval, and well type
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completion_testing_norms',
        help_text="Location (Company Code) for this completion testing norm"
    )
    well_depth_start = models.IntegerField(help_text="Well depth interval start in meters")
    well_depth_end = models.IntegerField(help_text="Well depth interval end in meters")
    well_type = models.CharField(
        max_length=50,
        choices=[
            ('Development', 'Development'),
            ('Exploratory', 'Exploratory'),
        ],
        help_text="Well type"
    )
    days = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        help_text="Number of days for completion testing"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['location', 'well_depth_start', 'well_type']
        verbose_name = "Completion Testing Norm"
        verbose_name_plural = "Completion Testing Norms"
    
    def __str__(self):
        location_str = self.location.location if self.location else 'No Location'
        return f"{location_str} - {self.well_type} ({self.well_depth_start}-{self.well_depth_end}m): {self.days} days"


class AdditionalTest(models.Model):
    """
    Model for additional testing operations and their norm times
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='additional_tests',
        help_text="Location from Company Codes"
    )
    job = models.TextField(help_text="Job description")
    norm_time = models.CharField(max_length=255, help_text="Norm time for the job")
    notes = models.TextField(blank=True, null=True, help_text="Additional notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['job']
        verbose_name = "Additional Test"
        verbose_name_plural = "Additional Tests"
        unique_together = ['location', 'job']
    
    def __str__(self):
        return f"{self.job} - {self.norm_time}"


class LocationSpecFactor(models.Model):
    """
    Model for managing location-specific factor choices.
    Each location can have its own set of loc_spec_factor values.
    Admin-only management.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.CASCADE,
        related_name='loc_spec_factors',
        help_text="Location (Company Code) for this factor"
    )
    factor_value = models.CharField(
        max_length=50,
        help_text="The factor value (e.g., '2CP', '3CP', 'Main Pool', 'other than Main')"
    )
    display_order = models.IntegerField(
        default=0,
        help_text="Order for display in dropdowns"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the default value for the location"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this factor is currently active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['location', 'display_order', 'factor_value']
        verbose_name = "Location Spec Factor"
        verbose_name_plural = "Location Spec Factors"
        unique_together = ['location', 'factor_value']
    
    def __str__(self):
        location_str = self.location.location if self.location else 'No Location'
        default_str = " (default)" if self.is_default else ""
        return f"{location_str}: {self.factor_value}{default_str}"
    
    @classmethod
    def get_factors_for_location(cls, location_name):
        """Get all active factors for a given location"""
        return cls.objects.filter(
            location__location__iexact=location_name,
            is_active=True
        ).order_by('display_order', 'factor_value')
    
    @classmethod
    def get_default_for_location(cls, location_name):
        """Get the default factor for a location"""
        default = cls.objects.filter(
            location__location__iexact=location_name,
            is_default=True,
            is_active=True
        ).first()
        if default:
            return default.factor_value
        # Fallback to first factor if no default set
        first = cls.objects.filter(
            location__location__iexact=location_name,
            is_active=True
        ).first()
        return first.factor_value if first else '2CP'


class CompanyCode(models.Model):
    """
    Model for managing company codes and cost centres mapping
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fund_centre = models.CharField(max_length=50, help_text="Fund Centre code")
    company_code = models.CharField(max_length=50, help_text="Company Code")
    cost_centre = models.CharField(max_length=50, help_text="Cost Centre")
    category = models.CharField(max_length=100, help_text="Category (Asset/Basin/Plant/Other)")
    name = models.CharField(max_length=255, help_text="Name of the entity")
    city = models.CharField(max_length=100, help_text="City")
    state = models.CharField(max_length=100, help_text="State")
    location = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Location/Asset name or code (centralized location field)"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Description of the location"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this location is currently active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['company_code', 'name']
        verbose_name = "Company Code"
        verbose_name_plural = "Company Codes"
        unique_together = ['fund_centre', 'cost_centre']
    
    @property
    def code(self):
        """Compatibility alias for legacy location code usage."""
        return self.location or self.company_code
    
    def save(self, *args, **kwargs):
        """Override save to convert location to title case for consistency"""
        if self.location:
            self.location = self.location.title()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"


class MasterPersonnelInfo(models.Model):
    """
    Master Personnel Information (MPI) model for managing employee data
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Primary Fields
    cpf_no = models.CharField(max_length=20, unique=True, help_text="CPF Number")
    crc = models.CharField(max_length=50, blank=True, null=True, help_text="CRC")
    duty_type = models.CharField(max_length=50, blank=True, null=True, help_text="Duty Type")
    work_pattern = models.CharField(max_length=50, blank=True, null=True, help_text="Work Pattern")
    pwd = models.CharField(max_length=50, blank=True, null=True, help_text="PwD")
    q_new = models.CharField(max_length=50, blank=True, null=True, help_text="Q New")
    
    # Organization Fields
    org_unit = models.CharField(max_length=50, blank=True, null=True, help_text="ORG.UNIT")
    group_1 = models.CharField(max_length=100, blank=True, null=True, help_text="GROUP 1")
    group_2 = models.CharField(max_length=100, blank=True, null=True, help_text="GROUP 2")
    org_new = models.CharField(max_length=100, blank=True, null=True, help_text="ORG NEW")
    org_unit_text = models.CharField(max_length=255, blank=True, null=True, help_text="ORG.UNIT TEXT")
    position_text = models.CharField(max_length=255, blank=True, null=True, help_text="POSITION TEXT")
    
    # Location and Sector
    location = models.CharField(max_length=100, blank=True, null=True, help_text="LOCATION")
    sector = models.CharField(max_length=100, blank=True, null=True, help_text="SECTOR")
    
    # Personal Information
    name = models.CharField(max_length=255, help_text="NAME")
    designation = models.CharField(max_length=100, blank=True, null=True, help_text="DESIGNATION")
    lvl = models.CharField(max_length=20, blank=True, null=True, help_text="LVL")
    disp = models.CharField(max_length=100, blank=True, null=True, help_text="DISP")
    subdisp = models.CharField(max_length=100, blank=True, null=True, help_text="SUBDISP")
    gender_key = models.CharField(max_length=10, blank=True, null=True, help_text="GENDER KEY")
    
    # Date Fields
    dob = models.DateField(blank=True, null=True, help_text="Date of Birth")
    dor = models.DateField(blank=True, null=True, help_text="Date of Retirement")
    doj_ongc = models.DateField(blank=True, null=True, help_text="Date of Join ONGC")
    date_of_join_post = models.DateField(blank=True, null=True, help_text="Date of Join Post")
    eff_date_prom = models.DateField(blank=True, null=True, help_text="Effective Date of Promotion")
    date_of_join_per_area = models.DateField(blank=True, null=True, help_text="Date of Join Personal Area")
    date_of_join_position = models.DateField(blank=True, null=True, help_text="Date of Join Position")
    date_of_retirement = models.DateField(blank=True, null=True, help_text="Date of Retirement")
    
    # Additional Fields
    personal_area = models.CharField(max_length=100, blank=True, null=True, help_text="PERSONAL AREA")
    state_deployed = models.CharField(max_length=100, blank=True, null=True, help_text="STATE DEPLOYED")
    qual_text = models.CharField(max_length=255, blank=True, null=True, help_text="QUAL_TEXT")
    home_state = models.CharField(max_length=100, blank=True, null=True, help_text="HOME STATE")
    
    # DL Fields
    dl_designation_text = models.CharField(max_length=255, blank=True, null=True, help_text="DL-DESIGNATION TEXT")
    dl_discipline_text = models.CharField(max_length=255, blank=True, null=True, help_text="DL-DISCIPLINE TEXT")
    dl_sub_disp_text = models.CharField(max_length=255, blank=True, null=True, help_text="DL-SUB DISP TEXT")
    
    # Type and Contact
    type_i = models.CharField(max_length=50, blank=True, null=True, help_text="Type-I")
    mobile_no = models.CharField(max_length=20, blank=True, null=True, help_text="Mobile Number")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name', 'cpf_no']
        verbose_name = "Master Personnel Info"
        verbose_name_plural = "Master Personnel Info"
        indexes = [
            models.Index(fields=['cpf_no']),
            models.Index(fields=['name']),
            models.Index(fields=['location']),
        ]
    
    def __str__(self):
        return f"{self.cpf_no} - {self.name}"


class AuthorizedUser(models.Model):
    """
    Authorized users who can log in to the application.
    Only users in this table can authenticate via LDAP.
    Synced from MPI table CPF numbers.
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),  # Full access to everything
        ('L1', 'L1'),        # Can see all locations but not admin-only content
        ('user', 'User'),    # Limited to assigned location
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cpf_no = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text="CPF Number (Employee ID) - used as username for LDAP"
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Full name from MPI"
    )
    email = models.EmailField(
        blank=True,
        null=True,
        help_text="Email from LDAP"
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='user',
        help_text="User role: admin, L1, or user"
    )
    assigned_location = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Location assigned to user (for 'user' role)"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Only active users can log in"
    )
    
    # Link to Django User model (created after successful LDAP authentication)
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='authorized_user',
        help_text="Linked Django User account (created after LDAP auth)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful LDAP login"
    )
    
    class Meta:
        ordering = ['cpf_no']
        verbose_name = "Authorized User"
        verbose_name_plural = "Authorized Users"
        indexes = [
            models.Index(fields=['cpf_no', 'is_active']),
            models.Index(fields=['role']),
        ]
    
    def __str__(self):
        return f"{self.cpf_no} - {self.name or 'Unknown'}"
    
    def can_view_all_locations(self):
        """Check if user can view all locations (admin or L1)"""
        return self.role in ['admin', 'L1']
    
    def is_admin_role(self):
        """Check if user is admin"""
        return self.role == 'admin'
    
    def get_accessible_locations(self):
        """Get list of locations this user can access"""
        if self.can_view_all_locations():
            return None  # None means all locations
        return [self.assigned_location] if self.assigned_location else []


class LoginAttempt(models.Model):
    """
    Track all login attempts (successful and failed) for security monitoring.
    """
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed_ldap', 'Failed - Invalid LDAP Credentials'),
        ('failed_unauthorized', 'Failed - User Not Authorized'),
        ('failed_inactive', 'Failed - User Inactive'),
        ('failed_error', 'Failed - System Error'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Username/CPF used in login attempt"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        help_text="Result of login attempt"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of login attempt"
    )
    user_agent = models.TextField(
        blank=True,
        null=True,
        help_text="Browser/client user agent"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Error details (not shown to user)"
    )
    attempted_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the login attempt occurred"
    )
    
    # Link to user if exists
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='login_attempts',
        help_text="Django user (if login was successful)"
    )
    
    class Meta:
        ordering = ['-attempted_at']
        verbose_name = "Login Attempt"
        verbose_name_plural = "Login Attempts"
        indexes = [
            models.Index(fields=['-attempted_at']),
            models.Index(fields=['username', '-attempted_at']),
            models.Index(fields=['status', '-attempted_at']),
        ]
    
    def __str__(self):
        return f"{self.username} - {self.get_status_display()} - {self.attempted_at.strftime('%Y-%m-%d %H:%M:%S')}"


class UserRole(models.Model):
    """
    DEPRECATED: Use AuthorizedUser instead.
    Kept for backward compatibility with existing migrations.
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('L1', 'L1'),
        ('user', 'User'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='role_assignment',
        help_text="Django user account"
    )
    cpf_no = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="CPF Number (linked to MPI)"
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='user',
        help_text="User role: admin, L1, or user"
    )
    assigned_location = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Location assigned to user (for 'user' role)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_user_roles',
        help_text="Admin who created this role assignment"
    )
    
    class Meta:
        ordering = ['user__username']
        verbose_name = "User Role (Deprecated)"
        verbose_name_plural = "User Roles (Deprecated)"
        indexes = [
            models.Index(fields=['cpf_no']),
            models.Index(fields=['role']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
    
    def can_view_all_locations(self):
        """Check if user can view all locations (admin or L1)"""
        return self.role in ['admin', 'L1']
    
    def is_admin(self):
        """Check if user is admin"""
        return self.role == 'admin'
    
    def get_accessible_locations(self):
        """Get list of locations this user can access"""
        if self.can_view_all_locations():
            return None  # None means all locations
        return [self.assigned_location] if self.assigned_location else []



class VideoTutorial(models.Model):
    """Model for storing video tutorials for users"""
    
    CATEGORY_CHOICES = [
        ('getting_started', 'Getting Started'),
        ('scheduling', 'Scheduling'),
        ('data_management', 'Data Management'),
        ('reports', 'Reports & Analytics'),
        ('admin', 'Admin Features'),
        ('other', 'Other'),
    ]
    
    PROCESSING_STATUS_CHOICES = [
        ('pending', 'Pending Processing'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(
        max_length=200,
        help_text="Title of the video tutorial"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what the video covers"
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='other',
        help_text="Category of the tutorial"
    )
    video_file = models.FileField(
        upload_to='tutorials/videos/',
        help_text="Video file (max 1GB) - will be automatically optimized"
    )
    
    # Processed video files
    optimized_video = models.FileField(
        upload_to='tutorials/videos/',
        blank=True,
        null=True,
        help_text="Optimized version for fast streaming"
    )
    compressed_video = models.FileField(
        upload_to='tutorials/videos/',
        blank=True,
        null=True,
        help_text="Compressed version for smaller file size"
    )
    
    # Processing status
    processing_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS_CHOICES,
        default='pending',
        help_text="Video processing status"
    )
    processing_error = models.TextField(
        blank=True,
        help_text="Error message if processing failed"
    )
    
    thumbnail = models.ImageField(
        upload_to='tutorials/thumbnails/',
        blank=True,
        null=True,
        help_text="Thumbnail image for the video"
    )
    duration_minutes = models.IntegerField(
        blank=True,
        null=True,
        help_text="Duration of video in minutes"
    )
    order = models.IntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this video is visible to users"
    )
    
    # Metadata
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_tutorials',
        help_text="Admin who uploaded this video"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    view_count = models.IntegerField(
        default=0,
        help_text="Number of times this video has been viewed"
    )
    
    # File sizes for reference
    original_size_mb = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Original file size in MB"
    )
    optimized_size_mb = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Optimized file size in MB"
    )
    compressed_size_mb = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Compressed file size in MB"
    )
    
    class Meta:
        ordering = ['category', 'order', 'title']
        verbose_name = "Video Tutorial"
        verbose_name_plural = "Video Tutorials"
    
    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"
    
    def increment_view_count(self):
        """Increment the view count"""
        self.view_count += 1
        self.save(update_fields=['view_count'])
    
    def get_best_video_file(self):
        """Get the best available video file for streaming."""
        # Prefer compressed, then optimized, then original
        if self.compressed_video:
            return self.compressed_video
        elif self.optimized_video:
            return self.optimized_video
        else:
            return self.video_file
    
    def get_video_url(self):
        """Get URL for the best available video."""
        video_file = self.get_best_video_file()
        if video_file:
            return video_file.url
        return None


# =============================================================================
# SCHEDULE EXECUTION MODULE (SEM) MODELS
# =============================================================================

class ExecutionSchedule(models.Model):
    """
    Independent execution copy of an approved schedule.
    Maintains its own state separate from the planning schedule.
    """
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('PAUSED', 'Paused'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="Execution schedule name")
    source_schedule = models.ForeignKey(
        Schedule,
        on_delete=models.PROTECT,
        related_name='executions',
        help_text="Original approved schedule this execution is based on"
    )
    location = models.ForeignKey(
        'CompanyCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='execution_schedules',
        help_text="Location (Company Code) for this execution"
    )
    financial_year = models.CharField(max_length=9, help_text="Financial Year (e.g., 2025-2026)")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='ACTIVE')
    cutoff_date = models.DateField(
        null=True,
        blank=True,
        help_text="All wells before this date are considered locked"
    )

    # Aggregated metrics
    total_planned_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    total_actual_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    planned_end_date = models.DateField(null=True, blank=True)
    projected_end_date = models.DateField(null=True, blank=True)

    # Optimization tracking
    optimization_runs = models.IntegerField(default=0, help_text="Number of re-optimization runs")
    last_optimized_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_executions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Execution Schedule"
        verbose_name_plural = "Execution Schedules"

    def __str__(self):
        return f"{self.name} ({self.status})"

    @property
    def total_wells(self):
        return self.execution_wells.count()

    @property
    def locked_wells_count(self):
        return self.execution_wells.filter(is_locked=True).count()

    @property
    def completed_wells_count(self):
        return self.execution_wells.filter(status='COMPLETED').count()

    @property
    def progress_percentage(self):
        total = self.total_wells
        if total == 0:
            return 0
        return round((self.completed_wells_count / total) * 100, 1)

    @property
    def schedule_variance_days(self):
        """Overall schedule variance in days (positive = behind schedule)"""
        from django.db.models import Sum, F, ExpressionWrapper, DurationField
        wells_with_actuals = self.execution_wells.filter(
            actual_end_date__isnull=False,
            planned_end_date__isnull=False
        )
        total_variance = 0
        for w in wells_with_actuals:
            total_variance += (w.actual_end_date - w.planned_end_date).days
        return total_variance

    def apply_cutoff_lock(self, cutoff_date):
        """Lock all wells whose planned start is on or before the cutoff date"""
        self.cutoff_date = cutoff_date
        self.save(update_fields=['cutoff_date', 'updated_at'])
        wells_to_lock = self.execution_wells.filter(
            planned_start_date__lte=cutoff_date,
            is_locked=False,
            status__in=['PLANNED', 'IN_PROGRESS']
        )
        count = 0
        for well in wells_to_lock:
            well.is_locked = True
            if well.status == 'PLANNED':
                well.status = 'LOCKED'
            well.save(update_fields=['is_locked', 'status', 'updated_at'])
            count += 1
        return count

    def recalculate_metrics(self):
        """Recalculate aggregated metrics from execution wells"""
        from django.db.models import Sum, Max
        agg = self.execution_wells.aggregate(
            total_planned=Sum('planned_drilling_cost'),
            total_actual=Sum('actual_drilling_cost'),
            max_planned_end=Max('planned_end_date'),
            max_actual_end=Max('actual_end_date'),
        )
        self.total_planned_cost = agg['total_planned'] or Decimal('0')
        self.total_actual_cost = agg['total_actual'] or Decimal('0')
        self.planned_end_date = agg['max_planned_end']
        projected = agg['max_actual_end']
        # For projected end, use max of actual ends for completed and planned ends for remaining
        remaining_max = self.execution_wells.filter(
            actual_end_date__isnull=True
        ).aggregate(m=Max('planned_end_date'))['m']
        if projected and remaining_max:
            self.projected_end_date = max(projected, remaining_max)
        elif remaining_max:
            self.projected_end_date = remaining_max
        else:
            self.projected_end_date = projected
        self.save(update_fields=[
            'total_planned_cost', 'total_actual_cost',
            'planned_end_date', 'projected_end_date', 'updated_at'
        ])


class ExecutionRig(models.Model):
    """
    Tracks rigs participating in this execution schedule.
    Can be added/removed during execution.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution_schedule = models.ForeignKey(
        ExecutionSchedule,
        on_delete=models.CASCADE,
        related_name='execution_rigs'
    )
    rig = models.ForeignKey(
        Rig,
        on_delete=models.PROTECT,
        related_name='execution_rigs'
    )
    is_active = models.BooleanField(default=True, help_text="Whether this rig is active in execution")
    added_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['execution_schedule', 'rig']
        verbose_name = "Execution Rig"
        verbose_name_plural = "Execution Rigs"

    def __str__(self):
        status = "Active" if self.is_active else "Removed"
        return f"{self.rig.name} - {status}"


class ExecutionWell(models.Model):
    """
    Individual well being tracked during execution.
    Contains both planned and actual data, and locking state.
    """
    STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('LOCKED', 'Locked'),
        ('DEFERRED', 'Deferred'),
        ('REMOVED', 'Removed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution_schedule = models.ForeignKey(
        ExecutionSchedule,
        on_delete=models.CASCADE,
        related_name='execution_wells'
    )
    well = models.ForeignKey(
        Well,
        on_delete=models.PROTECT,
        related_name='execution_wells'
    )
    rig = models.ForeignKey(
        Rig,
        on_delete=models.PROTECT,
        related_name='execution_well_assignments',
        help_text="Currently assigned rig"
    )
    source_assignment = models.ForeignKey(
        Assignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='execution_wells',
        help_text="Original assignment from the source schedule"
    )

    # Planned dates (baseline from optimization)
    planned_start_date = models.DateField(help_text="Planned/optimized start date")
    planned_end_date = models.DateField(help_text="Planned/optimized end date")

    # Actual dates (filled during execution)
    actual_start_date = models.DateField(null=True, blank=True, help_text="Actual drilling start date")
    actual_end_date = models.DateField(null=True, blank=True, help_text="Actual drilling end date")

    # Status and locking
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PLANNED')
    is_locked = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Locked wells cannot be moved and act as constraints for re-optimization"
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locked_execution_wells'
    )

    # Sequence / ordering
    sequence_order = models.IntegerField(help_text="Order within rig's sequence")

    # Costs
    planned_drilling_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    actual_drilling_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    planned_ilm_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    actual_ilm_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))

    # Notes
    notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['rig__name', 'sequence_order']
        unique_together = ['execution_schedule', 'well']
        verbose_name = "Execution Well"
        verbose_name_plural = "Execution Wells"

    def __str__(self):
        return f"{self.well.name} → {self.rig.name} ({self.status})"

    @property
    def delay_days(self):
        """Calculate delay in days (positive = behind schedule)"""
        if self.actual_end_date and self.planned_end_date:
            return (self.actual_end_date - self.planned_end_date).days
        if self.actual_start_date and self.planned_start_date:
            return (self.actual_start_date - self.planned_start_date).days
        return 0

    @property
    def planned_duration_days(self):
        if self.planned_start_date and self.planned_end_date:
            return (self.planned_end_date - self.planned_start_date).days
        return 0

    @property
    def actual_duration_days(self):
        if self.actual_start_date and self.actual_end_date:
            return (self.actual_end_date - self.actual_start_date).days
        return None

    @property
    def cost_variance(self):
        """Cost variance (positive = over budget)"""
        return float(self.actual_drilling_cost - self.planned_drilling_cost)

    def lock(self, user=None):
        """Lock this well - makes it immovable"""
        self.is_locked = True
        self.locked_at = timezone.now()
        self.locked_by = user
        if self.status == 'PLANNED':
            self.status = 'LOCKED'
        self.save(update_fields=['is_locked', 'locked_at', 'locked_by', 'status', 'updated_at'])

    def set_actual_dates(self, actual_start=None, actual_end=None, user=None):
        """Set actual dates and auto-lock/update status"""
        if actual_start:
            self.actual_start_date = actual_start
            if self.status == 'PLANNED' or self.status == 'LOCKED':
                self.status = 'IN_PROGRESS'
        if actual_end:
            self.actual_end_date = actual_end
            self.status = 'COMPLETED'
        # Auto-lock when actuals are set
        if actual_start or actual_end:
            self.is_locked = True
            if not self.locked_at:
                self.locked_at = timezone.now()
                self.locked_by = user
        self.save()


class ExecutionLog(models.Model):
    """
    Audit log for all execution actions (locks, modifications, re-optimizations).
    """
    ACTION_CHOICES = [
        ('ACTIVATED', 'Schedule Activated'),
        ('ACTUAL_SET', 'Actual Dates Set'),
        ('LOCKED', 'Well Locked'),
        ('CUTOFF_APPLIED', 'Cutoff Lock Applied'),
        ('WELL_ADDED', 'Well Added'),
        ('WELL_REMOVED', 'Well Removed'),
        ('WELL_REPLACED', 'Well Replaced'),
        ('RIG_ADDED', 'Rig Added'),
        ('RIG_REMOVED', 'Rig Removed'),
        ('RIG_REPLACED', 'Rig Replaced'),
        ('REOPTIMIZED', 'Re-optimization Run'),
        ('STATUS_CHANGE', 'Status Changed'),
        ('DEFERRED', 'Well Deferred'),
        ('DATES_SHIFTED', 'Dates Shifted'),
        ('REMARKS_UPDATED', 'Remarks Updated'),
        ('SCENARIO_CREATED', 'Scenario Created'),
        ('SCENARIO_APPLIED', 'Scenario Applied'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution_schedule = models.ForeignKey(
        ExecutionSchedule,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    action = models.CharField(max_length=25, choices=ACTION_CHOICES)
    description = models.TextField(help_text="Human-readable description of the action")
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON details of the action (well/rig IDs, dates, etc.)"
    )
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='execution_logs'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Execution Log"
        verbose_name_plural = "Execution Logs"

    def __str__(self):
        return f"{self.action} - {self.description[:50]}"


class ExecutionScenario(models.Model):
    """
    What-if scenario snapshot of an execution schedule.
    Stores a JSON snapshot of all wells/rigs state so users can create
    multiple scenarios (e.g. 'remove rig A' vs 'remove rig B'), compare,
    and apply the best one without modifying the live execution.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution_schedule = models.ForeignKey(
        ExecutionSchedule,
        on_delete=models.CASCADE,
        related_name='scenarios'
    )
    name = models.CharField(max_length=200, help_text="Scenario name, e.g. 'Remove Rig-5 scenario'")
    description = models.TextField(blank=True, default='', help_text="What-if description")

    # Full snapshot — JSON capture of all wells + rigs at the time of creation
    snapshot = models.JSONField(
        default=dict,
        help_text="JSON snapshot: {rigs: [...], wells: [...], metrics: {...}}"
    )

    # Delta summary — what differs from the live execution
    is_optimized = models.BooleanField(default=False, help_text="Was the optimizer run for this scenario?")
    solver_status = models.CharField(max_length=20, blank=True, default='')
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    total_duration_days = models.IntegerField(default=0)
    end_date = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_scenarios'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Execution Scenario"
        verbose_name_plural = "Execution Scenarios"

    def __str__(self):
        return f"{self.name} ({self.execution_schedule.name})"


# =============================================================================
# USER ACTIVITY TRACKING
# =============================================================================

class UserActivity(models.Model):
    """
    Comprehensive user activity tracking.
    Captures every significant action: logins, logouts, page views,
    data modifications, admin actions, API calls, etc.
    """
    CATEGORY_CHOICES = [
        ('AUTH', 'Authentication'),
        ('PAGE_VIEW', 'Page View'),
        ('DATA_CREATE', 'Data Create'),
        ('DATA_UPDATE', 'Data Update'),
        ('DATA_DELETE', 'Data Delete'),
        ('DATA_IMPORT', 'Data Import'),
        ('DATA_EXPORT', 'Data Export'),
        ('SCHEDULE', 'Scheduling'),
        ('EXECUTION', 'Execution'),
        ('ADMIN', 'Administration'),
        ('API', 'API Call'),
        ('SYSTEM', 'System Event'),
    ]

    SEVERITY_CHOICES = [
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Who
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        help_text="User who performed the action"
    )
    username = models.CharField(
        max_length=150,
        blank=True,
        default='',
        help_text="Username snapshot (preserved even if user is deleted)"
    )
    
    # What
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    action = models.CharField(max_length=255, help_text="Short action description e.g. 'User Login', 'Created Well'")
    description = models.TextField(blank=True, default='', help_text="Detailed description of the action")
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='INFO')
    
    # Where  
    ip_address = models.GenericIPAddressField(null=True, blank=True, help_text="Client IP address")
    user_agent = models.TextField(blank=True, default='', help_text="Browser/client user agent string")
    request_method = models.CharField(max_length=10, blank=True, default='', help_text="HTTP method (GET, POST, etc.)")
    request_path = models.CharField(max_length=500, blank=True, default='', help_text="URL path accessed")
    
    # Context
    target_model = models.CharField(max_length=100, blank=True, default='', help_text="Model/entity affected e.g. 'Well', 'Rig', 'User'")
    target_id = models.CharField(max_length=255, blank=True, default='', help_text="ID of the affected object")
    target_name = models.CharField(max_length=255, blank=True, default='', help_text="Display name of affected object")
    
    # Extra data (JSON)
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional structured data about the action")
    
    # Session info
    session_key = models.CharField(max_length=60, blank=True, default='', help_text="Session key for correlating actions")
    
    # When
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "User Activity"
        verbose_name_plural = "User Activities"
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['category', '-created_at']),
            models.Index(fields=['ip_address', '-created_at']),
            models.Index(fields=['target_model', '-created_at']),
        ]
    
    def __str__(self):
        return f"[{self.category}] {self.username}: {self.action} ({self.created_at:%Y-%m-%d %H:%M})"
    
    @classmethod
    def log(cls, request=None, user=None, category='SYSTEM', action='', description='',
            severity='INFO', target_model='', target_id='', target_name='', metadata=None):
        """
        Convenience class method to create an activity log entry.
        """
        ip_address = None
        user_agent = ''
        request_method = ''
        request_path = ''
        session_key = ''
        
        if request:
            ip_address = cls.get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:1000]
            request_method = request.method
            request_path = request.get_full_path()[:500]
            session_key = request.session.session_key or ''
            if not user and hasattr(request, 'user') and request.user.is_authenticated:
                user = request.user
        
        username = ''
        if user:
            username = user.username
        
        return cls.objects.create(
            user=user,
            username=username,
            category=category,
            action=action,
            description=description,
            severity=severity,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            target_model=target_model,
            target_id=str(target_id) if target_id else '',
            target_name=target_name,
            metadata=metadata or {},
            session_key=session_key,
        )
    
    @staticmethod
    def get_client_ip(request):
        """Extract real client IP from request, handling proxies."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip.strip()
        return request.META.get('REMOTE_ADDR')

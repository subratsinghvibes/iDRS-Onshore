"""
Activity Tracking Middleware
Captures page views, API calls, and attaches IP info to requests.
"""

import logging
import time
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# Paths to skip logging (static files, health checks, etc.)
SKIP_PATHS = (
    '/static/',
    '/media/',
    '/favicon.ico',
    '/apple-touch-icon',
    '/admin/jsi18n/',
)

# API paths that are high-frequency and low-value to log individually
SKIP_API_PATHS = (
    '/api/company-codes/',  # loaded on every page
)

# Page view paths to track (template views, not API)
PAGE_VIEW_PATHS = {
    '/': 'Home',
    '/dashboard/': 'Dashboard',
    '/data/': 'Data Management',
    '/scheduling/': 'Scheduling',
    '/schedules/': 'Schedules List',
    '/gantt/': 'Interactive Gantt',
    '/execution/': 'Execution Dashboard',
    '/schedule-maps/': 'Movement Maps',
    '/user-management/': 'User Management',
    '/company-codes/': 'Company Codes',
    '/database-viewer/': 'Database Viewer',
    '/er-diagram/': 'ER Diagram',
    '/tutorials/': 'Video Tutorials',
    '/mpi-table/': 'MPI Table',
    '/staged-wells/': 'Staged Wells',
    '/well-upload/': 'Well Upload',
    '/view-all-rigs/': 'All Rigs',
    '/view-all-wells/': 'All Wells',
}


class ActivityTrackingMiddleware(MiddlewareMixin):
    """
    Middleware to automatically log page views and significant API calls.
    Attaches client IP to all requests for downstream use.
    """

    def process_request(self, request):
        """Attach timing and IP to request."""
        request._activity_start_time = time.time()
        request._client_ip = self._get_client_ip(request)

    def process_response(self, request, response):
        """Log activity after response is generated."""
        path = request.path

        # Skip static/media files
        if any(path.startswith(sp) for sp in SKIP_PATHS):
            return response

        # Skip if no user or not authenticated
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return response

        # Skip high-frequency low-value API paths
        if any(path.startswith(sp) for sp in SKIP_API_PATHS):
            return response

        try:
            self._log_activity(request, response)
        except Exception as e:
            logger.error(f"Activity tracking error: {e}")

        return response

    def _log_activity(self, request, response):
        """Create activity log entry based on request type."""
        from .models import UserActivity

        path = request.path
        method = request.method
        status_code = response.status_code

        # Calculate response time
        duration_ms = 0
        if hasattr(request, '_activity_start_time'):
            duration_ms = int((time.time() - request._activity_start_time) * 1000)

        # ---- Page Views (GET requests to known template URLs) ----
        if method == 'GET' and status_code == 200:
            # Exact match page views
            page_name = PAGE_VIEW_PATHS.get(path)
            
            # Partial match for dynamic pages like /execution/<uuid>/
            if not page_name:
                if path.startswith('/execution/') and path != '/execution/':
                    page_name = 'Execution Detail'
                elif path.startswith('/schedule/') and path != '/schedule/':
                    page_name = 'Schedule Detail'
                elif path.startswith('/tutorials/') and path != '/tutorials/':
                    page_name = 'Tutorial Detail'
                elif path.startswith('/database-viewer/') and path != '/database-viewer/':
                    page_name = 'Database Table Detail'

            if page_name:
                UserActivity.log(
                    request=request,
                    category='PAGE_VIEW',
                    action=f'Viewed {page_name}',
                    description=f'Accessed {page_name} page',
                    metadata={'page': page_name, 'path': path, 'duration_ms': duration_ms},
                )
                return

        # ---- Significant API Actions (POST/PUT/PATCH/DELETE with success) ----
        if method in ('POST', 'PUT', 'PATCH', 'DELETE') and path.startswith('/api/') and 200 <= status_code < 300:
            action_info = self._classify_api_action(path, method)
            if action_info:
                category, action_desc, target_model = action_info
                UserActivity.log(
                    request=request,
                    category=category,
                    action=action_desc,
                    description=f'{method} {path} → {status_code}',
                    metadata={
                        'method': method,
                        'path': path,
                        'status_code': status_code,
                        'duration_ms': duration_ms,
                    },
                    target_model=target_model,
                )

    def _classify_api_action(self, path, method):
        """
        Classify an API call into a meaningful category and action.
        Returns (category, action_description, target_model) or None.
        """
        # Schedule operations
        if '/api/schedules/' in path:
            if method == 'POST':
                return ('SCHEDULE', 'Created Schedule', 'Schedule')
            elif method == 'DELETE':
                return ('DATA_DELETE', 'Deleted Schedule', 'Schedule')
            elif method in ('PUT', 'PATCH'):
                return ('DATA_UPDATE', 'Updated Schedule', 'Schedule')

        # Well operations
        if '/api/wells/' in path:
            if method == 'POST':
                return ('DATA_CREATE', 'Created Well', 'Well')
            elif method == 'DELETE':
                return ('DATA_DELETE', 'Deleted Well', 'Well')
            elif method in ('PUT', 'PATCH'):
                return ('DATA_UPDATE', 'Updated Well', 'Well')

        # Rig operations
        if '/api/rigs/' in path:
            if method == 'POST':
                return ('DATA_CREATE', 'Created Rig', 'Rig')
            elif method == 'DELETE':
                return ('DATA_DELETE', 'Deleted Rig', 'Rig')
            elif method in ('PUT', 'PATCH'):
                return ('DATA_UPDATE', 'Updated Rig', 'Rig')

        # User management
        if '/api/authorized-users/' in path:
            if 'toggle' in path:
                return ('ADMIN', 'Toggled User Status', 'User')
            elif 'delete' in path:
                return ('ADMIN', 'Deleted User', 'User')
            elif 'update' in path:
                return ('ADMIN', 'Updated User', 'User')
            elif 'bulk-add' in path:
                return ('ADMIN', 'Bulk Added Users', 'User')
            elif 'reactivate' in path:
                return ('ADMIN', 'Reactivated User', 'User')

        # User roles
        if '/api/user-roles/' in path:
            if 'assign' in path:
                return ('ADMIN', 'Assigned User Role', 'UserRole')
            elif 'remove' in path:
                return ('ADMIN', 'Removed User Role', 'UserRole')

        # Company codes
        if '/api/company-codes/' in path:
            if 'create' in path:
                return ('DATA_CREATE', 'Created Company Code', 'CompanyCode')
            elif 'delete' in path:
                return ('DATA_DELETE', 'Deleted Company Code', 'CompanyCode')
            elif 'update' in path:
                return ('DATA_UPDATE', 'Updated Company Code', 'CompanyCode')
            elif 'upload' in path:
                return ('DATA_IMPORT', 'Uploaded Company Codes', 'CompanyCode')

        # MPI
        if '/api/mpi/' in path:
            if 'upload' in path:
                return ('DATA_IMPORT', 'Uploaded MPI Data', 'MPI')

        # Well upload
        if '/api/well-upload' in path or '/well-upload' in path:
            return ('DATA_IMPORT', 'Uploaded Wells', 'Well')

        # Staged wells
        if '/api/staged-wells/' in path:
            if method == 'POST':
                return ('DATA_CREATE', 'Staged Wells Action', 'StagedWell')
            elif method == 'DELETE':
                return ('DATA_DELETE', 'Deleted Staged Wells', 'StagedWell')

        # SEM operations  
        if '/api/sem/' in path:
            if 'activate' in path:
                return ('EXECUTION', 'Activated Execution Schedule', 'ExecutionSchedule')
            elif 'update-actuals' in path:
                return ('EXECUTION', 'Updated Execution Actuals', 'ExecutionWell')
            elif 'lock-well' in path:
                return ('EXECUTION', 'Locked Well', 'ExecutionWell')
            elif 'unlock-well' in path:
                return ('EXECUTION', 'Unlocked Well', 'ExecutionWell')
            elif 'apply-cutoff' in path:
                return ('EXECUTION', 'Applied Cutoff Lock', 'ExecutionSchedule')
            elif 'add-well' in path:
                return ('EXECUTION', 'Added Well to Execution', 'ExecutionWell')
            elif 'remove-well' in path:
                return ('EXECUTION', 'Removed Well from Execution', 'ExecutionWell')
            elif 'defer-well' in path:
                return ('EXECUTION', 'Deferred Well', 'ExecutionWell')
            elif 'add-rig' in path:
                return ('EXECUTION', 'Added Rig to Execution', 'ExecutionRig')
            elif 'remove-rig' in path:
                return ('EXECUTION', 'Removed Rig from Execution', 'ExecutionRig')
            elif 'reoptimize' in path:
                return ('EXECUTION', 'Re-optimized Schedule', 'ExecutionSchedule')
            elif 'update-status' in path:
                return ('EXECUTION', 'Updated Execution Status', 'ExecutionSchedule')
            elif 'update-remarks' in path:
                return ('EXECUTION', 'Updated Well Remarks', 'ExecutionWell')

        # Export operations  
        if '/api/export/' in path:
            if 'excel' in path:
                return ('DATA_EXPORT', 'Exported Schedule (Excel)', 'Schedule')
            else:
                return ('DATA_EXPORT', 'Exported Schedule (CSV)', 'Schedule')

        # Scheduling/optimization
        if '/api/calculate-well-parameters' in path:
            return ('SCHEDULE', 'Calculated Well Parameters', 'Well')

        # ILM Cost
        if '/api/ilm-cost/' in path:
            if 'recalculate' in path:
                return ('SCHEDULE', 'Recalculated ILM Costs', 'ILMCost')

        return None

    @staticmethod
    def _get_client_ip(request):
        """Extract real client IP from request headers."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip.strip()
        return request.META.get('REMOTE_ADDR')

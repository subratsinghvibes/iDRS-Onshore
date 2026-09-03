"""
Graceful Error Handling Middleware

Catches common exceptions (SessionInterrupted, DatabaseError/OperationalError)
and returns user-friendly responses instead of raw Django error pages.

IMPORTANT: This middleware MUST be placed ABOVE SessionMiddleware in the
MIDDLEWARE list so it can catch SessionInterrupted raised by session save.
"""
import logging
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.backends.base import UpdateError
from django.db.utils import OperationalError, DatabaseError
from django.core.exceptions import BadRequest, SuspiciousOperation
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse

logger = logging.getLogger(__name__)


class GracefulErrorMiddleware:
    """
    Middleware to gracefully handle:
    - SessionInterrupted / UpdateError / BadRequest: redirect to login or return 401
    - Database lock / OperationalError: return friendly message or 503
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except (SessionInterrupted, UpdateError):
            logger.warning(f"Session error for {request.path} - redirecting to login")
            return self._handle_session_error(request)
        except (BadRequest, SuspiciousOperation) as e:
            # SessionInterrupted is a subclass of BadRequest
            error_str = str(e).lower()
            if 'session' in error_str or 'deleted before' in error_str:
                logger.warning(f"Session-related BadRequest for {request.path}: {e}")
                return self._handle_session_error(request)
            raise
        except (OperationalError, DatabaseError) as e:
            error_str = str(e).lower()
            if 'locked' in error_str or 'database is locked' in error_str:
                logger.error(f"Database lock error on {request.path}: {e}")
                if self._is_api_request(request):
                    return JsonResponse(
                        {'error': 'The database is temporarily busy. Please wait a moment and try again.'},
                        status=503
                    )
                return HttpResponse(
                    '<html><body style="font-family:sans-serif;text-align:center;padding:50px;">'
                    '<h2>Database Temporarily Busy</h2>'
                    '<p>The server is processing another request. Please wait a moment and try again.</p>'
                    '<p><a href="javascript:location.reload()">Reload Page</a> | '
                    '<a href="/">Go to Dashboard</a></p>'
                    '</body></html>',
                    status=503
                )
            # Re-raise non-lock DB errors
            raise

    def _handle_session_error(self, request):
        """Handle session expiration/interruption gracefully."""
        if self._is_api_request(request):
            return JsonResponse(
                {'error': 'Your session has expired. Please refresh the page and log in again.'},
                status=401
            )
        # Can't use messages framework since we're above SessionMiddleware
        return HttpResponseRedirect('/login/?next=' + request.path)

    @staticmethod
    def _is_api_request(request):
        """Check if the request is an API/AJAX call"""
        if request.path.startswith('/api/'):
            return True
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return True
        if 'application/json' in request.headers.get('Accept', ''):
            return True
        if request.content_type and 'application/json' in request.content_type:
            return True
        return False

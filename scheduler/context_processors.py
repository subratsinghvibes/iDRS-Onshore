"""
Context processors for making settings available in templates
"""
from django.conf import settings


def external_app_settings(request):
    """
    Add external app settings to template context from database
    """
    from scheduler.models import ExternalAppSetting
    
    try:
        setting = ExternalAppSetting.get_setting()
        return {
            'EXTERNAL_APP_URL': setting.url,
            'EXTERNAL_APP_NAME': setting.name,
            'EXTERNAL_APP_SECRET': setting.secret_key,
            'EXTERNAL_APP_ENABLED': setting.enabled,
        }
    except Exception:
        # Fallback to settings.py values
        return {
            'EXTERNAL_APP_URL': getattr(settings, 'EXTERNAL_APP_URL', 'http://127.0.0.1:8000'),
            'EXTERNAL_APP_NAME': getattr(settings, 'EXTERNAL_APP_NAME', 'Submit Bug/Enhancement'),
            'EXTERNAL_APP_SECRET': 'iDRS_secret_key_12345',
            'EXTERNAL_APP_ENABLED': True,
        }

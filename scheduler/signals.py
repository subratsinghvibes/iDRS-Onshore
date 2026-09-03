"""
Signals for automatic video processing on upload and user activity tracking.
"""

import logging
import threading
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from .models import VideoTutorial

logger = logging.getLogger(__name__)


def process_video_async(tutorial_id):
    """Process video in background thread."""
    from .video_processor import process_uploaded_video, get_file_size_mb
    from .models import VideoTutorial
    from django.core.files import File
    import os
    
    try:
        tutorial = VideoTutorial.objects.get(id=tutorial_id)
        tutorial.processing_status = 'processing'
        tutorial.save(update_fields=['processing_status'])
        
        logger.info(f"Starting video processing for tutorial: {tutorial.title}")
        
        # Get original file size
        if tutorial.video_file:
            tutorial.original_size_mb = get_file_size_mb(tutorial.video_file.path)
            tutorial.save(update_fields=['original_size_mb'])
        
        # Process video
        results = process_uploaded_video(tutorial.video_file, tutorial_id)
        
        if results['success']:
            # Check if there's an error message (e.g., FFmpeg not installed)
            if results.get('error'):
                tutorial.processing_status = 'completed'
                tutorial.processing_error = results['error']
                logger.warning(f"Video uploaded but not processed: {results['error']}")
            else:
                tutorial.processing_status = 'completed'
                tutorial.processing_error = ''
            
            # Update tutorial with processed files
            if results.get('optimized') and os.path.exists(results['optimized']):
                with open(results['optimized'], 'rb') as f:
                    tutorial.optimized_video.save(
                        os.path.basename(results['optimized']),
                        File(f),
                        save=False
                    )
                tutorial.optimized_size_mb = get_file_size_mb(results['optimized'])
            
            if results.get('compressed') and os.path.exists(results['compressed']):
                with open(results['compressed'], 'rb') as f:
                    tutorial.compressed_video.save(
                        os.path.basename(results['compressed']),
                        File(f),
                        save=False
                    )
                tutorial.compressed_size_mb = get_file_size_mb(results['compressed'])
            
            tutorial.save()
            
            if results.get('error'):
                logger.warning(f"Video saved but not optimized for tutorial: {tutorial.title}")
                logger.warning(f"Original: {tutorial.original_size_mb}MB (no compression)")
            else:
                logger.info(f"Video processing completed for tutorial: {tutorial.title}")
                logger.info(f"Original: {tutorial.original_size_mb}MB, "
                           f"Optimized: {tutorial.optimized_size_mb}MB, "
                           f"Compressed: {tutorial.compressed_size_mb}MB")
        else:
            tutorial.processing_status = 'failed'
            tutorial.processing_error = 'Processing failed. Check server logs.'
            tutorial.save()
            logger.error(f"Video processing failed for tutorial: {tutorial.title}")
            
    except Exception as e:
        logger.error(f"Error in video processing thread: {e}")
        try:
            tutorial = VideoTutorial.objects.get(id=tutorial_id)
            tutorial.processing_status = 'failed'
            tutorial.processing_error = str(e)
            tutorial.save()
        except:
            pass


@receiver(post_save, sender=VideoTutorial)
def process_video_on_upload(sender, instance, created, raw, **kwargs):
    """
    Automatically process video when uploaded.
    Runs in background thread to avoid blocking the upload.
    Skip when loading fixtures (raw=True) — media files are not present then.
    """
    if raw:
        # Called by loaddata / fixture loading — do not trigger video processing
        return

    if created and instance.video_file:
        # Start processing in background thread
        thread = threading.Thread(
            target=process_video_async,
            args=(instance.id,)
        )
        thread.daemon = True
        thread.start()
        
        logger.info(f"Started background video processing for: {instance.title}")


# =============================================================================
# USER ACTIVITY TRACKING SIGNALS
# =============================================================================

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log successful user login."""
    from .models import UserActivity
    try:
        UserActivity.log(
            request=request,
            user=user,
            category='AUTH',
            action='User Login',
            description=f'{user.username} logged in successfully',
            target_model='User',
            target_id=str(user.id),
            target_name=user.get_full_name() or user.username,
            metadata={
                'login_method': 'LDAP' if not user.has_usable_password() else 'Django',
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
            },
        )
    except Exception as e:
        logger.error(f"Failed to log user login: {e}")


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log user logout."""
    from .models import UserActivity
    try:
        if user:
            UserActivity.log(
                request=request,
                user=user,
                category='AUTH',
                action='User Logout',
                description=f'{user.username} logged out',
                target_model='User',
                target_id=str(user.id),
                target_name=user.get_full_name() or user.username,
            )
    except Exception as e:
        logger.error(f"Failed to log user logout: {e}")


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    """Log failed login attempts."""
    from .models import UserActivity
    try:
        username = credentials.get('username', 'unknown')
        UserActivity.log(
            request=request,
            user=None,
            category='AUTH',
            action='Login Failed',
            description=f'Failed login attempt for username: {username}',
            severity='WARNING',
            metadata={'attempted_username': username},
        )
    except Exception as e:
        logger.error(f"Failed to log login failure: {e}")

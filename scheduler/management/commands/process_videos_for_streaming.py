"""
Management command to process existing videos for streaming optimization.

Usage:
    python manage.py process_videos_for_streaming
    python manage.py process_videos_for_streaming --tutorial-id <uuid>
    python manage.py process_videos_for_streaming --force
"""

from django.core.management.base import BaseCommand, CommandError
from scheduler.models import VideoTutorial
from scheduler.video_processing import (
    process_video_for_streaming,
    is_ffmpeg_available,
    get_video_info,
)
import uuid


class Command(BaseCommand):
    help = 'Process videos for optimal streaming (compression, HLS generation)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tutorial-id',
            type=str,
            help='Process a specific tutorial by UUID',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reprocessing of already processed videos',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually processing',
        )

    def handle(self, *args, **options):
        # Check FFmpeg availability
        if not is_ffmpeg_available():
            self.stderr.write(self.style.ERROR(
                'FFmpeg is not installed or not in PATH.\n'
                'Please install FFmpeg:\n'
                '  macOS: brew install ffmpeg\n'
                '  Windows: winget install ffmpeg\n'
                '  Linux: apt install ffmpeg'
            ))
            return

        self.stdout.write(self.style.SUCCESS('FFmpeg is available'))

        # Get videos to process
        if options['tutorial_id']:
            try:
                tutorial_uuid = uuid.UUID(options['tutorial_id'])
                tutorials = VideoTutorial.objects.filter(id=tutorial_uuid)
                if not tutorials.exists():
                    raise CommandError(f'Tutorial not found: {options["tutorial_id"]}')
            except ValueError:
                raise CommandError(f'Invalid UUID: {options["tutorial_id"]}')
        else:
            if options['force']:
                tutorials = VideoTutorial.objects.filter(is_active=True)
            else:
                tutorials = VideoTutorial.objects.filter(
                    is_active=True,
                    processing_status__in=['pending', 'failed']
                )

        total = tutorials.count()
        
        if total == 0:
            self.stdout.write(self.style.WARNING('No videos to process'))
            return

        self.stdout.write(f'Found {total} video(s) to process')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('\n--- DRY RUN ---\n'))
            for tutorial in tutorials:
                video_info = get_video_info(tutorial.video_file.path) if tutorial.video_file else None
                size_mb = video_info.get('size', 0) / (1024 * 1024) if video_info else 0
                self.stdout.write(
                    f'  - {tutorial.title}\n'
                    f'    Status: {tutorial.processing_status}\n'
                    f'    Size: {size_mb:.2f} MB\n'
                    f'    Duration: {video_info.get("duration_minutes", 0) if video_info else "?"} min\n'
                )
            self.stdout.write(self.style.WARNING('\nNo changes made (dry run)'))
            return

        # Process videos
        success_count = 0
        failed_count = 0

        for i, tutorial in enumerate(tutorials, 1):
            self.stdout.write(f'\n[{i}/{total}] Processing: {tutorial.title}')
            
            try:
                result = process_video_for_streaming(tutorial)
                
                if result['success']:
                    success_count += 1
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Processed successfully'))
                    
                    if result['optimized']:
                        self.stdout.write(f'    - Optimized for streaming')
                    if result['compressed']:
                        self.stdout.write(
                            f'    - Compressed: {result["original_size_mb"]:.2f}MB → '
                            f'{result["compressed_size_mb"]:.2f}MB'
                        )
                    if result['hls_generated']:
                        self.stdout.write(f'    - HLS adaptive streaming generated')
                    if result['thumbnail_generated']:
                        self.stdout.write(f'    - Thumbnail generated')
                else:
                    failed_count += 1
                    self.stdout.write(self.style.ERROR(f'  ✗ Failed: {result.get("error", "Unknown error")}'))
                    
            except Exception as e:
                failed_count += 1
                self.stdout.write(self.style.ERROR(f'  ✗ Error: {str(e)}'))

        # Summary
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(f'Processing complete!')
        self.stdout.write(self.style.SUCCESS(f'  Success: {success_count}'))
        if failed_count > 0:
            self.stdout.write(self.style.ERROR(f'  Failed: {failed_count}'))

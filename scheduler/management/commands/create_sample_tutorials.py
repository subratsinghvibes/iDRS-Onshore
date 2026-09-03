"""
Management command to create sample tutorial placeholders.
This helps admins see the structure before uploading real videos.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from scheduler.models import VideoTutorial


class Command(BaseCommand):
    help = 'Creates sample video tutorial placeholders for testing'

    def handle(self, *args, **options):
        # Get or create an admin user for uploaded_by field
        admin_user = User.objects.filter(is_superuser=True).first()
        
        if not admin_user:
            self.stdout.write(self.style.WARNING(
                'No admin user found. Please create an admin user first.'
            ))
            return

        # Sample tutorials data
        sample_tutorials = [
            {
                'title': 'Getting Started with iDRS',
                'description': 'Learn the basics of navigating the iDRS application and understanding its key features.',
                'category': 'getting_started',
                'duration_minutes': 10,
                'order': 1,
                'video_file': 'tutorials/videos/iDRS_Merged_Video.mov',  # Pre-existing video
                'is_active': True,  # This one has a real video
            },
            {
                'title': 'Creating Your First Schedule',
                'description': 'Step-by-step guide to creating and optimizing your first drilling schedule.',
                'category': 'scheduling',
                'duration_minutes': 15,
                'order': 1,
            },
            {
                'title': 'Managing Wells and Rigs',
                'description': 'How to add, edit, and manage wells and rigs in the data management module.',
                'category': 'data_management',
                'duration_minutes': 12,
                'order': 1,
            },
            {
                'title': 'Understanding the Gantt Chart',
                'description': 'Learn how to read and interact with the interactive Gantt chart visualization.',
                'category': 'scheduling',
                'duration_minutes': 8,
                'order': 2,
            },
            {
                'title': 'Configuring Drilling Norms',
                'description': 'Set up and manage drilling benchmarks, daily drilling rates, and other norms.',
                'category': 'data_management',
                'duration_minutes': 20,
                'order': 2,
            },
            {
                'title': 'Viewing Schedule Reports',
                'description': 'Generate and analyze reports from your completed schedules.',
                'category': 'reports',
                'duration_minutes': 10,
                'order': 1,
            },
            {
                'title': 'User Management and Permissions',
                'description': 'How to manage users, roles, and access permissions in iDRS.',
                'category': 'admin',
                'duration_minutes': 12,
                'order': 1,
            },
        ]

        created_count = 0
        skipped_count = 0

        for tutorial_data in sample_tutorials:
            # Check if tutorial with same title already exists
            if VideoTutorial.objects.filter(title=tutorial_data['title']).exists():
                self.stdout.write(self.style.WARNING(
                    f'Skipped: "{tutorial_data["title"]}" (already exists)'
                ))
                skipped_count += 1
                continue

            # Handle video file if provided
            video_file_path = tutorial_data.pop('video_file', None)
            
            tutorial_data['uploaded_by'] = admin_user
            # Set is_active based on whether video file is provided
            tutorial_data.setdefault('is_active', False)
            
            tutorial = VideoTutorial.objects.create(**tutorial_data)
            
            # If video file path is provided, set it
            if video_file_path:
                from django.core.files.base import ContentFile
                import os
                # For existing files, we need to set the field directly
                tutorial.video_file = video_file_path
                tutorial.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Created tutorial with video: "{tutorial_data["title"]}"'
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f'Created placeholder: "{tutorial_data["title"]}"'
                ))
            created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nSummary: Created {created_count} placeholders, skipped {skipped_count}'
        ))
        
        if created_count > 0:
            self.stdout.write(self.style.WARNING(
                '\nNote: These are placeholders without video files.'
            ))
            self.stdout.write(self.style.WARNING(
                'Please upload actual videos through the admin interface at /admin/'
            ))

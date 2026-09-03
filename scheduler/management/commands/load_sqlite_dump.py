"""
Custom management command to load fixture data while disabling post_save signals
that would cause duplicate UserProfile entries.
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db.models.signals import post_save
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Load fixture data with signals temporarily disabled'

    def add_arguments(self, parser):
        parser.add_argument('fixture', type=str, help='Path to the fixture file')

    def handle(self, *args, **options):
        fixture = options['fixture']
        
        # Import the signal handler
        from scheduler.models import create_user_profile
        
        # Disconnect the post_save signal temporarily
        post_save.disconnect(create_user_profile, sender=User)
        self.stdout.write('Disconnected post_save signal for UserProfile creation')
        
        try:
            # Delete any auto-created UserProfiles from flush/migrate
            from scheduler.models import UserProfile
            auto_created = UserProfile.objects.all().count()
            if auto_created:
                UserProfile.objects.all().delete()
                self.stdout.write(f'Deleted {auto_created} auto-created UserProfile(s)')
            
            call_command('loaddata', fixture, verbosity=2)
            self.stdout.write(self.style.SUCCESS('Data loaded successfully!'))
        finally:
            # Reconnect the signal
            post_save.connect(create_user_profile, sender=User)
            self.stdout.write('Reconnected post_save signal')

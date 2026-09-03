"""
Management command to set user roles (staff/admin)
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Set user role (staff or regular user)'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to modify')
        parser.add_argument('--staff', action='store_true', help='Make user a staff member (can access admin)')
        parser.add_argument('--no-staff', action='store_true', help='Remove staff privileges')
        parser.add_argument('--superuser', action='store_true', help='Make user a superuser (full admin access)')
        parser.add_argument('--no-superuser', action='store_true', help='Remove superuser privileges')

    def handle(self, *args, **options):
        username = options['username']
        
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User "{username}" does not exist'))
            return
        
        changes = []
        
        if options['staff']:
            user.is_staff = True
            changes.append('Added staff privileges')
        
        if options['no_staff']:
            user.is_staff = False
            changes.append('Removed staff privileges')
        
        if options['superuser']:
            user.is_superuser = True
            user.is_staff = True  # Superusers must be staff
            changes.append('Added superuser privileges')
        
        if options['no_superuser']:
            user.is_superuser = False
            changes.append('Removed superuser privileges')
        
        if changes:
            user.save()
            self.stdout.write(self.style.SUCCESS(f'\nUser: {username}'))
            for change in changes:
                self.stdout.write(self.style.SUCCESS(f'  ✓ {change}'))
            
            self.stdout.write(self.style.SUCCESS(f'\nCurrent status:'))
            self.stdout.write(f'  is_staff: {user.is_staff}')
            self.stdout.write(f'  is_superuser: {user.is_superuser}')
            self.stdout.write(f'  is_active: {user.is_active}')
            
            if user.is_staff or user.is_superuser:
                self.stdout.write(self.style.SUCCESS(f'\n{username} can now access ER Diagram and Admin pages'))
            else:
                self.stdout.write(self.style.WARNING(f'\n{username} is a regular user (no access to ER Diagram and Admin)'))
        else:
            self.stdout.write(self.style.WARNING('No changes specified. Use --staff, --no-staff, --superuser, or --no-superuser'))

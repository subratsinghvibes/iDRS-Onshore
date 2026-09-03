"""
Management command to list all users and their roles
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'List all users and their roles'

    def handle(self, *args, **options):
        users = User.objects.all().order_by('username')
        
        if not users:
            self.stdout.write(self.style.WARNING('No users found'))
            return
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('USER ROLES SUMMARY'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))
        
        # Header
        self.stdout.write(f"{'Username':<20} {'Email':<30} {'Staff':<8} {'Admin':<8} {'Active':<8}")
        self.stdout.write('-'*80)
        
        for user in users:
            username = user.username[:19]
            email = user.email[:29] if user.email else '-'
            is_staff = '✓' if user.is_staff else '✗'
            is_superuser = '✓' if user.is_superuser else '✗'
            is_active = '✓' if user.is_active else '✗'
            
            # Color code based on role
            if user.is_superuser:
                style = self.style.SUCCESS
            elif user.is_staff:
                style = self.style.WARNING
            else:
                style = lambda x: x  # No color for regular users
            
            self.stdout.write(style(f"{username:<20} {email:<30} {is_staff:<8} {is_superuser:<8} {is_active:<8}"))
        
        self.stdout.write('\n' + '='*80)
        
        # Legend
        self.stdout.write('\nLegend:')
        self.stdout.write('  Staff = Can access ER Diagram and Admin pages')
        self.stdout.write('  Admin = Full administrative access (superuser)')
        self.stdout.write('  Active = Can log in to the application')
        
        # Statistics
        total = users.count()
        staff_count = users.filter(is_staff=True).count()
        superuser_count = users.filter(is_superuser=True).count()
        regular_count = total - staff_count
        
        self.stdout.write('\nStatistics:')
        self.stdout.write(f'  Total users: {total}')
        self.stdout.write(f'  Superusers: {superuser_count}')
        self.stdout.write(f'  Staff (non-superuser): {staff_count - superuser_count}')
        self.stdout.write(f'  Regular users: {regular_count}')
        
        self.stdout.write('\n' + '='*80 + '\n')
        
        # Instructions
        self.stdout.write(self.style.WARNING('To change user roles, use:'))
        self.stdout.write('  python manage.py set_user_role <username> --staff')
        self.stdout.write('  python manage.py set_user_role <username> --no-staff')
        self.stdout.write('  python manage.py set_user_role <username> --superuser')
        self.stdout.write('  python manage.py set_user_role <username> --no-superuser\n')

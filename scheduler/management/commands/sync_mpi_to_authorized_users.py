"""
Management command to sync MPI users to AuthorizedUser table.
This creates authorized user entries for all personnel in the MPI database.
All users default to 'user' role unless specified otherwise.
"""

from django.core.management.base import BaseCommand
from scheduler.models import MasterPersonnelInfo, AuthorizedUser


class Command(BaseCommand):
    help = 'Sync MPI users to AuthorizedUser table for LDAP authentication'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--role',
            type=str,
            default='user',
            choices=['admin', 'L1', 'user'],
            help='Default role for newly created users (default: user)'
        )
        parser.add_argument(
            '--activate',
            action='store_true',
            help='Activate all users (set is_active=True)'
        )
        parser.add_argument(
            '--deactivate',
            action='store_true',
            help='Deactivate all users (set is_active=False)'
        )
    
    def handle(self, *args, **options):
        default_role = options['role']
        activate = options.get('activate', False)
        deactivate = options.get('deactivate', False)
        
        self.stdout.write(self.style.SUCCESS('Starting MPI to AuthorizedUser sync...'))
        
        # Get all MPI records
        mpi_users = MasterPersonnelInfo.objects.all()
        total = mpi_users.count()
        
        self.stdout.write(f'Found {total} MPI records')
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        for mpi in mpi_users:
            # Skip if CPF is empty
            if not mpi.cpf_no:
                skipped_count += 1
                continue
            
            # Get or create authorized user
            auth_user, created = AuthorizedUser.objects.get_or_create(
                cpf_no=mpi.cpf_no,
                defaults={
                    'name': mpi.name or '',
                    'role': default_role,
                    'is_active': True if activate else (False if deactivate else True),
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✓ Created: {mpi.cpf_no} - {mpi.name}'))
            else:
                # Update name if changed
                if auth_user.name != mpi.name and mpi.name:
                    auth_user.name = mpi.name
                    auth_user.save(update_fields=['name'])
                    updated_count += 1
                    self.stdout.write(self.style.WARNING(f'⟳ Updated: {mpi.cpf_no} - {mpi.name}'))
        
        self.stdout.write(self.style.SUCCESS('\n=== Sync Complete ==='))
        self.stdout.write(f'Total MPI records: {total}')
        self.stdout.write(self.style.SUCCESS(f'Created: {created_count}'))
        self.stdout.write(self.style.WARNING(f'Updated: {updated_count}'))
        self.stdout.write(f'Skipped (no CPF): {skipped_count}')
        self.stdout.write(f'Total AuthorizedUsers: {AuthorizedUser.objects.count()}')

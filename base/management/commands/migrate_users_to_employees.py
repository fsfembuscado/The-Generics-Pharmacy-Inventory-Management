"""
Django management command to migrate existing auth_user accounts to Employee system.

Usage:
    python manage.py migrate_users_to_employees

This command will:
1. Create Employee profiles for all active users without one
2. Assign roles based on is_superuser or Django Groups
3. Create EmployeeDesignation linking employees to roles
4. Preserve all existing authentication functionality

Options:
    --dry-run: Show what would be done without making changes
    --force: Overwrite existing Employee profiles
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group
from django.db import transaction
from base.models import Employee, Role, EmployeeDesignation


class Command(BaseCommand):
    help = 'Migrate existing auth_user accounts to the new Employee/Role system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing Employee profiles',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made\n'))

        # Get or create roles
        try:
            manager_role = Role.objects.get(role_name='Manager')
            staff_role = Role.objects.get(role_name='Staff')
            self.stdout.write(self.style.SUCCESS(f'✓ Found roles: Manager (ID: {manager_role.role_id}), Staff (ID: {staff_role.role_id})'))
        except Role.DoesNotExist:
            raise CommandError('Roles not found! Please ensure Manager and Staff roles exist.')

        # Get all active users
        users = User.objects.filter(is_active=True).order_by('id')
        total_users = users.count()
        
        self.stdout.write(f'\nFound {total_users} active users to process\n')

        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

        for user in users:
            username = user.username
            
            # Check if employee profile exists
            has_profile = hasattr(user, 'employee_profile')
            
            if has_profile and not force:
                skipped_count += 1
                self.stdout.write(f'  ⊘ Skipping {username} - already has Employee profile')
                continue

            # Determine role based on permissions
            is_manager = user.is_superuser or user.groups.filter(name='Manager').exists()
            role = manager_role if is_manager else staff_role
            role_name = role.role_name

            # Prepare employee data
            first_name = user.first_name or username
            last_name = user.last_name or ''
            
            if dry_run:
                action = 'UPDATE' if has_profile else 'CREATE'
                self.stdout.write(
                    f'  [{action}] {username} → Employee ({first_name} {last_name}) with role: {role_name}'
                )
                created_count += 1
                continue

            # Perform actual migration
            try:
                with transaction.atomic():
                    # Create or update employee
                    if has_profile and force:
                        employee = user.employee_profile
                        employee.first_name = first_name
                        employee.last_name = last_name
                        if not employee.hire_date:
                            employee.hire_date = user.date_joined
                        employee.save()
                        updated_count += 1
                        action = self.style.WARNING('UPDATED')
                    else:
                        employee = Employee.objects.create(
                            user=user,
                            first_name=first_name,
                            last_name=last_name,
                            hire_date=user.date_joined
                        )
                        created_count += 1
                        action = self.style.SUCCESS('CREATED')

                    # Create or update designation
                    designation, created = EmployeeDesignation.objects.get_or_create(
                        employee=employee,
                        role=role,
                        defaults={
                            'is_primary': True,
                            'assigned_date': user.date_joined
                        }
                    )

                    self.stdout.write(
                        f'  {action} {username} → {employee.employee_number} '
                        f'({employee.full_name}) with role: {role_name}'
                    )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'  ✗ ERROR migrating {username}: {str(e)}')
                )

        # Summary
        self.stdout.write('\n' + '=' * 60)
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETE - No changes were made'))
            self.stdout.write(f'Would create: {created_count} Employee profiles')
        else:
            self.stdout.write(self.style.SUCCESS('MIGRATION COMPLETE'))
            self.stdout.write(f'Total users processed: {total_users}')
            self.stdout.write(self.style.SUCCESS(f'Created: {created_count}'))
            if updated_count:
                self.stdout.write(self.style.WARNING(f'Updated: {updated_count}'))
            if skipped_count:
                self.stdout.write(f'Skipped: {skipped_count}')
            if error_count:
                self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))

        self.stdout.write('=' * 60 + '\n')

        # Next steps
        if not dry_run and created_count > 0:
            self.stdout.write(self.style.SUCCESS('\n✓ Users successfully migrated to Employee system!'))
            self.stdout.write('\nNext steps:')
            self.stdout.write('1. Verify employees in Django admin: /admin/base/employee/')
            self.stdout.write('2. Check role assignments: /admin/base/employeedesignation/')
            self.stdout.write('3. Test role-based permissions in the application')
            self.stdout.write('4. (Optional) Remove old Django Groups if no longer needed\n')

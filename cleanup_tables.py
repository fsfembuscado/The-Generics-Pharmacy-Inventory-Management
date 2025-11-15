import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'todo_list.settings')
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    print("Checking for existing Role/Employee tables...\n")
    
    # Check if tables exist
    cursor.execute("SHOW TABLES LIKE 'base_role%'")
    role_tables = cursor.fetchall()
    print(f"Role-related tables: {[t[0] for t in role_tables]}")
    
    cursor.execute("SHOW TABLES LIKE 'base_employee%'")
    emp_tables = cursor.fetchall()
    print(f"Employee-related tables: {[t[0] for t in emp_tables]}")
    
    # If base_role exists, show its structure
    if role_tables:
        print("\nbase_role structure:")
        cursor.execute("DESCRIBE base_role")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[0]}: {col[1]}")
    
    # Drop tables
    print("\n Dropping tables...")
    
    try:
        cursor.execute("DROP TABLE IF EXISTS base_employeedesignation")
        print("✓ Dropped base_employeedesignation")
    except Exception as e:
        print(f"✗ Could not drop base_employeedesignation: {e}")
    
    try:
        cursor.execute("DROP TABLE IF EXISTS base_employee")
        print("✓ Dropped base_employee")
    except Exception as e:
        print(f"✗ Could not drop base_employee: {e}")
    
    try:
        cursor.execute("DROP TABLE IF EXISTS base_role")
        print("✓ Dropped base_role")
    except Exception as e:
        print(f"✗ Could not drop base_role: {e}")
    
    print("\n✓ Tables dropped successfully!")
    print("\nNext steps:")
    print("1. python manage.py makemigrations")
    print("2. python manage.py migrate")

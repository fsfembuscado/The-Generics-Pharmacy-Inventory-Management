import MySQLdb

try:
    conn = MySQLdb.connect(
        host='localhost',
        user='root',
        password='ImongMAMA123',
        database='inventorytgp_new'
    )
    cursor = conn.cursor()
    
    # Check suppliers
    cursor.execute("SELECT COUNT(*) FROM base_supplier WHERE is_deleted = 0")
    count = cursor.fetchone()[0]
    print(f"Active Suppliers: {count}")
    
    if count > 0:
        cursor.execute("SELECT id, name, status FROM base_supplier WHERE is_deleted = 0 LIMIT 5")
        print("\nSuppliers:")
        for row in cursor.fetchall():
            print(f"  ID: {row[0]}, Name: {row[1]}, Status: {row[2]}")
    else:
        print("\nNo suppliers found. Need to create suppliers first!")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")

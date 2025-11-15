import MySQLdb

try:
    conn = MySQLdb.connect(
        host='localhost',
        user='root',
        password='ImongMAMA123',
        database='inventorytgp_new'
    )
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SHOW TABLES LIKE 'base_%'")
    tables = cursor.fetchall()
    
    print("=== Related Tables ===")
    for table in tables:
        if 'purchase' in table[0].lower() or 'supplier' in table[0].lower():
            print(f"\n{table[0]}:")
            cursor.execute(f"DESC {table[0]}")
            for row in cursor.fetchall():
                print(f"  {row[0]} - {row[1]}")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")

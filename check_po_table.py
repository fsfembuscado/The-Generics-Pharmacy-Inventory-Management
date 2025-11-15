import MySQLdb

try:
    conn = MySQLdb.connect(
        host='localhost',
        user='root',
        password='ImongMAMA123',
        database='inventorytgp_new'
    )
    cursor = conn.cursor()
    
    # Check if table exists and get structure
    cursor.execute("SHOW CREATE TABLE base_purchaseorder")
    result = cursor.fetchone()
    if result:
        print("=== Current PurchaseOrder Table Structure ===")
        print(result[1])
    
    conn.close()
    print("\n=== Success ===")
except Exception as e:
    print(f"Error: {e}")

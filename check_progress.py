from load_data import db
try:
    with db.get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM stock_1min_qfq")
            count = cur.fetchone()[0]
            print(f"Current rows in stock_1min_qfq: {count}")
            
            cur.execute("SELECT filename, status, skipped_lines, processed_at FROM load_log")
            logs = cur.fetchall()
            print("\nLoad Logs:")
            for log in logs:
                print(log)
except Exception as e:
    print(f"Error checking progress: {e}")

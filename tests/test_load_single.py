import os
import logging
from data_infra import db, loader, config

# Configure logging to see output clearly
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def test_single_file():
    # 1. Initialize DB (Create tables, hypertable, etc.)
    try:
        db.init_db()
    except Exception as e:
        print(f"Failed to initialize DB: {e}")
        return

    # 2. Pick the smallest file for testing
    test_file = os.path.join(config.DATA_DIR, "2000_1min.zip")
    
    if not os.path.exists(test_file):
        print(f"Test file not found: {test_file}")
        return

    print(f"Starting test load for: {test_file}")
    
    # 3. Run the loader for this single file
    loader.process_zip_file(test_file)
    
    # 4. Verify results in DB
    try:
        with db.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check row count
                cur.execute("SELECT count(*) FROM stock_1min_qfq")
                count = cur.fetchone()[0]
                print(f"Verification: Found {count} rows in stock_1min_qfq table.")
                
                # Check load_log
                cur.execute("SELECT filename, status, skipped_lines, error_msg FROM load_log WHERE filename = '2000_1min.zip'")
                log = cur.fetchone()
                print(f"Load Log: {log}")
                
                if log and log[1] in ('SUCCESS', 'WARNING'):
                    print("Test PASSED!")
                else:
                    print("Test FAILED or Status unexpected.")
    except Exception as e:
        print(f"Verification query failed: {e}")

if __name__ == "__main__":
    test_single_file()

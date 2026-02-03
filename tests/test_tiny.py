import zipfile, csv, io, os
from load_data import db, loader, config, utils
from datetime import datetime

def test_tiny_load():
    zip_path = os.path.join(config.DATA_DIR, "2000_1min.zip")
    zip_filename = os.path.basename(zip_path)
    conn = db.get_db_connection()
    
    try:
        # Mocking metadata
        stat = os.stat(zip_path)
        file_size = stat.st_size
        last_modified = datetime.fromtimestamp(stat.st_mtime)
        
        buffer = io.StringIO()
        csv_writer = csv.writer(buffer)
        
        with zipfile.ZipFile(zip_path, 'r') as z:
            # Only pick the FIRST csv file
            csv_file = [f for f in z.namelist() if f.endswith('.csv')][0]
            print(f"Testing with single file inside zip: {csv_file}")
            
            with z.open(csv_file, 'r') as f:
                text_io = io.TextIOWrapper(f, encoding='utf-8-sig')
                reader = csv.reader(text_io)
                next(reader) # skip header
                for row in reader:
                    # Clean/Transform (minimal version of loader.py logic)
                    std_code = utils.transform_code(row[1])
                    clean_row = [row[0], std_code, row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10]]
                    csv_writer.writerow(clean_row)
        
        # Bulk Insert
        db.bulk_insert(conn, buffer)
        conn.commit()
        print("Data committed.")
        
        # Write Log
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO load_log (filename, status, skipped_lines, processed_at, file_size, last_modified)
                VALUES (%s, 'SUCCESS', 0, NOW(), %s, %s)
                ON CONFLICT (filename) DO UPDATE SET status='SUCCESS', processed_at=NOW();
            """, (zip_filename, file_size, last_modified))
        conn.commit()
        print("Log written.")
        
    except Exception as e:
        print(f"Tiny test failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    test_tiny_load()

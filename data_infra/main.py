import os
import argparse
import logging
import glob
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime

from . import config
from . import db
from . import loader

# Configure Logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_FILE)
    ]
)
logger = logging.getLogger(__name__)

def get_processed_files(retry_warnings=False, force=False):
    """
    Retrieve map of filename -> metadata that should be skipped.
    Returns a dict: {filename: {'size': size, 'mtime': mtime}}
    """
    if force:
        return {}

    try:
        with db.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Retrieve all potentially skippable files
                cur.execute("""
                    SELECT filename, status, file_size, last_modified 
                    FROM load_log 
                    WHERE status IN ('SUCCESS', 'WARNING')
                """)
                rows = cur.fetchall()
                
                processed = {}
                for filename, status, size, mtime in rows:
                    if status == 'WARNING' and retry_warnings:
                        continue
                    processed[filename] = {'size': size, 'mtime': mtime}
                return processed
    except Exception as e:
        logger.warning(f"Could not read load_log (first run?): {e}")
        return {}

def main():
    parser = argparse.ArgumentParser(description="Bulk load A-share 1-minute data into TimescaleDB.")
    parser.add_argument("--retry-warnings", action="store_true", help="Retry files that ended with WARNING status.")
    parser.add_argument("--force", action="store_true", help="Force re-process all files, ignoring load_log.")
    args = parser.parse_args()

    # 1. Initialize Database
    try:
        db.init_db()
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}")
        return

    # 2. Scan Data Directory
    logger.info(f"Scanning data directory: {config.DATA_DIR}")
    zip_pattern = os.path.join(config.DATA_DIR, "*_1min.zip")
    all_zip_files = sorted(glob.glob(zip_pattern))
    
    if not all_zip_files:
        logger.error(f"No zip files found in {config.DATA_DIR}")
        return

    # 3. Filter Processed Files (Checkpointing with Strict Validation)
    processed_map = get_processed_files(args.retry_warnings, args.force)
    
    tasks = []
    skipped_count = 0
    
    for zip_path in all_zip_files:
        filename = os.path.basename(zip_path)
        
        if filename in processed_map:
            # Validate Metadata
            try:
                stat = os.stat(zip_path)
                current_size = stat.st_size
                # Compare mtime with tolerance (DB might truncate milliseconds)
                # But simple size check + filename is usually enough. 
                # Let's check size strict, mtime loose or strict?
                # Let's stick to size for now as it's most robust against simple touch.
                # Actually, design doc says check BOTH.
                # Note: DB timestamp might be offset aware or not.
                
                log_data = processed_map[filename]
                
                # Check Metadata Existence (Handle legacy logs with NULL metadata)
                if log_data['size'] is None or log_data['mtime'] is None:
                    logger.info(f"File {filename} has missing metadata in DB. Reprocessing to update log.")
                    tasks.append(zip_path)
                    continue

                # Check Size
                if log_data['size'] is not None and log_data['size'] != current_size:
                    logger.info(f"File {filename} changed size (DB:{log_data['size']}, Disk:{current_size}). Reprocessing.")
                    tasks.append(zip_path)
                    continue
                    
                # Check Mtime (Allow 2 seconds tolerance for DB/File system precision diffs)
                if log_data['mtime'] is not None:
                    db_mtime = log_data['mtime']
                    file_mtime = datetime.fromtimestamp(os.stat(zip_path).st_mtime)
                    
                    # Ensure both are naive or both aware (assuming Naive from loader.py/db)
                    delta = abs((db_mtime - file_mtime).total_seconds())
                    if delta > 2.0:
                        logger.info(f"File {filename} changed mtime (DB:{db_mtime}, Disk:{file_mtime}, Delta:{delta}s). Reprocessing.")
                        tasks.append(zip_path)
                        continue
                
                skipped_count += 1
                continue
                
            except OSError:
                # File access error, maybe reprocess?
                tasks.append(zip_path)
        else:
            tasks.append(zip_path)

    logger.info(f"Total files: {len(all_zip_files)}. To process: {len(tasks)}. Skipped: {skipped_count}")

    if not tasks:
        logger.info("All files processed. Nothing to do.")
        return

    # 4. Start Parallel Processing
    logger.info(f"Starting execution with {config.MAX_WORKERS} workers...")
    
    with ProcessPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        futures = {executor.submit(loader.process_zip_file, zip_path): zip_path for zip_path in tasks}
        
        # Progress Bar
        with tqdm(total=len(tasks), unit="file") as pbar:
            for future in as_completed(futures):
                zip_path = futures[future]
                filename = os.path.basename(zip_path)
                try:
                    future.result() 
                    logger.info(f"Finished: {filename}")
                except Exception as e:
                    logger.error(f"Worker exception for {filename}: {e}")
                finally:
                    pbar.update(1)

    logger.info("All tasks completed.")

if __name__ == "__main__":
    main()
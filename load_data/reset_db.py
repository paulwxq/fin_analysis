import logging
import sys
from pathlib import Path

try:
    from . import db
except ImportError:
    # Support direct execution: python load_data/reset_db.py
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from load_data import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_tables():
    confirm = input("⚠️  DANGER: This will DELETE ALL DATA in 'stock_1min_qfq' and 'load_log'.\nAre you sure? (type 'yes' to proceed): ")
    if confirm != "yes":
        print("Operation cancelled.")
        return

    conn = db.get_db_connection()
    try:
        with conn.cursor() as cur:
            logger.info("Truncating stock_1min_qfq (this may take a moment)...")
            cur.execute("TRUNCATE TABLE stock_1min_qfq;")
            
            logger.info("Clearing load_log...")
            cur.execute("TRUNCATE TABLE load_log;")
            
        conn.commit()
        logger.info("Tables reset successfully. Ready for fresh load.")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Reset failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    reset_tables()

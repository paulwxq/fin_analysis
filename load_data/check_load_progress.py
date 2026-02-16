import sys
from pathlib import Path


try:
    from . import db
except ImportError:
    # Support direct execution: python load_data/check_load_progress.py
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from load_data import db


def main() -> None:
    try:
        with db.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM stock_1min_qfq")
                count = cur.fetchone()[0]
                print(f"Current rows in stock_1min_qfq: {count}")

                cur.execute(
                    "SELECT filename, status, skipped_lines, processed_at "
                    "FROM load_log"
                )
                logs = cur.fetchall()
                print("\nLoad Logs:")
                for log in logs:
                    print(log)
    except Exception as e:
        print(f"Error checking progress: {e}")


if __name__ == "__main__":
    main()

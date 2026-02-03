import psycopg
from psycopg import sql
from contextlib import contextmanager
from typing import Generator
import logging

from . import config

logger = logging.getLogger(__name__)

def get_db_connection():
    """Establish a connection to the database."""
    return psycopg.connect(config.DB_DSN, autocommit=False)

@contextmanager
def get_cursor(conn) -> Generator[psycopg.Cursor, None, None]:
    """Context manager for database cursor."""
    with conn.cursor() as cur:
        yield cur

def init_db():
    """Initialize database tables and TimescaleDB extension."""
    logger.info("Initializing database...")
    
    ddl_statements = [
        # 1. Ensure TimescaleDB extension exists
        "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;",
        
        # 2. Create the main table
        """
        CREATE TABLE IF NOT EXISTS stock_1min_qfq (
            time        TIMESTAMP NOT NULL,
            code        TEXT NOT NULL,
            name        TEXT,
            open        NUMERIC(16, 4),
            high        NUMERIC(16, 4),
            low         NUMERIC(16, 4),
            close       NUMERIC(16, 4),
            volume      BIGINT,
            amount      NUMERIC(20, 4),
            change_pct  NUMERIC(10, 4),
            amplitude   NUMERIC(10, 4),
            UNIQUE (code, time)
        );
        """,
        
        # 3. Convert to Hypertable (TimescaleDB)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM timescaledb_information.hypertables 
                WHERE hypertable_name = 'stock_1min_qfq'
            ) THEN
                PERFORM create_hypertable('stock_1min_qfq', 'time', chunk_time_interval => INTERVAL '7 days');
            END IF;
        END $$;
        """,
        
        # 4. Enable Compression
        """
        ALTER TABLE stock_1min_qfq SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'code',
            timescaledb.compress_orderby = 'time DESC'
        );
        """,
        
        # 5. Create Load Log table for checkpointing
        """
        CREATE TABLE IF NOT EXISTS load_log (
            filename TEXT PRIMARY KEY,
            processed_at TIMESTAMP DEFAULT NOW(),
            status TEXT, -- 'SUCCESS', 'WARNING', 'FAILED'
            skipped_lines INTEGER DEFAULT 0,
            error_msg TEXT,
            file_size BIGINT,
            last_modified TIMESTAMP
        );
        """
    ]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for stmt in ddl_statements:
                try:
                    cur.execute(stmt)
                    conn.commit()
                except psycopg.errors.DuplicateObject:
                    conn.rollback()
                except psycopg.errors.InternalError_ as e: # Specifically for Timescale errors
                     conn.rollback()
                     if "compression is already enabled" in str(e):
                         pass
                     else:
                         raise
                except Exception as e:
                    conn.rollback()
                    if "already" in str(e) or "exists" in str(e):
                        logger.debug(f"Skipping initialization step (already exists): {e}")
                    else:
                        logger.error(f"DB Init failed on statement: {stmt[:50]}...")
                        raise e
    logger.info("Database initialized successfully.")

def bulk_insert(conn, data_io):
    """
    Execute bulk insert using COPY -> Temp Table -> INSERT ON CONFLICT.
    """
    with conn.cursor() as cur:
        # 1. Create Temp Table (Session-scoped)
        cur.execute("""
            CREATE TEMP TABLE tmp_stock_1min_qfq (
                LIKE stock_1min_qfq INCLUDING DEFAULTS
            ) ON COMMIT DROP;
        """)
        
        # 2. COPY data to Temp Table
        with cur.copy(
            """
            COPY tmp_stock_1min_qfq (
                time, code, name, open, close, high, low, volume, amount, change_pct, amplitude
            ) FROM STDIN WITH (FORMAT CSV, HEADER FALSE, NULL '')
            """
        ) as copy:
            copy.write(data_io.getvalue())
            
        # 3. Merge from Temp to Target (Explicit columns)
        cur.execute("""
            INSERT INTO stock_1min_qfq (
                time, code, name, open, close, high, low, volume, amount, change_pct, amplitude
            )
            SELECT 
                time, code, name, open, close, high, low, volume, amount, change_pct, amplitude
            FROM tmp_stock_1min_qfq
            ON CONFLICT (code, time) DO NOTHING;
        """)
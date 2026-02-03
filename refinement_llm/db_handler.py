import psycopg
from typing import List, Dict, Any
from .config import RefinementConfig
from .models import AnalysisResult
from .logger import LoggerConfig

logger = LoggerConfig.setup_logger("db_handler")

class DBHandler:
    def __init__(self, db_url: str):
        """Initialize database connection"""
        self.db_url = db_url

    def _get_connection(self):
        return psycopg.connect(self.db_url)

    def init_table(self):
        """Create the table if it doesn't exist"""
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {RefinementConfig.DB_TABLE} (
            stock_code VARCHAR(20) PRIMARY KEY,
            score NUMERIC(4,2) NOT NULL,
            pattern_name VARCHAR(100),
            reasoning TEXT,
            stage VARCHAR(50),
            ma30_status VARCHAR(50),
            volume_pattern VARCHAR(100),
            image_path VARCHAR(255),
            analysis_timestamp TIMESTAMP DEFAULT NOW(),
            create_time TIMESTAMP DEFAULT NOW(),
            update_time TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_score ON {RefinementConfig.DB_TABLE}(score DESC);
        CREATE INDEX IF NOT EXISTS idx_pattern ON {RefinementConfig.DB_TABLE}(pattern_name);
        """
        try:
            with self._get_connection() as conn:
                conn.execute(create_sql)
                conn.commit()
                logger.info("Database table initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize table: {e}")
            raise

    def truncate_table(self) -> bool:
        """Truncate the table"""
        try:
            with self._get_connection() as conn:
                conn.execute(f"TRUNCATE TABLE {RefinementConfig.DB_TABLE}")
                conn.commit()
                logger.info(f"Table {RefinementConfig.DB_TABLE} truncated.")
            return True
        except Exception as e:
            logger.error(f"Failed to truncate table: {e}")
            return False

    def batch_insert(self, results: List[AnalysisResult]) -> int:
        """Batch insert analysis results"""
        if not results:
            return 0
            
        insert_sql = f"""
        INSERT INTO {RefinementConfig.DB_TABLE} 
        (stock_code, score, pattern_name, reasoning, stage, ma30_status, volume_pattern, image_path, analysis_timestamp)
        VALUES 
        (%(stock_code)s, %(score)s, %(pattern_name)s, %(reasoning)s, %(stage)s, %(ma30_status)s, %(volume_pattern)s, %(image_path)s, %(analysis_timestamp)s)
        ON CONFLICT (stock_code) DO UPDATE SET
            score = EXCLUDED.score,
            pattern_name = EXCLUDED.pattern_name,
            reasoning = EXCLUDED.reasoning,
            stage = EXCLUDED.stage,
            ma30_status = EXCLUDED.ma30_status,
            volume_pattern = EXCLUDED.volume_pattern,
            image_path = EXCLUDED.image_path,
            analysis_timestamp = EXCLUDED.analysis_timestamp,
            update_time = NOW();
        """
        
        valid_results = [r for r in results if r.success]
        data = [
            {
                "stock_code": r.stock_code,
                "score": r.score,
                "pattern_name": r.pattern_name,
                "reasoning": r.reasoning,
                "stage": r.stage,
                "ma30_status": r.ma30_status,
                "volume_pattern": r.volume_pattern,
                "image_path": r.image_path,
                "analysis_timestamp": r.analysis_timestamp
            }
            for r in valid_results
        ]

        if not data:
            return 0

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(insert_sql, data)
                conn.commit()
                logger.info(f"Inserted {len(data)} records.")
            return len(data)
        except Exception as e:
            logger.error(f"Failed to batch insert: {e}")
            return 0

    def get_top_stocks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get top scoring stocks"""
        query = f"""
        SELECT * FROM {RefinementConfig.DB_TABLE}
        ORDER BY score DESC
        LIMIT %(limit)s
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                    cur.execute(query, {"limit": limit})
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Failed to fetch top stocks: {e}")
            return []

import logging
import psycopg
import time
from . import db

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] ManualCompress: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def run_manual_compression():
    logger.info("Starting robust manual compression...")
    
    # 1. 获取待压缩列表
    chunks_to_compress = []
    try:
        with db.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.chunk_schema, c.chunk_name
                    FROM timescaledb_information.chunks c
                    WHERE c.hypertable_name = 'stock_1min_qfq'
                      AND c.is_compressed = FALSE
                      AND c.range_end < NOW() - INTERVAL '7 days'
                    ORDER BY c.range_end DESC;
                """)
                chunks_to_compress = cur.fetchall()
        logger.info(f"Found {len(chunks_to_compress)} chunks needing compression.")
    except Exception as e:
        logger.error(f"Failed to fetch chunk list: {e}")
        return

    # 2. 逐个压缩 (每个都是独立事务)
    success_count = 0
    skip_count = 0
    fail_count = 0

    for i, (schema, name) in enumerate(chunks_to_compress):
        full_name = f"{schema}.{name}"
        progress = f"[{i+1}/{len(chunks_to_compress)}]"
        
        try:
            # 每次循环使用新的连接，确保 autocommit
            with db.get_db_connection() as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    # 设置较长的锁等待时间，减少死锁概率
                    cur.execute("SET lock_timeout = '60s';")
                    
                    logger.info(f"{progress} Compressing {full_name}...")
                    cur.execute(f"SELECT compress_chunk('{full_name}', if_not_compressed => TRUE);")
                    
            logger.info(f"{progress} SUCCESS: {full_name}")
            success_count += 1
            
        except psycopg.errors.DuplicateObject:
            # 对应的就是 "already compressed" 错误
            logger.warning(f"{progress} SKIPPED: {full_name} (Already compressed)")
            skip_count += 1
            
        except psycopg.errors.DeadlockDetected:
            logger.error(f"{progress} DEADLOCK: {full_name} - Retrying in 10s...")
            time.sleep(10)
            # 简单重试逻辑 (可选)
            fail_count += 1
            
        except Exception as e:
            if "already compressed" in str(e):
                 logger.warning(f"{progress} SKIPPED: {full_name} (Captured by text match)")
                 skip_count += 1
            else:
                logger.error(f"{progress} FAILED: {full_name} - {e}")
                fail_count += 1

    logger.info("="*30)
    logger.info(f"Compression Task Finished.")
    logger.info(f"Success: {success_count}")
    logger.info(f"Skipped: {skip_count}")
    logger.info(f"Failed:  {fail_count}")

if __name__ == "__main__":
    run_manual_compression()

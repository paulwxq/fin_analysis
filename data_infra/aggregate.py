import logging
import psycopg
import sys
from . import db

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def run_aggregation(force_backfill=False):
    """
    执行月线聚合视图的创建与历史数据回填。
    基于逻辑幂等设计，可重复运行。
    """
    logger.info("Starting Phase 1: Metadata Definition (DDL)...")
    view_created = False
    
    # Phase 1: 元数据定义 (事务模式)
    try:
        with db.get_db_connection() as conn:
            # Phase 1 不需要特殊的 autocommit，使用标准事务确保 DDL 原子性
            with conn.cursor() as cur:
                # 1. 检查是否存在 (实现逻辑幂等)
                cur.execute("SELECT 1 FROM timescaledb_information.continuous_aggregates WHERE view_name = 'stock_monthly_kline'")
                if cur.fetchone():
                    logger.info("Continuous aggregate view 'stock_monthly_kline' already exists.")
                else:
                    # 2. 创建持续聚合视图
                    logger.info("Creating materialized view 'stock_monthly_kline'...")
                    cur.execute("""
                        CREATE MATERIALIZED VIEW stock_monthly_kline
                        WITH (timescaledb.continuous) AS
                        SELECT
                            time_bucket('1 month', time) AS month,
                            code,
                            last(name, time) as name,  -- 取该月最后一条记录的股票名称 (处理更名)
                            first(open, time) as open,
                            max(high) as high,
                            min(low) as low,
                            last(close, time) as close,
                            sum(volume) as volume,
                            sum(amount) as amount
                        FROM stock_1min_qfq
                        WHERE volume >= 0  -- 隐式过滤 NULL
                          AND amount >= 0

                          -- 以下逻辑不检查价格正负，以支持前复权负价格
                          AND high >= GREATEST(open, close)
                          AND low <= LEAST(open, close)
                        GROUP BY month, code
                        WITH NO DATA;
                    """)
                    logger.info("Materialized View definition created.")
                    view_created = True

                # 3. 创建索引 (幂等操作)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_monthly_code_time ON stock_monthly_kline (code, month DESC);")
                
                # 4. 添加自动刷新策略 (幂等操作)
                cur.execute("""
                    SELECT add_continuous_aggregate_policy('stock_monthly_kline',
                        start_offset => INTERVAL '3 months',
                        end_offset => INTERVAL '1 hour',
                        schedule_interval => INTERVAL '30 minutes',
                        if_not_exists => TRUE);
                """)
                logger.info("Index and Refresh Policy checked/created.")

            # 显式提交事务 (虽然 with 块结束会自动提交，但 DDL 建议明确)
            conn.commit()

    except psycopg.Error as e:
        logger.error(f"Database error during Phase 1 (DDL): {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during Phase 1: {e}")
        raise

    # Phase 2: 历史数据回填 (Autocommit 模式)
    # CALL refresh_continuous_aggregate 必须在事务块之外运行
    if view_created or force_backfill:
        logger.info("Starting Phase 2: Full Historical Backfill (2000-Now)...")
        if force_backfill and not view_created:
            logger.warning("Force backfill requested for an existing view.")
            
        logger.warning("This is a HEAVY long-running task for 7B+ records. DO NOT INTERRUPT.")
        
        try:
            with db.get_db_connection() as conn:
                # 必须开启 autocommit 以支持存储过程中的事务控制
                conn.autocommit = True
                with conn.cursor() as cur:
                    # 设置会话时区以对齐 NOW()
                    cur.execute("SET TIME ZONE 'Asia/Shanghai';")
                    logger.info("Executing CALL refresh_continuous_aggregate...")
                    # 修正：显式转换 NOW() 为 timestamp (without time zone) 以匹配源表类型
                    cur.execute("CALL refresh_continuous_aggregate('stock_monthly_kline', '2000-01-01', NOW()::timestamp);")
            logger.info("Phase 2: History backfill completed successfully.")
        except psycopg.Error as e:
            logger.error(f"Backfill failed: {e}")
            logger.error("Tip: You can resume by running with --force-backfill.")
            raise
    else:
        logger.info("Step 2: Skipping backfill (view already exists and no --force-backfill).")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stock Monthly Aggregation Loader")
    parser.add_argument("--force-backfill", action="store_true", help="Force run full historical backfill")
    args = parser.parse_args()

    try:
        run_aggregation(force_backfill=args.force_backfill)
        logger.info("Aggregation task finished.")
    except KeyboardInterrupt:
        logger.warning("Task interrupted by user.")
        sys.exit(1)
    except Exception:
        logger.error("Task failed.")
        sys.exit(1)

# 月K线生成自动化设计文档 (基于 TimescaleDB 持续聚合)

本文档设计了一个 Python 自动化模块 (`load_data/aggregate.py`)，用于在 1 分钟分时数据加载完成后，自动创建并维护月度 K 线数据 (`stock_monthly_kline`)。

## 1. 设计目标

*   **自动化**: 替代手工 SQL 操作，一键完成视图创建、索引构建和历史数据回填。
*   **高性能**: 利用 TimescaleDB Continuous Aggregates 实现零搬运聚合。
*   **数据清洗**: 在聚合层实施二次过滤（`WHERE` 子句），确保生成的 K 线不受脏数据污染。

## 2. 模块设计

### 2.1 文件位置
`load_data/aggregate.py`

### 2.2 核心逻辑 (`run_aggregation`)

该函数将按顺序执行以下 SQL 操作，具备**逻辑幂等性**（即通过代码判断对象是否存在，确保重复运行不报错）：

#### A. 检查并创建物化视图
首先查询 `timescaledb_information.continuous_aggregates` 视图以确认视图是否已存在。
- **如果不存在**: 执行 `CREATE MATERIALIZED VIEW` 语句。
- **如果已存在**: 打印提示信息并跳过创建步骤。

```sql
-- 检查视图是否存在的 SQL 示例
SELECT 1 FROM timescaledb_information.continuous_aggregates 
WHERE view_name = 'stock_monthly_kline';
```

定义月 K 线聚合逻辑（含内嵌数据清洗规则）：

```sql
CREATE MATERIALIZED VIEW stock_monthly_kline
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 month', time) AS month,
    code,
    last(name, time) as name,  -- 取该月最后一条记录的股票名称 (处理更名情况)
    first(open, time) as open,
    max(high) as high,
    min(low) as low,
    last(close, time) as close,
    sum(volume) as volume,
    sum(amount) as amount
FROM stock_1min_qfq
WHERE volume >= 0  -- volume/amount >= 0 会隐式过滤掉 NULL 记录 (视为无效脏数据)
  AND amount >= 0

  -- 以下逻辑不检查价格正负，以支持前复权可能出现的负价格
  AND high >= GREATEST(open, close)
  AND low <= LEAST(open, close)
GROUP BY month, code
WITH NO DATA;
```

#### B. 创建索引
优化查询性能。

```sql
CREATE INDEX IF NOT EXISTS idx_monthly_code_time ON stock_monthly_kline (code, month DESC);
```

#### C. 添加自动刷新策略
针对未来新入库的数据。

```sql
SELECT add_continuous_aggregate_policy('stock_monthly_kline',
    -- 刷新窗口：重新计算过去 3 个月内发生变化的数据 (适应偶尔的补充修正)
    start_offset => INTERVAL '3 months',
    -- 缓冲时间：最近 1 小时的数据暂不聚合 (避免因乱序/未提交数据导致频繁重算)
    end_offset => INTERVAL '1 hour',
    -- 执行频率：每 30 分钟检查一次是否需要刷新
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE);
```

#### D. 全量回填历史数据 (Mandatory Backfill)
由于历史数据量巨大且无持续写入流，**必须**在 Python 脚本中立即手动触发全量刷新，而不是等待后台策略。

```sql
-- 刷新从 2000 年至今的所有数据
-- 注意：NOW() 返回的时间依赖当前会话时区，需确保设置为 'Asia/Shanghai' 以对齐业务时间
CALL refresh_continuous_aggregate(
    'stock_monthly_kline',
    '2000-01-01',
    NOW()
);
```

## 3. 实施代码框架

### `load_data/aggregate.py`

```python
import logging
import psycopg
# 依赖说明: 
# 1. db.get_db_connection() 需返回一个支持上下文管理器的 psycopg Connection 对象。
# 2. 连接在退出 'with' 块时应自动关闭。
# 3. 初始连接通常处于非 autocommit 状态（即开启事务）。
from . import db

logger = logging.getLogger(__name__)

def run_aggregation(force_backfill=False):
    logger.info("Step 1: Checking/Creating Materialized View...")
    view_created = False
    
    # Phase 1: 元数据定义 (事务模式)
    # 使用独立连接确保 CREATE VIEW/INDEX/POLICY 在同一事务中原子执行
    try:
        with db.get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. 检查是否存在 (实现逻辑幂等)
                cur.execute("SELECT 1 FROM timescaledb_information.continuous_aggregates WHERE view_name = 'stock_monthly_kline'")
                if cur.fetchone():
                    logger.info("View 'stock_monthly_kline' already exists.")
                else:
                    # 2. 创建视图
                    cur.execute("""
                        CREATE MATERIALIZED VIEW stock_monthly_kline
                        WITH (timescaledb.continuous) AS
                        SELECT
                            time_bucket('1 month', time) AS month,
                            code,
                            last(name, time) as name,  -- 取该月最后一条记录的股票名称
                            first(open, time) as open,
                            max(high) as high,
                            min(low) as low,
                            last(close, time) as close,
                            sum(volume) as volume,
                            sum(amount) as amount
                        FROM stock_1min_qfq
                        WHERE volume >= 0  -- volume/amount >= 0 会隐式过滤掉 NULL 记录
                          AND amount >= 0

                          -- 以下逻辑不检查价格正负，以支持前复权可能出现的负价格
                          AND high >= GREATEST(open, close)
                          AND low <= LEAST(open, close)
                        GROUP BY month, code
                        WITH NO DATA;
                    """)
                    logger.info("Materialized View created.")
                    view_created = True

                # 3. 创建索引 (幂等操作)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_monthly_code_time ON stock_monthly_kline (code, month DESC);")
                
                # 4. 添加自动刷新策略 (幂等操作)
                cur.execute("""
                    SELECT add_continuous_aggregate_policy('stock_monthly_kline',
                        -- 重新计算过去 3 个月的数据
                        start_offset => INTERVAL '3 months',
                        -- 忽略最近 1 小时内的数据
                        end_offset => INTERVAL '1 hour',
                        -- 每 30 分钟执行一次检查
                        schedule_interval => INTERVAL '30 minutes',
                        if_not_exists => TRUE);
                """)
                logger.info("Index and Policy checked/created.")

            # 事务自动提交 (conn exit)

    except psycopg.Error as e:
        logger.error(f"Database error during view creation: {e}")
        raise

    # Phase 2: 历史数据回填 (Autocommit 模式)
    # 仅在新建视图或显式要求时执行，独立连接
    if view_created or force_backfill:
        logger.info("Step 2: Starting full historical backfill (2000-Now)...")
        logger.warning("This is a long-running heavy task. Do not interrupt.")
        
        try:
            with db.get_db_connection() as conn:
                conn.autocommit = True  # 必须开启 autocommit
                with conn.cursor() as cur:
                    cur.execute("SET TIME ZONE 'Asia/Shanghai';")
                    cur.execute("CALL refresh_continuous_aggregate('stock_monthly_kline', '2000-01-01', NOW());")
            logger.info("History backfill completed successfully.")
        except psycopg.Error as e:
            logger.error(f"Backfill failed: {e}")
            raise
    else:
        logger.info("Step 2: Skipping backfill (view already exists). Use force_backfill=True to override.")

if __name__ == "__main__":
    # 默认不强制回填
    run_aggregation(force_backfill=False)
```

## 4. 注意事项

*   **事务处理**: `CALL refresh_continuous_aggregate` 命令在 TimescaleDB 中通常需要在事务外执行。在 `psycopg` 中，需确保连接处于 `autocommit = True` 状态。
*   **资源占用**: 回填过程会消耗大量 I/O 和 CPU。建议在数据库参数优化（如 `synchronous_commit = off`）依然开启的情况下执行。
*   **状态确认**: 只有当 Python 脚本打印 "backfill completed successfully" 时，物化视图才可供高效查询。
*   **时区假设**: 
    1.  **数据存储**: 假设 `time` 字段存储的是**北京时间**（业务发生时间）的字面值（`timestamp without time zone`）。`time_bucket` 将直接基于此字面值进行月份切割，不涉及跨时区转换。
    2.  **会话设置**: 本模块强制设置会话时区（`Asia/Shanghai`），仅是为了确保 `NOW()` 函数在生成回填指令和定义调度策略时，能正确对齐到北京时间。
*   **异常恢复**: 如果回填过程中断（如服务器重启、网络波动），只需重新运行带 `--force-backfill` 参数的命令即可重新执行以完成聚合，系统具备逻辑幂等性。
*   **部分失败**: 如果视图创建成功但回填未执行（如程序崩溃），视图会存在但无数据。此时运行带 `--force-backfill` 的命令即可触发补录回填。
*   **视图更新**: 如需修改视图定义（如调整 `WHERE` 条件），必须先手动删除旧视图：`DROP MATERIALIZED VIEW IF EXISTS stock_monthly_kline CASCADE;` 然后重新运行脚本。注意：`CASCADE` 会同时删除依赖的索引和刷新策略。


## 5. 集成计划

在全量数据加载脚本 `load_data/main.py` 中，应增加以下参数解析和调用逻辑，实现“加载+聚合”的自动化流程。

### 5.1 参数定义建议

```python
import argparse
import logging
from . import aggregate

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Stock Data Loader")
    # ... 其他参数 ...
    
    # 新增聚合相关参数
    parser.add_argument("--aggregate", action="store_true", 
                        help="Run monthly aggregation after loading")
    parser.add_argument("--force-backfill", action="store_true",
                        help="Force full historical backfill for aggregation view")
    
    args = parser.parse_args()
    
    # ... 执行数据加载逻辑 (Worker Pool) ...
    
    # 数据加载完成后，执行聚合
    if args.aggregate:
        logger.info("="*50)
        logger.info("Starting Monthly Aggregation...")
        try:
            aggregate.run_aggregation(force_backfill=args.force_backfill)
        except Exception as e:
            logger.error(f"Aggregation failed: {e}")
            exit(1)
```

### 5.2 命令行使用示例

```bash
# 仅加载数据
python -m load_data.main

# 加载数据并在结束后自动创建/检查视图（推荐）
python -m load_data.main --aggregate

# 强制重跑历史数据回填（慎用，仅在逻辑变更或修复数据时使用）
python -m load_data.main --aggregate --force-backfill
```

## 6. 验证与排查

聚合完成后，建议手动执行以下 SQL 检查数据质量。

### 6.1 数据验证

> **注**：以下示例使用 `'600000.SH'` 格式，请根据实际数据库中的 `code` 格式调整。

```sql
-- 1. 确认生成的总数据量 (应为: 股票数量 × 交易月份数，约数十万至数百万行)
SELECT count(*) FROM stock_monthly_kline;

-- 2. 抽查某只股票的月线数据 (按时间倒序)
SELECT * FROM stock_monthly_kline 
WHERE code = '600000.SH' 
ORDER BY month DESC 
LIMIT 5;

-- 3. 验证清洗与聚合逻辑 (异常数据排查)

-- A. 检查是否存在异常大的涨幅 (排除除零风险)
SELECT * FROM stock_monthly_kline 
WHERE open > 0 AND (close - open) / open > 10.0; -- 月度涨幅超过 1000%

-- B. 检查成交量/成交额负值 (预期结果: 0 行)
-- 注：前复权价格允许为负；本查询确认不存在 volume < 0 或 amount < 0 的非法数据
SELECT * FROM stock_monthly_kline
WHERE volume < 0 OR amount < 0; 

-- C. 检查价格逻辑合理性 (预期结果: 0 行)
SELECT * FROM stock_monthly_kline
WHERE high < low 
   OR high < open 
   OR high < close 
   OR low > open 
   OR low > close;

-- D. 检查成交额逻辑 (预期结果: 0 行)
-- 检查是否存在有成交量但无成交额的异常记录
SELECT * FROM stock_monthly_kline
WHERE volume > 0 AND amount = 0;

-- E. 检查元数据完整性 (预期结果: 0 行)
-- 确认 last(name) 是否成功获取到股票名称
SELECT * FROM stock_monthly_kline WHERE name IS NULL;
```

### 6.2 状态检查

```sql
-- 查看持续聚合视图的元数据和刷新状态
SELECT view_name, materialization_hypertable_name, last_refresh 
FROM timescaledb_information.continuous_aggregates
WHERE view_name = 'stock_monthly_kline';
```

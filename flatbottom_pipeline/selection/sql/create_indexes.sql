-- =========================================
-- 性能优化索引（针对 stock_monthly_kline 表）
-- =========================================
-- 用途：加速"平底锅"选股模块的 SQL 查询性能
-- 预期提升：SQL 查询从 ~9秒 降至 ~3-5秒

-- 索引1: 复合索引（code, month）用于窗口函数
-- 说明：窗口函数 PARTITION BY code ORDER BY month 的核心索引
CREATE INDEX IF NOT EXISTS idx_stock_monthly_code_month
ON stock_monthly_kline (code, month DESC);

-- 索引2: 单列索引（month）用于全局时间过滤（如果未来需要）
-- 说明：虽然当前设计移除了全局时间过滤，但保留此索引用于其他查询优化
CREATE INDEX IF NOT EXISTS idx_stock_monthly_month
ON stock_monthly_kline (month DESC);

-- 索引3: 覆盖索引（包含常用列）
-- 说明：包含 SQL 中常用的字段，减少回表查询
-- 注意：此索引较大，仅在查询性能仍不足时创建
-- CREATE INDEX IF NOT EXISTS idx_stock_monthly_covering
-- ON stock_monthly_kline (code, month DESC)
-- INCLUDE (close, high, low, name);

-- =========================================
-- TimescaleDB 超表的特殊说明
-- =========================================
-- 如果 stock_monthly_kline 是 TimescaleDB 超表（Hypertable）：
-- 1. 普通索引会自动应用到所有 chunks（分片）
-- 2. 可以正常创建 B-tree、BRIN、Hash 等索引
-- 3. 索引创建时间较长（因为需要对所有 chunks 创建）
-- 4. 建议在低峰期创建索引

-- 查看索引创建进度：
-- SELECT * FROM pg_stat_progress_create_index;

-- 查看已创建的索引：
-- SELECT schemaname, tablename, indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'stock_monthly_kline';

-- =========================================
-- TimescaleDB 连续聚合（Continuous Aggregate）索引
-- =========================================
-- 连续聚合（即物化视图）**可以创建索引**！
--
-- 示例：如果你有月度聚合的连续聚合视图
-- CREATE MATERIALIZED VIEW stock_monthly_agg
-- WITH (timescaledb.continuous) AS
-- SELECT time_bucket('1 month', time) AS month,
--        code,
--        AVG(close) AS avg_close,
--        ...
-- FROM stock_1min_qfq
-- GROUP BY month, code;
--
-- 可以在连续聚合上创建索引：
-- CREATE INDEX idx_monthly_agg_code_month
-- ON stock_monthly_agg (code, month DESC);
--
-- 注意事项：
-- 1. ✅ 可以在连续聚合上创建任何类型的索引（B-tree, BRIN, Hash等）
-- 2. ✅ 索引会随着连续聚合的刷新自动更新
-- 3. ⚠️  索引创建在物化视图上，不影响源表
-- 4. ⚠️  需要定期刷新物化视图：CALL refresh_continuous_aggregate('stock_monthly_agg', ...)

-- =========================================
-- 索引效果验证
-- =========================================
-- 创建索引后，运行以下查询验证效果：

-- 1. 检查索引是否生效（应该看到 Index Scan 而不是 Seq Scan）
-- EXPLAIN ANALYZE
-- SELECT code, month, close
-- FROM stock_monthly_kline
-- WHERE code = '600000.SH'
-- ORDER BY month DESC
-- LIMIT 120;

-- 2. 检查窗口函数查询的执行计划
-- EXPLAIN ANALYZE
-- SELECT code,
--        MAX(high) OVER (PARTITION BY code ORDER BY month ROWS BETWEEN 119 PRECEDING AND CURRENT ROW)
-- FROM stock_monthly_kline
-- LIMIT 1000;

-- 3. 验证查询时间改善
-- \timing on
-- [运行你的完整筛选 SQL]

-- =========================================
-- 索引维护建议
-- =========================================
-- 1. 定期重建索引（避免索引膨胀）：
--    REINDEX INDEX CONCURRENTLY idx_stock_monthly_code_month;
--
-- 2. 监控索引使用情况：
--    SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read
--    FROM pg_stat_user_indexes
--    WHERE tablename = 'stock_monthly_kline'
--    ORDER BY idx_scan DESC;
--
-- 3. 如果索引未被使用（idx_scan = 0），考虑删除：
--    DROP INDEX IF EXISTS idx_stock_monthly_month;

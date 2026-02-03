-- =========================================
-- "平底锅"形态股票粗筛SQL (v2.3 双轨修正版)
-- =========================================
-- 说明：使用窗口函数计算核心指标，一次性筛选出候选股票
-- 参数：通过 Python 字符串格式化注入（见下文）
--
-- 设计要点：
-- 1. 不使用全局时间过滤，确保窗口函数计算准确
-- 2. 使用 ROW_NUMBER 获取每股最新月份，避免停牌股被误过滤
-- 3. 对 NULL 值使用 COALESCE 设置默认值，避免误过滤
-- 4. 所有阈值可配置（包括 price_position 范围）
-- 5. 窗口长度精确到 N 个月：ROWS BETWEEN 为包含两端，故传入 LOOKBACK-1

WITH
-- CTE 1: 计算窗口统计量
StockMetrics AS (
    SELECT
        code,
        month,
        close,
        high,
        low,
        name,  -- 用于后续ST股票过滤

        -- 历史高点（默认120个月 = 10年）
        MAX(high) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN {history_lookback_minus_1} PRECEDING AND CURRENT ROW
        ) AS history_high,

        -- 历史低点（用于辉煌度计算）
        MIN(low) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN {history_lookback_minus_1} PRECEDING AND CURRENT ROW
        ) AS history_low,

        -- 近期最高价（默认24个月）
        MAX(high) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN {recent_lookback_minus_1} PRECEDING AND CURRENT ROW
        ) AS recent_high,

        -- 近期最低价
        MIN(low) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN {recent_lookback_minus_1} PRECEDING AND CURRENT ROW
        ) AS recent_low,

        -- 近期波动率
        STDDEV(close) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN {recent_lookback_minus_1} PRECEDING AND CURRENT ROW
        ) AS recent_stddev,

        -- 历史波动率（排除近期，避免重叠）
        STDDEV(close) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN {history_lookback_minus_1} PRECEDING AND {recent_lookback} PRECEDING
        ) AS historical_stddev,

        -- 数据完整性
        COUNT(*) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN {history_lookback_minus_1} PRECEDING AND CURRENT ROW
        ) AS data_points

    FROM stock_monthly_kline
    WHERE 1=1
    {code_filter_clause}
    -- 重要：不使用全局时间过滤（WHERE month >= ...）
    -- 原因：确保窗口函数能获取完整历史数据，计算准确
),

-- CTE 2: 计算派生指标
DerivedMetrics AS (
    SELECT
        code,
        name,
        close AS current_price,
        history_high,
        history_low,
        recent_high,
        recent_low,

        -- 辉煌度（双轨指标：正价段倍率，负价段回退振幅）
        CASE
            WHEN history_high > 0 AND history_low > {min_positive_low}
            THEN history_high / history_low
            WHEN history_high IS NOT NULL AND history_low IS NOT NULL
                 AND GREATEST(ABS(history_high), ABS(history_low)) > 0
            THEN (history_high - history_low) / GREATEST(ABS(history_high), ABS(history_low))
            ELSE NULL
        END AS glory_ratio,

        -- 辉煌度类型标记（用于分析/调试）
        CASE
            WHEN history_high > 0 AND history_low > {min_positive_low}
            THEN 'ratio'
            WHEN history_high IS NOT NULL AND history_low IS NOT NULL
            THEN 'amplitude'
            ELSE NULL
        END AS glory_type,

        -- 回撤幅度（使用绝对值归一化，兼容负价）
        CASE
            WHEN history_high IS NOT NULL AND ABS(history_high) > 0
            THEN (close - history_high) / ABS(history_high)
            ELSE NULL
        END AS drawdown_pct,

        -- 箱体振幅（使用绝对值归一化，兼容负价）
        CASE
            WHEN recent_high IS NOT NULL AND recent_low IS NOT NULL
                 AND GREATEST(ABS(recent_high), ABS(recent_low)) > 0
            THEN (recent_high - recent_low) / GREATEST(ABS(recent_high), ABS(recent_low))
            ELSE NULL
        END AS box_range_pct,

        -- 波动率收敛比（使用 COALESCE 处理 NULL）
        CASE
            WHEN historical_stddev > 0 THEN recent_stddev / historical_stddev
            WHEN historical_stddev IS NULL THEN NULL  -- 数据不足，返回NULL
            ELSE 999  -- 历史波动率为0，设置为极大值（会被过滤）
        END AS volatility_ratio,

        -- 价格在箱体中的位置
        CASE
            WHEN (recent_high - recent_low) > 0
            THEN (close - recent_low) / (recent_high - recent_low)
            ELSE 0.5
        END AS price_position,

        data_points,

        -- 行号（用于获取每股最新月份）
        ROW_NUMBER() OVER (PARTITION BY code ORDER BY month DESC) as rn

    FROM StockMetrics
    WHERE data_points >= {min_data_months}  -- 只在这里过滤数据完整性
),

-- CTE 3: 只保留每股最新月份的数据
LatestPerStock AS (
    SELECT
        code,
        name,
        current_price,
        history_high,
        history_low,
        glory_ratio,
        glory_type,
        drawdown_pct,
        box_range_pct,
        volatility_ratio,
        price_position,
        data_points
    FROM DerivedMetrics
    WHERE rn = 1  -- 每股最新月份（解决停牌股被误过滤的问题）
),

-- CTE 4: 应用筛选条件并计算综合得分
ScoredCandidates AS (
    SELECT
        code,
        name,
        current_price,
        history_high,
        glory_ratio,
        glory_type,
        drawdown_pct,
        box_range_pct,
        volatility_ratio,
        price_position,
        data_points,

        -- 综合得分（加权公式）
        (
            -- 回撤越深，得分越高（归一化到0-40分，加入上限避免极端值刷分）
            GREATEST(
                0,
                COALESCE(
                    (LEAST(ABS(drawdown_pct), {max_drawdown_abs}) - {min_drawdown_abs})
                    / NULLIF(({max_drawdown_abs} - {min_drawdown_abs}), 0) * 40,
                    0
                )
            ) +

            -- 箱体越窄，得分越高（归一化到0-30分）
            GREATEST(0, ({max_box_range} - box_range_pct) / {max_box_range} * 30) +

            -- 波动率收敛越明显，得分越高（归一化到0-30分）
            GREATEST(0, ({max_volatility_ratio} - COALESCE(volatility_ratio, 999)) / {max_volatility_ratio} * 30)
        ) AS composite_score

    FROM LatestPerStock
    WHERE
        -- 条件1: 辉煌度（双轨语义：正价倍率 / 负价振幅）
        (
            (glory_type = 'ratio' AND glory_ratio >= {min_glory_ratio})
            OR
            (glory_type = 'amplitude' AND glory_ratio >= {min_glory_amplitude})
        )
        -- 额外约束：确保"曾经辉煌"来自正价区间（可按需调整）
        AND history_high > {min_high_price}

        -- 条件2: 深度回调（跌幅超过阈值，以配置为准）
        AND drawdown_pct < {min_drawdown}

        -- 条件3: 箱体收敛（振幅小于阈值，以配置为准）
        AND box_range_pct < {max_box_range}

        -- 条件4: 波动率收敛（使用 COALESCE 避免 NULL 被过滤）
        AND COALESCE(volatility_ratio, 999) < {max_volatility_ratio}

        -- 条件5: 价格位置合理（可配置范围）
        AND price_position >= {price_position_min}
        AND price_position <= {price_position_max}

        -- 条件6: 排除仙股（价格过低，使用绝对值以兼容负价）
        AND ABS(current_price) >= {min_price}

        -- 条件7: 排除异常值
        AND history_high IS NOT NULL
        AND drawdown_pct IS NOT NULL
        AND box_range_pct IS NOT NULL
)

-- 最终输出：按得分排序
{final_query}

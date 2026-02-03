# “平底锅”形态股票粗筛算法（Python + SQL）设计文档

本文档用于**粗筛**（初筛）“平底锅”形态股票：
- **曾经辉煌**：历史上出现过显著高点；
- **深度回调**：当前价格明显低于历史高点；
- **底部沉淀**：近 1~3 年横盘、波动收敛、未出现大幅拉升。

粗筛目标：**快速剔除明显不符合形态的股票**，输出候选集供后续精筛/可视化/LLM 使用。

参考资料：
- `docs/reference/量化选股工具流程设计.md`
- `docs/reference/量化选股流程设计建议.md`

---

## 1. 数据输入

**来源表：**`stock_monthly_kline`

```
month  | timestamp
code   | text
name   | text
open   | numeric
high   | numeric
low    | numeric
close  | numeric
volume | numeric
amount | numeric
```

---

## 2. 粗筛逻辑（核心指标）

### 2.1 曾经辉煌（历史高点）
- 在 `peak_window_months`（建议 120 个月 = 10 年）内的最高价 `history_high`。

### 2.2 深度回调（回撤幅度）
- `drawdown = (close - history_high) / history_high`
- 或 `drawdown_ratio = 1 - close/history_high`
- 建议阈值：`drawdown <= -0.6 ~ -0.7`

### 2.3 底部沉淀（横盘箱体 + 斜率）
在 `flat_window_months`（建议 24~36 个月）内计算：
- **箱体振幅**：
  `box_range = (recent_high - recent_low) / recent_low`
- **斜率**（可选）：`regr_slope(close, month_index)`
- **过滤破位**：`close >= recent_low * (1 + min_off_low)`

### 2.4 安全过滤（可选）
- **ST过滤**：`name NOT LIKE '%ST%'`
- **流动性过滤**：近 `liq_window_months` 月平均成交额 `avg_amount >= min_avg_amount`
- **上市时间过滤**：月线条数 `>= min_listed_months`

---

## 3. 可配置参数

| 参数 | 含义 | 建议值 |
| --- | --- | --- |
| `peak_window_months` | 历史高点窗口 | 120 |
| `flat_window_months` | 横盘窗口 | 24~36 |
| `min_drawdown` | 最小回撤幅度 | 0.6~0.7 |
| `max_box_range` | 最大箱体振幅 | 0.35~0.50 |
| `min_months_since_peak` | 距高点最小月数 | 24 |
| `min_off_low` | 最近价高于低点比例 | 0.05 |
| `liq_window_months` | 流动性窗口 | 3~6 |
| `min_avg_amount` | 最小月均成交额 | 1e8（可按需） |
| `min_listed_months` | 最小上市月数 | 36 |
| `max_abs_slope` | 斜率绝对值上限 | 0.02 |

---

## 4. SQL 粗筛（核心示例）

> 使用窗口函数在数据库内完成大部分筛选，降低 Python 压力。

```sql
WITH base AS (
    SELECT
        code,
        name,
        month,
        close,
        high,
        low,
        amount,
        -- 历史高点 (过去 N 个月)
        MAX(high) OVER (PARTITION BY code ORDER BY month
                        ROWS BETWEEN :peak_window_months PRECEDING AND CURRENT ROW) AS history_high,
        -- 近 K 个月箱体上下轨
        MAX(high) OVER (PARTITION BY code ORDER BY month
                        ROWS BETWEEN :flat_window_months PRECEDING AND CURRENT ROW) AS recent_high,
        MIN(low) OVER (PARTITION BY code ORDER BY month
                        ROWS BETWEEN :flat_window_months PRECEDING AND CURRENT ROW) AS recent_low,
        -- 近 L 个月成交额均值 (流动性过滤)
        AVG(amount) OVER (PARTITION BY code ORDER BY month
                          ROWS BETWEEN :liq_window_months PRECEDING AND CURRENT ROW) AS avg_amount,
        -- 近 K 个月斜率 (可选)
        REGR_SLOPE(close, EXTRACT(EPOCH FROM month)) OVER (
            PARTITION BY code ORDER BY month
            ROWS BETWEEN :flat_window_months PRECEDING AND CURRENT ROW
        ) AS slope_k
    FROM stock_monthly_kline
    WHERE month >= date_trunc('month', now()) - interval ':peak_window_months months'
),
latest AS (
    SELECT DISTINCT ON (code)
        code, name, month, close, history_high, recent_high, recent_low,
        avg_amount, slope_k
    FROM base
    ORDER BY code, month DESC
),
peak_month AS (
    SELECT DISTINCT ON (code)
        code,
        month AS peak_month,
        high AS peak_high
    FROM stock_monthly_kline
    WHERE month >= date_trunc('month', now()) - interval ':peak_window_months months'
    ORDER BY code, high DESC, month DESC
)
SELECT
    l.code,
    l.name,
    l.close,
    l.history_high,
    (l.close - l.history_high) / NULLIF(l.history_high, 0) AS drawdown,
    (l.recent_high - l.recent_low) / NULLIF(l.recent_low, 0) AS box_range,
    l.slope_k,
    EXTRACT(YEAR FROM age(l.month, p.peak_month))*12
      + EXTRACT(MONTH FROM age(l.month, p.peak_month)) AS months_since_peak
FROM latest l
JOIN peak_month p USING (code)
WHERE
    -- 深度回撤
    (l.close - l.history_high) / NULLIF(l.history_high, 0) <= -:min_drawdown
    -- 横盘箱体
    AND (l.recent_high - l.recent_low) / NULLIF(l.recent_low, 0) <= :max_box_range
    -- 非破位
    AND l.close >= l.recent_low * (1 + :min_off_low)
    -- 距离高点至少 N 个月
    AND (EXTRACT(YEAR FROM age(l.month, p.peak_month))*12
         + EXTRACT(MONTH FROM age(l.month, p.peak_month))) >= :min_months_since_peak
    -- 斜率过滤（可选）
    AND ABS(l.slope_k) <= :max_abs_slope
    -- 流动性过滤（可选）
    AND (l.avg_amount IS NULL OR l.avg_amount >= :min_avg_amount)
    -- ST 过滤（可选）
    AND (l.name IS NULL OR l.name NOT ILIKE '%ST%')
ORDER BY drawdown ASC;
```

> 说明：若不使用斜率或流动性过滤，可在 Python 层或 SQL 层关闭对应条件。

---

## 5. Python 粗筛流程（概要）

### 5.1 步骤
1. 读取参数配置（阈值可调）
2. 执行 SQL 粗筛（返回候选集）
3. 输出结果到 `output/flat_pan_preselection.csv`

### 5.2 伪代码
```python
params = load_config()
rows = run_sql(params)
write_csv(rows, "output/flat_pan_preselection.csv")
```

---

## 6. 输出字段建议

粗筛输出字段建议包含：
- `code, name`
- `close, history_high, drawdown`
- `recent_high, recent_low, box_range`
- `months_since_peak`
- `slope_k`
- `avg_amount`

---

## 7. 关键注意事项

- 这是**粗筛**，用于剔除明显不符合形态的股票，不作为最终选股依据。
- `stock_monthly_kline` 为月线数据，**足够用于初筛**。
- 前复权价格可能为负，避免使用对数收益。
- 参数阈值应根据市场环境调参（如 drawdown 从 60% → 70%）。

---

## 8. 推荐默认阈值（初始配置）

```
peak_window_months = 120
flat_window_months = 36
min_drawdown = 0.65
max_box_range = 0.40
min_months_since_peak = 24
min_off_low = 0.05
liq_window_months = 6
min_avg_amount = 1e8
min_listed_months = 36
max_abs_slope = 0.02
```

---

## 9. 后续精筛方向（非本阶段）

- 进一步引入**波动率收敛**（如 rolling std / ATR）
- 引入成交量结构变化
- 引入行业或基本面过滤
- 对候选集做相似度排序或可视化复核


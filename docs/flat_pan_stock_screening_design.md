# 平底锅形态股票筛选设计文档

本文档描述如何基于 `stock_monthly_kline`（月K线）与模板股票列表（`visualization/stocks.txt` 与/或已有图片）筛选“曾经大涨 → 大幅回撤 → 近 2~3 年横盘起伏不大”的股票形态。方案以 **规则筛选 + 轻量相似度** 为主，不依赖全量图片识别或重型机器学习。

---

## 1. 目标与原则

**目标**：找到与模板股票相似的“平底锅”形态股票，用于进一步人工筛选与长期观察。

**原则**：
- **不生成全量图片**，避免昂贵的视觉处理。
- **不引入重型 ML**，以可解释的特征与轻量相似度为主。
- **先过滤再排序**：先用规则缩小候选，再做相似度排序。

---

## 2. 数据输入

- 月K线表：`stock_monthly_kline`
  - 字段：`month`, `code`, `open`, `high`, `low`, `close`, `volume`, `amount`, `name`
- 模板股票：`visualization/stocks.txt`
  - 代码（不含交易所后缀），需标准化为 `600000.SH/000001.SZ` 格式
- 可选图片：`output/*.png`（仅用于人工确认）

---

## 3. 形态定义（核心约束）

### 3.1 “曾经涨很高”
- 过去 `N_years`（例如 10 年）内最高价 `peak_close` 显著高于当前价。
- **回撤幅度**：
  ```
  drawdown = (peak_close - last_close) / peak_close
  ```
  建议阈值：`drawdown >= 0.40 ~ 0.70`。

### 3.2 “回落已发生一段时间”
- 最高点到现在至少过去 `M_months`（例如 24 个月），避免“刚跌完”。

### 3.3 “近 24~36 月横盘”
在最近 `K` 月（建议 24~36）上计算：
- **价格斜率**：`regr_slope(close, month_index)` 接近 0（上涨幅度不大）
- **区间波动**：`(max(close)/min(close) - 1)` 小于阈值（例如 0.25~0.40）
- **收益波动率**：月收益率标准差低于阈值
- **不创新低**（可选）：当前价高于近 K 月最低价一定比例

---

## 4. 特征设计

### 4.1 全局特征（用于规则筛选）
- `peak_close_10y`：过去 10 年最高收盘
- `last_close`：最新收盘
- `drawdown`：回撤幅度
- `months_since_peak`
- `range_24m`：最近 24 月区间幅度
- `slope_24m`：最近 24 月趋势斜率
- `vol_24m`：最近 24 月收益波动率

### 4.2 形态特征（用于相似度）
- 归一化后的最近 `K` 月 `close` 序列（min-max）
- 特征向量：`[drawdown, months_since_peak, range_24m, slope_24m, vol_24m, ...]`

---

## 5. SQL 设计（概要）

### 5.1 近 K 月特征计算
```sql
-- 以最近 36 个月为例
WITH base AS (
  SELECT *
  FROM stock_monthly_kline
  WHERE month >= (date_trunc('month', now()) - interval '36 months')
), idx AS (
  SELECT
    code,
    month,
    close,
    ROW_NUMBER() OVER (PARTITION BY code ORDER BY month) AS m_idx
  FROM base
)
SELECT
  code,
  max(close) AS max_close_36m,
  min(close) AS min_close_36m,
  (max(close)/NULLIF(min(close),0) - 1) AS range_36m,
  regr_slope(close, m_idx) AS slope_36m
FROM idx
GROUP BY code;
```

### 5.2 10 年最高点 + 回撤 + 最高点时间
```sql
WITH base AS (
  SELECT *
  FROM stock_monthly_kline
  WHERE month >= (date_trunc('month', now()) - interval '10 years')
), peak AS (
  SELECT DISTINCT ON (code)
    code,
    close AS peak_close,
    month AS peak_month
  FROM base
  ORDER BY code, close DESC, month DESC
), last AS (
  SELECT DISTINCT ON (code)
    code,
    close AS last_close,
    month AS last_month
  FROM stock_monthly_kline
  ORDER BY code, month DESC
)
SELECT
  p.code,
  p.peak_close,
  p.peak_month,
  l.last_close,
  l.last_month,
  (p.peak_close - l.last_close)/NULLIF(p.peak_close,0) AS drawdown,
  EXTRACT(YEAR FROM age(l.last_month, p.peak_month))*12
    + EXTRACT(MONTH FROM age(l.last_month, p.peak_month)) AS months_since_peak
FROM peak p
JOIN last l USING (code);
```

### 5.3 规则筛选（示例阈值）
```sql
SELECT *
FROM features
WHERE drawdown >= 0.5
  AND months_since_peak >= 24
  AND range_36m <= 0.35
  AND abs(slope_36m) <= 0.02;
```

> 注：`features` 可用 SQL CTE 合并，或由 Python 拉取后合并。

---

## 6. Python 设计（概要）

### 6.1 主要步骤
1. **读取模板股票**（`visualization/stocks.txt`）并标准化代码格式。
2. **从数据库获取特征**：执行 SQL 计算各股票的特征。
3. **规则筛选**：根据阈值过滤候选集。
4. **相似度排序**：
   - 方式 A：特征向量相似度（欧氏/余弦）
   - 方式 B：归一化 close 序列相似度（DTW 或欧氏距离）
5. **输出候选列表**：CSV/JSON + Top N 图像生成（仅候选）。

### 6.2 Python 模块结构建议
```
load_data/
  aggregate.py
  screen_flat_pan.py        # 新增：筛选入口
  features.py               # 特征提取
  similarity.py             # 相似度计算
  io_utils.py               # 读写
```

### 6.3 关键函数（伪代码）
```python
# 1) 读取模板
codes = load_codes("visualization/stocks.txt")

# 2) 拉取特征
features_df = fetch_features(conn)

# 3) 规则筛选
candidates = rule_filter(features_df)

# 4) 相似度排序
scores = compute_similarity(candidates, template_codes)

# 5) 输出
save_results(scores, "output/flat_pan_candidates.csv")
```

### 6.4 依赖建议
- 必需：`psycopg`
- 轻量：`numpy`（向量计算）
- 可选：`pandas`（若允许）

---

## 7. 参数建议（可配置）

| 参数 | 含义 | 建议值 |
| --- | --- | --- |
| `peak_window_years` | 峰值回溯窗口 | 10 |
| `flat_window_months` | 横盘窗口 | 24~36 |
| `min_drawdown` | 最小回撤幅度 | 0.5 |
| `min_months_since_peak` | 峰值距今月数 | 24 |
| `max_range_flat` | 横盘区间幅度 | 0.35 |
| `max_abs_slope` | 横盘斜率绝对值 | 0.02 |
| `top_n` | 输出前 N | 100 |

---

## 8. 输出结果

- `output/flat_pan_candidates.csv`
  - `code, score, drawdown, range_36m, slope_36m, months_since_peak, ...`
- 可选：对 Top N 生成月K图用于人工确认

---

## 9. 风险与注意事项

- 前复权价格可能为负，**避免 log/收益率的无意义计算**，建议使用线性斜率或做平移。
- `NULL` 数据处理需明确（当前策略默认过滤 `volume/amount IS NULL`）。
- 筛选是形态匹配，不构成投资建议。

---

## 10. LLM/视觉模型的辅助使用建议

本方案**不建议用“LLM 看图打分”作为主筛选**，原因是图像风格干扰大、可解释性弱、成本高。更稳妥的做法是：

1. **规则筛选 → 候选集**：先用数值规则把全市场缩小到 1%~5%。  
2. **数值相似度排序**：用特征向量或归一化序列做相似度排序。  
3. **LLM 作为“解释器/辅助排序”**：把候选股票的特征摘要喂给 LLM，让其输出评分与理由。  
4. **视觉/多模态 LLM 仅用于复核**：对 Top N 生成标准化图像后再复核，而不是全量图像识别。

### 10.1 LLM 推荐输入格式（特征摘要）
```
股票：600000.SH
过去10年最高价：12.5
当前价：6.1
回撤：51%
距高点月数：38
近36月区间振幅：24%
近36月斜率：-0.002
近36月月收益波动率：低
请判断其是否符合“长期下跌后底部横盘”，评分 0-10，并给出理由。
```

### 10.2 视觉模型使用前提（如需）
- **图像必须标准化**：统一时间窗口、统一价格归一化、统一绘制风格。
- **仅对候选集使用**：避免全量图片生成与推理成本。
- 视觉模型结果仅作复核参考，最终仍以数值特征为主。

---

## 11. 推荐的最小落地路径

1. 先做 **规则筛选** → 输出候选列表
2. 在候选上做 **相似度排序**
3. 人工确认 Top N（生成少量图片即可）

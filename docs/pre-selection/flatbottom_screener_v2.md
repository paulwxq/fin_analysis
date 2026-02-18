# "平底锅"形态选股策略设计文档 (v2.3 - Dual-Track Glory)

本文档基于 `flatbottom_pre_screening_algorithm.md` 进行深度优化，旨在构建一个**高性能**的 A 股"平底锅"形态筛选系统。

## 1. 核心优化点

相比 v1 版本，v2 版本主要解决了以下工程痛点：

1. **消除 N+1 查询**: Python 精筛阶段不再逐个查询股价，改为一次性批量拉取，**性能提升 3-5 倍**。
2. **SQL 逻辑解耦**: 将复杂的 SQL 逻辑抽离为独立文件，便于维护和调试。
3. **模块职责清晰**: 本模块专注于数据筛选，输出 CSV 结果；图表生成由 `visualization` 模块独立负责。
4. **风险控制增强**: 可选过滤 ST 股票、黑名单股票，提升选股安全性。

---

## 2. 系统架构

### 2.1 模块结构

```text
/opt/fin_analysis/
├── selection/                    # 股票筛选模块
│   ├── __init__.py
│   ├── config.py                # (新增) 筛选参数配置 + 日志配置
│   ├── logger.py                # (新增) 日志工具模块
│   ├── find_flatbottom.py       # (新增) 主筛选程序
│   └── sql/
│       └── flatbottom_screen.sql # (新增) 核心SQL逻辑
├── visualization/                # 图表可视化模块（独立）
│   ├── __init__.py
│   └── plot_kline.py            # K线绘图模块（仅负责生成图表）
├── logs/                         # (自动创建) 日志文件目录
│   └── selection.log            # 筛选模块日志
├── output/                       # (自动创建) 输出目录
│   └── stock_flatbottom_preselect_*.csv
├── .env                          # 敏感信息（数据库密码等，不提交到git）
└── docs/
    └── pre-selection/
        └── flatbottom_screener_v2.md
```

**配置文件说明**:
- `selection/config.py`: 筛选算法参数（业务逻辑配置，纳入版本控制）
- `.env`: 敏感信息（数据库密码、API密钥等，不上传到GitHub）

**版本控制规则** (`.gitignore`):
```gitignore
# 敏感信息 - 不上传
.env
*.env

# 日志文件 - 不上传
logs/
*.log

# 输出文件 - 不上传
output/

# 业务配置和代码 - 应该上传
selection/config.py
selection/logger.py
selection/find_flatbottom.py
selection/sql/
```

### 2.2 数据库表总览

本模块涉及的数据库表：

| 表名 | 类型 | 用途 | 必需字段 |
|:---|:---|:---|:---|
| `stock_monthly_kline` | **读取** | 月K线数据源 | code, month, open, high, low, close, volume, name |
| `stock_blacklist` | 读取（可选） | 黑名单股票 | code, is_active |
| `stock_flatbottom_preselect` | **写入** | 初筛结果存储（TRUNCATE + INSERT） | 见 2.3 节表结构 |

### 2.3 结果存储表

筛选结果将写入以下数据库表：

**表名**: `stock_flatbottom_preselect`

**表结构** (DDL):

```sql
-- =========================================
-- "平底锅"形态候选股票表（SQL筛选结果）
-- =========================================
CREATE TABLE IF NOT EXISTS stock_flatbottom_preselect (
    -- 股票基本信息
    code VARCHAR(20) PRIMARY KEY,          -- 股票代码（主键）
    name VARCHAR(100),

    -- 筛选指标
    current_price NUMERIC(10, 2),
    history_high NUMERIC(10, 2),
    glory_ratio NUMERIC(10, 2),
    glory_type VARCHAR(20),
    drawdown_pct NUMERIC(10, 2),
    box_range_pct NUMERIC(10, 2),
    volatility_ratio NUMERIC(10, 4),
    price_position NUMERIC(10, 4),

    -- 精筛指标
    slope NUMERIC(10, 6),
    r_squared NUMERIC(10, 4),
    score NUMERIC(10, 2),

    -- 元数据
    screening_preset VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_flatbottom_preselect_score ON stock_flatbottom_preselect(score DESC);
CREATE INDEX IF NOT EXISTS idx_flatbottom_preselect_updated_at ON stock_flatbottom_preselect(updated_at);

-- 添加表注释
COMMENT ON TABLE stock_flatbottom_preselect IS '平底锅形态初筛结果（每个股票只保留最新一条记录）';

-- 添加字段注释
COMMENT ON COLUMN stock_flatbottom_preselect.code IS '股票代码（主键，如 600000.SH, 000001.SZ）';
COMMENT ON COLUMN stock_flatbottom_preselect.name IS '股票名称';
COMMENT ON COLUMN stock_flatbottom_preselect.current_price IS '当前价格（元，筛选使用绝对值判断）';
COMMENT ON COLUMN stock_flatbottom_preselect.history_high IS '历史高点价格（默认120个月内，元）';
COMMENT ON COLUMN stock_flatbottom_preselect.glory_ratio IS '辉煌度：双轨指标（正价段用倍率，高/低；负价段回退为归一化振幅）';
COMMENT ON COLUMN stock_flatbottom_preselect.glory_type IS '辉煌度类型：ratio（倍率语义，正价段）/ amplitude（归一化振幅，负价回退）';
COMMENT ON COLUMN stock_flatbottom_preselect.drawdown_pct IS '回撤幅度（%）：(当前价 - 历史高点) / ABS(历史高点) × 100，负数表示跌幅';
COMMENT ON COLUMN stock_flatbottom_preselect.box_range_pct IS '箱体振幅（%）：近期波动幅度，(近期最高 - 近期最低) / MAX(ABS(近期最高), ABS(近期最低)) × 100';
COMMENT ON COLUMN stock_flatbottom_preselect.volatility_ratio IS '波动率收敛比：近期标准差 / 历史标准差，小于1表示波动收敛';
COMMENT ON COLUMN stock_flatbottom_preselect.price_position IS '价格在箱体中的位置：0-1之间，0表示箱体底部，1表示箱体顶部';
COMMENT ON COLUMN stock_flatbottom_preselect.slope IS '趋势斜率：线性回归计算的价格走势斜率，正数上涨、负数下跌';
COMMENT ON COLUMN stock_flatbottom_preselect.r_squared IS '拟合度 R²：线性回归的拟合优度，0-1之间，越大表示走势越规律';
COMMENT ON COLUMN stock_flatbottom_preselect.score IS '综合得分：加权计算的总分，得分越高表示越符合平底锅形态';
COMMENT ON COLUMN stock_flatbottom_preselect.screening_preset IS '筛选时使用的预设配置（conservative/balanced/aggressive）';
COMMENT ON COLUMN stock_flatbottom_preselect.created_at IS '记录首次创建时间';
COMMENT ON COLUMN stock_flatbottom_preselect.updated_at IS '记录最后更新时间';
```

**设计说明**:

1. **每次运行只保留最新结果**（TRUNCATE + INSERT）
   - 主键：`code`（股票代码）
   - 每次执行前清空整表
   - 表中只保留本次运行结果

2. **数据更新策略**
   - 执行 `TRUNCATE` 清空历史结果
   - 执行 `INSERT` 写入本次筛选结果
   - `created_at` / `updated_at` 为本次执行时间

3. **数据示例**
   ```
   code      | name     | score | screening_preset | created_at          | updated_at
   ----------|----------|-------|------------------|---------------------|---------------------
   600000.SH | 浦发银行  | 87.1  | balanced         | 2026-01-27 09:00:00 | 2026-01-28 09:00:00
   000001.SZ | 平安银行  | 82.5  | balanced         | 2026-01-27 09:00:00 | 2026-01-27 09:00:00
   ```

4. **历史记录保存**
   - 不在数据库保留历史记录
   - 每次筛选自动导出带时间戳的 CSV 文件
   - CSV 文件名格式：`stock_flatbottom_preselect_YYYYMMDD_HHMMSS.csv`
   - 示例：`stock_flatbottom_preselect_20260127_090530.csv`

**使用建议**:

1. **首次使用**: 执行上述 DDL 创建表

2. **日常运行**: 直接运行筛选（TRUNCATE + INSERT）
   ```bash
   python -m selection.find_flatbottom
   ```

3. **查询结果**: 直接查询，无需时间过滤
   ```sql
   -- 查询所有筛选结果（按得分排序）
   SELECT * FROM stock_flatbottom_preselect
   ORDER BY score DESC;

   -- 查询 Top 10
   SELECT code, name, score FROM stock_flatbottom_preselect
   ORDER BY score DESC LIMIT 10;
   ```

4. **历史分析**: 使用导出的 CSV 文件
   - CSV 文件保存在 `output/` 目录
   - 可对比不同日期的 CSV 文件分析趋势

### 2.4 数据流 (Pipeline)

```
阶段1: SQL 粗筛 (数据库层)
  ├─ 输入: stock_monthly_kline 表（全市场 5000+ 只股票）
  ├─ 处理: 窗口函数计算 8 个核心指标
  ├─ 过滤: 多条件筛选 + 综合评分
  └─ 输出: Top 200 候选股 (耗时 < 5秒)
       ↓
阶段2: 批量数据获取 (解决N+1问题)
  ├─ 输入: 200 个股票代码
  ├─ 处理: WHERE code = ANY(...) 批量查询 stock_monthly_kline
  └─ 输出: 200 只股票 × 24 个月价格数据 (耗时 < 1秒)
       ↓
阶段3: Python 精筛 (内存计算)
  ├─ 输入: 批量价格数据
  ├─ 处理:
  │   ├─ ST 股票过滤 (可选，默认关闭)
  │   ├─ 黑名单过滤 (可选，默认关闭，从 stock_blacklist 读取)
  │   ├─ 线性回归趋势分析
  │   └─ R² 拟合度验证
  └─ 输出: 50-100 只精选股 (耗时 < 2秒)
       ↓
阶段4: 结果持久化
  ├─ 写入数据库: stock_flatbottom_preselect 表（TRUNCATE + INSERT，耗时 < 1秒）
  ├─ 自动导出 CSV: output/stock_flatbottom_preselect_YYYYMMDD_HHMMSS.csv
  └─ 日志输出: 筛选统计信息
```

**总耗时**: **< 10 秒** (包含数据库写入和CSV导出，相比 v1 的 15 秒提升 30%)

**注意**:
- 本模块负责筛选和结果存储（数据库 TRUNCATE + INSERT + 自动CSV导出）
- 数据库表采用 TRUNCATE + INSERT，每个股票只保留最新一条记录
- 每次筛选自动导出带时间戳的 CSV 文件用于历史记录
- 如需生成 K 线图，请使用 `visualization` 模块独立处理
- 数据库表 `stock_flatbottom_preselect` 需要提前创建（见 2.3 节 DDL）

---

## 3. SQL 层设计 (粗筛)

### 3.1 核心指标计算

利用 PostgreSQL 窗口函数计算核心指标与关键约束：

| 指标 | 计算方法 | 阈值 | 金融含义 |
|:---|:---|:---|:---|
| **历史高点** | `MAX(high) OVER (120个月)` | - | 曾经辉煌的证据 |
| **辉煌度** | 正价段：`历史高点 / 历史低点`；负价段：`(高-低) / MAX(ABS(高),ABS(低))` | 正价段 ≥ 3.0；负价段 ≥ 0.6（示例，以配置为准） | 曾经辉煌（双轨语义） |
| **回撤幅度** | `(当前价 - 历史高点) / ABS(历史高点)` | < -40% | 深度回调（兼容负价） |
| **箱体振幅** | `(近期最高 - 近期最低) / MAX(ABS(近期最高), ABS(近期最低))` | < 50% | 底部横盘（兼容负价） |
| **波动率比** | `近期标准差 / 历史标准差` | < 0.60 | 情绪冷却 |
| **价格位置** | `(当前价 - 近期最低) / 箱体高度` | 0.05-0.80 | 避免追高/破位 |
| **数据完整性** | `COUNT(*) OVER (...)` | ≥ 60 | 确保历史可追溯 |
| **最低价格** | `ABS(close)` | ≥ 3.0元 | 排除仙股（绝对价格） |
| **正价高点约束** | `history_high > MIN_HIGH_PRICE` | ≥ 2~5元 | 确保“曾经辉煌”来自正价区间 |

### 3.2 SQL 查询逻辑

**文件位置**: `selection/sql/flatbottom_screen.sql`

```sql
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
        -- 额外约束：确保“曾经辉煌”来自正价区间（可按需调整）
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
SELECT
    code,
    name,
    ROUND(current_price::numeric, 2) AS current_price,
    ROUND(history_high::numeric, 2) AS history_high,
    ROUND(glory_ratio::numeric, 2) AS glory_ratio,
    glory_type,
    ROUND(drawdown_pct::numeric * 100, 1) AS drawdown_pct,
    ROUND(box_range_pct::numeric * 100, 1) AS box_range_pct,
    ROUND(volatility_ratio::numeric, 3) AS volatility_ratio,
    ROUND(price_position::numeric, 3) AS price_position,
    ROUND(composite_score::numeric, 1) AS score,
    data_points
FROM ScoredCandidates
ORDER BY composite_score DESC
LIMIT {sql_limit};
```

**重要说明**：

1. **全局时间过滤已移除**
   - 原因：确保窗口函数能获取完整历史数据
   - 影响：全表扫描，但数据量不大（72万行），性能可接受
   - 优化：在 `(code, month)` 上建复合索引

2. **每股最新月份获取**
   - 使用 `ROW_NUMBER() OVER (PARTITION BY code ORDER BY month DESC)`
   - 解决停牌股被误过滤的问题（不再依赖全表最大月份）

3. **NULL 值处理**
   - `volatility_ratio`: 使用 `COALESCE(volatility_ratio, 999)` 避免数据不足时被误过滤
   - `historical_stddev = 0`: 设置为 999（极大值），会被正常过滤

4. **所有阈值可配置**
   - 包括新增的 `price_position_min` 和 `price_position_max`
   - 文档中的具体数值（如 -40%）仅为示例，以配置文件为准

5. **负价兼容处理（前复权场景）**
   - `glory_ratio` 采用双轨语义：正价段倍率，负价段回退为归一化振幅
   - `drawdown_pct`、`box_range_pct` 使用绝对值归一化
   - 价格底线筛选使用 `ABS(current_price)`，避免负价被误剔除

### 3.3 Python 中的 SQL 调用

```python
from pathlib import Path
from selection.config import get_config, validate_config

class FlatbottomScreener:
    def __init__(self, config: dict = None):
        """
        初始化筛选器

        Args:
            config: 配置字典（如果为None，使用默认配置）
        """
        if config is None:
            config = get_config()  # 从 config.py 获取默认配置

        validate_config(config)  # 验证配置合法性
        self.config = config

    def _build_sql_query(self) -> str:
        """构建SQL查询（参数化）"""
        cfg = self.config

        # 读取SQL模板
        sql_template_path = Path(__file__).parent / 'sql' / 'flatbottom_screen.sql'
        with open(sql_template_path, 'r', encoding='utf-8') as f:
            sql_template = f.read()

        # 参数注入
        return sql_template.format(
            history_lookback_minus_1=cfg['HISTORY_LOOKBACK'] - 1,
            recent_lookback_minus_1=cfg['RECENT_LOOKBACK'] - 1,
            recent_lookback=cfg['RECENT_LOOKBACK'],
            min_drawdown=cfg['MIN_DRAWDOWN'],
            min_drawdown_abs=abs(cfg['MIN_DRAWDOWN']),
            max_box_range=cfg['MAX_BOX_RANGE'],
            max_volatility_ratio=cfg['MAX_VOLATILITY_RATIO'],
            min_glory_ratio=cfg['MIN_GLORY_RATIO'],
            min_glory_amplitude=cfg['MIN_GLORY_AMPLITUDE'],
            min_positive_low=cfg['MIN_POSITIVE_LOW'],
            max_drawdown_abs=cfg['MAX_DRAWDOWN_ABS'],  # 新增：回撤绝对值上限（防极端值刷分）
            min_high_price=cfg['MIN_HIGH_PRICE'],  # 新增：历史高点最低值
            min_price=cfg['MIN_PRICE'],
            min_data_months=cfg['MIN_DATA_MONTHS'],
            price_position_min=cfg['PRICE_POSITION_MIN'],  # 新增
            price_position_max=cfg['PRICE_POSITION_MAX'],  # 新增
            sql_limit=cfg['SQL_LIMIT']
        )
```

### 3.4 已知问题和权衡 (Known Issues and Tradeoffs)

本节记录 SQL 设计中的重要决策和权衡，帮助未来开发者理解设计思路。

#### 3.4.1 全局时间过滤的移除

**决策**: 在 v2.3 中移除了全局时间过滤条件 `WHERE month >= NOW() - INTERVAL '{history_lookback} months'`

**问题背景**:
- 原始设计中，全局时间过滤会在窗口函数执行前截断数据
- 导致窗口函数无法获取完整的历史数据进行计算

**示例说明**:
```
假设数据范围: 2010-01 到 2026-01（16年数据）
HISTORY_LOOKBACK = 120 个月（10年）

❌ 使用全局过滤:
  - WHERE month >= NOW() - INTERVAL '120 months'  # 过滤出 2016-01 到 2026-01
  - 窗口函数在 2016-01 计算时，只能看到 2016-01 这一个月的数据
  - history_high 计算不准确（缺少 2006-2015 的数据）

✅ 移除全局过滤:
  - 窗口函数可以访问完整的历史数据
  - 2016-01 计算时能看到完整的 10 年历史（2006-2016）
  - history_high 计算准确
```

**权衡分析**:
- **优点**: 窗口函数计算准确，所有历史数据都能参与计算
- **缺点**: 需要扫描全表数据（约 72 万行）
- **性能影响**: 可接受（实测 ~5 秒，数据量不大）
- **优化建议**: 如性能成为瓶颈，可在 `(code, month)` 上建立复合索引

**结论**: 选择准确性优先，移除全局时间过滤

---

#### 3.4.2 每股最新月份的获取

**决策**: 使用 `ROW_NUMBER() OVER (PARTITION BY code ORDER BY month DESC)` 获取每股最新月份

**问题背景**:
- 原始设计使用 `WHERE month = (SELECT MAX(month) FROM stock_monthly_kline)`
- 假设所有股票的最新月份都相同（等于全表最大月份）
- 但停牌、退市股票的最新月份可能早于全表最大月份，导致被误过滤

**示例说明**:
```
全表最大月份: 2026-01
股票A: 最新月份 2026-01 ✅ 被保留
股票B: 最新月份 2025-06（停牌6个月）❌ 被过滤（应该保留）
股票C: 最新月份 2024-12（退市）❌ 被过滤（应该保留）
```

**解决方案**:
```sql
ROW_NUMBER() OVER (PARTITION BY code ORDER BY month DESC) as rn
...
WHERE rn = 1  -- 每股的最新月份
```

**权衡分析**:
- **优点**: 确保所有股票都能参与筛选（包括停牌股）
- **缺点**: ROW_NUMBER 计算略增加开销
- **替代方案**: PostgreSQL 的 `DISTINCT ON (code)` 性能更好，但兼容性较差
- **性能影响**: 可忽略（~0.1 秒）

**结论**: 选择兼容性和准确性，使用 ROW_NUMBER

---

#### 3.4.3 NULL 值的处理策略

**决策**: 对 `volatility_ratio` 使用 `COALESCE(volatility_ratio, 999)` 处理 NULL 值

**问题背景**:
- `STDDEV()` 窗口函数在数据不足时返回 NULL
- `historical_stddev = NULL` 会导致 `volatility_ratio = NULL`
- SQL 的 `WHERE volatility_ratio < threshold` 会过滤掉 NULL 值
- 导致数据不足的股票被错误地保留或过滤

**解决方案**:
```sql
-- 计算波动率收敛比
CASE
    WHEN historical_stddev > 0 THEN recent_stddev / historical_stddev
    WHEN historical_stddev IS NULL THEN NULL  -- 数据不足
    ELSE 999  -- 历史波动率为0（异常情况）
END AS volatility_ratio

-- 过滤时使用 COALESCE
WHERE COALESCE(volatility_ratio, 999) < {max_volatility_ratio}
```

**权衡分析**:
- **优点**: 明确处理数据不足的情况，避免误判
- **行为**: 数据不足的股票设置为极大值（999），会被正常过滤掉
- **符合预期**: 历史数据不足的股票本来就不应该被筛选出来

**结论**: 使用 COALESCE 设置默认值，确保逻辑一致性

---

#### 3.4.4 配置值的权威性

**问题**: 文档中多处提到具体阈值（如"-40%回撤"、"50%箱体振幅"），但实际值由配置文件决定

**澄清**:
- 文档中的具体数值**仅为示例说明**
- 实际阈值以 `selection/config.py` 中的配置为准
- 不同预设使用不同的值：
  - `conservative`: MIN_DRAWDOWN = -0.50（-50%）, MAX_BOX_RANGE = 0.40（40%）
  - `balanced`: MIN_DRAWDOWN = -0.40（-40%）, MAX_BOX_RANGE = 0.50（50%）
  - `aggressive`: MIN_DRAWDOWN = -0.30（-30%）, MAX_BOX_RANGE = 0.60（60%）

**最佳实践**:
- 阅读文档时，关注算法逻辑而非具体数值
- 运行程序前，使用 `print_config()` 查看实际使用的参数值
- 自定义参数时，通过 CLI 参数或直接修改配置文件

---

#### 3.4.5 价格位置范围的可配置化

**决策**: 将原本硬编码的 `price_position` 范围（0.05-0.80）改为可配置参数

**问题背景**:
- 原始 SQL 中 `price_position BETWEEN 0.05 AND 0.80` 是硬编码的
- 不同风险偏好可能需要不同的范围
- 无法通过配置文件调整

**解决方案**:
- 新增配置参数: `PRICE_POSITION_MIN` 和 `PRICE_POSITION_MAX`
- 不同预设使用不同范围:
  - `conservative`: 0.05 - 0.75（避免追高，更保守）
  - `balanced`: 0.05 - 0.80（标准范围）
  - `aggressive`: 0.05 - 0.85（允许更高位置，更激进）

**权衡分析**:
- **优点**: 提供更大的策略灵活性
- **缺点**: 增加两个配置参数，略增复杂度
- **影响**: 配置表新增两行，SQL 模板新增两个占位符

**结论**: 灵活性的提升值得增加的复杂度

---

#### 3.4.6 性能优化的未来方向

当前设计优先准确性，如未来数据量显著增长（如 > 500 万行），可考虑以下优化：

**方案1: 索引优化**
```sql
CREATE INDEX idx_monthly_kline_code_month ON stock_monthly_kline(code, month DESC);
```

**方案2: 分区表**（TimescaleDB 原生支持）
```sql
-- 按月份分区，只查询最近 N 年的分区
SELECT create_hypertable('stock_monthly_kline', 'month');
```

**方案3: 物化视图**（适合定时批量运行）
```sql
-- 预计算窗口指标，每日刷新
CREATE MATERIALIZED VIEW stock_metrics_mv AS (
    SELECT ... -- 窗口函数计算
);
REFRESH MATERIALIZED VIEW stock_metrics_mv;
```

**当前状态**: 无需优化，性能充足（< 5 秒）

---

#### 3.4.7 辉煌度双轨指标的设计决策

**为什么不使用统一公式**:
- 统一用“归一化振幅”会丢失“涨了几倍”的业务语义
- 统一用“高/低倍率”在负价或接近 0 价格区间失去可解释性

**双轨方案的优点**:
- **语义保真**：正价段保留倍率语义，符合业务直觉
- **兼容异常**：负价段可用振幅回退，不因少数负价样本中断筛选
- **可追溯**：`glory_type` 明确标注指标来源，便于分析与调参

**双轨方案的缺点**:
- 增加 3 个配置参数（倍率阈值、振幅阈值、正价判定阈值）
- 结果分布存在两套量纲，需要监控分布合理性

**未来调整考虑**:
- 若负价样本占比极低，可切换到“正价域限定”简化逻辑
- 若负价样本较多，需单独评估其数据质量与策略有效性
- 可通过统计 `glory_type` 分布判断是否需要收紧/放宽负价段阈值

---

**本节小结**:

所有设计决策都经过仔细权衡，优先考虑：
1. **准确性** > 性能（移除全局过滤）
2. **完整性** > 简洁性（ROW_NUMBER 处理停牌股）
3. **明确性** > 隐式行为（COALESCE 处理 NULL）
4. **灵活性** > 简单性（可配置 price_position）

如有疑问或需要调整，请参考本节说明或联系设计团队。

---

## 4. Python 层设计 (精筛)

### 4.0 数据库连接配置

本模块复用项目现有的数据库连接工具，无需重新实现连接逻辑。

#### 4.0.1 导入数据库连接

```python
from data_infra.db import get_db_connection
```

**函数签名**:
```python
def get_db_connection() -> psycopg.Connection:
    """
    建立到 PostgreSQL/TimescaleDB 的连接

    Returns:
        psycopg.Connection: 数据库连接对象

    Raises:
        psycopg.OperationalError: 连接失败时抛出
    """
```

#### 4.0.2 数据库配置（.env 文件）

数据库连接信息通过项目根目录的 `.env` 文件配置：

```ini
# Database Configuration
DB_HOST=172.29.128.1
DB_PORT=5432
DB_USER=postgres
DB_PASS=PostgreSql-18
DB_NAME=fin_db
```

**配置说明**:
- `DB_HOST`: 数据库服务器地址
- `DB_PORT`: 数据库端口（默认 5432）
- `DB_USER`: 数据库用户名
- `DB_PASS`: 数据库密码
- `DB_NAME`: 数据库名称

**安全注意事项**:
- ⚠️ `.env` 文件包含敏感信息，**禁止提交到 git**
- ✅ 确保 `.gitignore` 中已包含 `.env` 和 `*.env`
- ✅ 生产环境建议使用环境变量而非文件

#### 4.0.3 使用示例

**基本用法**:
```python
from data_infra.db import get_db_connection
import pandas as pd

# 方式1: 手动管理连接
conn = get_db_connection()
try:
    df = pd.read_sql("SELECT * FROM stock_monthly_kline LIMIT 10", conn)
    print(df)
finally:
    conn.close()

# 方式2: 使用上下文管理器（推荐）
with get_db_connection() as conn:
    df = pd.read_sql("""
        SELECT code, month, close
        FROM stock_monthly_kline
        WHERE code = '300444.SZ'
        ORDER BY month DESC
        LIMIT 24
    """, conn)
```

**错误处理**:
```python
from data_infra.db import get_db_connection
import psycopg
from selection.logger import logger

try:
    conn = get_db_connection()
except psycopg.OperationalError as e:
    logger.error(f"数据库连接失败: {e}")
    logger.info("请检查 .env 文件中的数据库配置")
    raise
except Exception as e:
    logger.error(f"未知错误: {e}")
    raise
```

#### 4.0.4 依赖说明

**必需的 Python 包**:
```toml
# pyproject.toml 或 requirements.txt
psycopg = "^3.1.0"      # PostgreSQL 适配器（psycopg3）
pandas = "^2.0.0"       # 数据处理
python-dotenv = "^1.0"  # 环境变量加载
```

**数据库要求**:
- PostgreSQL 14+
- TimescaleDB 2.0+ 扩展（用于时序数据优化）

**安装命令**:
```bash
# 使用 uv（推荐）
uv pip install psycopg pandas python-dotenv

# 或使用 pip
pip install psycopg pandas python-dotenv
```

#### 4.0.5 连接池配置（可选）

如果需要高并发场景，可以考虑使用连接池：

```python
# data_infra/db.py 中可选增强
from psycopg_pool import ConnectionPool

# 创建连接池（示例）
pool = ConnectionPool(
    conninfo=config.DB_DSN,
    min_size=1,
    max_size=10
)

def get_db_connection():
    """从连接池获取连接"""
    return pool.getconn()
```

**注意**: 本项目当前使用简单连接模式，暂不需要连接池。

---

### 4.1 批量数据获取 (关键优化)

**前置说明**: 本节及后续代码示例中的 `get_db_connection()` 函数需从 `data_infra.db` 导入（参见 4.0 节）。

**v1 的 N+1 问题**:
```python
# ❌ 坏味道：200次数据库查询
for code in candidates:
    prices = get_prices(code)  # 每次都建立连接和查询
    slope = calculate_slope(prices)
```

**v2 批量优化**:
```python
def _get_prices_batch(self, codes: list, months: int) -> pd.DataFrame:
    """
    批量获取多只股票的价格数据

    Args:
        codes: 股票代码列表（如 ['600000.SH', '000001.SZ']）
        months: 回溯月数

    Returns:
        DataFrame with columns: code, month, close
    """
    conn = get_db_connection()

    # ✅ 使用 PostgreSQL 的 ANY 语法，一次查询所有股票
    df = pd.read_sql("""
        SELECT code, month, close
        FROM stock_monthly_kline
        WHERE code = ANY(%s)
          AND month >= NOW() - INTERVAL '%s months'
        ORDER BY code, month ASC
    """, conn, params=(codes, months))

    conn.close()

    return df

# 使用示例
codes = candidates['code'].tolist()  # ['600000.SH', '000001.SZ', ...]
prices_df = self._get_prices_batch(codes, months=24)

# 内存中按股票分组计算
for code, group in prices_df.groupby('code'):
    prices = group['close'].values
    slope, r_squared = self._calculate_trend(prices)
    ...
```

**性能对比**:
- v1: 200 次查询 × 50ms = **10 秒**
- v2: 1 次批量查询 = **0.5 秒**
- **提升**: 20 倍 🚀

### 4.2 风险股票过滤（可选）

#### 4.2.1 ST 股票过滤

```python
def _filter_st_stocks(self, candidates: pd.DataFrame) -> pd.DataFrame:
    """
    批量过滤 ST 股票（可选功能）

    Args:
        candidates: SQL粗筛结果（包含name列）

    Returns:
        过滤后的DataFrame

    注意:
        仅当 EXCLUDE_ST=True 时生效
        当前ST股票数据尚未完全准备，建议暂时关闭此功能
    """
    if not self.config.get('EXCLUDE_ST', False):
        logger.info("ST 股票过滤已禁用（EXCLUDE_ST=False）")
        return candidates

    # ST标识列表
    st_markers = ['ST', '*ST', 'S*ST', 'SST', '退市', 'PT', '终止上市']

    def is_st(name: str) -> bool:
        if pd.isna(name):
            return False
        return any(marker in name for marker in st_markers)

    # 向量化过滤
    st_mask = candidates['name'].apply(is_st)
    filtered = candidates[~st_mask].copy()

    st_count = st_mask.sum()
    if st_count > 0:
        logger.info(f"已过滤 {st_count} 只 ST 股票")

    return filtered
```

#### 4.2.2 黑名单过滤

```python
def _filter_blacklist(self, candidates: pd.DataFrame) -> pd.DataFrame:
    """
    批量过滤黑名单股票（可选功能）

    Args:
        candidates: 候选股票 DataFrame

    Returns:
        过滤后的DataFrame

    注意:
        仅当 EXCLUDE_BLACKLIST=True 时生效
        需要数据库中存在 stock_blacklist 表
    """
    if not self.config.get('EXCLUDE_BLACKLIST', False):
        logger.info("黑名单过滤已禁用（EXCLUDE_BLACKLIST=False）")
        return candidates

    conn = get_db_connection()

    try:
        # 从数据库查询黑名单
        blacklist_df = pd.read_sql("""
            SELECT code
            FROM stock_blacklist
            WHERE is_active = TRUE
        """, conn)

        blacklist_codes = set(blacklist_df['code'].tolist())

        if not blacklist_codes:
            logger.info("黑名单表为空，跳过过滤")
            return candidates

        # 过滤黑名单股票
        before_count = len(candidates)
        filtered = candidates[~candidates['code'].isin(blacklist_codes)].copy()
        after_count = len(filtered)

        removed_count = before_count - after_count
        if removed_count > 0:
            logger.info(f"已过滤 {removed_count} 只黑名单股票")

        return filtered

    except Exception as e:
        logger.warning(f"黑名单过滤失败（可能表不存在）: {e}")
        return candidates

    finally:
        conn.close()
```

### 4.3 线性趋势验证

对最近 24 个月的价格进行线性回归分析：

```python
from scipy.stats import linregress

def _calculate_trend(self, prices: np.ndarray) -> tuple:
    """
    计算价格序列的线性趋势

    Args:
        prices: 收盘价数组（按时间升序）

    Returns:
        (slope, r_squared): 斜率和拟合度
    """
    if len(prices) < 12:  # 至少需要12个月
        return (0, 0)

    x = np.arange(len(prices))
    y = prices / prices[0]  # 归一化（相对第一个价格的变化率）

    slope, intercept, r_value, p_value, std_err = linregress(x, y)

    return (slope, r_value ** 2)

def _validate_trend(self, slope: float, r_squared: float) -> bool:
    """
    验证趋势是否符合"平底锅"标准

    Returns:
        True: 符合（微跌到微涨，且拟合度足够）
        False: 不符合
    """
    cfg = self.config

    # 条件1: 斜率在合理范围内
    slope_ok = cfg['SLOPE_MIN'] <= slope <= cfg['SLOPE_MAX']

    # 条件2: 拟合度足够高（不是杂乱无章）
    fit_ok = r_squared >= cfg['MIN_R_SQUARED']

    return slope_ok and fit_ok
```

**趋势判断标准**:
- **斜率 ∈ [-0.01, 0.02]**: 拒绝大跌（下跌中继）或大涨（追高风险）
- **R² > 0.3**: 确保价格走势有规律性，不是随机波动

### 4.4 完整精筛流程

```python
def _python_refine(self, candidates: pd.DataFrame) -> pd.DataFrame:
    """
    Python 层精细筛选（批量处理）

    Args:
        candidates: SQL 粗筛结果（~200只）

    Returns:
        精筛后的 DataFrame（50-100只）
    """
    # 步骤1: 过滤 ST 股票（可选）
    candidates = self._filter_st_stocks(candidates)
    if candidates.empty:
        logger.warning("ST 过滤后无候选股票，筛选终止")
        return pd.DataFrame()

    # 步骤2: 过滤黑名单股票（可选）
    candidates = self._filter_blacklist(candidates)
    if candidates.empty:
        logger.warning("黑名单过滤后无候选股票，筛选终止")
        return pd.DataFrame()

    logger.info(f"风险过滤后剩余 {len(candidates)} 只")

    # 步骤3: 批量获取价格数据
    codes = candidates['code'].tolist()

    try:
        prices_df = self._get_prices_batch(codes, self.config['RECENT_LOOKBACK'])
    except Exception as e:
        logger.error(f"批量获取价格数据失败: {e}")
        return pd.DataFrame()

    # 步骤4: 数据完整性验证
    data_counts = prices_df.groupby('code').size()
    insufficient_codes = data_counts[data_counts < 12].index.tolist()

    if len(insufficient_codes) > 0:
        logger.warning(f"{len(insufficient_codes)} 只股票数据不足12个月，已移除")
        candidates = candidates[~candidates['code'].isin(insufficient_codes)]

    # 步骤5: 逐只分析趋势（内存计算，无需查询数据库）
    results = []

    for _, row in candidates.iterrows():
        code = row['code']

        # 获取该股票的价格序列
        stock_prices = prices_df[prices_df['code'] == code]['close'].values

        if len(stock_prices) < 12:
            continue

        # 计算趋势
        slope, r_squared = self._calculate_trend(stock_prices)

        # 验证趋势
        if not self._validate_trend(slope, r_squared):
            logger.debug(f"{code}: 趋势不符合（slope={slope:.4f}, R²={r_squared:.3f}）")
            continue

        # 通过验证，添加到结果
        results.append({
            **row.to_dict(),
            'slope': round(slope, 4),
            'r_squared': round(r_squared, 3)
        })

    # 转为 DataFrame
    if not results:
        logger.warning("精筛后无符合条件的股票")
        return pd.DataFrame()

    result_df = pd.DataFrame(results)

    # 按综合得分排序
    result_df = result_df.sort_values('score', ascending=False)

    # 限制输出数量
    return result_df.head(self.config['FINAL_LIMIT'])
```

### 4.5 结果写入数据库（TRUNCATE + INSERT）

```python
from datetime import datetime

def _save_to_database(self, results: pd.DataFrame, preset: str) -> int:
    """
    将筛选结果写入数据库（TRUNCATE + INSERT）

    Args:
        results: 筛选结果 DataFrame
        preset: 使用的预设配置名称

    Returns:
        成功写入的记录数
    """
    if results.empty:
        logger.warning("结果为空，跳过数据库写入")
        return 0

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 每次运行先清空结果表
        cursor.execute("TRUNCATE stock_flatbottom_preselect;")

        # TRUNCATE + INSERT SQL
        insert_sql = """
            INSERT INTO stock_flatbottom_preselect (
                code, name, current_price, history_high, glory_ratio, glory_type,
                drawdown_pct, box_range_pct, volatility_ratio, price_position,
                slope, r_squared, score, screening_preset, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                NOW(),
                NOW()
            )
        """

        # 构建数据元组列表
        data_tuples = []
        for _, row in results.iterrows():
            data_tuples.append((
                row.get('code', None),
                row.get('name', None),
                row.get('current_price', None),
                row.get('history_high', None),
                row.get('glory_ratio', None),
                row.get('glory_type', None),
                row.get('drawdown_pct', None),
                row.get('box_range_pct', None),
                row.get('volatility_ratio', None),
                row.get('price_position', None),
                row.get('slope', None),
                row.get('r_squared', None),
                row.get('score', None),
                preset,
            ))

        # 批量INSERT
        cursor.executemany(insert_sql, data_tuples)
        conn.commit()

        inserted_count = len(data_tuples)
        logger.info(f"✓ 成功写入 {inserted_count} 条记录到数据库")

        return inserted_count

    except Exception as e:
        conn.rollback()
        logger.error(f"数据库写入失败: {e}")
        raise

    finally:
        cursor.close()
        conn.close()


def _export_to_csv(self, results: pd.DataFrame) -> str:
    """
    自动导出结果到带时间戳的 CSV 文件

    Args:
        results: 筛选结果 DataFrame

    Returns:
        CSV 文件路径（成功时），None（失败时）
    """
    if results.empty:
        logger.warning("结果为空，跳过 CSV 导出")
        return None

    try:
        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"stock_flatbottom_preselect_{timestamp}.csv"
        output_dir = 'output'
        output_path = os.path.join(output_dir, filename)

        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        # 导出 CSV
        results.to_csv(output_path, index=False, encoding='utf-8-sig')
        logger.info(f"✓ CSV 文件已保存: {output_path}")

        return output_path

    except Exception as e:
        logger.error(f"CSV 导出失败: {e}")
        return None
```

### 4.6 主流程整合

```python
from selection.logger import logger
import time

def run(self, preset: str = 'balanced') -> pd.DataFrame:
    """
    执行完整筛选流程

    Args:
        preset: 使用的预设配置名称

    Returns:
        筛选结果 DataFrame
    """
    logger.info(f"开始执行筛选 (预设配置: {preset})")
    start_time = time.time()

    try:
        # 阶段1: SQL 粗筛
        logger.debug("阶段1: 执行 SQL 粗筛")
        sql_candidates = self._sql_screen()
        logger.info(f"SQL 粗筛完成: {len(sql_candidates)} 只候选股")

        if sql_candidates.empty:
            logger.warning("SQL 粗筛无结果，流程终止")
            return pd.DataFrame()

        # 阶段2: Python 精筛
        logger.debug("阶段2: 执行 Python 精筛")
        final_results = self._python_refine(sql_candidates)
        logger.info(f"Python 精筛完成: {len(final_results)} 只最终候选股")

        if final_results.empty:
            logger.warning("精筛无结果，流程终止")
            return pd.DataFrame()

        # 阶段3: 写入数据库（TRUNCATE + INSERT）
        logger.debug("阶段3: 写入数据库")
        self._save_to_database(final_results, preset)

        # 阶段4: 自动导出带时间戳的 CSV
        logger.debug("阶段4: 导出 CSV 文件")
        csv_path = self._export_to_csv(final_results)

        # 统计信息
        elapsed_time = time.time() - start_time
        logger.info(f"\n{'='*60}")
        logger.info(f"筛选完成！总耗时: {elapsed_time:.2f} 秒")
        logger.info(f"最终入选股票数量: {len(final_results)}")
        if csv_path:
            logger.info(f"CSV 文件: {csv_path}")
        logger.info(f"{'='*60}\n")

        return final_results

    except Exception as e:
        logger.error(f"筛选过程出错: {e}", exc_info=True)
        raise
```

---

## 5. 参数配置系统

### 5.1 配置文件设计 (config.py)

**文件位置**: `selection/config.py`

```python
"""
"平底锅"形态选股策略参数配置
所有筛选算法的参数统一在此配置，纳入版本控制
"""

# =============================================================================
# 日志配置
# =============================================================================

# 日志文件配置
LOG_DIR = 'logs'                          # 日志目录（项目根目录下）
LOG_FILE = 'selection.log'               # 日志文件名
LOG_MAX_BYTES = 10 * 1024 * 1024          # 单个日志文件最大 10MB
LOG_BACKUP_COUNT = 5                      # 保留最近 5 个日志文件

# 日志级别配置
CONSOLE_LOG_LEVEL = 'INFO'                # 控制台日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL
FILE_LOG_LEVEL = 'DEBUG'                  # 文件日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL

# 日志格式
LOG_FORMAT_CONSOLE = '%(levelname)-8s | %(message)s'
LOG_FORMAT_FILE = '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


# =============================================================================
# 预设配置
# =============================================================================

PRESETS = {
    'conservative': {
        # ===== SQL 层参数 =====
        'HISTORY_LOOKBACK': 120,      # 历史回溯月数
        'RECENT_LOOKBACK': 36,        # 近期窗口月数
        'MIN_DRAWDOWN': -0.50,        # 最小回撤幅度（负数，如-0.50表示-50%）
        'MAX_DRAWDOWN_ABS': 0.90,     # 回撤绝对值上限（防极端值刷分）
        'MAX_BOX_RANGE': 0.40,        # 最大箱体振幅（如0.40表示40%）
        'MAX_VOLATILITY_RATIO': 0.50, # 最大波动率比
        'MIN_GLORY_RATIO': 3.5,       # 最小辉煌度（正价段倍率：历史高点/历史低点）
        'MIN_GLORY_AMPLITUDE': 0.70,  # 最小辉煌度（负价段回退：归一化振幅）
        'MIN_POSITIVE_LOW': 0.01,     # 正价判定阈值（历史低点 > 该值才用倍率）
        'MIN_HIGH_PRICE': 5.0,        # 历史高点最低值（确保“曾经辉煌”来自正价区间）
        'MIN_PRICE': 5.0,             # 最低绝对股价（元）
        'MIN_DATA_MONTHS': 120,       # 最少数据月数
        'PRICE_POSITION_MIN': 0.05,   # 价格箱体位置下限（避免破位下跌）
        'PRICE_POSITION_MAX': 0.75,   # 价格箱体位置上限（避免追高）
        'SQL_LIMIT': 150,             # SQL返回上限

        # ===== Python 层参数 =====
        'SLOPE_MIN': -0.005,          # 趋势斜率下限
        'SLOPE_MAX': 0.015,           # 趋势斜率上限
        'MIN_R_SQUARED': 0.40,        # 最小拟合度R²
        'EXCLUDE_ST': True,           # 是否排除ST股
        'EXCLUDE_BLACKLIST': True,    # 是否排除黑名单股票
        'FINAL_LIMIT': 50,            # 最终输出数量
    },

    'balanced': {
        # ===== SQL 层参数 =====
        'HISTORY_LOOKBACK': 120,
        'RECENT_LOOKBACK': 24,
        'MIN_DRAWDOWN': -0.40,        # -40% 回撤（以配置为准）
        'MAX_DRAWDOWN_ABS': 0.90,     # 回撤绝对值上限（防极端值刷分）
        'MAX_BOX_RANGE': 0.50,        # 50% 箱体振幅（以配置为准）
        'MAX_VOLATILITY_RATIO': 0.60,
        'MIN_GLORY_RATIO': 3.0,
        'MIN_GLORY_AMPLITUDE': 0.60,
        'MIN_POSITIVE_LOW': 0.01,
        'MIN_HIGH_PRICE': 3.0,
        'MIN_PRICE': 3.0,             # 最低绝对股价（元）
        'MIN_DATA_MONTHS': 60,
        'PRICE_POSITION_MIN': 0.05,   # 箱体位置 5%-80%
        'PRICE_POSITION_MAX': 0.80,
        'SQL_LIMIT': 200,

        # ===== Python 层参数 =====
        'SLOPE_MIN': -0.01,
        'SLOPE_MAX': 0.02,
        'MIN_R_SQUARED': 0.30,
        'EXCLUDE_ST': False,          # 默认关闭（ST数据未就绪）
        'EXCLUDE_BLACKLIST': False,   # 默认关闭
        'FINAL_LIMIT': 100,
    },

    'aggressive': {
        # ===== SQL 层参数 =====
        'HISTORY_LOOKBACK': 60,
        'RECENT_LOOKBACK': 12,
        'MIN_DRAWDOWN': -0.30,        # -30% 回撤（以配置为准）
        'MAX_DRAWDOWN_ABS': 0.90,     # 回撤绝对值上限（防极端值刷分）
        'MAX_BOX_RANGE': 0.60,        # 60% 箱体振幅（以配置为准）
        'MAX_VOLATILITY_RATIO': 0.70,
        'MIN_GLORY_RATIO': 2.5,
        'MIN_GLORY_AMPLITUDE': 0.50,
        'MIN_POSITIVE_LOW': 0.01,
        'MIN_HIGH_PRICE': 2.0,
        'MIN_PRICE': 2.0,             # 最低绝对股价（元）
        'MIN_DATA_MONTHS': 36,
        'PRICE_POSITION_MIN': 0.05,   # 箱体位置 5%-85%（更宽松）
        'PRICE_POSITION_MAX': 0.85,
        'SQL_LIMIT': 300,

        # ===== Python 层参数 =====
        'SLOPE_MIN': -0.02,
        'SLOPE_MAX': 0.03,
        'MIN_R_SQUARED': 0.25,
        'EXCLUDE_ST': False,
        'EXCLUDE_BLACKLIST': False,
        'FINAL_LIMIT': 150,
    }
}

# =============================================================================
# 默认配置（可被命令行参数覆盖）
# =============================================================================

DEFAULT_PRESET = 'balanced'


# =============================================================================
# 工具函数
# =============================================================================

def get_config(preset: str = None, **overrides) -> dict:
    """
    获取配置（支持预设 + 自定义覆盖）

    Args:
        preset: 预设名称 ('conservative' | 'balanced' | 'aggressive')
        **overrides: 自定义参数（覆盖预设值）

    Returns:
        完整配置字典

    Examples:
        >>> # 使用默认配置
        >>> cfg = get_config()

        >>> # 使用保守配置
        >>> cfg = get_config('conservative')

        >>> # 使用均衡配置，并覆盖部分参数
        >>> cfg = get_config('balanced', MIN_DRAWDOWN=-0.50, EXCLUDE_ST=True)
    """
    if preset is None:
        preset = DEFAULT_PRESET

    if preset not in PRESETS:
        raise ValueError(f"未知预设: {preset}，可选值: {list(PRESETS.keys())}")

    # 复制预设配置
    config = PRESETS[preset].copy()

    # 应用自定义覆盖
    config.update(overrides)

    return config


def validate_config(config: dict) -> None:
    """
    验证配置参数的合法性

    Args:
        config: 配置字典

    Raises:
        ValueError: 参数不合法时
    """
    # 范围检查
    assert config['MIN_DRAWDOWN'] < 0, "MIN_DRAWDOWN 必须为负数"
    assert config['MAX_BOX_RANGE'] > 0, "MAX_BOX_RANGE 必须为正数"
    assert config['MIN_GLORY_RATIO'] > 1.0, "MIN_GLORY_RATIO 必须 > 1.0（正价段倍率）"
    assert 0 < config['MIN_GLORY_AMPLITUDE'] <= 2.0, "MIN_GLORY_AMPLITUDE 必须在 (0, 2] 区间（归一化振幅）"
    assert config['MIN_POSITIVE_LOW'] > 0, "MIN_POSITIVE_LOW 必须为正数"
    assert 0 < config['MAX_DRAWDOWN_ABS'] <= 1.5, "MAX_DRAWDOWN_ABS 必须在 (0, 1.5] 区间"
    assert config['MAX_DRAWDOWN_ABS'] > abs(config['MIN_DRAWDOWN']), \
        "MAX_DRAWDOWN_ABS 必须 > abs(MIN_DRAWDOWN)（用于得分归一化）"
    assert config['MIN_HIGH_PRICE'] > 0, "MIN_HIGH_PRICE 必须为正数"
    assert config['MIN_PRICE'] > 0, "MIN_PRICE 必须为正数"
    assert config['SLOPE_MIN'] < config['SLOPE_MAX'], "SLOPE_MIN 必须小于 SLOPE_MAX"
    assert 0 < config['MIN_R_SQUARED'] <= 1.0, "MIN_R_SQUARED 必须在 (0, 1] 区间"

    # 逻辑检查
    assert config['RECENT_LOOKBACK'] < config['HISTORY_LOOKBACK'], \
        "RECENT_LOOKBACK 必须小于 HISTORY_LOOKBACK"


def print_config(config: dict) -> None:
    """打印当前配置（用于调试）"""
    print("\n" + "=" * 60)
    print("当前筛选配置")
    print("=" * 60)

    print("\n【SQL 层参数】")
    print(f"  历史回溯月数:        {config['HISTORY_LOOKBACK']}")
    print(f"  近期窗口月数:        {config['RECENT_LOOKBACK']}")
    print(f"  最小回撤幅度:        {config['MIN_DRAWDOWN']:.1%}")
    print(f"  回撤绝对值上限:      {config['MAX_DRAWDOWN_ABS']:.1%}")
    print(f"  最大箱体振幅:        {config['MAX_BOX_RANGE']:.1%}")
    print(f"  最大波动率比:        {config['MAX_VOLATILITY_RATIO']:.2f}")
    print(f"  最小辉煌度(倍率):    {config['MIN_GLORY_RATIO']:.2f}")
    print(f"  最小辉煌度(振幅):    {config['MIN_GLORY_AMPLITUDE']:.2f}")
    print(f"  正价判定阈值:        {config['MIN_POSITIVE_LOW']:.2f}")
    print(f"  历史高点最低值:      {config['MIN_HIGH_PRICE']:.1f} 元")
    print(f"  最低绝对股价:        {config['MIN_PRICE']:.1f} 元")
    print(f"  最少数据月数:        {config['MIN_DATA_MONTHS']}")
    print(f"  箱体位置范围:        [{config['PRICE_POSITION_MIN']:.2f}, {config['PRICE_POSITION_MAX']:.2f}]")
    print(f"  SQL 返回上限:        {config['SQL_LIMIT']}")

    print("\n【Python 层参数】")
    print(f"  趋势斜率范围:        [{config['SLOPE_MIN']:.3f}, {config['SLOPE_MAX']:.3f}]")
    print(f"  最小拟合度 R²:       {config['MIN_R_SQUARED']:.2f}")
    print(f"  排除 ST 股票:        {'是' if config['EXCLUDE_ST'] else '否'}")
    print(f"  排除黑名单股票:      {'是' if config['EXCLUDE_BLACKLIST'] else '否'}")
    print(f"  最终输出数量:        {config['FINAL_LIMIT']}")

    print("=" * 60 + "\n")
```

### 5.2 使用示例

```python
# selection/find_flatbottom.py

from selection.config import get_config, validate_config, print_config

def main():
    # 方式1: 使用默认配置
    config = get_config()

    # 方式2: 使用预设配置
    config = get_config('conservative')

    # 方式3: 使用预设 + 自定义覆盖
    config = get_config(
        'balanced',
        MIN_DRAWDOWN=-0.50,
        EXCLUDE_ST=True
    )

    # 方式4: 从命令行参数构建配置
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset', default='balanced')
    parser.add_argument('--min-drawdown', type=float)
    parser.add_argument('--exclude-st', action='store_true')
    args = parser.parse_args()

    # 构建覆盖字典（只包含非None的参数）
    overrides = {}
    if args.min_drawdown is not None:
        overrides['MIN_DRAWDOWN'] = args.min_drawdown
    if args.exclude_st:
        overrides['EXCLUDE_ST'] = True

    config = get_config(args.preset, **overrides)

    # 验证并打印配置
    validate_config(config)
    print_config(config)

    # 使用配置进行筛选
    screener = FlatbottomScreener(config)
    results = screener.run()
```

### 5.3 完整参数表

**重要说明**：文档中提到的具体数值（如"-40%回撤"、"50%箱体振幅"）仅为示例说明，**实际阈值以配置文件为准**。

| 参数名称 | 类型 | 默认值 | 保守值 | 进取值 | 说明 |
|:---|:---|:---|:---|:---|:---|
| **SQL 层参数** | | | | | |
| `HISTORY_LOOKBACK` | int | 120 | 120 | 60 | 历史回溯月数（窗口大小） |
| `RECENT_LOOKBACK` | int | 24 | 36 | 12 | 近期窗口月数（箱体计算范围） |
| `MIN_DRAWDOWN` | float | -0.40 | -0.50 | -0.30 | 最小回撤幅度（负数，-0.40表示-40%） |
| `MAX_DRAWDOWN_ABS` | float | 0.90 | 0.90 | 0.90 | 回撤绝对值上限（防极端值刷分） |
| `MAX_BOX_RANGE` | float | 0.50 | 0.40 | 0.60 | 最大箱体振幅（0.50表示50%） |
| `MAX_VOLATILITY_RATIO` | float | 0.60 | 0.50 | 0.70 | 最大波动率比（近期/历史） |
| `MIN_GLORY_RATIO` | float | 3.0 | 3.5 | 2.5 | 最小辉煌度倍率（正价段：历史高点/历史低点） |
| `MIN_GLORY_AMPLITUDE` | float | 0.60 | 0.70 | 0.50 | 最小辉煌度振幅（负价段回退：归一化振幅） |
| `MIN_POSITIVE_LOW` | float | 0.01 | 0.01 | 0.01 | 正价判定阈值（历史低点 > 该值才用倍率） |
| `MIN_HIGH_PRICE` | float | 3.0 | 5.0 | 2.0 | 历史高点最低值（确保“曾经辉煌”来自正价区间） |
| `MIN_PRICE` | float | 3.0 | 5.0 | 2.0 | 最低绝对股价（元，排除仙股） |
| `MIN_DATA_MONTHS` | int | 60 | 120 | 36 | 最少数据月数（数据完整性要求） |
| `PRICE_POSITION_MIN` | float | 0.05 | 0.05 | 0.05 | 箱体位置下限（避免破位下跌） |
| `PRICE_POSITION_MAX` | float | 0.80 | 0.75 | 0.85 | 箱体位置上限（避免追高） |
| `SQL_LIMIT` | int | 200 | 150 | 300 | SQL返回上限（粗筛候选数） |
| **Python 层参数** | | | | | |
| `SLOPE_MIN` | float | -0.01 | -0.005 | -0.02 | 趋势斜率下限（允许微跌） |
| `SLOPE_MAX` | float | 0.02 | 0.015 | 0.03 | 趋势斜率上限（避免追涨） |
| `MIN_R_SQUARED` | float | 0.30 | 0.40 | 0.25 | 最小拟合度R²（趋势规律性） |
| `EXCLUDE_ST` | bool | **False** | True | False | 是否排除ST股（当前ST数据未就绪） |
| `EXCLUDE_BLACKLIST` | bool | **False** | True | False | 是否排除黑名单股票 |
| `FINAL_LIMIT` | int | 100 | 50 | 150 | 最终输出数量 |

### 5.4 适用场景

| 配置模式 | 回撤阈值 | 箱体振幅 | 适用场景 | 预期结果 |
|:---|:---|:---|:---|:---|
| **conservative** | -50% | 40% | 熊市末期、高风险期 | 30-50只极度安全的标的 |
| **balanced** | -40% | 50% | 震荡市、常规选股 | 50-100只底部扎实的标的 |
| **aggressive** | -30% | 60% | 牛市初期、机会挖掘 | 100-150只潜在标的 |

---

## 6. 日志系统设计

### 6.1 日志配置 (config.py)

日志相关配置已在 `selection/config.py` 中定义：

```python
# 日志文件配置
LOG_DIR = 'logs'                          # 日志目录（项目根目录下）
LOG_FILE = 'selection.log'               # 日志文件名
LOG_MAX_BYTES = 10 * 1024 * 1024          # 单个日志文件最大 10MB
LOG_BACKUP_COUNT = 5                      # 保留最近 5 个日志文件

# 日志级别配置
CONSOLE_LOG_LEVEL = 'INFO'                # 控制台日志级别
FILE_LOG_LEVEL = 'DEBUG'                  # 文件日志级别

# 日志格式
LOG_FORMAT_CONSOLE = '%(levelname)-8s | %(message)s'
LOG_FORMAT_FILE = '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
```

**配置说明**:
- `CONSOLE_LOG_LEVEL`: 控制台输出级别，建议 INFO（只显示重要信息）
- `FILE_LOG_LEVEL`: 文件输出级别，建议 DEBUG（保存详细日志便于排查问题）
- 日志文件自动轮转（超过 10MB 自动创建新文件，保留最近 5 个）

### 6.2 日志工具模块 (logger.py)

**文件位置**: `selection/logger.py`

```python
"""
日志工具模块
提供统一的日志配置和初始化功能
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from selection import config


def setup_logger(name: str = 'selection') -> logging.Logger:
    """
    设置并返回配置好的 logger

    Args:
        name: logger 名称（默认为 'selection'）

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG)  # logger 自身设置为最低级别

    # =========================================
    # 控制台 Handler
    # =========================================
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.CONSOLE_LOG_LEVEL))
    console_formatter = logging.Formatter(
        config.LOG_FORMAT_CONSOLE,
        datefmt=config.LOG_DATE_FORMAT
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # =========================================
    # 文件 Handler（带轮转）
    # =========================================
    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)  # 确保日志目录存在

    log_file = log_dir / config.LOG_FILE
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, config.FILE_LOG_LEVEL))
    file_formatter = logging.Formatter(
        config.LOG_FORMAT_FILE,
        datefmt=config.LOG_DATE_FORMAT
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


# =========================================
# 模块级 logger（可直接导入使用）
# =========================================
logger = setup_logger('selection')
```

### 6.3 使用示例

**在主程序中使用**:

```python
# selection/find_flatbottom.py

from selection.logger import logger

def main():
    logger.info("开始执行平底锅形态筛选")

    try:
        # 阶段1: SQL 粗筛
        logger.info("阶段1: SQL 粗筛...")
        sql_candidates = screener._sql_screen()
        logger.info(f"SQL 粗筛完成: {len(sql_candidates)} 只候选股")

        # 阶段2: Python 精筛
        logger.debug("开始 Python 精筛阶段")
        final_results = screener._python_refine(sql_candidates)
        logger.info(f"Python 精筛完成: {len(final_results)} 只最终候选股")

        # 数据库写入
        logger.debug("写入数据库...")
        count = screener._save_to_database(final_results, preset)
        logger.info(f"✓ 成功写入 {count} 条记录到数据库")

    except Exception as e:
        logger.error(f"筛选过程出错: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
```

**在其他模块中使用**:

```python
# 方式1: 使用模块级 logger（推荐）
from selection.logger import logger

logger.info("这是一条信息日志")
logger.debug("这是一条调试日志")
logger.warning("这是一条警告日志")
logger.error("这是一条错误日志")

# 方式2: 创建子 logger
import logging
logger = logging.getLogger('selection.submodule')
logger.info("子模块日志")
```

### 6.4 日志级别说明

| 级别 | 数值 | 使用场景 | 示例 |
|:---|:---|:---|:---|
| **DEBUG** | 10 | 详细诊断信息 | 变量值、中间计算结果、SQL语句 |
| **INFO** | 20 | 正常流程确认 | 筛选开始/完成、记录数统计 |
| **WARNING** | 30 | 警告但不影响运行 | 数据为空、使用默认值 |
| **ERROR** | 40 | 错误但程序可继续 | 数据库连接失败、CSV导出失败 |
| **CRITICAL** | 50 | 严重错误导致程序终止 | 配置文件损坏、无法创建必需资源 |

### 6.5 日志输出示例

**控制台输出**（`CONSOLE_LOG_LEVEL = 'INFO'`）:
```
INFO     | 开始执行平底锅形态筛选 (预设配置: balanced)
INFO     | SQL 粗筛完成: 185 只候选股
INFO     | 风险过滤后剩余 178 只
INFO     | Python 精筛完成: 82 只最终候选股
INFO     | ✓ 成功写入 82 条记录到数据库
INFO     | ✓ CSV 文件已保存: output/stock_flatbottom_preselect_20260127_093015.csv
INFO     | 筛选完成！总耗时: 8.35 秒
```

**日志文件内容**（`FILE_LOG_LEVEL = 'DEBUG'`）:
```
2026-01-27 09:30:08 | INFO     | selection:45 | 开始执行平底锅形态筛选 (预设配置: balanced)
2026-01-27 09:30:08 | DEBUG    | selection:127 | 构建SQL查询，参数: HISTORY_LOOKBACK=120, RECENT_LOOKBACK=24
2026-01-27 09:30:08 | DEBUG    | selection:145 | 执行SQL粗筛查询
2026-01-27 09:30:13 | INFO     | selection:152 | SQL 粗筛完成: 185 只候选股
2026-01-27 09:30:13 | DEBUG    | selection:234 | 批量获取价格数据: 185 只股票
2026-01-27 09:30:14 | INFO     | selection:278 | 风险过滤后剩余 178 只
2026-01-27 09:30:15 | DEBUG    | selection:312 | 600000.SH: 趋势不符合（slope=-0.0234, R²=0.251）
2026-01-27 09:30:16 | INFO     | selection:345 | Python 精筛完成: 82 只最终候选股
2026-01-27 09:30:16 | DEBUG    | selection:412 | TRUNCATE + INSERT 数据库: 82 条记录
2026-01-27 09:30:17 | INFO     | selection:425 | ✓ 成功写入 82 条记录到数据库
```

### 6.6 动态调整日志级别

**通过 CLI 参数控制**:

```bash
# 启用详细日志（控制台也显示 DEBUG）
python -m selection.find_flatbottom --verbose

# 实现方式（在 find_flatbottom.py 中）
if args.verbose:
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(logging.DEBUG)
```

**通过配置文件调整**:

直接修改 `selection/config.py`:
```python
# 开发环境：详细日志
CONSOLE_LOG_LEVEL = 'DEBUG'
FILE_LOG_LEVEL = 'DEBUG'

# 生产环境：简洁日志
CONSOLE_LOG_LEVEL = 'INFO'
FILE_LOG_LEVEL = 'INFO'
```

### 6.7 日志文件管理

**日志文件结构**:
```
logs/
├── selection.log          # 当前日志
├── selection.log.1        # 第1个备份（上一次轮转）
├── selection.log.2        # 第2个备份
├── selection.log.3        # 第3个备份
├── selection.log.4        # 第4个备份
└── selection.log.5        # 第5个备份（最旧）
```

**自动轮转规则**:
- 当 `selection.log` 超过 10MB 时，自动轮转
- `selection.log` → `selection.log.1`
- `selection.log.1` → `selection.log.2`
- ...
- `selection.log.5` 被删除

**手动清理日志**:
```bash
# 删除所有日志
rm -rf logs/selection.log*

# 只保留最近的日志
find logs/ -name "selection.log.*" -mtime +7 -delete
```

---

## 7. CLI 命令行工具

### 7.1 基本用法

```bash
# 使用默认配置（balanced，参数定义在 selection/config.py）
python -m selection.find_flatbottom

# 使用保守配置（适合熊市末期）
python -m selection.find_flatbottom --preset conservative

# 使用进取配置（适合牛市初期）
python -m selection.find_flatbottom --preset aggressive

# 仅筛选指定股票（从文件读取，每行一个代码）
python -m selection.find_flatbottom -f selection/check_list.txt
```

### 7.2 参数覆盖

```bash
# 使用 balanced 预设，但覆盖部分参数
python -m selection.find_flatbottom \
  --preset balanced \
  --min-drawdown -0.50 \
  --max-box-range 0.40 \
  --final-limit 50

# 启用 ST 股票过滤
python -m selection.find_flatbottom --exclude-st

# 启用黑名单过滤
python -m selection.find_flatbottom --exclude-blacklist

# 同时启用两种过滤
python -m selection.find_flatbottom --exclude-st --exclude-blacklist

# 自定义多个参数
python -m selection.find_flatbottom \
  --preset balanced \
  --min-drawdown -0.45 \
  --max-drawdown-abs 0.90 \
  --min-glory-ratio 3.0 \
  --min-glory-amplitude 0.60 \
  --min-positive-low 0.01 \
  --min-high-price 3.0 \
  --exclude-st \
  --exclude-blacklist

# 使用文件过滤 + 参数覆盖
python -m selection.find_flatbottom \
  -f selection/check_list.txt \
  --preset balanced \
  --min-drawdown 0.40
```

**过滤文件说明**:
- `-f/--filter-file` 指向一个 txt 文件，每行一个股票代码
- 支持空行与 `#` 注释行
- 会自动标准化代码格式（如 `600000` -> `600000.SH`，`300750` -> `300750.SZ`）
- 会自动去重（保留首次出现顺序）

### 7.3 日志和调试

```bash
# 调试模式（控制台也显示 DEBUG 级别日志）
python -m selection.find_flatbottom --verbose

# 查看当前配置（不执行筛选）
python -m selection.find_flatbottom --preset conservative --dry-run

# 调试模式 + 自定义参数
python -m selection.find_flatbottom --verbose --min-drawdown -0.45 --exclude-st
```

**日志说明**:
- 默认：控制台显示 INFO 级别，文件保存 DEBUG 级别
- `--verbose`: 控制台也显示 DEBUG 级别（详细诊断信息）
- 日志文件位置：`logs/selection.log`
- 日志自动轮转，保留最近 5 个文件

### 7.5 输出说明

**默认行为**:
- ✅ 结果自动写入数据库（TRUNCATE + INSERT，每次执行前清空）
- ✅ 自动导出带时间戳的 CSV 文件到 `output/` 目录
- ✅ CSV 文件名格式：`stock_flatbottom_preselect_YYYYMMDD_HHMMSS.csv`
- ✅ 示例：`output/stock_flatbottom_preselect_20260127_093015.csv`

**历史记录**:
- 数据库表只保留每个股票的最新记录
- 历史记录通过导出的 CSV 文件保存
- 可对比不同日期的 CSV 文件进行历史分析

### 7.6 完整 CLI 参数列表

```python
# selection/find_flatbottom.py (main函数)

parser = argparse.ArgumentParser(
    description='平底锅形态股票筛选工具',
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
示例:
  # 使用默认配置（结果写入数据库并自动导出CSV）
  python -m selection.find_flatbottom

  # 使用保守配置并启用ST过滤
  python -m selection.find_flatbottom --preset conservative --exclude-st

  # 完整示例：启用所有过滤
  python -m selection.find_flatbottom \\
    --preset balanced \\
    --exclude-st \\
    --exclude-blacklist \\
    --min-drawdown -0.45

  # 调试模式（控制台显示详细日志）
  python -m selection.find_flatbottom --verbose

输出:
  - 数据库: stock_flatbottom_preselect 表（TRUNCATE + INSERT）
  - CSV 文件: output/stock_flatbottom_preselect_YYYYMMDD_HHMMSS.csv
  - 日志文件: logs/selection.log
    """
)

# 预设配置
parser.add_argument('--preset', choices=['conservative', 'balanced', 'aggressive'],
                    default='balanced', help='预设配置模式')
parser.add_argument('-f', '--filter-file', help='股票代码过滤文件（每行一个代码）')

# SQL层参数（可选覆盖）
parser.add_argument('--history-lookback', type=int, help='历史回溯月数')
parser.add_argument('--recent-lookback', type=int, help='近期窗口月数')
parser.add_argument('--min-drawdown', type=float, help='最小回撤幅度（负数）')
parser.add_argument('--max-drawdown-abs', type=float, help='回撤绝对值上限')
parser.add_argument('--max-box-range', type=float, help='最大箱体振幅')
parser.add_argument('--max-volatility-ratio', type=float, help='最大波动率比')
parser.add_argument('--min-glory-ratio', type=float, help='最小辉煌度（正价段倍率）')
parser.add_argument('--min-glory-amplitude', type=float, help='最小辉煌度（负价段振幅）')
parser.add_argument('--min-positive-low', type=float, help='正价判定阈值（历史低点）')
parser.add_argument('--min-high-price', type=float, help='历史高点最低值（元）')
parser.add_argument('--min-price', type=float, help='最低绝对股价（元）')
parser.add_argument('--min-data-months', type=int, help='最少数据月数')
parser.add_argument('--sql-limit', type=int, help='SQL返回上限')

# Python层参数（可选覆盖）
parser.add_argument('--slope-min', type=float, help='趋势斜率下限')
parser.add_argument('--slope-max', type=float, help='趋势斜率上限')
parser.add_argument('--min-r-squared', type=float, help='最小拟合度R²')
parser.add_argument('--exclude-st', action='store_true', help='排除ST股票')
parser.add_argument('--exclude-blacklist', action='store_true', help='排除黑名单股票')
parser.add_argument('--final-limit', type=int, help='最终输出数量')

# 运行控制
parser.add_argument('--verbose', action='store_true',
                    help='显示详细日志（控制台也输出 DEBUG 级别）')
parser.add_argument('--dry-run', action='store_true',
                    help='仅显示配置，不执行筛选')
```

---

## 8. 输出示例

### 8.1 数据库记录

**表**: `stock_flatbottom_preselect`

执行筛选后，结果会自动写入数据库（TRUNCATE + INSERT）。查询示例：

```sql
-- ============================================================
-- 基本查询（无需时间过滤，表中只有最新记录）
-- ============================================================

-- 查询所有筛选结果（按得分排序）
SELECT code, name, current_price, score, updated_at
FROM stock_flatbottom_preselect
ORDER BY score DESC;

-- 查询 Top 10 股票
SELECT code, name, current_price, glory_ratio, glory_type, drawdown_pct, score
FROM stock_flatbottom_preselect
ORDER BY score DESC
LIMIT 10;

-- 查询某只股票的详细信息
SELECT *
FROM stock_flatbottom_preselect
WHERE code = '300444.SZ';

-- 查询得分在某个范围内的股票
SELECT code, name, score
FROM stock_flatbottom_preselect
WHERE score >= 80
ORDER BY score DESC;


-- ============================================================
-- 统计分析
-- ============================================================

-- 查看数据库总记录数和更新时间
SELECT
    COUNT(*) as total_stocks,
    MAX(updated_at) as latest_update,
    MIN(updated_at) as earliest_update
FROM stock_flatbottom_preselect;

-- 按预设配置统计（如果多次运行使用了不同配置）
SELECT screening_preset, COUNT(*) as count, AVG(score) as avg_score
FROM stock_flatbottom_preselect
GROUP BY screening_preset
ORDER BY screening_preset;

-- 得分分布统计
SELECT
    CASE
        WHEN score >= 90 THEN '90-100'
        WHEN score >= 80 THEN '80-89'
        WHEN score >= 70 THEN '70-79'
        ELSE '< 70'
    END as score_range,
    COUNT(*) as count
FROM stock_flatbottom_preselect
GROUP BY score_range
ORDER BY score_range DESC;

-- 辉煌度类型分布监控（双轨指标）
SELECT
    glory_type,
    COUNT(*) as count,
    AVG(glory_ratio) as avg_ratio,
    MIN(glory_ratio) as min_ratio,
    MAX(glory_ratio) as max_ratio
FROM stock_flatbottom_preselect
GROUP BY glory_type;


-- ============================================================
-- 数据维护
-- ============================================================

-- 查看今天更新的股票
SELECT code, name, score, updated_at
FROM stock_flatbottom_preselect
WHERE updated_at >= CURRENT_DATE
ORDER BY score DESC;

-- 清空所有数据（慎用）
TRUNCATE TABLE stock_flatbottom_preselect;

-- 删除得分过低的股票（如果需要）
DELETE FROM stock_flatbottom_preselect
WHERE score < 60;
```

### 8.2 CSV 文件（自动导出）

**目录**: `output/`

**文件名格式**: `stock_flatbottom_preselect_YYYYMMDD_HHMMSS.csv`

**示例文件**:
- `output/stock_flatbottom_preselect_20260127_093015.csv`
- `output/stock_flatbottom_preselect_20260128_100522.csv`
- `output/stock_flatbottom_preselect_20260129_094738.csv`

**CSV 内容示例**:

```csv
code,name,current_price,history_high,glory_ratio,glory_type,drawdown_pct,box_range_pct,volatility_ratio,price_position,score,slope,r_squared
300444.SZ,双杰电气,8.25,26.80,0.72,-69.2,38.5,0.45,0.42,85.3,0.0082,0.65
002823.SZ,凯中精密,10.50,29.50,0.66,-64.4,42.1,0.52,0.38,78.6,0.0045,0.58
600482.SH,中国动力,18.30,48.20,0.70,-62.0,45.8,0.48,0.51,75.2,-0.0023,0.61
```

> 注：`current_price` 可能为负值，筛选时使用 **ABS(current_price)** 判断最低价格门槛。

**历史记录分析**:

通过对比不同日期的 CSV 文件，可以进行：
- 观察哪些股票反复入选（高频信号）
- 跟踪某只股票的得分变化趋势
- 对比不同配置的筛选效果
- 回测历史筛选结果的表现

### 8.3 后续图表生成

本模块仅负责筛选并输出结果（数据库 + CSV）。如需为筛选出的股票生成 K 线图，请使用 `visualization` 模块：

```bash
# 为单只股票生成K线图
python -m visualization.plot_kline 300444 --out output/flatbottom/300444_kline.png

# 从数据库读取筛选结果并批量生成图表（待开发）
# 或从 CSV 文件读取并批量绘图
```

---

## 9. 性能优化总结

### 9.1 性能对比

| 阶段 | v1 耗时 | v2.3 耗时 | 提升 |
|:---|:---|:---|:---|
| SQL 粗筛 | 5秒 | 5秒 | - |
| Python 精筛 | 10秒 | 2秒 | **5倍** |
| 数据库写入（TRUNCATE + INSERT） | - | < 1秒 | - |
| CSV 自动导出 | - | < 1秒 | - |
| **总耗时** | **15秒** | **< 10秒** | **33%** |

### 9.2 核心优化技术

1. **批量查询**: `WHERE code = ANY(...)` 替代循环查询
2. **内存计算**: 数据加载后在内存中分组计算，无需重复IO
3. **TRUNCATE + INSERT**: 每次执行前清空结果表，再写入本次结果
4. **自动导出**: 带时间戳的 CSV 文件，保留历史记录
5. **模块解耦**: 筛选与可视化分离，各司其职
6. **条件过滤**: ST和黑名单过滤采用开关设计，灵活控制

---

## 10. 下一步实施

### 10.1 必需步骤

1. ✅ **创建数据库表**: 执行 2.3 节的 DDL 语句，创建 `stock_flatbottom_preselect` 表
2. ✅ **创建配置文件**: `selection/config.py`（定义所有筛选参数 + 日志配置）
3. ✅ **创建日志模块**: `selection/logger.py`（统一日志配置）
4. ✅ **创建 SQL 文件**: `selection/sql/flatbottom_screen.sql`
5. ✅ **实现主程序**: `selection/find_flatbottom.py`
   - 导入并使用 logger
   - 实现 TRUNCATE + INSERT 数据库写入逻辑
   - 实现自动导出带时间戳的 CSV
6. ✅ **实现 CLI 接口**: 支持预设配置和参数覆盖
7. ✅ **创建必要目录**:
   ```bash
   mkdir -p logs output
   ```
8. ✅ **测试验证**: 使用已知股票验证准确性

### 10.2 可选增强

**基础功能**:
- [ ] 添加单元测试
- [ ] 实现参数敏感性分析
- [ ] 完善 ST 股票名单数据
- [ ] 建立黑名单表 (stock_blacklist)

**CSV历史分析工具**:
- [ ] 开发 CSV 对比工具（对比不同日期的筛选结果）
- [ ] 实现高频入选股票识别（分析多个 CSV 文件）
- [ ] 添加得分趋势可视化（读取历史 CSV 绘制趋势图）
- [ ] 实现策略效果回测（基于历史 CSV 文件）

**可视化与集成**:
- [ ] 开发批量绘图工具（读取数据库或 CSV，调用 visualization 模块）
- [ ] 集成 LLM 精选阶段（对数据库中的股票进行二次筛选）
- [ ] 添加回测模块（基于历史 CSV 记录）
- [ ] 开发 Web 看板（展示数据库实时结果和 CSV 历史趋势）

---

**文档版本**: v2.3
**最后更新**: 2026-01-27
**状态**: Ready for Implementation
**作者**: Claude Code Team

**重要说明**:
- **模块职责**: 从 `stock_monthly_kline` 表进行粗筛，结果写入 `stock_flatbottom_preselect` 表
- **图表生成**: 由 `visualization` 模块独立负责
- **ST过滤**: 默认关闭（数据未就绪，EXCLUDE_ST=False）
- **黑名单过滤**: 默认关闭（EXCLUDE_BLACKLIST=False）
- **数据管理**: TRUNCATE + INSERT，每个股票只保留最新记录

**数据流**:
- **读取**: `stock_monthly_kline`（月K线）、`stock_blacklist`（可选）
- **写入**: `stock_flatbottom_preselect`（结果表，TRUNCATE + INSERT）
- **导出**: 自动导出带时间戳的 CSV 文件到 `output/` 目录

---

## 11. 负价逻辑说明（前复权兼容）

由于前复权数据可能出现负价，本方案对**辉煌度**采用**双轨指标**，其余比例类指标采用**绝对值归一化**，避免负价导致的比例失真：

1. **辉煌度（glory_ratio）**  
   - 正价段（倍率语义）：
     ```
     history_high / history_low
     ```
   - 负价段（回退振幅）：
     ```
     (history_high - history_low) / MAX(ABS(history_high), ABS(history_low))
     ```
   并通过 `glory_type` 标记使用的计算方式（ratio / amplitude）。

2. **回撤幅度（drawdown_pct）**  
   ```
   (close - history_high) / ABS(history_high)
   ```
   公式兼容负价，但筛选时额外要求 `history_high > MIN_HIGH_PRICE`，确保“曾经辉煌”来自正价区间。

3. **箱体振幅（box_range_pct）**  
   ```
   (recent_high - recent_low) / MAX(ABS(recent_high), ABS(recent_low))
   ```
   避免负价导致分母为负或符号翻转。

4. **最低价格过滤**  
   ```
   ABS(current_price) >= MIN_PRICE
   ```
   使用绝对值判断“仙股”，避免负价被误剔除。

5. **辉煌度有效性约束**  
   ```
   history_high > MIN_HIGH_PRICE
   ```
   确保“曾经辉煌”来自正价区间，避免负价极端波动误判。

> 该逻辑确保负价股票在粗筛阶段不会被系统性误排，同时仍能保留“曾经辉煌→深度回调→底部沉淀”的形态特征。

**负价占比检查（建议运行）**:
```sql
-- 检查负价股票数量（按最新月份窗口）
SELECT
    COUNT(DISTINCT code) AS total_stocks,
    SUM(CASE WHEN history_low <= 0 THEN 1 ELSE 0 END) AS stocks_with_negative_low,
    ROUND(100.0 * SUM(CASE WHEN history_low <= 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS negative_pct
FROM (
    SELECT
        code,
        MIN(low) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN 119 PRECEDING AND CURRENT ROW
        ) AS history_low,
        ROW_NUMBER() OVER (PARTITION BY code ORDER BY month DESC) as rn
    FROM stock_monthly_kline
) sub
WHERE rn = 1;
```

**数据库表设计**（简化方案）:
- **主键**: `code`（股票代码）
- **每股票一条记录**: TRUNCATE + INSERT（仅保留本次结果）
- **历史记录**: 通过导出的 CSV 文件保存
- **CSV 文件名**: `stock_flatbottom_preselect_YYYYMMDD_HHMMSS.csv`
- **查询简单**: 无需时间过滤，直接查询即可

**配置管理**:
- `selection/config.py`: 存放所有筛选算法参数 + 日志配置（纳入版本控制，上传到GitHub）
- `selection/logger.py`: 统一日志工具模块（纳入版本控制）
- `.env`: 存放敏感信息（数据库密码、API密钥等，不上传到GitHub）
- 配置文件提供三种预设：conservative（保守）、balanced（均衡）、aggressive（进取）
- CLI 支持使用预设配置 + 自定义参数覆盖
- 日志支持控制台和文件分别配置输出级别

**日志管理**:
- 日志文件位置：`logs/selection.log`
- 控制台默认级别：INFO（只显示重要信息）
- 文件默认级别：DEBUG（保存详细日志）
- 自动轮转：单文件超过 10MB 自动创建新文件，保留最近 5 个
- 使用 `--verbose` 参数启用控制台详细日志

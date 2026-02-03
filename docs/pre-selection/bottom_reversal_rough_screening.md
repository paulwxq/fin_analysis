# 底部反转（平底锅）形态粗筛算法设计文档

本文档详细定义了如何基于 `stock_monthly_kline` 月线数据，使用 Python + SQL 实现“平底锅”形态股票的初级筛选。本算法旨在从全市场股票中快速剔除不符合形态的标的，为后续的精细化分析（如 AI 识别）提供高质量候选池。

## 1. 算法目标与形态定义

我们的目标是寻找符合 **“辉煌 -> 沉沦 -> 沉淀”** 三部曲的股票。

| 特征维度 | 业务描述 | 量化逻辑映射 | 默认参数建议 |
| :--- | :--- | :--- | :--- |
| **曾经辉煌** | 历史上曾大幅上涨，并创下高点。 | 必须存在一个显著的历史最高价 ($P_{max\_hist}$)，且该高点出现在“很久以前”。 | 高点距今 > 3 年 |
| **深度回调** | 股价长期下跌，当前价远低于历史高点。 | 当前价格 ($P_{curr}$) 相对于历史最高价 ($P_{max\_hist}$) 的跌幅巨大。 | 累计跌幅 > 50% |
| **底部沉淀** | 最近几年波动收敛，箱体震荡，未大涨。 | 在观察窗口内（最近 N 年），股价的振幅 ($Amplitude$) 较小，未出现倍增行情。 | 近3年最大涨幅 < 150% |

## 2. 算法详细设计

### 2.1 核心参数定义 (Configurable)

算法应支持以下参数配置，以便在不同市场环境下调整筛选宽松度。

```python
CONFIG = {
    # 时间窗口
    "OBSERVATION_YEARS": 3,      # 观察窗口长度（年），用于定义“最近”和“底部”
    
    # 筛选阈值
    "MIN_HISTORY_AGE": 36,       # (月) 历史高点距今的最小月数，排除刚上市或刚崩盘的股票
    "MAX_DRAWDOWN": -0.50,       # (比率) 历史最大回撤阈值 (当前价/历史高点 - 1)，例如 -0.5 代表腰斩
    "MAX_AMPLITUDE": 2.5,        # (倍数) 底部箱体振幅阈值 (观察期最高/最低)，2.5 代表振幅不超过 150%
    "MIN_LISTING_MONTHS": 48,    # (月) 最小上市时长，确保有足够历史数据
}
```

### 2.2 数据获取 (SQL Layer)

为了最大化性能，我们使用 SQL 一次性拉取所需的 OHLC 数据。不需要在 SQL 层做复杂聚合，保留原始月线数据以便 Pandas 灵活处理。

```sql
-- 1. 基础数据快照
SELECT 
    code,
    month,
    close,
    high,
    low,
    volume
FROM stock_monthly_kline
ORDER BY code, month ASC;
```

### 2.3 特征工程与过滤 (Python/Pandas Layer)

算法逻辑分为三个步骤：**分组 -> 计算 -> 过滤**。

#### Step 1: 预处理
*   加载数据至 DataFrame。
*   计算全局截止日期 `cutoff_date = NOW - OBSERVATION_YEARS`。
*   按 `code` 分组处理。

#### Step 2: 单股特征计算 (Vectorized)
对于每一只股票：

1.  **上市时间检查**:
    *   `listing_months = len(df)`
    *   若 `listing_months < MIN_LISTING_MONTHS` -> **排除** (新股数据不足)。

2.  **切分历史与近期**:
    *   `history_df`: `month < cutoff_date` (远古历史)
    *   `recent_df`: `month >= cutoff_date` (近期观察区)

3.  **计算“曾经辉煌”指标**:
    *   若 `history_df` 为空 -> **排除** (说明主要是次新股)。
    *   `hist_high_price` = `history_df['high'].max()`
    *   `hist_high_date` = `history_df['high'].idxmax()`
    *   `months_since_peak` = `(NOW - hist_high_date).months`
    *   **判定 1**: 若 `months_since_peak < MIN_HISTORY_AGE` -> **排除** (高点太近，还在下跌途中)。

4.  **计算“深度回调”指标**:
    *   `current_price` = `recent_df['close'].iloc[-1]`
    *   `drawdown` = `(current_price / hist_high_price) - 1`
    *   **判定 2**: 若 `drawdown > MAX_DRAWDOWN` (注意是负数比较，即跌幅不够深) -> **排除**。

5.  **计算“底部沉淀”指标**:
    *   `recent_high` = `recent_df['high'].max()`
    *   `recent_low` = `recent_df['low'].min()`
    *   `amplitude_ratio` = `recent_high / recent_low`
    *   **判定 3**: 若 `amplitude_ratio > MAX_AMPLITUDE` -> **排除** (近期已经大涨过，不符合底部特征)。

#### Step 3: 结果输出
*   输出符合条件的股票列表，包含关键指标：`code`, `drawdown`, `amplitude`, `peak_date`。
*   按 `drawdown` (跌得越深越好) 或 `amplitude` (越平越好) 进行排序。

## 3. 模块接口设计

建议创建 `analysis/rough_filter.py` 模块。

### 输入
*   `--drawdown`: 跌幅阈值 (默认 -0.5)
*   `--years`: 观察窗口年数 (默认 3)
*   `--output`: 结果 CSV 保存路径

### 输出
*   CSV 文件: 包含筛选出的股票代码及指标。
*   (可选) 自动调用绘图脚本生成前 20 名的 K 线图用于人工抽检。

## 4. 算法优势

*   **纯数学逻辑**: 不依赖黑盒模型，逻辑透明，完全可解释。
*   **参数解耦**: “观察期”和“回撤阈值”分离，可以灵活组合（例如寻找“腰斩后横盘1年”的短线机会，或“跌去90%后横盘5年”的极值机会）。
*   **计算高效**: 利用 Pandas `groupby` 和向量化运算，处理 5000 只股票的月线数据仅需秒级。

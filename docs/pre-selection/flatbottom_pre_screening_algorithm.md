# "平底锅"形态股票粗筛算法设计文档

## 文档说明

**版本**: v1.0
**创建日期**: 2026-01-27
**适用阶段**: SQL+Python 粗筛（LLM精选前的初筛阶段）
**数据源**: `stock_monthly_kline` 月K线聚合视图
**目标**: 从全市场3000+只股票中筛选出100-200只候选股票，排除明显不符合"平底锅"特征的标的

---

## 1. 核心投资逻辑

### 1.1 "平底锅"形态定义

"平底锅"形态是一种经典的底部反转形态，对应威科夫理论中的"吸筹区"（Accumulation Phase）。其核心特征包括：

1. **曾经辉煌**: 历史上曾经有过大幅上涨，并在数年前达到高点
2. **深度回调**: 股价经历了长期的下跌或消化，当前价格远低于历史高点
3. **底部沉淀**: 在最近1-3年内，股价波动率收敛，处于相对低位的箱体震荡

### 1.2 形态示意图

```
价格
 │
 │    ╱╲                  三阶段特征：
 │   ╱  ╲                 阶段1: 曾经辉煌（历史高点）
 │  ╱    ╲___             阶段2: 深度回调（跌幅>70%）
 │ ╱         ‾‾‾‾‾‾‾‾     阶段3: 底部沉淀（横盘震荡）
 │╱
 └────────────────────────> 时间
   2015   2018   2022  2025
```

### 1.3 金融学原理

- **均值回归理论**: 极端超跌后的估值修复
- **行为金融学**: 市场过度反应假说，恐慌→绝望→冷漠的情绪周期
- **威科夫理论**: 吸筹区特征为波动率收敛、成交量萎缩、筹码交换

---

## 2. 量化指标体系

### 2.1 核心指标定义

| 指标编号 | 指标名称 | 计算公式 | 阈值范围 | 金融含义 |
|:---|:---|:---|:---|:---|
| **I1** | 历史高点 | `MAX(high)` over 回溯窗口 | 需 > 当前价3倍 | 证明有过爆发力 |
| **I2** | 回撤幅度 | `(当前价 - 历史高点) / 历史高点` | < -0.40 (跌幅>40%) | 深度回调，泡沫释放 |
| **I3** | 箱体震荡幅度 | `(近期最高 - 近期最低) / 近期最低` | < 0.50 (振幅<50%) | 底部横盘特征 |
| **I4** | 波动率收敛比 | `近期标准差 / 历史标准差` | < 0.60 | 情绪冷却 |
| **I5** | 趋势斜率 | 线性回归斜率 | -0.01 ~ 0.02 | 锅底平整度 |
| **I6** | 均线粘合度 | `STDDEV(MA5, MA10, MA20)` | < 阈值 | 多空平衡 |
| **I7** | 价格位置 | `(当前价 - 近期最低) / (近期最高 - 近期最低)` | 0.10 ~ 0.60 | 避免追高或破位 |
| **I8** | 数据完整性 | 有效数据月数 | ≥ 60个月 | 确保历史可追溯 |

### 2.2 参数配置表

以下参数可根据市场环境动态调整：

| 参数名称 | 默认值 | 保守值 | 进取值 | 说明 |
|:---|:---|:---|:---|:---|
| `HISTORY_LOOKBACK` | 120个月 | 60个月 | 180个月 | 历史高点回溯窗口 |
| `RECENT_LOOKBACK` | 24个月 | 36个月 | 12个月 | 底部沉淀判断窗口 |
| `MIN_DRAWDOWN` | -0.40 | -0.50 | -0.30 | 最小回撤幅度（绝对值） |
| `MAX_BOX_RANGE` | 0.50 | 0.40 | 0.60 | 最大箱体震荡幅度 |
| `MAX_VOLATILITY_RATIO` | 0.60 | 0.50 | 0.70 | 波动率收敛比上限 |
| `SLOPE_MIN` | -0.01 | -0.005 | -0.02 | 趋势斜率下限 |
| `SLOPE_MAX` | 0.02 | 0.015 | 0.03 | 趋势斜率上限 |
| `MIN_GLORY_RATIO` | 3.0 | 4.0 | 2.5 | 历史高点/基期倍数 |
| `MIN_PRICE` | 3.0 | 5.0 | 2.0 | 最低股价（元，排除仙股） |
| `MIN_DATA_MONTHS` | 60 | 120 | 36 | 最少数据月数 |

---

## 3. SQL层粗筛算法

### 3.1 设计思路

利用TimescaleDB/PostgreSQL的窗口函数，在数据库层直接完成：
1. 历史高点计算
2. 回撤幅度计算
3. 箱体震荡幅度计算
4. 初步过滤（排除90%+的股票）

**优势**：
- 避免将全量数据传输到Python，减少网络IO
- 利用数据库索引加速查询
- 降低Python内存压力

### 3.2 完整SQL查询

```sql
-- =========================================
-- "平底锅"形态股票粗筛SQL
-- =========================================

WITH
-- 步骤1: 计算每只股票的历史统计指标
StockMetrics AS (
    SELECT
        code,
        month,
        close,
        high,
        low,
        volume,

        -- I1: 计算历史高点（过去N年，默认120个月=10年）
        MAX(high) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN 120 PRECEDING AND CURRENT ROW
        ) AS history_high,

        -- 辅助：计算历史低点（用于辉煌度判断）
        MIN(low) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN 120 PRECEDING AND CURRENT ROW
        ) AS history_low,

        -- I3: 计算近期最高价（用于箱体判断，默认24个月）
        MAX(high) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN 24 PRECEDING AND CURRENT ROW
        ) AS recent_high,

        -- I3: 计算近期最低价
        MIN(low) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN 24 PRECEDING AND CURRENT ROW
        ) AS recent_low,

        -- I4: 计算近期价格标准差（波动率）
        STDDEV(close) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN 24 PRECEDING AND CURRENT ROW
        ) AS recent_stddev,

        -- I4: 计算历史价格标准差（用于对比）
        STDDEV(close) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN 120 PRECEDING AND 25 PRECEDING  -- 避免包含近期
        ) AS historical_stddev,

        -- I8: 计算有效数据点数
        COUNT(*) OVER (
            PARTITION BY code
            ORDER BY month
            ROWS BETWEEN 120 PRECEDING AND CURRENT ROW
        ) AS data_points

    FROM stock_monthly_kline
    WHERE month >= NOW() - INTERVAL '10 years'  -- 只加载必要的历史数据
),

-- 步骤2: 计算派生指标并过滤
FilteredStocks AS (
    SELECT
        code,
        close AS current_price,
        history_high,
        history_low,
        recent_high,
        recent_low,

        -- I1: 辉煌度（历史高点相对于历史低点的倍数）
        CASE
            WHEN history_low > 0 THEN history_high / history_low
            ELSE NULL
        END AS glory_ratio,

        -- I2: 回撤幅度（当前价相对于历史高点的跌幅）
        CASE
            WHEN history_high > 0 THEN (close - history_high) / history_high
            ELSE NULL
        END AS drawdown_pct,

        -- I3: 箱体震荡幅度（近期波动幅度）
        CASE
            WHEN recent_low > 0 THEN (recent_high - recent_low) / recent_low
            ELSE NULL
        END AS box_range_pct,

        -- I4: 波动率收敛比
        CASE
            WHEN historical_stddev > 0 THEN recent_stddev / historical_stddev
            ELSE NULL
        END AS volatility_ratio,

        -- I7: 当前价格在箱体中的位置（0=最低点，1=最高点）
        CASE
            WHEN (recent_high - recent_low) > 0
            THEN (close - recent_low) / (recent_high - recent_low)
            ELSE 0.5
        END AS price_position,

        data_points

    FROM StockMetrics
    -- 只保留最新一个月的数据（每只股票一条记录）
    WHERE month = (SELECT MAX(month) FROM stock_monthly_kline)
),

-- 步骤3: 应用筛选条件
CandidateStocks AS (
    SELECT
        code,
        current_price,
        history_high,
        glory_ratio,
        drawdown_pct,
        box_range_pct,
        volatility_ratio,
        price_position,
        data_points,

        -- 计算综合得分（用于排序）
        (
            -- 回撤越深，得分越高（归一化到0-100）
            (ABS(drawdown_pct) - 0.40) / 0.40 * 40 +
            -- 箱体越窄，得分越高
            (0.50 - box_range_pct) / 0.50 * 30 +
            -- 波动率收敛越明显，得分越高
            (0.60 - volatility_ratio) / 0.60 * 30
        ) AS composite_score

    FROM FilteredStocks
    WHERE
        -- 条件1: 有足够的历史数据
        data_points >= 60

        -- 条件2: 曾经辉煌（历史高点至少是历史低点的3倍）
        AND glory_ratio >= 3.0

        -- 条件3: 深度回调（跌幅超过40%）
        AND drawdown_pct < -0.40

        -- 条件4: 底部沉淀（箱体震荡幅度小于50%）
        AND box_range_pct < 0.50

        -- 条件5: 波动率收敛（近期波动率低于历史的60%）
        AND volatility_ratio < 0.60

        -- 条件6: 价格位置合理（不在箱体顶部，避免追高）
        AND price_position < 0.80

        -- 条件7: 价格位置合理（不在箱体底部破位，避免下跌中继）
        AND price_position > 0.05

        -- 条件8: 排除仙股（价格过低，流动性差）
        AND current_price >= 3.0

        -- 条件9: 排除异常值
        AND history_high IS NOT NULL
        AND drawdown_pct IS NOT NULL
        AND box_range_pct IS NOT NULL
)

-- 步骤4: 输出结果（按综合得分排序）
SELECT
    code,
    ROUND(current_price::numeric, 2) AS current_price,
    ROUND(history_high::numeric, 2) AS history_high,
    ROUND(glory_ratio::numeric, 2) AS glory_ratio,
    ROUND(drawdown_pct::numeric * 100, 1) AS drawdown_pct,
    ROUND(box_range_pct::numeric * 100, 1) AS box_range_pct,
    ROUND(volatility_ratio::numeric, 3) AS volatility_ratio,
    ROUND(price_position::numeric, 3) AS price_position,
    ROUND(composite_score::numeric, 1) AS score,
    data_points
FROM CandidateStocks
ORDER BY composite_score DESC
LIMIT 200;  -- 粗筛后保留Top 200只股票
```

### 3.3 SQL查询说明

**核心技术**：
- **窗口函数 `OVER (...)`**: 对每只股票独立计算滚动统计量，无需GROUP BY
- **ROWS BETWEEN**: 精确控制回溯窗口大小
- **PARTITION BY code**: 确保不同股票的计算相互独立
- **CTE (WITH子句)**: 分步计算，逻辑清晰，易于调试

**性能优化**：
- 时间过滤：`WHERE month >= NOW() - INTERVAL '10 years'` 减少扫描数据量
- 索引利用：需在 `(code, month DESC)` 上建立复合索引
- 最终筛选：只保留每只股票的最新记录，避免冗余计算

---

## 4. Python层精筛算法

### 4.1 设计目标

SQL层完成初步筛选后（100-200只候选股），Python层负责：
1. 更复杂的统计分析（线性回归、趋势检测）
2. 剔除ST股票、退市风险股
3. 计算更精细的形态指标
4. 准备LLM分析所需的数据

### 4.2 核心函数设计

#### 函数1: 主筛选函数

```python
import pandas as pd
import numpy as np
from scipy.stats import linregress
from data_infra.db import get_db_connection
import logging

logger = logging.getLogger(__name__)

class FlatbottomPreScreener:
    """
    "平底锅"形态股票粗筛器

    两阶段筛选：
    1. SQL层快速筛选（3000+ -> 100-200只）
    2. Python层精细筛选（100-200 -> 50-100只）
    """

    def __init__(self, config: dict = None):
        """
        初始化筛选器

        Args:
            config: 配置参数字典，包含所有可调节参数
        """
        self.config = self._get_default_config()
        if config:
            self.config.update(config)

    def _get_default_config(self) -> dict:
        """默认配置参数"""
        return {
            # SQL层参数
            'HISTORY_LOOKBACK': 120,      # 历史回溯月数
            'RECENT_LOOKBACK': 24,        # 近期窗口月数
            'MIN_DRAWDOWN': -0.40,        # 最小回撤幅度
            'MAX_BOX_RANGE': 0.50,        # 最大箱体振幅
            'MAX_VOLATILITY_RATIO': 0.60, # 最大波动率比
            'MIN_GLORY_RATIO': 3.0,       # 最小辉煌度
            'MIN_PRICE': 3.0,             # 最低股价
            'MIN_DATA_MONTHS': 60,        # 最少数据月数
            'SQL_LIMIT': 200,             # SQL返回记录数上限

            # Python层参数
            'SLOPE_MIN': -0.01,           # 趋势斜率下限
            'SLOPE_MAX': 0.02,            # 趋势斜率上限
            'MIN_R_SQUARED': 0.3,         # 线性拟合最小R²
            'EXCLUDE_ST': True,           # 是否排除ST股票
            'FINAL_LIMIT': 100,           # 最终输出股票数
        }

    def screen(self) -> pd.DataFrame:
        """
        执行完整的粗筛流程

        Returns:
            DataFrame包含筛选后的股票列表及指标
        """
        logger.info("开始SQL层粗筛...")
        sql_candidates = self._sql_screen()
        logger.info(f"SQL层筛选完成，获得 {len(sql_candidates)} 只候选股")

        logger.info("开始Python层精筛...")
        final_candidates = self._python_refine(sql_candidates)
        logger.info(f"精筛完成，最终 {len(final_candidates)} 只股票")

        return final_candidates

    def _sql_screen(self) -> pd.DataFrame:
        """SQL层粗筛"""
        sql = self._build_sql_query()

        conn = get_db_connection()
        df = pd.read_sql(sql, conn)
        conn.close()

        return df

    def _build_sql_query(self) -> str:
        """构建SQL查询（使用配置参数）"""
        cfg = self.config

        return f"""
        WITH
        StockMetrics AS (
            SELECT
                code,
                month,
                close,
                high,
                low,
                volume,

                MAX(high) OVER (
                    PARTITION BY code
                    ORDER BY month
                    ROWS BETWEEN {cfg['HISTORY_LOOKBACK']} PRECEDING AND CURRENT ROW
                ) AS history_high,

                MIN(low) OVER (
                    PARTITION BY code
                    ORDER BY month
                    ROWS BETWEEN {cfg['HISTORY_LOOKBACK']} PRECEDING AND CURRENT ROW
                ) AS history_low,

                MAX(high) OVER (
                    PARTITION BY code
                    ORDER BY month
                    ROWS BETWEEN {cfg['RECENT_LOOKBACK']} PRECEDING AND CURRENT ROW
                ) AS recent_high,

                MIN(low) OVER (
                    PARTITION BY code
                    ORDER BY month
                    ROWS BETWEEN {cfg['RECENT_LOOKBACK']} PRECEDING AND CURRENT ROW
                ) AS recent_low,

                STDDEV(close) OVER (
                    PARTITION BY code
                    ORDER BY month
                    ROWS BETWEEN {cfg['RECENT_LOOKBACK']} PRECEDING AND CURRENT ROW
                ) AS recent_stddev,

                STDDEV(close) OVER (
                    PARTITION BY code
                    ORDER BY month
                    ROWS BETWEEN {cfg['HISTORY_LOOKBACK']} PRECEDING AND {cfg['RECENT_LOOKBACK'] + 1} PRECEDING
                ) AS historical_stddev,

                COUNT(*) OVER (
                    PARTITION BY code
                    ORDER BY month
                    ROWS BETWEEN {cfg['HISTORY_LOOKBACK']} PRECEDING AND CURRENT ROW
                ) AS data_points

            FROM stock_monthly_kline
            WHERE month >= NOW() - INTERVAL '{cfg['HISTORY_LOOKBACK']} months'
        ),

        FilteredStocks AS (
            SELECT
                code,
                close AS current_price,
                history_high,
                history_low,
                recent_high,
                recent_low,

                CASE
                    WHEN history_low > 0 THEN history_high / history_low
                    ELSE NULL
                END AS glory_ratio,

                CASE
                    WHEN history_high > 0 THEN (close - history_high) / history_high
                    ELSE NULL
                END AS drawdown_pct,

                CASE
                    WHEN recent_low > 0 THEN (recent_high - recent_low) / recent_low
                    ELSE NULL
                END AS box_range_pct,

                CASE
                    WHEN historical_stddev > 0 THEN recent_stddev / historical_stddev
                    ELSE NULL
                END AS volatility_ratio,

                CASE
                    WHEN (recent_high - recent_low) > 0
                    THEN (close - recent_low) / (recent_high - recent_low)
                    ELSE 0.5
                END AS price_position,

                data_points

            FROM StockMetrics
            WHERE month = (SELECT MAX(month) FROM stock_monthly_kline)
        ),

        CandidateStocks AS (
            SELECT
                code,
                current_price,
                history_high,
                glory_ratio,
                drawdown_pct,
                box_range_pct,
                volatility_ratio,
                price_position,
                data_points,

                (
                    (ABS(drawdown_pct) - {abs(cfg['MIN_DRAWDOWN'])}) / {abs(cfg['MIN_DRAWDOWN'])} * 40 +
                    ({cfg['MAX_BOX_RANGE']} - box_range_pct) / {cfg['MAX_BOX_RANGE']} * 30 +
                    ({cfg['MAX_VOLATILITY_RATIO']} - volatility_ratio) / {cfg['MAX_VOLATILITY_RATIO']} * 30
                ) AS composite_score

            FROM FilteredStocks
            WHERE
                data_points >= {cfg['MIN_DATA_MONTHS']}
                AND glory_ratio >= {cfg['MIN_GLORY_RATIO']}
                AND drawdown_pct < {cfg['MIN_DRAWDOWN']}
                AND box_range_pct < {cfg['MAX_BOX_RANGE']}
                AND volatility_ratio < {cfg['MAX_VOLATILITY_RATIO']}
                AND price_position < 0.80
                AND price_position > 0.05
                AND current_price >= {cfg['MIN_PRICE']}
                AND history_high IS NOT NULL
                AND drawdown_pct IS NOT NULL
                AND box_range_pct IS NOT NULL
        )

        SELECT
            code,
            ROUND(current_price::numeric, 2) AS current_price,
            ROUND(history_high::numeric, 2) AS history_high,
            ROUND(glory_ratio::numeric, 2) AS glory_ratio,
            ROUND(drawdown_pct::numeric * 100, 1) AS drawdown_pct,
            ROUND(box_range_pct::numeric * 100, 1) AS box_range_pct,
            ROUND(volatility_ratio::numeric, 3) AS volatility_ratio,
            ROUND(price_position::numeric, 3) AS price_position,
            ROUND(composite_score::numeric, 1) AS score,
            data_points
        FROM CandidateStocks
        ORDER BY composite_score DESC
        LIMIT {cfg['SQL_LIMIT']};
        """

    def _python_refine(self, candidates: pd.DataFrame) -> pd.DataFrame:
        """Python层精细筛选"""
        refined = []

        for _, row in candidates.iterrows():
            code = row['code']

            # 1. 排除ST股票
            if self.config['EXCLUDE_ST']:
                if self._is_st_stock(code):
                    logger.debug(f"{code}: 跳过（ST股票）")
                    continue

            # 2. 获取近期价格数据
            prices = self._get_recent_prices(code, self.config['RECENT_LOOKBACK'])

            if len(prices) < 12:  # 至少需要12个月数据
                logger.debug(f"{code}: 跳过（数据不足）")
                continue

            # 3. 线性回归分析（检测趋势）
            slope, r_squared = self._calculate_trend(prices)

            # 4. 判断是否符合"平底锅"标准
            if not (self.config['SLOPE_MIN'] <= slope <= self.config['SLOPE_MAX']):
                logger.debug(f"{code}: 跳过（斜率={slope:.4f}，不在范围内）")
                continue

            if r_squared < self.config['MIN_R_SQUARED']:
                logger.debug(f"{code}: 跳过（R²={r_squared:.3f}，拟合度不足）")
                continue

            # 5. 添加到最终结果
            refined.append({
                **row.to_dict(),
                'slope': round(slope, 4),
                'r_squared': round(r_squared, 3)
            })

        # 转为DataFrame并排序
        result = pd.DataFrame(refined)

        if len(result) == 0:
            logger.warning("精筛后无符合条件的股票！")
            return result

        # 按综合得分排序
        result = result.sort_values('score', ascending=False)

        # 限制最终输出数量
        return result.head(self.config['FINAL_LIMIT'])

    def _is_st_stock(self, code: str) -> bool:
        """判断是否为ST股票（通过股票名称）"""
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT name
            FROM stock_monthly_kline
            WHERE code = %s
            ORDER BY month DESC
            LIMIT 1
        """, (code,))

        result = cur.fetchone()
        conn.close()

        if result is None:
            return False

        name = result[0]

        # ST、*ST、退市等标识
        st_markers = ['ST', '*ST', 'S*ST', 'SST', '退市', 'PT']
        return any(marker in name for marker in st_markers)

    def _get_recent_prices(self, code: str, months: int) -> np.ndarray:
        """获取指定股票的近期收盘价序列"""
        conn = get_db_connection()

        df = pd.read_sql(f"""
            SELECT close
            FROM stock_monthly_kline
            WHERE code = %s
            ORDER BY month DESC
            LIMIT {months}
        """, conn, params=(code,))

        conn.close()

        # 反转顺序（从旧到新）
        return df['close'].values[::-1]

    def _calculate_trend(self, prices: np.ndarray) -> tuple:
        """
        计算价格序列的线性趋势

        Returns:
            (slope, r_squared): 斜率和R²值
        """
        x = np.arange(len(prices))

        # 归一化价格（以第一个价格为基准）
        y = prices / prices[0]

        slope, intercept, r_value, p_value, std_err = linregress(x, y)

        return slope, r_value ** 2
```

#### 函数2: 配置管理

```python
def load_config_from_file(filepath: str) -> dict:
    """从JSON/YAML文件加载配置"""
    import json

    with open(filepath, 'r') as f:
        config = json.load(f)

    return config

def get_preset_config(preset: str) -> dict:
    """获取预设配置"""
    presets = {
        'conservative': {  # 保守配置（严格筛选）
            'MIN_DRAWDOWN': -0.50,
            'MAX_BOX_RANGE': 0.40,
            'MAX_VOLATILITY_RATIO': 0.50,
            'MIN_GLORY_RATIO': 4.0,
            'SLOPE_MIN': -0.005,
            'SLOPE_MAX': 0.015,
        },
        'balanced': {  # 均衡配置（默认）
            'MIN_DRAWDOWN': -0.40,
            'MAX_BOX_RANGE': 0.50,
            'MAX_VOLATILITY_RATIO': 0.60,
            'MIN_GLORY_RATIO': 3.0,
        },
        'aggressive': {  # 进取配置（放宽标准）
            'MIN_DRAWDOWN': -0.30,
            'MAX_BOX_RANGE': 0.60,
            'MAX_VOLATILITY_RATIO': 0.70,
            'MIN_GLORY_RATIO': 2.5,
            'SLOPE_MIN': -0.02,
            'SLOPE_MAX': 0.03,
        }
    }

    return presets.get(preset, {})
```

### 4.3 CLI命令行工具

```python
# visualization/find_flatbottom.py

import argparse
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(
        description='"平底锅"形态股票粗筛工具'
    )

    # 预设配置
    parser.add_argument(
        '--preset',
        choices=['conservative', 'balanced', 'aggressive'],
        default='balanced',
        help='使用预设配置'
    )

    # 自定义参数（覆盖预设）
    parser.add_argument('--min-drawdown', type=float, help='最小回撤幅度')
    parser.add_argument('--max-box-range', type=float, help='最大箱体振幅')
    parser.add_argument('--max-volatility-ratio', type=float, help='最大波动率比')
    parser.add_argument('--min-glory-ratio', type=float, help='最小辉煌度')
    parser.add_argument('--slope-min', type=float, help='斜率下限')
    parser.add_argument('--slope-max', type=float, help='斜率上限')

    # 输出选项
    parser.add_argument(
        '--export-csv',
        type=str,
        default='output/flatbottom_candidates.csv',
        help='导出CSV文件路径'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='限制输出股票数量'
    )

    args = parser.parse_args()

    # 构建配置
    config = get_preset_config(args.preset)

    # 应用自定义参数
    if args.min_drawdown is not None:
        config['MIN_DRAWDOWN'] = args.min_drawdown
    if args.max_box_range is not None:
        config['MAX_BOX_RANGE'] = args.max_box_range
    if args.max_volatility_ratio is not None:
        config['MAX_VOLATILITY_RATIO'] = args.max_volatility_ratio
    if args.min_glory_ratio is not None:
        config['MIN_GLORY_RATIO'] = args.min_glory_ratio
    if args.slope_min is not None:
        config['SLOPE_MIN'] = args.slope_min
    if args.slope_max is not None:
        config['SLOPE_MAX'] = args.slope_max
    if args.limit is not None:
        config['FINAL_LIMIT'] = args.limit

    # 执行筛选
    logger.info(f"使用配置: {args.preset}")
    logger.info(f"主要参数: 回撤>{abs(config.get('MIN_DRAWDOWN', 0.4))*100:.0f}%, "
                f"箱体<{config.get('MAX_BOX_RANGE', 0.5)*100:.0f}%, "
                f"波动率比<{config.get('MAX_VOLATILITY_RATIO', 0.6):.2f}")

    screener = FlatbottomPreScreener(config)
    results = screener.screen()

    # 输出结果
    if len(results) == 0:
        logger.warning("未找到符合条件的股票！建议放宽筛选参数。")
        sys.exit(0)

    logger.info(f"\n筛选完成！共找到 {len(results)} 只候选股票\n")

    # 打印Top 20
    print("\nTop 20 候选股票:\n")
    print(results.head(20).to_string(index=False))

    # 导出CSV
    output_path = Path(args.export_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results.to_csv(output_path, index=False, encoding='utf-8-sig')
    logger.info(f"\n完整结果已保存到: {output_path}")

if __name__ == "__main__":
    main()
```

---

## 5. 使用指南

### 5.1 快速开始

```bash
# 使用默认配置（均衡模式）
python -m visualization.find_flatbottom

# 使用保守配置（更严格的筛选）
python -m visualization.find_flatbottom --preset conservative

# 使用进取配置（放宽标准）
python -m visualization.find_flatbottom --preset aggressive

# 自定义参数
python -m visualization.find_flatbottom \
  --min-drawdown -0.50 \
  --max-box-range 0.40 \
  --limit 50
```

### 5.2 参数调优建议

#### 场景1: 牛市初期（适度进取）
```bash
python -m visualization.find_flatbottom --preset aggressive --limit 150
```

#### 场景2: 震荡市（稳健配置）
```bash
python -m visualization.find_flatbottom --preset balanced
```

#### 场景3: 熊市/高风险期（极度保守）
```bash
python -m visualization.find_flatbottom \
  --preset conservative \
  --min-drawdown -0.60 \
  --limit 30
```

### 5.3 输出说明

CSV输出包含以下字段：

| 字段名 | 说明 | 示例值 |
|:---|:---|:---|
| code | 股票代码 | 300444.SZ |
| current_price | 当前价格 | 8.25 |
| history_high | 历史高点 | 26.80 |
| glory_ratio | 辉煌度 | 4.52 |
| drawdown_pct | 回撤幅度(%) | -69.2 |
| box_range_pct | 箱体振幅(%) | 38.5 |
| volatility_ratio | 波动率比 | 0.45 |
| price_position | 箱体位置 | 0.42 |
| score | 综合得分 | 85.3 |
| slope | 趋势斜率 | 0.008 |
| r_squared | 拟合优度 | 0.65 |

---

## 6. 性能优化

### 6.1 数据库优化

#### 必需索引

```sql
-- 复合索引（支持窗口函数查询）
CREATE INDEX idx_monthly_code_time ON stock_monthly_kline (code, month DESC);

-- 单列索引（支持时间范围过滤）
CREATE INDEX idx_monthly_time ON stock_monthly_kline (month DESC);
```

#### 分析统计信息

```sql
-- 更新表统计信息（提高查询计划质量）
ANALYZE stock_monthly_kline;
```

### 6.2 查询性能预估

基于月K线表（假设5000只股票 × 120个月 = 60万条记录）：

| 操作 | 预计耗时 | 说明 |
|:---|:---|:---|
| SQL粗筛 | 2-5秒 | 利用索引+窗口函数 |
| Python精筛（100只） | 5-10秒 | 逐只分析+数据库查询 |
| **总耗时** | **<15秒** | 端到端全流程 |

### 6.3 优化建议

1. **使用连接池**: 避免频繁创建数据库连接
2. **批量查询**: Python层获取价格数据时，改为一次性批量查询
3. **缓存结果**: 将SQL筛选结果缓存，避免重复计算
4. **并行处理**: 对Python层的逐只分析使用多进程加速

---

## 7. 扩展功能

### 7.1 参数敏感性分析

```python
def parameter_sensitivity_analysis():
    """分析参数变化对筛选结果的影响"""
    base_config = get_preset_config('balanced')

    # 测试不同回撤阈值
    for drawdown in [-0.30, -0.40, -0.50, -0.60]:
        config = {**base_config, 'MIN_DRAWDOWN': drawdown}
        screener = FlatbottomPreScreener(config)
        results = screener.screen()
        print(f"回撤阈值={drawdown}: 筛选出 {len(results)} 只")
```

### 7.2 回测验证

对历史筛选结果进行回测，验证策略有效性：

```python
def backtest_screening_strategy(start_date, end_date):
    """
    回测筛选策略

    模拟在历史时间点运行筛选器，
    观察筛选出的股票在未来N个月的表现
    """
    pass  # 待实现
```

---

## 8. 常见问题

### Q1: SQL查询耗时过长怎么办？

**A**:
1. 确认已创建必需的索引
2. 减小 `HISTORY_LOOKBACK` 窗口（如改为60个月）
3. 使用 `EXPLAIN ANALYZE` 分析查询计划

### Q2: 筛选结果为空？

**A**:
1. 检查参数是否过于严格（尝试 `--preset aggressive`）
2. 确认数据库中有足够的历史数据
3. 查看日志中的跳过原因

### Q3: 如何处理数据质量问题？

**A**:
- SQL层已包含 `IS NOT NULL` 检查
- Python层会验证数据点数量
- 可添加异常值检测逻辑（如价格突变）

---

## 9. 附录

### A. 完整配置参数表

| 参数名 | 类型 | 默认值 | 范围 | 说明 |
|:---|:---|:---|:---|:---|
| HISTORY_LOOKBACK | int | 120 | 60-180 | 历史回溯月数 |
| RECENT_LOOKBACK | int | 24 | 12-36 | 近期窗口月数 |
| MIN_DRAWDOWN | float | -0.40 | -0.7~-0.3 | 最小回撤幅度 |
| MAX_BOX_RANGE | float | 0.50 | 0.3-0.6 | 最大箱体振幅 |
| MAX_VOLATILITY_RATIO | float | 0.60 | 0.4-0.8 | 最大波动率比 |
| MIN_GLORY_RATIO | float | 3.0 | 2.0-5.0 | 最小辉煌度 |
| MIN_PRICE | float | 3.0 | 2.0-5.0 | 最低股价 |
| MIN_DATA_MONTHS | int | 60 | 36-120 | 最少数据月数 |
| SLOPE_MIN | float | -0.01 | -0.02~0 | 斜率下限 |
| SLOPE_MAX | float | 0.02 | 0~0.03 | 斜率上限 |
| MIN_R_SQUARED | float | 0.3 | 0.2-0.5 | 最小拟合优度 |
| EXCLUDE_ST | bool | True | - | 是否排除ST股 |
| SQL_LIMIT | int | 200 | 100-500 | SQL返回上限 |
| FINAL_LIMIT | int | 100 | 50-200 | 最终输出上限 |

### B. 数学公式汇总

1. **辉煌度**: `glory_ratio = history_high / history_low`
2. **回撤幅度**: `drawdown = (current_price - history_high) / history_high`
3. **箱体振幅**: `box_range = (recent_high - recent_low) / recent_low`
4. **波动率比**: `volatility_ratio = recent_stddev / historical_stddev`
5. **价格位置**: `price_position = (current_price - recent_low) / (recent_high - recent_low)`
6. **综合得分**: `score = 40×归一化回撤 + 30×归一化箱体 + 30×归一化波动率`

---

**文档版本**: v1.0
**最后更新**: 2026-01-27
**作者**: Claude Code Team

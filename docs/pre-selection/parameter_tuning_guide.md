# 平底锅选股参数调优指南

## 1. 三个预设的核心差异

| 维度 | Conservative（保守） | Balanced（均衡） | Aggressive（进取） |
|------|---------------------|------------------|-------------------|
| **目标场景** | 熊市末期、高风险规避 | 震荡市、日常筛选 | 牛市初期、机会挖掘 |
| **预期结果数** | 30-50只 | 50-100只 | 100-150只 |
| **风险偏好** | 极低风险 | 中等风险 | 高风险高回报 |

---

## 2. 关键参数调优建议

### 2.1 MIN_GLORY_RATIO（正价段辉煌度倍率）

**当前设置**：
- Conservative: 3.5（曾涨3.5倍）
- Balanced: 3.0（曾涨3倍）
- Aggressive: 2.5（曾涨2.5倍）

**调优建议**：

#### 📊 数据驱动的调整方法
```sql
-- 查询当前市场的辉煌度分布
SELECT
    CASE
        WHEN glory_ratio < 2.0 THEN '< 2x'
        WHEN glory_ratio < 3.0 THEN '2-3x'
        WHEN glory_ratio < 5.0 THEN '3-5x'
        WHEN glory_ratio < 10.0 THEN '5-10x'
        ELSE '> 10x'
    END AS glory_range,
    COUNT(*) as stock_count,
    ROUND(AVG(drawdown_pct), 1) as avg_drawdown,
    ROUND(AVG(score), 1) as avg_score
FROM stock_flatbottom_preselect
WHERE glory_type = 'ratio'
GROUP BY glory_range
ORDER BY MIN(glory_ratio);
```

#### 🎯 推荐调整策略

**场景1：结果太少（< 30只）**
```python
# 降低辉煌度要求
'MIN_GLORY_RATIO': 2.0,  # 从 3.0 降至 2.0
```

**场景2：结果太多（> 150只）**
```python
# 提高辉煌度要求
'MIN_GLORY_RATIO': 4.0,  # 从 3.0 升至 4.0
```

**场景3：市场风格切换（大盘股 vs 小盘股）**
```python
# 大盘股通常辉煌度较低（波动小）
'MIN_GLORY_RATIO': 2.0,  # 适配大盘蓝筹

# 小盘股辉煌度较高（波动大）
'MIN_GLORY_RATIO': 5.0,  # 适配小盘成长
```

**⚠️ 警告**：
- 不要设置 < 1.5（失去"曾经辉煌"语义）
- 不要设置 > 15（过滤掉几乎所有股票）

---

### 2.2 MIN_DRAWDOWN（最小回撤幅度）

**当前设置**：
- Conservative: -0.50（-50%回撤）
- Balanced: -0.40（-40%回撤）
- Aggressive: -0.30（-30%回撤）

**调优建议**：

#### 📊 查询当前回撤分布
```sql
-- 查看筛选结果的回撤分布
SELECT
    CASE
        WHEN drawdown_pct > -30 THEN '0-30%'
        WHEN drawdown_pct > -50 THEN '30-50%'
        WHEN drawdown_pct > -70 THEN '50-70%'
        WHEN drawdown_pct > -85 THEN '70-85%'
        ELSE '> 85%'
    END AS drawdown_range,
    COUNT(*) as stock_count,
    ROUND(AVG(glory_ratio), 2) as avg_glory,
    ROUND(AVG(score), 1) as avg_score
FROM stock_flatbottom_preselect
GROUP BY drawdown_range
ORDER BY MAX(drawdown_pct) DESC;
```

#### 🎯 推荐调整策略

**A股市场特点**：
- **牛市顶部 → 熊市底部**：通常跌幅 50-80%
- **题材股/科技股**：跌幅可达 80-90%
- **蓝筹股/银行股**：跌幅通常 30-50%

**根据市场阶段调整**：

```python
# 熊市末期（2018年底、2022年底）
'MIN_DRAWDOWN': -0.70,  # 寻找跌幅 > 70% 的深度回调股票

# 震荡市（2019-2020、2023-2024）
'MIN_DRAWDOWN': -0.50,  # 寻找跌幅 > 50% 的中度回调

# 牛市初期/中期（2020-2021、2024-2025）
'MIN_DRAWDOWN': -0.30,  # 寻找跌幅 > 30% 的浅度回调
```

**⚠️ 警告**：
- 过深的回撤（< -90%）可能是基本面恶化（退市风险）
- 过浅的回撤（> -20%）可能还未充分调整

**💡 组合策略**：
```python
# 严格模式：深度回调 + 高辉煌度
'MIN_DRAWDOWN': -0.70,
'MIN_GLORY_RATIO': 5.0,
# 结果：少而精，曾经的大牛股深度回调

# 宽松模式：中度回调 + 中等辉煌度
'MIN_DRAWDOWN': -0.40,
'MIN_GLORY_RATIO': 2.5,
# 结果：多而广，涵盖更多机会
```

---

### 2.3 MIN_R_SQUARED（最小拟合度）

**当前设置**：
- Conservative: 0.40（R² ≥ 40%）
- Balanced: 0.30（R² ≥ 30%）
- Aggressive: 0.25（R² ≥ 25%）

**调优建议**：

#### 📊 查询 R² 分布
```sql
-- 查看线性拟合度分布
SELECT
    CASE
        WHEN r_squared < 0.2 THEN '< 20%'
        WHEN r_squared < 0.4 THEN '20-40%'
        WHEN r_squared < 0.6 THEN '40-60%'
        WHEN r_squared < 0.8 THEN '60-80%'
        ELSE '> 80%'
    END AS r2_range,
    COUNT(*) as stock_count,
    ROUND(AVG(slope), 4) as avg_slope,
    ROUND(AVG(score), 1) as avg_score
FROM stock_flatbottom_preselect
GROUP BY r2_range
ORDER BY MIN(r_squared);
```

#### 🎯 推荐调整策略

**R² 的金融含义**：
- **R² > 0.7**：趋势非常规律（强趋势股）
- **R² = 0.4-0.7**：趋势较规律（平稳横盘）
- **R² < 0.3**：趋势杂乱（高波动/无规律）

**根据选股目标调整**：

```python
# 目标1：寻找"真正的平底锅"（横盘稳定）
'MIN_R_SQUARED': 0.50,  # 高拟合度，过滤掉波动大的股票
'SLOPE_MIN': -0.005,
'SLOPE_MAX': 0.005,
# 结果：非常稳定的横盘股票

# 目标2：寻找"底部反转"（允许小幅上涨）
'MIN_R_SQUARED': 0.30,  # 中等拟合度
'SLOPE_MIN': 0.0,
'SLOPE_MAX': 0.02,
# 结果：有上涨迹象的底部股票

# 目标3：广撒网（包含各种可能）
'MIN_R_SQUARED': 0.20,  # 低拟合度
'SLOPE_MIN': -0.02,
'SLOPE_MAX': 0.03,
# 结果：涵盖更多机会，但噪音较大
```

**⚠️ 警告**：
- R² < 0.15：基本无规律，可能是垃圾股
- R² > 0.90：过于规律，可能是僵尸股（无成交量）

**💡 与斜率的联合调优**：
```python
# 策略A：严格横盘（保守）
'MIN_R_SQUARED': 0.50,
'SLOPE_MIN': -0.005,
'SLOPE_MAX': 0.005,

# 策略B：允许微涨（均衡）
'MIN_R_SQUARED': 0.30,
'SLOPE_MIN': -0.01,
'SLOPE_MAX': 0.02,

# 策略C：反转初期（进取）
'MIN_R_SQUARED': 0.25,
'SLOPE_MIN': 0.0,
'SLOPE_MAX': 0.03,
```

---

## 3. 调优工作流程

### Step 1: 基线测试
```bash
# 运行默认配置
uv run python -m flatbottom_pipeline.selection.find_flatbottom --preset balanced
```

### Step 2: 分析结果分布
```sql
-- 执行上述查询 SQL，了解当前市场特征
SELECT
    COUNT(*) as total,
    ROUND(AVG(glory_ratio), 2) as avg_glory,
    ROUND(AVG(drawdown_pct), 1) as avg_drawdown,
    ROUND(AVG(r_squared), 3) as avg_r2,
    MIN(glory_ratio) as min_glory,
    MAX(drawdown_pct) as max_drawdown
FROM stock_flatbottom_preselect;
```

### Step 3: 调整参数
```python
# 在 selection/config.py 中修改
PRESETS = {
    'balanced': {
        # 根据 Step 2 的分析结果调整
        'MIN_GLORY_RATIO': 2.5,     # 降低以获得更多结果
        'MIN_DRAWDOWN': -0.50,      # 提高回撤要求
        'MIN_R_SQUARED': 0.25,      # 降低拟合度要求
        ...
    }
}
```

### Step 4: 回测验证
```bash
# 重新运行筛选
uv run python -m flatbottom_pipeline.selection.find_flatbottom --preset balanced

# 对比前后结果数量变化
```

### Step 5: 历史验证（可选）
```python
# 人工检查 Top 10 股票的历史走势
# 验证是否符合"平底锅"形态的预期
```

---

## 4. 常见场景的预设调整

### 场景1：市场刚经历暴跌（如2022年底）
```python
'MIN_DRAWDOWN': -0.80,      # 寻找深度回调
'MIN_GLORY_RATIO': 4.0,     # 高辉煌度（曾经的牛股）
'MIN_R_SQUARED': 0.30,      # 中等拟合度
```

### 场景2：市场处于震荡期（如2023-2024）
```python
'MIN_DRAWDOWN': -0.50,      # 中度回调
'MIN_GLORY_RATIO': 3.0,     # 中等辉煌度
'MIN_R_SQUARED': 0.35,      # 稍高拟合度（过滤噪音）
```

### 场景3：寻找科技股/题材股
```python
'MIN_DRAWDOWN': -0.70,      # 科技股跌幅大
'MIN_GLORY_RATIO': 5.0,     # 科技股辉煌度高
'MIN_R_SQUARED': 0.20,      # 低拟合度（科技股波动大）
'MAX_VOLATILITY_RATIO': 0.80,  # 允许更高波动
```

### 场景4：寻找蓝筹股/银行股
```python
'MIN_DRAWDOWN': -0.40,      # 蓝筹跌幅小
'MIN_GLORY_RATIO': 2.0,     # 蓝筹辉煌度低
'MIN_R_SQUARED': 0.50,      # 高拟合度（蓝筹走势稳）
'MAX_VOLATILITY_RATIO': 0.40,  # 低波动
```

---

## 5. 快速诊断工具

创建诊断脚本 `selection/diagnose.py`：

```python
from data_infra.db import get_db_connection
import pandas as pd

def diagnose_parameters():
    """诊断当前参数设置是否合理"""
    conn = get_db_connection()

    # 查询结果统计
    stats = pd.read_sql("""
        SELECT
            COUNT(*) as total_stocks,
            ROUND(AVG(glory_ratio), 2) as avg_glory,
            ROUND(AVG(drawdown_pct), 1) as avg_drawdown,
            ROUND(AVG(r_squared), 3) as avg_r2,
            MIN(glory_ratio) as min_glory,
            MAX(drawdown_pct) as max_drawdown
        FROM stock_flatbottom_preselect
    """, conn)

    print("\n" + "="*60)
    print("参数诊断报告")
    print("="*60)
    print(f"筛选结果数量: {stats['total_stocks'][0]}")
    print(f"平均辉煌度:   {stats['avg_glory'][0]:.2f}x")
    print(f"平均回撤:     {stats['avg_drawdown'][0]:.1f}%")
    print(f"平均R²:       {stats['avg_r2'][0]:.3f}")
    print("="*60)

    # 建议
    total = stats['total_stocks'][0]
    if total < 30:
        print("⚠️  结果太少，建议：")
        print("  - 降低 MIN_GLORY_RATIO (如 3.0 → 2.5)")
        print("  - 提高 MIN_DRAWDOWN (如 -0.40 → -0.30)")
    elif total > 150:
        print("⚠️  结果太多，建议：")
        print("  - 提高 MIN_GLORY_RATIO (如 3.0 → 3.5)")
        print("  - 降低 MIN_DRAWDOWN (如 -0.40 → -0.50)")
    else:
        print("✓ 结果数量合理（50-100只）")

    conn.close()

if __name__ == '__main__':
    diagnose_parameters()
```

运行诊断：
```bash
uv run python selection/diagnose.py
```

---

## 6. 总结：推荐的调优顺序

1. **MIN_GLORY_RATIO**（辉煌度）→ 最重要，决定"曾经的辉煌程度"
2. **MIN_DRAWDOWN**（回撤）→ 次重要，决定"调整的深度"
3. **MIN_R_SQUARED**（拟合度）→ 较重要，决定"底部的稳定性"
4. **其他参数**（波动率、箱体振幅等）→ 微调

**建议每次只调整1-2个参数，观察效果后再继续调整。**

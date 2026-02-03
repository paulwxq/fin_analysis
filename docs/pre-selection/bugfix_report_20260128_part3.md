# Bug修复报告（第四轮）- 2026-01-28

## 审核发现

用户在第四轮代码审核中发现了**2个重要问题**：

| Bug# | 问题描述 | 严重性 | 位置 |
|------|---------|-------|------|
| #8 | save_to_db异常处理掩盖原始错误 | ⚠️ 高 | find_flatbottom.py:508-510 |
| #9 | CLI参数覆盖后未验证配置 | ⚠️ 中等 | find_flatbottom.py:644-651 |

---

## Bug #8: save_to_db异常处理掩盖原始错误

### 问题分析

**位置**: `selection/find_flatbottom.py:508-510`

**问题代码**:
```python
def save_to_db(self, results: pd.DataFrame) -> int:
    conn = None
    cursor = None
    try:
        conn = get_db_connection()  # 如果这里失败，conn仍为None
        cursor = conn.cursor()
        # ... 操作 ...
        conn.commit()

    except Exception as e:
        conn.rollback()  # ❌ 如果conn是None，触发AttributeError
        logger.error(f"Database write failed: {e}")
        raise

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
```

**问题场景**:
1. `get_db_connection()` 失败（例如数据库不可用）
2. 抛出异常时 `conn` 仍为 `None`
3. except块中调用 `conn.rollback()` 触发 `AttributeError: 'NoneType' object has no attribute 'rollback'`
4. **原始错误被掩盖**，用户看到的是AttributeError而非真正的连接错误

**影响**:
- **严重性**: 高
- **影响范围**: 所有数据库写入操作
- **后果**: 调试困难，无法看到真正的数据库连接错误

### 最佳实践修复

```python
def save_to_db(self, results: pd.DataFrame) -> int:
    """
    Stage 4a: UPSERT results to database.

    Args:
        results: Screening results

    Returns:
        Number of records inserted/updated
    """
    if results.empty:
        logger.warning("Results are empty, skipping database write")
        return 0

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # UPSERT SQL
        upsert_sql = """
            INSERT INTO stock_flatbottom_preselect (
                code, name, current_price, history_high, glory_ratio, glory_type,
                drawdown_pct, box_range_pct, volatility_ratio, price_position,
                slope, r_squared, score, screening_preset, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                COALESCE((SELECT created_at FROM stock_flatbottom_preselect WHERE code = %s), NOW()),
                NOW()
            )
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                current_price = EXCLUDED.current_price,
                history_high = EXCLUDED.history_high,
                glory_ratio = EXCLUDED.glory_ratio,
                glory_type = EXCLUDED.glory_type,
                drawdown_pct = EXCLUDED.drawdown_pct,
                box_range_pct = EXCLUDED.box_range_pct,
                volatility_ratio = EXCLUDED.volatility_ratio,
                price_position = EXCLUDED.price_position,
                slope = EXCLUDED.slope,
                r_squared = EXCLUDED.r_squared,
                score = EXCLUDED.score,
                screening_preset = EXCLUDED.screening_preset,
                updated_at = NOW()
        """

        # Build data tuples
        data_tuples = []
        for _, row in results.iterrows():
            code = row['code']
            data_tuples.append((
                code,
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
                self.preset,
                code  # For COALESCE created_at lookup
            ))

        # Batch UPSERT
        cursor.executemany(upsert_sql, data_tuples)
        conn.commit()

        inserted_count = len(data_tuples)
        logger.info(f"✓ Successfully wrote/updated {inserted_count} records to database")

        return inserted_count

    except Exception as e:
        # ✅ 修复：仅在conn非None时才rollback
        if conn is not None:
            try:
                conn.rollback()
            except Exception as rollback_error:
                logger.warning(f"Rollback failed: {rollback_error}")

        logger.error(f"Database write failed: {e}")
        raise

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
```

**关键改进**:
1. **条件回滚**: 仅在 `conn is not None` 时才调用 `rollback()`
2. **安全回滚**: 将 `rollback()` 包装在 try-except 中（避免回滚本身失败）
3. **保留原始错误**: 确保原始异常正确传播给调用者

---

## Bug #9: CLI参数覆盖后未验证配置

### 问题分析

**位置**: `selection/find_flatbottom.py:644-651`

**问题代码**:
```python
# Get configuration with overrides
from selection.config import get_config
config = get_config(args.preset, **overrides)

# Initialize screener with custom config
screener = FlatbottomScreener(preset=args.preset)  # __init__中验证预设配置
screener.config = config  # ❌ 直接覆盖，绕过验证！
screener.preset = args.preset
```

**问题场景**:
```bash
# 用户传入无效参数
python -m selection.find_flatbottom \
  --preset balanced \
  --min-drawdown 0.5      # ❌ 应为负数，但未验证
  --min-glory-ratio 0.8   # ❌ 应 > 1.0，但未验证
  --slope-min 0.05 \
  --slope-max 0.02        # ❌ slope-min > slope-max，但未验证
```

**执行流程**:
1. `FlatbottomScreener.__init__` 验证预设配置 ✅
2. `get_config(preset, **overrides)` 应用CLI参数覆盖
3. `screener.config = config` **直接覆盖，跳过验证** ❌
4. 带着无效配置运行，可能产生错误结果或运行时错误

**影响**:
- **严重性**: 中等
- **影响范围**: 所有CLI参数覆盖场景
- **后果**:
  - 无效配置导致SQL语义错误（例如MIN_DRAWDOWN为正数）
  - 逻辑冲突导致筛选结果错误（例如SLOPE_MIN > SLOPE_MAX）
  - 运行时异常（例如MIN_R_SQUARED > 1.0）

### 最佳实践修复

**方案1: 在覆盖后验证配置**（推荐）

```python
def main():
    """Main entry point for command-line execution."""
    import argparse
    parser = argparse.ArgumentParser(
        description='Flatbottom stock screener',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use preset
  python -m selection.find_flatbottom --preset balanced

  # Override parameters
  python -m selection.find_flatbottom --preset balanced --min-drawdown -0.50 --exclude-st
        """
    )

    # ... 省略参数定义 ...

    args = parser.parse_args()

    # Collect CLI overrides
    overrides = {}
    if args.min_drawdown is not None:
        overrides['MIN_DRAWDOWN'] = args.min_drawdown
    # ... 省略其他参数收集 ...

    if args.exclude_st:
        overrides['EXCLUDE_ST'] = True
    if args.exclude_blacklist:
        overrides['EXCLUDE_BLACKLIST'] = True

    # Get configuration with overrides
    from selection.config import get_config, validate_config
    config = get_config(args.preset, **overrides)

    # ✅ 修复：验证覆盖后的配置
    try:
        validate_config(config)
    except AssertionError as e:
        logger.error(f"Invalid configuration: {e}")
        print(f"\n❌ Error: {e}")
        print("\nPlease check your command-line parameters.")
        return

    # Initialize screener with validated config
    screener = FlatbottomScreener(preset=args.preset)
    screener.config = config
    screener.preset = args.preset

    # Show config if requested
    if args.show_config:
        print_config(screener.config)
        if overrides:
            print("\nCommand-line overrides:")
            for key, value in overrides.items():
                print(f"  {key}: {value}")
        return

    # Run screening
    results = screener.run()

    # ... 省略其余代码 ...
```

**方案2: 修改get_config内部自动验证**（更彻底）

```python
# selection/config.py

def get_config(preset: str = 'balanced', **overrides) -> dict:
    """
    获取配置（支持参数覆盖）

    Args:
        preset: 预设名称 ('conservative' | 'balanced' | 'aggressive')
        **overrides: 覆盖参数（例如 MIN_DRAWDOWN=-0.50）

    Returns:
        配置字典

    Raises:
        AssertionError: 配置验证失败
    """
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}. Available: {list(PRESETS.keys())}")

    config = PRESETS[preset].copy()
    config.update(overrides)

    # ✅ 自动验证配置
    validate_config(config)

    return config
```

**推荐**: 使用**方案2**，在 `get_config` 内部自动验证，确保任何时候获取的配置都是有效的。

---

## 验证测试

### 测试Bug #8修复

```python
# 测试场景：数据库连接失败
import unittest
from unittest.mock import patch, MagicMock
from selection.find_flatbottom import FlatbottomScreener
import pandas as pd

class TestSaveToDbExceptionHandling(unittest.TestCase):

    def test_connection_failure_preserves_original_error(self):
        """测试连接失败时保留原始错误"""
        screener = FlatbottomScreener(preset='balanced')
        results = pd.DataFrame({
            'code': ['600000.SH'],
            'name': ['测试股票'],
            'score': [50.0]
        })

        # Mock get_db_connection to raise exception
        with patch('selection.find_flatbottom.get_db_connection') as mock_conn:
            mock_conn.side_effect = Exception("Database connection failed")

            # 应该看到原始错误，而非AttributeError
            with self.assertRaises(Exception) as context:
                screener.save_to_db(results)

            # 验证错误消息是原始错误
            self.assertIn("Database connection failed", str(context.exception))
            # 验证不是AttributeError
            self.assertNotIsInstance(context.exception, AttributeError)
```

### 测试Bug #9修复

```bash
# 测试场景1：无效的MIN_DRAWDOWN（正数）
$ python -m selection.find_flatbottom --preset balanced --min-drawdown 0.5

❌ Error: MIN_DRAWDOWN 必须为负数
Please check your command-line parameters.

# 测试场景2：无效的slope范围（min > max）
$ python -m selection.find_flatbottom \
    --preset balanced \
    --slope-min 0.05 \
    --slope-max 0.02

❌ Error: SLOPE_MIN 必须小于 SLOPE_MAX
Please check your command-line parameters.

# 测试场景3：无效的MIN_R_SQUARED（超出范围）
$ python -m selection.find_flatbottom --preset balanced --min-r-squared 1.5

❌ Error: MIN_R_SQUARED 必须在 (0, 1] 区间
Please check your command-line parameters.
```

---

## 修复总结

### Bug #8: 异常处理修复

| 修复点 | 修复前 | 修复后 |
|--------|--------|--------|
| rollback调用 | 无条件调用 | 仅在conn非None时调用 |
| rollback安全性 | 可能失败 | try-except包装 |
| 错误信息 | 可能被掩盖 | 保留原始错误 |

### Bug #9: 配置验证修复

| 修复点 | 修复前 | 修复后 |
|--------|--------|--------|
| 验证时机 | 仅在__init__验证预设 | 在get_config中自动验证 |
| CLI覆盖 | 未验证 | 自动验证 |
| 错误提示 | 运行时失败 | 启动时快速失败 |
| 用户体验 | 混乱的错误消息 | 清晰的参数错误提示 |

---

## 最佳实践总结

### 1. 异常处理中的资源访问

```python
# ❌ 错误：无条件访问可能为None的资源
except Exception as e:
    resource.cleanup()  # 如果resource是None，触发AttributeError
    raise

# ✅ 正确：条件检查 + 安全包装
except Exception as e:
    if resource is not None:
        try:
            resource.cleanup()
        except Exception as cleanup_error:
            logger.warning(f"Cleanup failed: {cleanup_error}")
    raise
```

### 2. 配置验证

```python
# ❌ 错误：仅在部分路径验证
def __init__(self, preset):
    config = get_config(preset)
    validate_config(config)  # 仅验证预设

# 后续直接覆盖
obj.config = modified_config  # 未验证！

# ✅ 正确：在配置生成函数内部验证
def get_config(preset, **overrides):
    config = PRESETS[preset].copy()
    config.update(overrides)
    validate_config(config)  # 自动验证
    return config
```

### 3. 快速失败原则

```python
# ✅ 在程序启动时验证配置
# - 避免运行到一半才发现配置错误
# - 提供清晰的错误消息
# - 节省用户时间
try:
    validate_config(config)
except AssertionError as e:
    logger.error(f"Invalid configuration: {e}")
    print(f"\n❌ Error: {e}")
    return  # 立即退出
```

---

## 影响评估

### Bug #8影响

- **触发概率**: 低（仅在数据库连接失败时）
- **影响范围**: 中（影响调试效率）
- **修复优先级**: 高（错误处理的基本要求）

### Bug #9影响

- **触发概率**: 中（用户使用CLI参数时）
- **影响范围**: 高（可能产生错误结果）
- **修复优先级**: 高（数据正确性风险）

---

**报告日期**: 2026-01-28
**审核人员**: User
**修复人员**: Claude Code
**Bug总数**: 2个（Bug #8-9）
**建议优先级**: 高（尽快修复）

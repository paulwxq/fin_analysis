#!/usr/bin/env python3
"""测试Bug #8和#9的修复"""

import sys
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from selection.find_flatbottom import FlatbottomScreener
from selection.config import get_config


def test_bug8_connection_failure_preserves_original_error():
    """
    Bug #8测试：数据库连接失败时保留原始错误

    修复前：抛出AttributeError (conn.rollback()失败)
    修复后：抛出原始的连接错误
    """
    print("=" * 80)
    print("测试 Bug #8: save_to_db异常处理")
    print("=" * 80)

    screener = FlatbottomScreener(preset='balanced')
    results = pd.DataFrame({
        'code': ['600000.SH'],
        'name': ['测试股票'],
        'current_price': [10.0],
        'history_high': [20.0],
        'glory_ratio': [2.0],
        'glory_type': ['ratio'],
        'drawdown_pct': [-50.0],
        'box_range_pct': [30.0],
        'volatility_ratio': [0.1],
        'price_position': [0.5],
        'slope': [0.01],
        'r_squared': [0.5],
        'score': [50.0]
    })

    # Mock get_db_connection to raise exception
    original_error_msg = "Database connection failed: host not reachable"

    with patch('selection.find_flatbottom.get_db_connection') as mock_conn:
        mock_conn.side_effect = Exception(original_error_msg)

        try:
            screener.save_to_db(results)
            print("❌ 测试失败：应该抛出异常")
            return False
        except AttributeError as e:
            print(f"❌ 测试失败：抛出了AttributeError（Bug未修复）")
            print(f"   错误消息: {e}")
            return False
        except Exception as e:
            # 验证错误消息是原始错误
            if original_error_msg in str(e):
                print(f"✅ 测试通过：保留了原始错误")
                print(f"   原始错误: {e}")
                return True
            else:
                print(f"❌ 测试失败：错误消息不匹配")
                print(f"   期望: {original_error_msg}")
                print(f"   实际: {e}")
                return False


def test_bug9_invalid_cli_parameters():
    """
    Bug #9测试：CLI参数覆盖后验证配置

    测试场景：
    1. MIN_DRAWDOWN为正数（应为负数）
    2. SLOPE_MIN > SLOPE_MAX（逻辑错误）
    3. MIN_R_SQUARED > 1.0（超出范围）
    """
    print("\n" + "=" * 80)
    print("测试 Bug #9: CLI参数验证")
    print("=" * 80)

    test_cases = [
        {
            'name': '无效的MIN_DRAWDOWN（正数）',
            'preset': 'balanced',
            'overrides': {'MIN_DRAWDOWN': 0.5},
            'expected_error': 'MIN_DRAWDOWN 必须为负数'
        },
        {
            'name': '无效的slope范围（min > max）',
            'preset': 'balanced',
            'overrides': {'SLOPE_MIN': 0.05, 'SLOPE_MAX': 0.02},
            'expected_error': 'SLOPE_MIN 必须小于 SLOPE_MAX'
        },
        {
            'name': '无效的MIN_R_SQUARED（超出范围）',
            'preset': 'balanced',
            'overrides': {'MIN_R_SQUARED': 1.5},
            'expected_error': 'MIN_R_SQUARED 必须在 (0, 1] 区间'
        },
        {
            'name': '无效的MIN_GLORY_RATIO（小于1）',
            'preset': 'balanced',
            'overrides': {'MIN_GLORY_RATIO': 0.8},
            'expected_error': 'MIN_GLORY_RATIO 必须 > 1.0'
        }
    ]

    all_passed = True

    for test in test_cases:
        print(f"\n测试场景: {test['name']}")
        print(f"  参数: {test['overrides']}")

        try:
            config = get_config(test['preset'], **test['overrides'])
            print(f"  ❌ 失败：应该抛出AssertionError（配置验证失败）")
            all_passed = False
        except AssertionError as e:
            if test['expected_error'] in str(e):
                print(f"  ✅ 通过：正确捕获错误")
                print(f"  错误消息: {e}")
            else:
                print(f"  ❌ 失败：错误消息不匹配")
                print(f"  期望: {test['expected_error']}")
                print(f"  实际: {e}")
                all_passed = False
        except Exception as e:
            print(f"  ❌ 失败：抛出了意外的异常类型")
            print(f"  异常类型: {type(e).__name__}")
            print(f"  错误消息: {e}")
            all_passed = False

    return all_passed


def test_valid_cli_parameters():
    """
    测试有效的CLI参数可以正常工作
    """
    print("\n" + "=" * 80)
    print("测试有效的CLI参数")
    print("=" * 80)

    # 有效的参数覆盖
    overrides = {
        'MIN_DRAWDOWN': -0.50,
        'MIN_GLORY_RATIO': 2.5,
        'SLOPE_MIN': -0.02,
        'SLOPE_MAX': 0.03,
        'MIN_R_SQUARED': 0.25
    }

    try:
        config = get_config('balanced', **overrides)
        print("✅ 测试通过：有效参数正常工作")
        print(f"   MIN_DRAWDOWN: {config['MIN_DRAWDOWN']}")
        print(f"   MIN_GLORY_RATIO: {config['MIN_GLORY_RATIO']}")
        print(f"   SLOPE_MIN: {config['SLOPE_MIN']}")
        print(f"   SLOPE_MAX: {config['SLOPE_MAX']}")
        print(f"   MIN_R_SQUARED: {config['MIN_R_SQUARED']}")
        return True
    except Exception as e:
        print(f"❌ 测试失败：有效参数不应抛出异常")
        print(f"   错误: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("Bug修复验证测试（Bug #8-9）")
    print("=" * 80 + "\n")

    results = []

    # 测试Bug #8
    results.append(('Bug #8: 异常处理', test_bug8_connection_failure_preserves_original_error()))

    # 测试Bug #9
    results.append(('Bug #9: 配置验证', test_bug9_invalid_cli_parameters()))

    # 测试有效参数
    results.append(('有效参数测试', test_valid_cli_parameters()))

    # 汇总结果
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)

    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {name}")

    all_passed = all(r[1] for r in results)

    if all_passed:
        print("\n🎉 所有测试通过！Bug #8和#9已成功修复。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查修复代码。")
        return 1


if __name__ == '__main__':
    sys.exit(main())

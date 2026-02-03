"""Configuration module for flatbottom stock screening."""
import os
from typing import Optional

# =============================================================================
# 日志文件配置
# =============================================================================

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
        'MIN_DRAWDOWN': -0.35,        # 最小回撤幅度（负数，如-0.35表示-35%）
        'MAX_DRAWDOWN_ABS': 0.90,     # 回撤绝对值上限（防极端值刷分）
        'MAX_BOX_RANGE': 0.55,        # 最大箱体振幅（如0.55表示55%）
        'MAX_VOLATILITY_RATIO': 0.70, # 最大波动率比
        'MIN_GLORY_RATIO': 3.0,       # 最小辉煌度（正价段倍率：历史高点/历史低点）
        'MIN_GLORY_AMPLITUDE': 0.70,  # 最小辉煌度（负价段回退：归一化振幅）
        'MIN_POSITIVE_LOW': 0.01,     # 正价判定阈值（历史低点 > 该值才用倍率）
        'MIN_HIGH_PRICE': 3.5,        # 历史高点最低值（确保"曾经辉煌"来自正价区间）
        'MIN_PRICE': 3.5,             # 最低绝对股价（元）
        'MIN_DATA_MONTHS': 84,        # 最少数据月数
        'PRICE_POSITION_MIN': 0.05,   # 价格箱体位置下限（避免破位下跌）
        'PRICE_POSITION_MAX': 0.82,   # 价格箱体位置上限（避免追高）
        'SQL_LIMIT': -1,             # SQL返回上限

        # ===== Python 层参数 =====
        'SLOPE_MIN': -0.010,          # 趋势斜率下限
        'SLOPE_MAX': 0.020,           # 趋势斜率上限
        'MIN_R_SQUARED': 0.25,        # 最小拟合度R²
        'EXCLUDE_ST': True,           # 是否排除ST股
        'EXCLUDE_BLACKLIST': True,    # 是否排除黑名单股票
        'FINAL_LIMIT': -1,            # 最终输出数量
    },

    'balanced': {
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
        'SQL_LIMIT': -1,

        # ===== Python 层参数 =====
        'SLOPE_MIN': -0.02,
        'SLOPE_MAX': 0.03,
        'MIN_R_SQUARED': 0.25,
        'EXCLUDE_ST': False,
        'EXCLUDE_BLACKLIST': False,
        'FINAL_LIMIT': -1,
    },

    'aggressive': {
        # ===== SQL 层参数 =====
        'HISTORY_LOOKBACK': 120,
        'RECENT_LOOKBACK': 24,
        'MIN_DRAWDOWN': -0.24,        # 最初推荐值: -0.40（原 -40% 回撤）
        'MAX_DRAWDOWN_ABS': 0.90,     # 回撤绝对值上限（防极端值刷分）
        'MAX_BOX_RANGE': 0.66,        # 最初推荐值: 0.50（原 50% 箱体振幅）
        'MAX_VOLATILITY_RATIO': 0.85, # 最初推荐值: 0.60
        'MIN_GLORY_RATIO': 2.3,       # 最初推荐值: 3.0（原正价段倍率阈值）
        'MIN_GLORY_AMPLITUDE': 0.60,
        'MIN_POSITIVE_LOW': 0.01,
        'MIN_HIGH_PRICE': 3.0,
        'MIN_PRICE': 3.0,             # 最低绝对股价（元）
        'MIN_DATA_MONTHS': 60,
        'PRICE_POSITION_MIN': 0.05,   # 箱体位置 5%-80%
        'PRICE_POSITION_MAX': 0.85,   # 最初推荐值: 0.80
        'SQL_LIMIT': -1,

        # ===== Python 层参数 =====
        'SLOPE_MIN': -0.015,          # 最初推荐值: -0.01
        'SLOPE_MAX': 0.03,            # 最初推荐值: 0.02
        'MIN_R_SQUARED': 0.12,        # 最初推荐值: 0.30
        'EXCLUDE_ST': False,          # 默认关闭（ST数据未就绪）
        'EXCLUDE_BLACKLIST': False,   # 默认关闭
        'FINAL_LIMIT': -1,
    }
}

# =============================================================================
# 默认配置（可被命令行参数覆盖）
# =============================================================================

DEFAULT_PRESET = 'conservative'


# =============================================================================
# 工具函数
# =============================================================================

def get_config(preset: Optional[str] = None, **overrides) -> dict:
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

    # 验证配置（包括覆盖后的参数）
    validate_config(config)

    return config


def validate_config(config: dict) -> None:
    """
    验证配置参数的合法性

    Args:
        config: 配置字典

    Raises:
        AssertionError: 参数不合法时
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
    assert config['RECENT_LOOKBACK'] >= 12, \
        "RECENT_LOOKBACK 必须 >= 12（月），以保证回归分析有效"
    assert config['SQL_LIMIT'] == -1 or config['SQL_LIMIT'] > 0, \
        "SQL_LIMIT 必须为正数，或 -1 表示不限制"
    assert config['FINAL_LIMIT'] == -1 or config['FINAL_LIMIT'] > 0, \
        "FINAL_LIMIT 必须为正数，或 -1 表示不限制"


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

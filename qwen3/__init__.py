"""
Qwen3 Chat Client for Microsoft Agent Framework
阿里云通义千问Qwen3系列模型的MAF原生集成
"""

__version__ = "1.0.0"
__author__ = "Your Team"

# 配置常量
from .config import DEFAULT_THINKING_BUDGET

# 配置类
from .qwen_options import QwenChatOptions, QwenVLChatOptions

# 异常类
from .exceptions import (
    QwenAPIError,
    ThinkingModeRequiresStreamError,
    UnsupportedParameterError,
    RateLimitError,
)

# 工具函数
from .utils import (
    map_finish_reason,
)

# 核心类
from .qwen_client import QwenChatClient
from .qwen_vl_client import QwenVLChatClient

__all__ = [
    "QwenChatClient",
    "QwenVLChatClient",
    "QwenChatOptions",
    "QwenVLChatOptions",
    "DEFAULT_THINKING_BUDGET",
    "QwenAPIError",
    "ThinkingModeRequiresStreamError",
    "UnsupportedParameterError",
    "RateLimitError",
    "map_finish_reason",
]

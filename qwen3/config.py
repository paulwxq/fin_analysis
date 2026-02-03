"""
Qwen3 全局配置
"""
import os

# 默认模型与推理参数
DEFAULT_MODEL_ID = "qwen-plus"          # 默认模型
DEFAULT_TEMPERATURE = 0.7               # 温度
DEFAULT_MAX_TOKENS = 2000               # 最大输出 Token
DEFAULT_TOP_P = 0.9                     # Top-p
DEFAULT_ENABLE_SEARCH = True            # 默认是否启用搜索

# 默认思考预算 (Token数)
# 可以通过环境变量 QWEN_DEFAULT_THINKING_BUDGET 覆盖
DEFAULT_THINKING_BUDGET = int(os.getenv("QWEN_DEFAULT_THINKING_BUDGET", "2048"))

# 网络与重试
REQUEST_TIMEOUT_S = 60                  # 请求超时（秒）
MAX_RETRIES = 3                         # 最大重试次数

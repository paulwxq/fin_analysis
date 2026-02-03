"""
Qwen3 自定义异常类
"""

class QwenAPIError(Exception):
    """DashScope API调用错误基类"""
    pass

class ThinkingModeRequiresStreamError(ValueError):
    """思考模式必须使用流式调用"""
    def __init__(self) -> None:
        super().__init__(
            "enable_thinking=True时必须使用流式响应。"
            "请使用get_streaming_response()或Agent.run_stream()。"
        )

class UnsupportedParameterError(ValueError):
    """模型不支持的参数"""
    pass

class RateLimitError(QwenAPIError):
    """API限流错误 (HTTP 429)"""
    pass

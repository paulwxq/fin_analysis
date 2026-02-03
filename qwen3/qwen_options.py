"""
Qwen模型配置类型定义
"""
from typing import TypedDict, NotRequired
from agent_framework import ChatOptions

class QwenChatOptions(ChatOptions):
    """Qwen文本模型完整配置"""

    # 思维链控制
    enable_thinking: NotRequired[bool]          # 思考总开关
    thinking_budget: NotRequired[int]           # 思考Token预算上限

    # 搜索与工具
    enable_search: NotRequired[bool]            # 原生搜索增强

    # 随机性控制
    seed: NotRequired[int]                      # 随机种子
    repetition_penalty: NotRequired[float]      # 重复惩罚

    # 调试选项
    include_reasoning: NotRequired[bool]        # 是否返回思考过程

    # Deep Research 选项
    report_type: NotRequired[str]               # 报告类型: model_detailed_report / model_summary_report

class QwenVLChatOptions(ChatOptions):
    """Qwen视觉模型配置"""

    # 视觉模型专用
    min_pixels: NotRequired[int]                # 最小分辨率
    max_pixels: NotRequired[int]                # 最大分辨率

    # 注意：不支持 enable_search

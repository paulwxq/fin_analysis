"""
Qwen3 工具函数
"""
import logging
from typing import Optional, Dict, Any
from agent_framework import FinishReason

logger = logging.getLogger(__name__)

def map_finish_reason(reason: Optional[str]) -> Optional[FinishReason]:
    """
    映射DashScope的结束原因到MAF格式
    
    DashScope finish_reason:
    - stop: 正常结束
    - length: 达到最大长度
    - null: 生成中
    - tool_calls: 工具调用 (qwen-max等)
    """
    if not reason or reason == "null":
        return None
    
    if reason == "stop":
        return FinishReason.STOP
    
    if reason == "length":
        return FinishReason.LENGTH
    
    if reason == "tool_calls":
        return FinishReason.TOOL_CALLS
        
    logger.warning(f"未知的结束原因: {reason}")
    return FinishReason.STOP

def extract_search_info(response: Any) -> Dict[str, Any]:
    """
    从DashScope响应中提取搜索引用信息
    """
    # 这一步依赖具体的 API 响应结构，通常在 message 的 additional_properties 中
    # 此处仅作预留，具体逻辑在 Client 实现中处理
    return {}

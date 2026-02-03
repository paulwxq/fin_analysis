"""
Qwen 视觉语言模型 Chat Client 实现
"""
from __future__ import annotations

import os
import asyncio
import logging
import threading
from typing import Any, AsyncIterable, List, Dict, Optional, Sequence, Union
from http import HTTPStatus

# MAF 导入
from agent_framework import (
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    ChatMessage,
    Role,
    Content,
    FinishReason,
    UsageDetails,
)

# DashScope 导入
import dashscope
from dashscope.api_entities.dashscope_response import MultiModalConversationResponse

# 本地导入
from .qwen_options import QwenVLChatOptions
from .exceptions import UnsupportedParameterError, QwenAPIError, RateLimitError
from .utils import map_finish_reason
from .config import (
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TOP_P,
    MAX_RETRIES,
)

logger = logging.getLogger(__name__)

# 默认视觉模型
DEFAULT_VL_MODEL_ID = "qwen3-vl-plus"

class QwenVLChatClient(BaseChatClient[QwenVLChatOptions]):
    """
    阿里云 Qwen 视觉语言模型封装 (qwen-vl-plus, qwen-vl-max)
    """

    def __init__(
        self,
        model_id: str = DEFAULT_VL_MODEL_ID,
        api_key: Optional[str] = None,
        **default_options: Any,
    ):
        """
        初始化 QwenVLChatClient
        """
        super().__init__()
        self.model_id = model_id
        
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("未配置 DASHSCOPE_API_KEY 环境变量，且未提供 api_key 参数。")

        # 默认配置 (VL 模型参数略有不同)
        self._default_options: QwenVLChatOptions = {
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "top_p": DEFAULT_TOP_P,
        }
        self._default_options.update(default_options)
        
        logger.info(f"QwenVLChatClient 已初始化: model={model_id}")

    def _process_content_item(self, item: Any) -> Dict[str, str]:
        """
        处理单个内容项，转换为 DashScope VL 格式
        
        DashScope VL 格式:
        {'text': '...'} 或 {'image': 'url_or_base64'}
        """
        # 1. 文本内容
        if isinstance(item, str):
            return {"text": item}
            
        if hasattr(item, "text") and item.text:
            return {"text": item.text}

        # 2. 图像内容 (URI/Data)
        if hasattr(item, "uri") and item.uri:
            uri_str = item.uri
            # Data URI (base64) 或 外部 URL
            if uri_str.startswith("data:"):
                # 如果是 Data URI，DashScope 也支持直接传
                # 或者从 data uri 中提取 base64
                # 简单起见，如果 startswith data:image，我们可以直接传给 DashScope
                return {"image": uri_str}
            elif uri_str.startswith("http"):
                return {"image": uri_str}
            elif uri_str.startswith("file://"):
                # 本地文件需要转 Base64 吗？
                # DashScope 支持 file:// 吗？通常 SDK 支持
                return {"image": uri_str}
            else:
                # 假设是本地路径
                return {"image": uri_str}

        return {"text": str(item)}

    def _convert_messages(self, messages: Sequence[ChatMessage]) -> List[Dict[str, Any]]:
        """
        将 MAF 的 ChatMessage 转换为 DashScope MultiModal 格式
        """
        converted = []
        for msg in messages:
            content_list = []
            
            # MAF 的 contents 可能是 Content 对象列表
            if msg.contents:
                for item in msg.contents:
                    content_list.append(self._process_content_item(item))
            elif msg.text:
                # 如果没有 contents 但有 text 属性
                content_list.append({"text": msg.text})

            converted.append({
                "role": msg.role.value,
                "content": content_list
            })
        return converted

    def _build_request_params(self, messages: Sequence[ChatMessage], **options: Any) -> Dict[str, Any]:
        """
        构建请求参数
        """
        # 检查不支持的参数
        if options.get("enable_search"):
            raise UnsupportedParameterError(
                f"模型 {self.model_id} 不支持 'enable_search' 参数。 "
                f"联网搜索功能仅在 qwen-plus/max 等推理模型中可用。"
            )

        merged_options = self._default_options.copy()
        merged_options.update(options)

        params = {
            "model": self.model_id,
            "messages": self._convert_messages(messages),
            "api_key": self.api_key,
            "incremental_output": True,
        }

        # 映射通用参数
        if "temperature" in merged_options:
            params["temperature"] = merged_options["temperature"]
        if "top_p" in merged_options:
            params["top_p"] = merged_options["top_p"]
        if "max_tokens" in merged_options:
            # DashScope VL 模型也支持 max_tokens
            params["max_tokens"] = merged_options["max_tokens"]
        if "seed" in merged_options:
            params["seed"] = merged_options["seed"]

        return params

    async def _inner_get_response(
        self,
        messages: Sequence[ChatMessage],
        **options: Any,
    ) -> ChatResponse:
        """
        非流式响应实现
        """
        params = self._build_request_params(messages, **options)
        params["stream"] = False

        # 注意：视觉模型使用 MultiModalConversation
        response = await asyncio.to_thread(
            dashscope.MultiModalConversation.call,
            **params
        )

        if response.status_code != HTTPStatus.OK:
            self._handle_error(response)

        return self._parse_response(response)

    async def _inner_get_streaming_response(
        self,
        messages: Sequence[ChatMessage],
        **options: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """
        流式响应实现
        """
        params = self._build_request_params(messages, **options)
        params["stream"] = True

        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        sentinel = object()

        def _producer():
            try:
                responses = dashscope.MultiModalConversation.call(**params)
                for resp in responses:
                    loop.call_soon_threadsafe(queue.put_nowait, resp)
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)

        threading.Thread(target=_producer, daemon=True).start()

        while True:
            item = await queue.get()
            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise item
            
            if item.status_code != HTTPStatus.OK:
                self._handle_error(item)

            # 解析 VL 响应
            choice = item.output.choices[0]
            message = choice.message
            
            updates = []
            
            # 视觉模型的 content 通常包含 text 字段
            # 注意：DashScope VL 流式返回的结构可能有所不同，需防守
            # 这里的 message 是一个 dict-like 对象
            content_list = message.get("content", [])
            
            # 如果 content 是列表 (非增量或首包)，提取文本
            if isinstance(content_list, list):
                for node in content_list:
                    if "text" in node:
                        updates.append(Content.from_text(text=node["text"]))
            # 如果是字典 (增量)
            elif isinstance(content_list, dict) and "text" in content_list:
                updates.append(Content.from_text(text=content_list["text"]))

            if updates:
                yield ChatResponseUpdate(contents=updates)

            if choice.finish_reason and choice.finish_reason != "null":
                usage = None
                if hasattr(item, "usage"):
                    usage = UsageDetails(
                        input_tokens=item.usage.input_tokens,
                        output_tokens=item.usage.output_tokens,
                    )
                
                # 兼容性处理：通过 additional_properties 传递 usage_details
                yield ChatResponseUpdate(
                    finish_reason=map_finish_reason(choice.finish_reason),
                    additional_properties={"usage_details": usage}
                )

    def _parse_response(self, response: MultiModalConversationResponse) -> ChatResponse:
        """解析同步响应"""
        choice = response.output.choices[0]
        message = choice.message
        
        contents = []
        # MultiModal 响应的 content 是一个列表: [{'text': '...'}]
        content_list = message.get("content", [])
        for node in content_list:
            if "text" in node:
                contents.append(Content.from_text(text=node["text"]))

        msg = ChatMessage(
            role=Role.ASSISTANT,
            contents=contents
        )

        usage = UsageDetails(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        return ChatResponse(
            messages=[msg],
            finish_reason=map_finish_reason(choice.finish_reason),
            usage_details=usage
        )

    def _handle_error(self, response: MultiModalConversationResponse):
        """统一错误处理"""
        error_msg = f"DashScope VL API 错误: {response.code} - {response.message} (Request ID: {response.request_id})"
        if response.status_code == 429:
            raise RateLimitError(error_msg)
        raise QwenAPIError(error_msg)
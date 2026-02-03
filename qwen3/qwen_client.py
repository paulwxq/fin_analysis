"""
Qwen推理模型 Chat Client 实现
"""
from __future__ import annotations

import os
import asyncio
import logging
import threading
from typing import Any, AsyncIterable, List, Dict, Optional, Sequence, Mapping, Union, Literal
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
from dashscope.api_entities.dashscope_response import GenerationResponse

# 本地 导入
from .qwen_options import QwenChatOptions
from .exceptions import ThinkingModeRequiresStreamError, QwenAPIError, RateLimitError
from .utils import map_finish_reason
from .config import (
    DEFAULT_MODEL_ID,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TOP_P,
    DEFAULT_ENABLE_SEARCH,
)

logger = logging.getLogger(__name__)

class QwenChatClient(BaseChatClient[QwenChatOptions]):
    """
    阿里云 Qwen 推理模型封装 (qwen-plus, qwen-max)
    """
    # 声明支持工具调用
    __function_invoking_chat_client__ = True

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        api_key: Optional[str] = None,
        **default_options: Any,
    ):
        """
        初始化 QwenChatClient
        """
        super().__init__()
        self.model_id = model_id
        
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("未配置 DASHSCOPE_API_KEY 环境变量，且未提供 api_key 参数。")

        # 默认配置
        self._default_options: QwenChatOptions = {
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "top_p": DEFAULT_TOP_P,
            "enable_search": DEFAULT_ENABLE_SEARCH,
        }
        self._default_options.update(default_options)
        
        logger.info(f"QwenChatClient 已初始化: model={model_id}")

    def _convert_messages(self, messages: Sequence[ChatMessage]) -> List[Dict[str, Any]]:
        """
        将 MAF 的 ChatMessage 转换为 DashScope 的消息格式
        增强对 FunctionCall 的支持
        """
        converted = []
        for msg in messages:
            dashscope_msg = {"role": msg.role.value}
            
            # 1. 尝试提取工具调用结果 (Tool Role)
            if msg.role == Role.TOOL:
                # MAF 的 Tool 消息通常包含 function_result 类型的 Content
                for content in msg.contents:
                    if content.type == "function_result":
                        # DashScope 格式:
                        # {"role": "tool", "content": "result", "name": "func_name", "tool_call_id": "id"}
                        
                        dashscope_msg["content"] = str(content.result)
                        if content.call_id:
                             dashscope_msg["tool_call_id"] = content.call_id
                        
                        # Content 对象中可能没有 name 属性 (如果是 function_result 类型)
                        # 如果需要 name，可能需要从 content.name 获取 (如果存在)
                        if hasattr(content, "name") and content.name:
                             dashscope_msg["name"] = content.name
                        
                        break
                
                # 如果没有找到 function_result，尝试直接取 text
                if "content" not in dashscope_msg:
                    dashscope_msg["content"] = msg.text

            # 2. 尝试提取工具调用请求 (Assistant Role)
            elif msg.role == Role.ASSISTANT:
                content_str = ""
                tool_calls = []
                
                for content in msg.contents:
                    if content.type == "function_call":
                        # 转换为 DashScope tool_calls 格式
                        tool_calls.append({
                            "type": "function",
                            "function": {
                                "name": content.name,
                                "arguments": content.arguments if isinstance(content.arguments, str) else str(content.arguments)
                            },
                            "id": content.call_id or "call_default" 
                        })
                    elif content.type == "text":
                        content_str += (content.text or "")
                
                if content_str:
                    dashscope_msg["content"] = content_str
                
                if tool_calls:
                    dashscope_msg["tool_calls"] = tool_calls
            
            # 3. 普通文本消息 (User/System Role)
            else:
                dashscope_msg["content"] = msg.text

            converted.append(dashscope_msg)
            
        return converted

    def _build_request_params(self, messages: Sequence[ChatMessage], **options: Any) -> Dict[str, Any]:
        """
        构建请求参数
        """
        # 合并选项
        merged_options = self._default_options.copy()
        merged_options.update(options)

        params = {
            "model": self.model_id,
            "messages": self._convert_messages(messages),
            "api_key": self.api_key,
            "result_format": "message",
        }

        logger.debug("QwenChatClient request messages: %s", params["messages"])

        # 映射参数
        if "temperature" in merged_options:
            params["temperature"] = merged_options["temperature"]
        if "top_p" in merged_options:
            params["top_p"] = merged_options["top_p"]
        if "max_tokens" in merged_options:
            params["max_tokens"] = merged_options["max_tokens"]
        if "seed" in merged_options:
            params["seed"] = merged_options["seed"]
        if "repetition_penalty" in merged_options:
            params["repetition_penalty"] = merged_options["repetition_penalty"]

        # Qwen 联网搜索支持 (支持三种方式)
        
        # 方式 1: 简单布尔开关 (enable_search)
        if merged_options.get("enable_search"):
            params["enable_search"] = True
            
        # 方式 2: 工具调用方式 (tools)
        # 如果用户直接在 options 中传入了包含 web_search 的 tools，我们予以保留
        if "tools" in merged_options:
            params["tools"] = merged_options["tools"]
        
        # 方式 3: 搜索选项配置 (search_options)
        if "search_options" in merged_options:
            params["search_options"] = merged_options["search_options"]
        
        if merged_options.get("enable_thinking"):
            params["enable_thinking"] = True
            if "thinking_budget" in merged_options:
                params["thinking_budget"] = merged_options["thinking_budget"]

        # 增加超时控制 (通用功能)
        if "request_timeout" in merged_options:
            params["request_timeout"] = merged_options["request_timeout"]

        # 并行工具调用支持
        if "parallel_tool_calls" in merged_options:
            params["parallel_tool_calls"] = merged_options["parallel_tool_calls"]

        return params

    async def _inner_get_response(
        self,
        messages: Sequence[ChatMessage],
        **options: Any,
    ) -> ChatResponse:
        """
        非流式响应实现
        """
        if options.get("enable_thinking") or self._default_options.get("enable_thinking"):
            raise ThinkingModeRequiresStreamError()

        params = self._build_request_params(messages, **options)
        params["stream"] = False

        response = await asyncio.to_thread(
            dashscope.Generation.call,
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
        params["incremental_output"] = True

        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        sentinel = object()

        include_reasoning = options.get("include_reasoning", 
                                       self._default_options.get("include_reasoning", True))

        def _producer():
            try:
                responses = dashscope.Generation.call(**params)
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

            # 标准 Qwen 响应处理: output.choices[0]
            choice = item.output.choices[0]
            message = choice.message
            
            # 使用 Content.from_text 创建 MAF 标准内容项
            updates = []
            
            reasoning = message.get("reasoning_content")
            if reasoning:
                if include_reasoning:
                    updates.append(Content.from_text(text=f"<thinking>{reasoning}</thinking>"))
            
            content = message.get("content")
            if content:
                updates.append(Content.from_text(text=content))

            # 处理 Tool Calls (流式)
            # 注意: Qwen 流式返回 tool_calls 可能是在最后一个包，也可能是分片的
            # 这里简化处理：假设 tool_calls 是一次性返回完整的 (DashScope特性)
            tool_calls = message.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", {})
                    updates.append(Content.from_function_call(
                        name=func.get("name"),
                        arguments=func.get("arguments"),
                        call_id=tc.get("id")
                    ))

            if updates:
                yield ChatResponseUpdate(contents=updates)

            if choice.finish_reason and choice.finish_reason != "null":
                usage = None
                if hasattr(item, "usage"):
                    usage = UsageDetails(
                        input_tokens=item.usage.input_tokens,
                        output_tokens=item.usage.output_tokens,
                    )
                
                yield ChatResponseUpdate(
                    finish_reason=map_finish_reason(choice.finish_reason),
                    additional_properties={"usage_details": usage}
                )

    def _parse_response(self, response: GenerationResponse) -> ChatResponse:
        """解析同步响应"""
        # 标准 Qwen 响应处理
        choice = response.output.choices[0]
        message = choice.message
        
        contents = []
        reasoning = message.get("reasoning_content")
        if reasoning:
            contents.append(Content.from_text(text=f"<thinking>{reasoning}</thinking>"))
        
        content = message.get("content") or ""
        if content:
            contents.append(Content.from_text(text=content))

        # 处理 Tool Calls (非流式)
        tool_calls = message.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                contents.append(Content.from_function_call(
                    name=func.get("name"),
                    arguments=func.get("arguments"),
                    call_id=tc.get("id")
                ))

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

    def _handle_error(self, response: GenerationResponse):
        """统一错误处理"""
        error_msg = f"DashScope API 错误: {response.code} - {response.message} (Request ID: {response.request_id})"
        if response.status_code == 429:
            raise RateLimitError(error_msg)
        raise QwenAPIError(error_msg)

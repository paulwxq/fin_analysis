"""
Qwen Deep Research 专属客户端实现
"""
from __future__ import annotations

import logging
import asyncio
import threading
from typing import Any, AsyncIterable, Sequence, Optional
from http import HTTPStatus

# MAF 导入
from agent_framework import (
    ChatResponse,
    ChatResponseUpdate,
    ChatMessage,
    Content,
    UsageDetails,
)

# DashScope 导入
import dashscope
from dashscope.api_entities.dashscope_response import GenerationResponse

# 本地导入
from .qwen_client import QwenChatClient
from .qwen_options import QwenChatOptions
from .exceptions import QwenAPIError
from .utils import map_finish_reason

logger = logging.getLogger(__name__)

DEFAULT_DEEP_RESEARCH_MODEL = "qwen-deep-research"
DEFAULT_DEEP_RESEARCH_TIMEOUT = 1800  # 默认 30 分钟超时

class QwenDeepResearchClient(QwenChatClient):
    """
    阿里云 Qwen Deep Research 深度研究模型专用客户端
    
    特点:
    1. 响应结构不同: 没有 choices 列表，直接返回 message
    2. 超时时间极长: 默认为 30 分钟
    3. 流式参数敏感: 必须严格控制 incremental_output
    """
    # 继承自 QwenChatClient，由于 QwenChatClient 已有标记，这里显式声明以确保万一
    __function_invoking_chat_client__ = True

    def __init__(
        self,
        model_id: str = DEFAULT_DEEP_RESEARCH_MODEL,
        api_key: Optional[str] = None,
        **default_options: Any,
    ):
        # 强制设置默认超时时间，如果用户没有指定
        default_options.setdefault("request_timeout", DEFAULT_DEEP_RESEARCH_TIMEOUT)
        
        super().__init__(model_id, api_key, **default_options)
        logger.info(f"QwenDeepResearchClient 已初始化: model={model_id}, timeout={default_options.get('request_timeout')}")

    def _build_request_params(self, messages: Sequence[ChatMessage], **options: Any) -> dict[str, Any]:
        """
        构建请求参数 (复用父类逻辑，但可以进行微调)
        """
        params = super()._build_request_params(messages, **options)
        
        # Deep Research 必须确保 request_timeout 足够长
        # 虽然 __init__ 设置了默认值，但这里可以作为双重保障，或者处理 options 里的覆盖
        if "request_timeout" not in params:
             params["request_timeout"] = DEFAULT_DEEP_RESEARCH_TIMEOUT

        # 处理 report_type 参数
        if "report_type" in options:
            params["report_type"] = options["report_type"]
             
        return params

    async def _inner_get_response(
        self,
        messages: Sequence[ChatMessage],
        **options: Any,
    ) -> ChatResponse:
        """
        非流式响应实现
        
        注意：Deep Research 模型仅支持流式输出，调用此方法将抛出异常。
        """
        raise QwenAPIError("Qwen Deep Research 模型仅支持流式调用 (stream=True)，请使用 agent.run_stream() 或设置 stream=True。")

    async def _inner_get_streaming_response(
        self,
        messages: Sequence[ChatMessage],
        **options: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """
        流式响应实现 (重写以适配 Deep Research 的特殊响应结构)
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

            # --- Deep Research 专属解析逻辑 ---
            # 结构特点: item.output.choices 为 None, 内容在 item.output.message 中
            if hasattr(item.output, "message"):
                message = item.output.message
                finish_reason = None
                if message.get("status") == "finished":
                    finish_reason = "stop"
            else:
                #以此防守，万一 API 变了
                raise QwenAPIError(f"Deep Research 响应格式异常: {item}")

            # 使用 Content.from_text 创建 MAF 标准内容项
            updates = []
            
            # Deep Research 的 reasoning 可能在 message 里，也可能没有，视 API 阶段而定
            # 这里保持与 QwenChatClient 类似的提取逻辑
            reasoning = message.get("reasoning_content")
            if reasoning and include_reasoning:
                updates.append(Content.from_text(text=f"<thinking>{reasoning}</thinking>"))
            
            content = message.get("content")
            if content:
                updates.append(Content.from_text(text=content))

            if updates:
                yield ChatResponseUpdate(contents=updates)

            if finish_reason:
                usage = None
                if hasattr(item, "usage"):
                    usage = UsageDetails(
                        input_tokens=item.usage.input_tokens,
                        output_tokens=item.usage.output_tokens,
                    )
                
                yield ChatResponseUpdate(
                    finish_reason=map_finish_reason(finish_reason),
                    additional_properties={"usage_details": usage}
                )

    def _parse_response(self, response: GenerationResponse) -> ChatResponse:
        """解析同步响应 (重写以适配 Deep Research 的特殊响应结构)"""
        # --- Deep Research 专属解析逻辑 ---
        if hasattr(response.output, "message"):
            message = response.output.message
            finish_reason = "stop" if message.get("status") == "finished" else None
        else:
             raise QwenAPIError(f"Unexpected Deep Research response format: {response}")
        
        contents = []
        reasoning = message.get("reasoning_content")
        if reasoning:
            contents.append(Content.from_text(text=f"<thinking>{reasoning}</thinking>"))
        
        content = message.get("content") or ""
        contents.append(Content.from_text(text=content))

        msg = ChatMessage(
            role=response.output.message.get("role", "assistant"), # Deep Research 通常也是 assistant
            contents=contents
        )

        usage = UsageDetails(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        return ChatResponse(
            messages=[msg],
            finish_reason=map_finish_reason(finish_reason),
            usage_details=usage
        )

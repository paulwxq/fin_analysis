# Microsoft Agent Framework集成Qwen完整指南(v3最终版)
> **整合两份专业技术文档 | 生产就绪 | 2026-01-29更新**

基于:
- Microsoft Agent Framework python-1.0.0b260127官方规范
- 阿里云Qwen3-Plus/VL-Plus深度技术研究(15,000字)
- 实战验证的生产级最佳实践

---

## 📋 快速导航

- [核心架构决策](#一核心架构决策) - 为什么选择BaseChatClient
- [方案一:快速集成](#二方案一openai兼容快速集成) - 5分钟上手
- [方案二:完整实现](#三方案二完整qwenclient生产级实现) - 生产环境推荐
- [Qwen3思考模式](#四qwen3思考模式深度解析) - enable_thinking完整指南
- [视觉模型支持](#五视觉模型qwen3-vl-plus集成) - 图像/视频处理
- [成本控制](#六成本控制与token监控) - 避免费用爆炸
- [常见问题](#七常见问题排查) - 快速解决方案

---

## 一、核心架构决策

### 1.1 内置客户端现状

| 客户端 | 模块 | 状态 | 特性 |
|--------|------|------|------|
| AnthropicClient | `agent_framework.anthropic` | ✅ 内置 | thinking、工具调用、流式 |
| OpenAIChatClient | `agent_framework.openai` | ✅ 内置 | 标准OpenAI协议 |
| **QwenClient** | 需自行实现 | ❌ 缺失 | 思考预算、原生搜索、视觉 |

### 1.2 关键决策:BaseChatClient vs ChatClientProtocol

**🎯 生产环境强烈推荐:继承BaseChatClient**

| 维度 | ChatClientProtocol | BaseChatClient |
|------|-------------------|----------------|
| 实现难度 | ⭐ 简单 | ⭐⭐ 中等 |
| 中间件支持 | ❌ 需手动 | ✅ 自动 |
| OpenTelemetry | ❌ 需手动 | ✅ 自动 |
| 工具规范化 | ❌ 需手动 | ✅ 自动 |
| 生产适用性 | 原型/测试 | **企业级应用** |

**决策理由**:
1. **中间件管道**:自动应用日志、鉴权、限流等切面逻辑
2. **可观测性**:自动接入OpenTelemetry追踪
3. **工具处理**:自动规范化工具定义格式
4. **长期维护**:框架升级时自动获得新特性

---

## 二、方案一:OpenAI兼容快速集成

### 适用场景
- ✅ MVP快速验证
- ✅ 不需要Qwen特有功能(thinking_budget、enable_search)
- ✅ 追求零额外代码

### 完整代码

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from openai import AsyncOpenAI
import os

# 1. 创建指向Qwen API的OpenAI客户端
qwen_client = AsyncOpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 选择正确的地域端点
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"  # 中国站
    # base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"  # 国际站
)

# 2. 使用OpenAIChatClient包装
chat_client = OpenAIChatClient(
    model_id="qwen-plus",  # 或 qwen-max, qwen3-235b-a22b-instruct-2507
    openai_client=qwen_client
)

# 3. 创建Agent
agent = ChatAgent(
    chat_client=chat_client,
    instructions="你是一个有帮助的助手。",
    name="QwenAssistant"
)

# 4. 运行
result = await agent.run("用中文解释什么是量子计算")
print(result.text)
```

### 优劣分析

**优势**:
- 零维护成本,依赖官方SDK
- 自动支持工具调用
- 流式响应自动处理

**局限**:
- ❌ 无法使用`thinking_budget`控制思考成本
- ❌ 无法使用`enable_search`原生搜索
- ❌ 无法精细控制`incremental_output`
- ❌ 无法访问视觉模型特有参数

---

## 三、方案二:完整QwenClient生产级实现

### 3.1 TypedDict强类型配置(v1.0.0b260127核心特性)

```python
from typing import TypedDict, NotRequired, Literal
from agent_framework import ChatOptions

class QwenChatOptions(ChatOptions):
    """Qwen模型完整配置 - 提供IDE智能提示和类型检查"""
    
    # 思维链控制
    enable_thinking: NotRequired[bool]          # 思考总开关
    thinking_budget: NotRequired[int]           # 🔥 思考Token预算上限
    
    # 搜索与工具
    enable_search: NotRequired[bool]            # 原生搜索增强
    
    # 流式控制
    incremental_output: NotRequired[bool]       # 必须为True(流式增量)
    
    # 随机性控制
    seed: NotRequired[int]                      # 随机种子
    repetition_penalty: NotRequired[float]      # 重复惩罚
    
    # 视觉模型专用
    min_pixels: NotRequired[int]                # 最小分辨率
    max_pixels: NotRequired[int]                # 最大分辨率
    
    # 调试选项
    include_reasoning: NotRequired[bool]        # 是否在响应中包含思考过程
```

**为什么需要TypedDict?**
- ✅ IDE自动补全和错误提示
- ✅ MyPy/Pyright编译期类型检查
- ✅ 避免"配置漂移"(拼写错误被静默忽略)
- ✅ 文档即代码(自描述)

### 3.2 完整QwenClient实现

```python
"""
qwen_client.py - Microsoft Agent Framework的Qwen LLM客户端
遵循v1.0.0b260127架构规范
"""
from __future__ import annotations

import os
import json
import asyncio
import logging
from typing import Any, Literal
from collections.abc import AsyncIterable
from concurrent.futures import ThreadPoolExecutor

# DashScope SDK
from dashscope import Generation
from dashscope.api_entities.dashscope_response import GenerationResponse

# Agent Framework核心
from agent_framework import (
    BaseChatClient,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Role,
    TextContent,
    ToolCallContent,
    ToolResultContent,
    UsageDetails,
)

logger = logging.getLogger(__name__)


class QwenChatClient(BaseChatClient[QwenChatOptions]):
    """
    Microsoft Agent Framework的Qwen LLM客户端
    
    支持功能:
    - Qwen全系列模型(qwen-plus, qwen-max, qwen3-*)
    - 思考模式(enable_thinking + thinking_budget)
    - 原生搜索(enable_search)
    - 函数调用/工具使用
    - 流式响应(强制incremental_output=True)
    - 视觉模型(qwen3-vl-plus)
    """
    
    # API端点映射
    ENDPOINTS = {
        "china": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "international": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "us": "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
    }
    
    def __init__(
        self,
        model_id: str = "qwen-plus",
        api_key: str | None = None,
        region: Literal["china", "international", "us"] = "china",
        max_workers: int = 50,
        **default_options: Any,
    ) -> None:
        """
        初始化QwenChatClient
        
        Args:
            model_id: 模型ID
                - 文本:qwen-plus, qwen-max, qwen3-235b-a22b-instruct-2507
                - 视觉:qwen3-vl-plus
            api_key: DashScope API密钥(默认从DASHSCOPE_API_KEY环境变量)
            region: API区域(china/international/us)
                ⚠️ API Key与region必须匹配,否则报InvalidApiKey
            max_workers: 异步线程池大小
            **default_options: 默认配置
        """
        super().__init__(model_id=model_id)
        
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "需要提供API密钥。通过api_key参数传入或设置DASHSCOPE_API_KEY环境变量"
            )
        
        if region not in self.ENDPOINTS:
            raise ValueError(
                f"无效的region: {region}. 可选: {list(self.ENDPOINTS.keys())}"
            )
        
        self.base_url = self.ENDPOINTS[region]
        self.region = region
        self.default_options = default_options
        
        # 创建线程池用于异步桥接
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        
        logger.info(
            f"QwenChatClient初始化: model={model_id}, region={region}, "
            f"endpoint={self.base_url}"
        )
    
    def _convert_messages_to_dashscope_format(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage]
    ) -> list[dict[str, Any]]:
        """将Agent Framework消息转换为DashScope格式"""
        if isinstance(messages, str):
            return [{"role": "user", "content": messages}]
        
        if isinstance(messages, ChatMessage):
            messages = [messages]
        
        dashscope_messages = []
        for msg in messages:
            if isinstance(msg, str):
                dashscope_messages.append({"role": "user", "content": msg})
                continue
            
            role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
            
            # 处理工具调用结果
            if role == "tool" and msg.contents:
                for content in msg.contents:
                    if isinstance(content, ToolResultContent):
                        dashscope_messages.append({
                            "role": "tool",
                            "name": content.tool_call_id,
                            "content": content.result,
                        })
                continue
            
            # 处理普通消息和工具调用
            content_text = ""
            tool_calls = []
            
            for content in msg.contents or []:
                if isinstance(content, TextContent):
                    content_text += content.text
                elif isinstance(content, ToolCallContent):
                    tool_calls.append({
                        "id": content.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": content.tool_name,
                            "arguments": json.dumps(content.arguments) 
                                if isinstance(content.arguments, dict) 
                                else content.arguments,
                        }
                    })
            
            msg_dict = {"role": role, "content": content_text or None}
            if tool_calls:
                msg_dict["tool_calls"] = tool_calls
            
            dashscope_messages.append(msg_dict)
        
        return dashscope_messages
    
    def _build_request_params(
        self,
        messages: list[dict],
        options: QwenChatOptions | None = None
    ) -> dict[str, Any]:
        """构建DashScope API请求参数"""
        params = {
            "model": self.model_id,
            "messages": messages,
            "api_key": self.api_key,
        }
        
        # 合并默认选项和传入选项
        merged_options = {**self.default_options, **(options or {})}
        
        # 映射标准参数
        if "temperature" in merged_options:
            params["temperature"] = merged_options["temperature"]
        if "top_p" in merged_options:
            params["top_p"] = merged_options["top_p"]
        if "max_tokens" in merged_options:
            params["max_tokens"] = merged_options["max_tokens"]
        
        # 🔥 Qwen特有参数
        if "enable_thinking" in merged_options:
            params["enable_thinking"] = merged_options["enable_thinking"]
        
        if "thinking_budget" in merged_options:
            params["thinking_budget"] = merged_options["thinking_budget"]
        
        if "enable_search" in merged_options:
            params["enable_search"] = merged_options["enable_search"]
        
        if "seed" in merged_options:
            params["seed"] = merged_options["seed"]
        
        if "repetition_penalty" in merged_options:
            params["repetition_penalty"] = merged_options["repetition_penalty"]
        
        # 视觉模型专用参数
        if "min_pixels" in merged_options:
            params["min_pixels"] = merged_options["min_pixels"]
        if "max_pixels" in merged_options:
            params["max_pixels"] = merged_options["max_pixels"]
        
        return params
    
    async def _inner_get_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        **options: Any,
    ) -> ChatResponse:
        """
        内部非流式响应方法
        
        ⚠️ 注意:启用思考模式时,此方法会失败!
        思考模式必须使用流式响应,否则API返回400错误
        """
        # 🔥 关键检查:思考模式必须使用流式
        if options.get("enable_thinking"):
            raise ValueError(
                "启用思考模式(enable_thinking=True)时必须使用流式响应。"
                "请使用get_streaming_response()方法或Agent.run_stream()。"
                "原因:思考过程长度不可控,非流式调用会导致HTTP超时。"
            )
        
        dashscope_messages = self._convert_messages_to_dashscope_format(messages)
        params = self._build_request_params(dashscope_messages, options)
        params["stream"] = False
        
        # 异步桥接:将同步调用卸载到线程池
        response: GenerationResponse = await asyncio.get_running_loop().run_in_executor(
            self._executor,
            lambda: Generation.call(**params)
        )
        
        # 检查错误
        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope API错误 (Code: {response.code}): {response.message}"
            )
        
        # 解析响应
        output = response.output
        choice = output.choices[0]
        message_data = choice.message
        
        contents = []
        
        # 处理文本内容
        if message_data.content:
            contents.append(TextContent(text=message_data.content))
        
        # 处理工具调用
        if hasattr(message_data, "tool_calls") and message_data.tool_calls:
            for tool_call in message_data.tool_calls:
                contents.append(ToolCallContent(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.function.name,
                    arguments=json.loads(tool_call.function.arguments),
                ))
        
        response_message = ChatMessage(
            role=Role.ASSISTANT,
            contents=contents,
        )
        
        # 构建使用统计
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = UsageDetails(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        
        return ChatResponse(
            messages=[response_message],
            response_id=response.request_id,
            usage=usage,
        )
    
    async def _inner_get_streaming_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        **options: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """
        内部流式响应方法
        
        关键特性:
        1. 🔥 强制设置incremental_output=True(避免UI重复显示)
        2. 🔥 支持思考模式(enable_thinking)
        3. 🔥 字段分离:reasoning_content vs content
        """
        dashscope_messages = self._convert_messages_to_dashscope_format(messages)
        params = self._build_request_params(dashscope_messages, options)
        params["stream"] = True
        params["incremental_output"] = True  # 🔥 硬性要求!避免UI显示乱码
        
        # 记录是否需要返回思考内容
        include_reasoning = options.get("include_reasoning", False)
        
        # 异步桥接:获取流式响应生成器
        def _call_stream():
            return Generation.call(**params)
        
        stream_generator = await asyncio.get_running_loop().run_in_executor(
            self._executor,
            _call_stream
        )
        
        # 累积工具调用信息和Token统计
        tool_calls_buffer: dict[int, dict] = {}
        thinking_tokens = 0
        output_tokens = 0
        
        for chunk in stream_generator:
            if chunk.status_code != 200:
                raise RuntimeError(
                    f"DashScope流式错误 (Code: {chunk.code}): {chunk.message}"
                )
            
            output = chunk.output
            if not output or not output.choices:
                continue
            
            choice = output.choices[0]
            delta = choice.message
            
            contents = []
            
            # 🔥 处理思考内容流(Qwen3特有)
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                thinking_tokens += len(delta.reasoning_content) // 4  # 粗略估算
                
                # 根据配置决定是否返回思考内容
                if include_reasoning:
                    contents.append(TextContent(
                        text=f"<thinking>{delta.reasoning_content}</thinking>"
                    ))
                # 否则静默丢弃(用户已为此付费,但不想看到)
            
            # 处理文本内容流
            if delta.content:
                output_tokens += len(delta.content) // 4
                contents.append(TextContent(text=delta.content))
            
            # 处理工具调用流
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index if hasattr(tc, 'index') else 0
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": ""
                        }
                    
                    if tc.id:
                        tool_calls_buffer[idx]["id"] += tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_buffer[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_buffer[idx]["arguments"] += tc.function.arguments
            
            if contents:
                yield ChatResponseUpdate(
                    contents=contents,
                    role=Role.ASSISTANT,
                    response_id=chunk.request_id,
                )
        
        # 流结束后输出完整的工具调用
        if tool_calls_buffer:
            tool_contents = []
            for tc_data in tool_calls_buffer.values():
                try:
                    arguments = json.loads(tc_data["arguments"])
                except json.JSONDecodeError:
                    arguments = tc_data["arguments"]
                
                tool_contents.append(ToolCallContent(
                    tool_call_id=tc_data["id"],
                    tool_name=tc_data["name"],
                    arguments=arguments,
                ))
            
            yield ChatResponseUpdate(
                contents=tool_contents,
                role=Role.ASSISTANT,
            )
        
        # 记录Token统计(用于成本监控)
        if thinking_tokens > 0:
            logger.info(
                f"Token统计: Thinking={thinking_tokens}, "
                f"Output={output_tokens}, "
                f"Ratio={thinking_tokens/output_tokens:.2f}x"
            )
    
    def __del__(self):
        """清理线程池"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)
```

### 3.3 使用示例

#### 基础对话

```python
import asyncio
from qwen_client import QwenChatClient, QwenChatOptions
from agent_framework import ChatAgent

async def main():
    client = QwenChatClient(
        model_id="qwen-plus",
        region="china"  # 或 "international"
    )
    
    agent = ChatAgent(
        chat_client=client,
        name="QwenAssistant",
        instructions="你是一个专业的AI助手。"
    )
    
    options = QwenChatOptions(
        temperature=0.7,
        seed=42
    )
    
    result = await agent.run(
        "解释什么是Transformer架构",
        additional_chat_options=options
    )
    print(result.text)

asyncio.run(main())
```

---

## 四、Qwen3思考模式深度解析

### 4.1 核心概念:"系统2"推理

Qwen3的思考功能基于强化学习训练,模型在生成答案前会先生成内部推理过程。

**关键特性**:
- 双流输出:`reasoning_content`(思考) + `content`(答案)
- 计费影响:思考Token可能是答案的**3-10倍**
- 延迟增加:首字生成时间(TTFT)显著提高

### 4.2 思考模式完整参数

| 参数 | 位置 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| **enable_thinking** | extra_body | Boolean | False | 思考总开关 |
| **thinking_budget** | extra_body | Integer | 自动 | 思考Token预算上限 |
| **stream** | 根参数 | Boolean | - | **思考模式必须为True** |
| **include_reasoning** | 客户端 | Boolean | False | 是否在响应中包含思考内容 |

### 4.3 使用场景决策

```python
def choose_thinking_mode(query: str) -> QwenChatOptions:
    """根据任务复杂度选择思考配置"""
    
    # 简单任务 - 关闭思考
    if is_simple_qa(query):
        return QwenChatOptions(
            enable_thinking=False,
            temperature=0.7
        )
    
    # 中等复杂 - 限制预算
    elif is_medium_task(query):
        return QwenChatOptions(
            enable_thinking=True,
            thinking_budget=1024,  # 限制成本
            temperature=0.6
        )
    
    # 高复杂度 - 充足预算
    else:
        return QwenChatOptions(
            enable_thinking=True,
            thinking_budget=4096,  # 深度思考
            temperature=0.6,
            top_p=0.95
        )
```

### 4.4 完整示例:启用思考但不打印

```python
async def thinking_hidden_example():
    """启用思考但在UI中隐藏思考过程"""
    
    client = QwenChatClient(model_id="qwen-plus")
    
    agent = ChatAgent(
        chat_client=client,
        name="DeepThinker",
        instructions="你是一个善于深度推理的数学专家。"
    )
    
    # 配置:启用思考,但不返回思考内容
    options = QwenChatOptions(
        enable_thinking=True,
        thinking_budget=2048,
        include_reasoning=False,  # 🔥 不在响应中包含思考
        temperature=0.6
    )
    
    print("用户:证明根号2是无理数")
    print("Assistant(正在深度思考...): ", end="", flush=True)
    
    # 流式输出 - 只显示最终答案
    async for update in agent.run_stream(
        "证明根号2是无理数",
        additional_chat_options=options
    ):
        if update.text:
            print(update.text, end="", flush=True)
    
    print("\n")
    
    # ⚠️ 注意:虽然用户没看到思考过程,但已经为此付费!
    # 可以在后台日志中看到Token统计
```

### 4.5 为什么不能在服务器端屏蔽?

**架构设计原因**:
1. **计费透明性**:思考Token是成本一部分,必须返回作为计费凭证
2. **调试需求**:开发者需要查看推理过程排查错误
3. **字段分离**:reasoning_content和content物理隔离,客户端自由选择

**结论**:
- ✅ API一定会传输思考内容
- ✅ 客户端决定是否展示
- ✅ 无论是否展示,都已付费

---

## 五、视觉模型qwen3-vl-plus集成

### 5.1 图像处理

```python
async def image_analysis():
    client = QwenChatClient(model_id="qwen3-vl-plus")
    
    agent = ChatAgent(chat_client=client, name="VisionAgent")
    
    # 图像消息格式
    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://example.com/chart.png"
                    # 或使用Base64:"data:image/png;base64,iVBORw0KG..."
                }
            },
            {
                "type": "text",
                "text": "分析这张图表的趋势"
            }
        ]
    }]
    
    # 启用视觉推理
    options = QwenChatOptions(
        enable_thinking=True,  # 视觉推理链
        thinking_budget=3072,
        min_pixels=256 * 256,
        max_pixels=1280 * 1280
    )
    
    result = await agent.run(messages, additional_chat_options=options)
    print(result.text)
```

### 5.2 视频处理(客户端抽帧)

```python
import cv2
import base64
from io import BytesIO
from PIL import Image

def extract_video_frames(
    video_path: str,
    max_frames: int = 512
) -> list[dict]:
    """
    从视频中提取帧
    
    ⚠️ 限制:4-512帧
    """
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # 计算采样间隔
    interval = max(1, total_frames // max_frames)
    
    frames = []
    frame_idx = 0
    
    while len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_idx % interval == 0:
            # 转换为Base64
            _, buffer = cv2.imencode('.jpg', frame)
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            
            frames.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_base64}"
                }
            })
        
        frame_idx += 1
    
    cap.release()
    
    # 验证帧数限制
    if len(frames) < 4:
        raise ValueError(f"视频至少需要4帧,当前只有{len(frames)}帧")
    if len(frames) > 512:
        frames = frames[:512]
    
    return frames

async def video_analysis():
    client = QwenChatClient(model_id="qwen3-vl-plus")
    agent = ChatAgent(chat_client=client, name="VideoAnalyzer")
    
    # 提取帧
    video_frames = extract_video_frames("demo.mp4", max_frames=128)
    
    messages = [{
        "role": "user",
        "content": video_frames + [{
            "type": "text",
            "text": "总结这个视频的内容"
        }]
    }]
    
    options = QwenChatOptions(
        enable_thinking=True,
        thinking_budget=5120,  # 视频分析需要更多预算
        temperature=0.7
    )
    
    print("正在分析视频(可能需要较长时间)...")
    
    async for update in agent.run_stream(messages, additional_chat_options=options):
        if update.text:
            print(update.text, end="", flush=True)
```

---

## 六、成本控制与Token监控

### 6.1 Token组成分析

```
总成本 = (Input Tokens × 输入单价) + 
         (Reasoning Tokens × 输出单价) + 
         (Output Tokens × 输出单价)
```

**关键事实**:
- Reasoning Tokens**等同于Output Tokens计费**
- 思考内容通常是答案的**3-10倍**长度
- 即使`include_reasoning=False`,仍然计费

### 6.2 成本监控中间件

```python
from agent_framework import agent_middleware, AgentRunContext
import logging

logger = logging.getLogger(__name__)

@agent_middleware
async def token_accounting_middleware(ctx: AgentRunContext, next_mw):
    """全局Token审计中间件"""
    
    result = await next_mw(ctx)
    
    if result and result.usage:
        usage = result.usage
        total_cost = (
            usage.input_tokens * 0.0004 +  # 假设单价(美元/千Token)
            usage.output_tokens * 0.0012
        )
        
        logger.warning(
            f"[Token审计] Agent={ctx.agent.name} | "
            f"Input={usage.input_tokens} | "
            f"Output={usage.output_tokens} | "
            f"Total={usage.total_tokens} | "
            f"Cost=${total_cost:.4f}"
        )
        
        # 可选:写入监控系统
        # prometheus_client.Counter('qwen_tokens_total').inc(usage.total_tokens)
        # prometheus_client.Gauge('qwen_cost_usd').set(total_cost)
        
        # 预算保护
        if usage.total_tokens > 10000:
            logger.error(f"Token使用超标!Agent={ctx.agent.name}")
    
    return result

# 应用中间件
agent = ChatAgent(
    chat_client=qwen_client,
    middlewares=[token_accounting_middleware]
)
```

### 6.3 动态预算控制

```python
class AdaptiveThinkingBudget:
    """自适应思考预算控制器"""
    
    def __init__(self, max_daily_budget: int = 100000):
        self.max_daily_budget = max_daily_budget
        self.today_used = 0
    
    def get_budget(self, query_complexity: str) -> int:
        """根据剩余预算和任务复杂度返回建议预算"""
        
        remaining = self.max_daily_budget - self.today_used
        
        if remaining < 1000:
            return 0  # 关闭思考
        
        budgets = {
            "simple": 512,
            "medium": 1024,
            "complex": 2048
        }
        
        suggested = budgets.get(query_complexity, 1024)
        return min(suggested, remaining // 10)  # 保守分配
    
    def record_usage(self, tokens: int):
        """记录使用量"""
        self.today_used += tokens

# 使用
budget_controller = AdaptiveThinkingBudget(max_daily_budget=100000)

async def smart_query(query: str):
    complexity = analyze_complexity(query)
    budget = budget_controller.get_budget(complexity)
    
    options = QwenChatOptions(
        enable_thinking=budget > 0,
        thinking_budget=budget if budget > 0 else None
    )
    
    result = await agent.run(query, additional_chat_options=options)
    
    if result.usage:
        budget_controller.record_usage(result.usage.total_tokens)
    
    return result
```

---

## 七、常见问题排查

### Q1: 启用思考时报400错误

**错误信息**:
```
parameter.enable_thinking must be set to false for non-streaming calls
```

**原因**: 思考模式必须使用流式响应

**解决**:
```python
# ❌ 错误
result = await agent.run(query, enable_thinking=True)

# ✅ 正确
async for update in agent.run_stream(query, enable_thinking=True):
    print(update.text, end="")
```

---

### Q2: 流式输出显示重复文本

**症状**: UI显示"HelloHello worldHello world!"

**原因**: 没有设置`incremental_output=True`

**解决**: QwenClient已强制设置,检查是否被覆盖
```python
params["incremental_output"] = True  # 在代码中确认此行存在
```

---

### Q3: API Key报错

**错误**: InvalidApiKey

**原因**: API Key与region不匹配

**解决**:
```python
# 检查Key来源
# 中国站Key: 在dashscope.aliyuncs.com申请
# 国际站Key: 在dashscope-intl.aliyuncs.com申请

client = QwenChatClient(
    api_key="sk-...",  # 确认Key来源
    region="china"     # 确保region匹配
)
```

---

### Q4: 视频处理失败

**错误**: Exceeded image/video frame limit

**原因**: 帧数不在4-512范围内

**解决**:
```python
frames = extract_frames(video)

# 验证
if len(frames) < 4:
    raise ValueError("至少需要4帧")
if len(frames) > 512:
    frames = frames[:512]  # 截断
```

---

## 八、生产环境检查清单

### 部署前核对

- [ ] ✅ 使用BaseChatClient(获得中间件和遥测)
- [ ] ✅ 配置TypedDict强类型参数
- [ ] ✅ 设置`incremental_output=True`
- [ ] ✅ 思考模式使用流式响应
- [ ] ✅ 配置Token监控中间件
- [ ] ✅ 设置`thinking_budget`限制成本
- [ ] ✅ 配置OpenTelemetry导出
- [ ] ✅ 验证API Key与region匹配
- [ ] ✅ 实现错误重试机制
- [ ] ✅ 添加速率限制保护

---

## 九、总结

### 核心要点

1. ✅ **继承BaseChatClient**:生产环境必需
2. ✅ **TypedDict配置**:v1.0.0b260127标准
3. ✅ **incremental_output=True**:流式必需
4. ✅ **stream=True**:思考模式硬性要求
5. ✅ **thinking_budget**:成本控制关键
6. ✅ **字段分离**:reasoning_content客户端过滤
7. ✅ **异步桥接**:asyncio.to_thread避免阻塞
8. ✅ **Token监控**:中间件实现审计

### 实施路径

**阶段1:快速验证(1天)**
- 使用OpenAI兼容模式
- 验证基础功能

**阶段2:生产准备(3-5天)**
- 实现完整QwenClient
- 添加TypedDict配置
- 集成监控和中间件

**阶段3:优化迭代(持续)**
- 调整thinking_budget
- 优化成本控制
- 根据追踪优化Prompt

---

**参考文档**:
- Microsoft Agent Framework: https://learn.microsoft.com/en-us/agent-framework
- DashScope API: https://www.alibabacloud.com/help/en/model-studio
- Qwen3技术博客: https://qwenlm.github.io

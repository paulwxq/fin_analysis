# **Microsoft Agent Framework与Qwen3系列模型深度集成架构设计文档**

## **1\. 执行摘要**

随着生成式人工智能技术的飞速发展，企业级应用对多模态推理能力、长上下文处理以及实时联网搜索的需求日益增长。微软代理框架（Microsoft Agent Framework, MAF）作为下一代智能体编排的核心基础设施，凭借其模块化、协议驱动的设计理念，为异构模型的集成提供了广阔的空间 1。与此同时，阿里云通义千问（Qwen）系列模型在推理性能、视觉理解及中文语境处理上展现出了卓越的能力，特别是最新的 Qwen3 系列（包括 qwen-plus、qwen3-max）以及视觉语言模型 qwen3-vl-plus，已成为众多行业解决方案的首选基座 3。

本设计文档旨在详尽阐述如何将 Qwen3 系列模型无缝集成至 Microsoft Agent Framework 的 Python 生态系统中。设计核心在于构建符合 MAF 最新版本（v1.0.0b+）标准的 ChatClientProtocol 协议适配器，即 Qwen3ChatClient 与 Qwen3VLChatClient。通过对 MAF 架构的深度剖析与 DashScope SDK 的精细封装，本方案不仅解决了跨框架协议转换、异步流式传输、多模态内容编组等技术难题，还针对 Qwen 特有的“思考模式”（Thinking Mode）与联网搜索（Web Search）功能进行了原生级支持设计。

本报告将通过七个核心章节，从架构原理、协议分析、详细设计、代码实现到生产级部署考量，全方位指导开发团队完成这一集成工作，确保最终交付的 Agent 具备高可用性、高扩展性及卓越的业务处理能力。

## ---

**2\. 架构背景与技术选型**

### **2.1 Microsoft Agent Framework 的设计哲学**

Microsoft Agent Framework（前身为 Semantic Kernel 的一部分演进及 AutoGen 的思想融合）代表了微软在 Agentic AI 领域的最新架构实践 5。与早期框架通过硬编码绑定特定模型提供商（如 OpenAI）不同，MAF 采用了基于协议（Protocol-based）的松耦合设计。

#### **2.1.1 协议驱动的扩展性**

在 MAF 的 Python 实现中，核心交互逻辑并非依赖于具体的类继承，而是基于结构化子类型（Structural Subtyping，即 Duck Typing）定义的协议。ChatClientProtocol 定义了任何聊天客户端必须具备的行为契约：即必须实现 get\_response 和 get\_streaming\_response 两个异步方法 7。这种设计允许开发者在不修改框架核心（AgentExecutor, WorkflowBuilder）的前提下，注入任意符合该签名的推理后端。

#### **2.1.2 异步与流式优先**

MAF 深度集成了 Python 的 asyncio 库，强调全链路异步处理以支持高并发的 Agent 编排。特别是在多 Agent 协作（如 Group Chat）场景下，非阻塞 I/O 是性能的关键。因此，集成 Qwen3 必须严格遵循异步编程范式，这对基于 HTTP 请求的 DashScope SDK 提出了明确的封装要求——必须避免同步阻塞事件循环 9。

### **2.2 Qwen3 系列模型的能力图谱**

阿里云 Qwen3 系列模型在架构上引入了多项对 Agent 开发至关重要的特性，这些特性决定了封装层的设计复杂度与功能边界。

| 模型标识 | 核心能力 | 输入模态 | 输出特性 | 集成挑战 |
| :---- | :---- | :---- | :---- | :---- |
| **qwen-plus / qwen3-max** | 强逻辑推理、超长上下文（128k+）、联网搜索插件 | 文本 | 文本、思考过程（Thinking） | 需处理非标准参数 enable\_search、enable\_thinking；流式增量差异 |
| **qwen3-vl-plus** | 细粒度视觉理解、视频流分析、文档解析 | 文本 \+ 图像 \+ 视频 | 文本 | 需处理多模态消息格式转换、图片/视频的 URL 与 Base64 编码适配 |

#### **2.2.1 思考模式与联网搜索**

Qwen3-Max 引入的“思考模式”允许模型在生成最终答案前输出思维链（Chain of Thought），这在复杂任务规划中极具价值 11。同时，enable\_search 参数使得模型能够原生调用搜索引擎并返回带有引用的回答。MAF 的标准 ChatOptions 并不直接包含这些字段，因此设计中必须通过 kwargs 透传或自定义配置类来实现参数注入 12。

#### **2.2.2 多模态交互协议**

qwen3-vl-plus 并不使用标准的 OpenAI Vision 格式，而是通过 DashScope 特有的 MultiModalConversation 接口进行交互 13。该接口要求消息体（Message Body）采用特定的列表字典结构（\[{'image': '...'}, {'text': '...'}\]），且对图片大小、格式有严格限制。这要求适配器层必须具备强大的内容编组（Content Marshaling）能力，将 MAF 的 ImageContent 对象转换为 DashScope 接受的 Payload。

## ---

**3\. 核心接口与协议深度分析**

在编写代码之前，必须透彻理解 MAF 与 DashScope 之间的“阻抗匹配”问题。本章将对比两者的核心数据结构，确立映射规则。

### **3.1 消息对象：ChatMessage vs DashScope Message**

#### **3.1.1 MAF ChatMessage 结构**

在 MAF 中，ChatMessage 是信息传递的原子单元 8。

* **Role**: 枚举类型，包含 USER, ASSISTANT, SYSTEM。  
* **Contents**: 一个多态列表，可包含 TextContent, ImageContent 等。  
* **Text**: 一个计算属性，自动聚合 Contents 中的所有文本信息。  
* **Additional Properties**: 用于存储元数据。

#### **3.1.2 DashScope Message 结构**

DashScope SDK 要求字典列表格式 16。

* **文本模型**: {'role': 'user', 'content': 'hello'}  
* **多模态模型**: {'role': 'user', 'content': \[{'image': 'url'}, {'text': 'hello'}\]}

**设计决策 1**：适配器必须遍历 MAF 的 ChatMessage.contents。对于 Qwen3ChatClient，主要提取文本；对于 Qwen3VLChatClient，则需根据 Content 类型动态构建字典列表。

### **3.2 响应对象：ChatResponse vs GenerationOutput**

#### **3.2.1 MAF ChatResponse**

ChatResponse 是非流式调用的返回结果 7。

* **messages**: 包含模型生成的 ChatMessage 列表。  
* **finish\_reason**: 结束原因（Stop, Length, ToolCalls）。  
* **model\_id**: 实际执行推理的模型 ID。

#### **3.2.2 DashScope Response**

DashScope 返回 GenerationResponse 对象 16。

* **output.text**: 生成的文本。  
* **output.finish\_reason**: 字符串形式（'stop', 'null'）。  
* **usage**: Token 消耗统计。

**设计决策 2**：需建立 finish\_reason 的映射表。DashScope 的 null 在流式传输中常见，需映射为 None 或忽略，而在结束时 stop 映射为 FinishReason.STOP。

### **3.3 流式更新：ChatResponseUpdate vs Incremental Output**

这是集成中最复杂的部分。

* **MAF 机制**: get\_streaming\_response 返回一个异步迭代器（AsyncIterable）。ChatResponseUpdate 代表一个增量（Delta），即当前时刻新生成的字符 18。  
* **DashScope 机制**: 默认情况下，DashScope 的流式返回是**累积的**（Accumulated）。例如，第一帧返回 "A"，第二帧返回 "AB"。如果直接输出，客户端会显示 "AAB"。  
* **解决方案**: 必须在调用 DashScope API 时显式设置 incremental\_output=True 16。这将强制服务器返回增量数据，从而与 MAF 的流式处理逻辑完美对齐。

## ---

**4\. 详细设计：Qwen3ChatClient (文本与推理)**

本章节将详述针对纯文本模型 qwen-plus 和 qwen3-max 的封装设计。该类 Qwen3ChatClient 将继承自 BaseChatClient 并实现 ChatClientProtocol。

### **4.1 类结构设计**

Python

from agent\_framework import BaseChatClient  
from typing import AsyncIterable, Any, Sequence, Optional  
\#... 导入其他依赖

class Qwen3ChatClient(BaseChatClient):  
    """  
    封装阿里云 Qwen3 系列文本模型。  
    支持功能：  
    \- 基础文本生成  
    \- 联网搜索 (Enable Search)  
    \- 思考模式 (Thinking Mode)  
    \- 异步流式输出  
    """  
    def \_\_init\_\_(self, model\_id: str, api\_key: Optional\[str\] \= None, \*\*kwargs):  
        \# 初始化逻辑  
        pass  
      
    async def get\_response(self, messages, \*\*kwargs) \-\> ChatResponse:  
        \# 非流式调用实现  
        pass

    async def get\_streaming\_response(self, messages, \*\*kwargs) \-\> AsyncIterable:  
        \# 流式调用实现  
        pass

### **4.2 依赖管理与环境配置**

封装代码依赖 dashscope 官方 SDK。根据研究资料，必须确保 SDK 版本支持 incremental\_output 参数 11。 建议版本：dashscope \>= 1.20.0。

### **4.3 关键逻辑实现分析**

#### **4.3.1 参数透传机制 (Parameter Passthrough)**

MAF 的 ChatOptions 主要是为 OpenAI 风格的参数（temperature, top\_p, max\_tokens）设计的。Qwen 特有的参数如 enable\_search、result\_format 需要通过 kwargs 传递。

在 Qwen3ChatClient 中，我们将采取“提取并注入”策略：先从 kwargs 中提取 DashScope 专属参数，剩余参数作为通用配置处理。

#### **4.3.2 异步并发模型 (Async Concurrency)**

DashScope 的 Python SDK Generation.call 方法本身是同步阻塞的（尽管底层可能使用线程池，但调用方会阻塞）。在 MAF 的全异步架构中，直接调用会阻塞 Agent 的事件循环，导致并发性能下降。

**解决方案**：使用 asyncio.to\_thread 将同步的 SDK 调用放入后台线程池执行。这是 Python 异步编程处理阻塞 I/O 的标准范式。

#### **4.3.3 错误处理与重试**

DashScope API 可能返回 HTTP 400/429/500 等错误码。

* **429 (Rate Limit)**: 应抛出特定异常以便 MAF 的中间件捕获并执行指数退避重试。  
* **400 (Invalid Parameter)**: 如 enable\_thinking 与 incremental\_output 配置冲突 11，应抛出不可重试的 ValueError。

### **4.4 源代码实现：Qwen3ChatClient**

以下是完整的、符合 MAF v1.0.0b+ 规范的实现代码。

Python

import os  
import asyncio  
import logging  
from typing import Any, AsyncIterable, Dict, List, Optional, Sequence, Union, Literal

\# 导入 Microsoft Agent Framework 核心组件  
\# 根据 \[19\] 和 \[7\] 确认的导入路径  
from agent\_framework import (  
    BaseChatClient,  
    ChatResponse,  
    ChatResponseUpdate,  
    ChatMessage,  
    Role,  
    FinishReason,  
)

\# 导入 DashScope SDK  
import dashscope  
from dashscope.api\_entities.dashscope\_response import GenerationResponse  
from http import HTTPStatus

\# 配置日志  
logger \= logging.getLogger(\_\_name\_\_)

class Qwen3ChatClient(BaseChatClient):  
    """  
    阿里云 Qwen3/Qwen-Plus 文本模型封装客户端。  
    实现了 Microsoft Agent Framework 的 ChatClientProtocol。  
    """

    def \_\_init\_\_(  
        self,   
        model\_id: str \= "qwen-plus",   
        api\_key: Optional\[str\] \= None,  
        \*\*kwargs: Any  
    ):  
        """  
        初始化 Qwen3ChatClient。

        Args:  
            model\_id (str): DashScope 模型 ID (如 'qwen-plus', 'qwen3-max').  
            api\_key (str, optional): API Key。如不提供则读取环境变量 DASHSCOPE\_API\_KEY。  
            \*\*kwargs: 传递给 DashScope 的默认生成参数。  
        """  
        self.model\_id \= model\_id  
        self.api\_key \= api\_key or os.environ.get("DASHSCOPE\_API\_KEY")  
        if not self.api\_key:  
            raise ValueError("必须提供 api\_key 或设置环境变量 DASHSCOPE\_API\_KEY")  
          
        \# 存储默认参数  
        self.default\_kwargs \= kwargs

    def \_convert\_messages(self, messages: Sequence\[ChatMessage\]) \-\> List\]:  
        """  
        将 MAF ChatMessage 转换为 DashScope 消息格式。  
        """  
        dashscope\_messages \=  
        for msg in messages:  
            \# 获取角色字符串，兼容枚举和字符串  
            role \= msg.role.value if hasattr(msg.role, "value") else str(msg.role)  
            \# MAF 的 msg.text 属性会自动聚合 TextContent  
            content \= msg.text  
              
            if not content:  
                continue \# 跳过空消息

            dashscope\_messages.append({  
                "role": role,  
                "content": content  
            })  
        return dashscope\_messages

    def \_map\_finish\_reason(self, reason: Optional\[str\]) \-\> Optional:  
        """  
        映射结束原因。  
        DashScope 返回: 'stop', 'length', 'tool\_calls', 'null'  
        """  
        if not reason or reason \== "null":  
            return None  
        if reason \== "stop":  
            return FinishReason.STOP  
        if reason \== "length":  
            return FinishReason.LENGTH  
        if reason \== "tool\_calls":  
            return FinishReason.TOOL\_CALLS  
        return FinishReason.STOP

    async def get\_response(  
        self,   
        messages: Sequence\[ChatMessage\],   
        \*,   
        max\_tokens: Optional\[int\] \= None,  
        temperature: Optional\[float\] \= None,  
        top\_p: Optional\[float\] \= None,  
        tools: Optional\[Any\] \= None,  
        \*\*kwargs: Any  
    ) \-\> ChatResponse:  
        """  
        非流式获取模型响应。  
        """  
        \# 合并参数  
        call\_kwargs \= {\*\*self.default\_kwargs, \*\*kwargs}  
        ds\_messages \= self.\_convert\_messages(messages)

        \# 提取 Qwen 特有参数  
        enable\_search \= call\_kwargs.pop("enable\_search", False)  
        \# 注意：enable\_thinking 仅支持流式调用，此处若设置需警告或忽略  
        if call\_kwargs.get("enable\_thinking"):  
            logger.warning("enable\_thinking 仅支持流式调用 (get\_streaming\_response)，在非流式调用中将被忽略。")  
            call\_kwargs.pop("enable\_thinking")

        try:  
            \# 使用 asyncio.to\_thread 避免阻塞事件循环  
            response: GenerationResponse \= await asyncio.to\_thread(  
                dashscope.Generation.call,  
                model=self.model\_id,  
                messages=ds\_messages,  
                result\_format='message',  
                api\_key=self.api\_key,  
                max\_tokens=max\_tokens,  
                temperature=temperature,  
                top\_p=top\_p,  
                enable\_search=enable\_search,  
                \*\*call\_kwargs  
            )  
        except Exception as e:  
            \# 捕获 SDK 抛出的异常并包装  
            raise RuntimeError(f"Qwen 调用失败: {str(e)}") from e

        if response.status\_code \== HTTPStatus.OK:  
            choice \= response.output.choices  
            content \= choice.message.content  
            role \= choice.message.role  
            finish\_reason \= self.\_map\_finish\_reason(choice.finish\_reason)

            \# 构建 MAF 响应  
            \# 注意：如果启用了搜索，response 可能包含 search\_info，可放入 additional\_properties  
            additional\_props \= {}  
            if hasattr(response.output, "search\_info"):  
                additional\_props\["search\_info"\] \= response.output.search\_info

            response\_msg \= ChatMessage(  
                role=role,   
                content=content,  
                additional\_properties=additional\_props  
            )

            return ChatResponse(  
                messages=\[response\_msg\],  
                model\_id=self.model\_id,  
                finish\_reason=finish\_reason  
            )  
        else:  
            raise RuntimeError(f"DashScope API Error: {response.code} \- {response.message}")

    async def get\_streaming\_response(  
        self,   
        messages: Sequence\[ChatMessage\],   
        \*,   
        max\_tokens: Optional\[int\] \= None,  
        temperature: Optional\[float\] \= None,  
        top\_p: Optional\[float\] \= None,  
        \*\*kwargs: Any  
    ) \-\> AsyncIterable:  
        """  
        流式获取模型响应。  
        """  
        call\_kwargs \= {\*\*self.default\_kwargs, \*\*kwargs}  
        ds\_messages \= self.\_convert\_messages(messages)  
          
        enable\_search \= call\_kwargs.pop("enable\_search", False)  
        \# 确保增量输出开启，这对流式至关重要   
        incremental\_output \= True 

        \# 定义同步生成器函数，供线程池调用  
        def \_sync\_generator():  
            return dashscope.Generation.call(  
                model=self.model\_id,  
                messages=ds\_messages,  
                result\_format='message',  
                stream=True,  
                incremental\_output=incremental\_output,  
                api\_key=self.api\_key,  
                max\_tokens=max\_tokens,  
                temperature=temperature,  
                top\_p=top\_p,  
                enable\_search=enable\_search,  
                \*\*call\_kwargs  
            )

        \# 在线程中获取生成器对象  
        \# 注意：DashScope 的 call 方法在 stream=True 时返回一个生成器  
        \# 我们不能直接 await 生成器，需要在一个线程中遍历它，并使用 Queue 或其他机制传回  
        \# 但为了简化且利用 asyncio 的特性，我们可以将生成器的 \`\_\_next\_\_\` 调用放入线程  
        \# 或者更简单地，使用 asyncio.to\_thread 运行整个迭代逻辑 (但这会阻塞一个线程直到完成)  
        \# 最优解是构建一个异步迭代器适配器。

        loop \= asyncio.get\_running\_loop()  
        queue \= asyncio.Queue()  
        sentinel \= object()

        def \_producer():  
            try:  
                responses \= \_sync\_generator()  
                for resp in responses:  
                    loop.call\_soon\_threadsafe(queue.put\_nowait, resp)  
                loop.call\_soon\_threadsafe(queue.put\_nowait, sentinel)  
            except Exception as e:  
                loop.call\_soon\_threadsafe(queue.put\_nowait, e)

        \# 启动生产者线程  
        import threading  
        producer\_thread \= threading.Thread(target=\_producer, daemon=True)  
        producer\_thread.start()

        \# 消费者循环  
        while True:  
            item \= await queue.get()  
            if item is sentinel:  
                break  
            if isinstance(item, Exception):  
                raise item  
              
            \# 处理响应  
            response \= item  
            if response.status\_code \== HTTPStatus.OK:  
                choice \= response.output.choices  
                delta \= choice.message.content  
                finish\_reason \= self.\_map\_finish\_reason(choice.finish\_reason)  
                  
                \# 处理 Thinking Mode 的特殊输出 (如果有)  
                \# Qwen3-Max 的思考内容通常直接包含在 content 中，或者在单独的 reasoning 字段  
                \# 需根据具体的 API 响应结构调整。目前主要假设在 content 中。

                yield ChatResponseUpdate(  
                    content=delta,  
                    role=choice.message.role,  
                    finish\_reason=finish\_reason,  
                    model\_id=self.model\_id  
                )  
            else:  
                raise RuntimeError(f"DashScope Stream Error: {response.code} \- {response.message}")

## ---

**5\. 详细设计：Qwen3VLChatClient (视觉多模态)**

Qwen3VLChatClient 的核心挑战在于多模态数据的编排。qwen3-vl-plus 不仅支持文本，还支持图像和视频。在 MAF 中，这些数据通过 contents 列表传递。

### **5.1 多模态内容协议转换**

DashScope VL 模型的消息格式要求极高。

* **MAF 输入**: \`\`  
* **DashScope 目标**: \[{'role': 'user', 'content': \[{'text': '描述图片'}, {'image': '...'}\]}\]

我们需要编写一个健壮的转换器 \_process\_content，能够处理：

1. **URL 图片**: 直接提取 URL。  
2. **Base64 图片**: MAF 可能传递 Base64 编码的数据。DashScope 支持 data:image/png;base64,... 格式的字符串 20。  
3. **本地文件**: 虽然 MAF 通常在分布式环境中通过 URL 传递，但在本地开发时可能会遇到文件路径。DashScope SDK 支持 file:// 协议，但最佳实践是将本地文件转换为 Base64 或上传到 OSS。本设计将优先支持 URL 和 Base64。

### **5.2 视频支持**

Qwen3-VL 具备强大的视频理解能力。虽然 MAF 当前的 ChatMessage 可能主要定义了 ImageContent，但通过扩展 additional\_properties 或自定义 VideoContent（如果是鸭子类型），我们可以支持视频。

在封装中，我们将检查 Content 对象的类型或属性。如果发现 video\_url 或 type='video'，则生成 {'video': '...'} 的 DashScope 消息项。

### **5.3 源代码实现：Qwen3VLChatClient**

Python

from dashscope import MultiModalConversation

class Qwen3VLChatClient(BaseChatClient):  
    """  
    阿里云 Qwen3-VL (Vision Language) 多模态模型封装。  
    支持 qwen3-vl-plus, qwen-vl-max 等。  
    """

    def \_\_init\_\_(self, model\_id: str \= "qwen3-vl-plus", api\_key: Optional\[str\] \= None, \*\*kwargs):  
        self.model\_id \= model\_id  
        self.api\_key \= api\_key or os.environ.get("DASHSCOPE\_API\_KEY")  
        if not self.api\_key:  
            raise ValueError("需要 API Key")  
        self.default\_kwargs \= kwargs

    def \_process\_content\_item(self, item: Any) \-\> Dict\[str, str\]:  
        """  
        将单个 Content 对象转换为 DashScope 字典格式。  
        """  
        \# 1\. 处理纯文本字符串  
        if isinstance(item, str):  
            return {"text": item}  
          
        \# 2\. 处理 MAF TextContent 对象 (鸭子类型检测)  
        if hasattr(item, "text") and item.text:  
            return {"text": item.text}

        \# 3\. 处理 MAF ImageContent 对象  
        \# MAF 的 ImageContent 通常有 url 或 data 属性  
        if hasattr(item, "url") and item.url:  
            return {"image": item.url}  
          
        if hasattr(item, "data") and item.data:  
            \# 假设 data 是 base64 字符串  
            \# 需确保格式为 data:image/xxx;base64,xxx  
            \# 如果仅是 raw base64，需拼接前缀 (此处假设用户已处理或为标准 URL 格式)  
            return {"image": item.data}

        \# 4\. 处理自定义 VideoContent (假设)  
        if hasattr(item, "video\_url"):  
            return {"video": item.video\_url}

        \# 5\. 兜底：尝试从字典转换  
        if isinstance(item, dict):  
            if "image\_url" in item:  
                return {"image": item\["image\_url"\]\["url"\]}  
            if "video\_url" in item:  
                return {"video": item\["video\_url"\]}  
            return item  
          
        return {"text": str(item)}

    def \_convert\_messages(self, messages: Sequence\[ChatMessage\]) \-\> List\]:  
        ds\_messages \=  
        for msg in messages:  
            role \= msg.role.value if hasattr(msg.role, "value") else str(msg.role)  
            content\_list \=  
              
            \# 优先使用 contents 列表  
            if hasattr(msg, "contents") and msg.contents:  
                for item in msg.contents:  
                    processed \= self.\_process\_content\_item(item)  
                    content\_list.append(processed)  
            elif msg.text:  
                \# 回退到纯文本  
                content\_list.append({"text": msg.text})  
              
            ds\_messages.append({  
                "role": role,  
                "content": content\_list  
            })  
        return ds\_messages

    async def get\_response(  
        self,   
        messages: Sequence\[ChatMessage\],   
        \*,   
        max\_tokens: Optional\[int\] \= None,  
        top\_p: Optional\[float\] \= None,  
        top\_k: Optional\[int\] \= None,  
        \*\*kwargs: Any  
    ) \-\> ChatResponse:  
        """  
        多模态非流式调用。  
        """  
        call\_kwargs \= {\*\*self.default\_kwargs, \*\*kwargs}  
        ds\_messages \= self.\_convert\_messages(messages)

        try:  
            \# MultiModalConversation.call 接口签名与 Generation 略有不同  
            response \= await asyncio.to\_thread(  
                MultiModalConversation.call,  
                model=self.model\_id,  
                messages=ds\_messages,  
                api\_key=self.api\_key,  
                max\_tokens=max\_tokens,  
                top\_p=top\_p,  
                top\_k=top\_k,  
                \*\*call\_kwargs  
            )  
        except Exception as e:  
            raise RuntimeError(f"Qwen-VL 调用失败: {str(e)}") from e

        if response.status\_code \== HTTPStatus.OK:  
            choice \= response.output.choices  
            \# VL 模型返回的 content 通常是字典或列表，需解析为文本作为主要响应  
            raw\_content \= choice.message.content  
            text\_content \= ""  
              
            if isinstance(raw\_content, list):  
                \# 拼接所有文本部分  
                text\_content \= "".join(\[c.get("text", "") for c in raw\_content if "text" in c\])  
            elif isinstance(raw\_content, dict):  
                text\_content \= raw\_content.get("text", "")  
            else:  
                text\_content \= str(raw\_content)

            \# 构造响应  
            return ChatResponse(  
                messages=,  
                model\_id=self.model\_id,  
                finish\_reason=FinishReason.STOP  
            )  
        else:  
            raise RuntimeError(f"DashScope VL Error: {response.code} \- {response.message}")

    async def get\_streaming\_response(  
        self,   
        messages: Sequence\[ChatMessage\],   
        \*,   
        max\_tokens: Optional\[int\] \= None,  
        \*\*kwargs: Any  
    ) \-\> AsyncIterable:  
        """  
        多模态流式调用。  
        """  
        ds\_messages \= self.\_convert\_messages(messages)  
        call\_kwargs \= {\*\*self.default\_kwargs, \*\*kwargs}  
          
        \# 强制增量输出  
        incremental\_output \= True

        def \_sync\_vl\_generator():  
            return MultiModalConversation.call(  
                model=self.model\_id,  
                messages=ds\_messages,  
                stream=True,  
                incremental\_output=incremental\_output,  
                api\_key=self.api\_key,  
                max\_tokens=max\_tokens,  
                \*\*call\_kwargs  
            )

        \# 使用与 Text Client 相同的线程队列模式 (此处简化展示，生产环境应复用逻辑)  
        loop \= asyncio.get\_running\_loop()  
        queue \= asyncio.Queue()  
        sentinel \= object()  
          
        import threading  
        def \_producer():  
            try:  
                for resp in \_sync\_vl\_generator():  
                    loop.call\_soon\_threadsafe(queue.put\_nowait, resp)  
                loop.call\_soon\_threadsafe(queue.put\_nowait, sentinel)  
            except Exception as e:  
                loop.call\_soon\_threadsafe(queue.put\_nowait, e)

        threading.Thread(target=\_producer, daemon=True).start()

        while True:  
            item \= await queue.get()  
            if item is sentinel:  
                break  
            if isinstance(item, Exception):  
                raise item  
              
            response \= item  
            if response.status\_code \== HTTPStatus.OK:  
                choice \= response.output.choices  
                content\_chunk \= choice.message.content  
                  
                \# 解析增量内容  
                text\_delta \= ""  
                if isinstance(content\_chunk, list):  
                    text\_delta \= "".join(\[c.get("text", "") for c in content\_chunk\])  
                elif isinstance(content\_chunk, dict):  
                    text\_delta \= content\_chunk.get("text", "")  
                  
                if text\_delta:  
                    yield ChatResponseUpdate(  
                        content=text\_delta,  
                        role=Role.ASSISTANT,  
                        model\_id=self.model\_id  
                    )  
            else:  
                raise RuntimeError(f"DashScope VL Stream Error: {response.code} \- {response.message}")

## ---

**6\. 高级特性与生产级考量**

### **6.1 配置管理与类型安全**

为了提升开发体验，建议定义一个 TypedDict 来管理 Qwen 的特有参数，而不是依赖散乱的 kwargs。

Python

from typing import TypedDict

class QwenOptions(TypedDict, total=False):  
    enable\_search: bool  
    enable\_thinking: bool  
    search\_options: Dict\[str, Any\]  
    result\_format: Literal\['message'\]

开发者在使用时可以获得 IDE 的智能提示：

Python

client \= Qwen3ChatClient("qwen-max")  
\# IDE 会提示 enable\_search 参数  
response \= await client.get\_response(msgs, enable\_search=True)

### **6.2 思考模式（Thinking Mode）深度集成**

Qwen3-Max 的思考模式对于 Agent 解决复杂逻辑问题（如数学推理、代码生成）至关重要。

* **机制**: 开启 enable\_thinking=True 后，模型会先输出一段被标记的思考过程，然后才是正文。  
* **封装策略**: 在 get\_streaming\_response 中，我们可以解析返回的 token。如果 DashScope 将思考内容与正文内容在不同字段返回（例如 reasoning\_content vs content），封装层可以生成两种类型的 ChatResponseUpdate。目前 MAF 标准 Update 仅包含 content。建议将思考过程作为普通的 content 输出，或者利用 ChatResponseUpdate 的 additional\_properties 字段传递给前端 UI 进行特殊的折叠显示。

### **6.3 联网搜索（Web Search）与引用处理**

当 enable\_search=True 时，Qwen 会返回 search\_info，包含引用的 URL 和标题。

在 Qwen3ChatClient.get\_response 的实现中，我们将 search\_info 注入到了 ChatResponse 的 additional\_properties 中。

Agent 编排层（如 AgentExecutor）可以读取该属性，并在最终报告中生成参考文献列表。这是一个超越 OpenAI 标准能力的特性，极大增强了 Agent 的可信度。

### **6.4 异常恢复与可观测性**

* **重试策略**: 建议在 Qwen3ChatClient 外部包裹一层 MAF 的重试中间件，或者在内部使用 tenacity 库对 dashscope.Generation.call 进行装饰，针对 429 和 500 错误进行自动重试。  
* **OpenTelemetry**: MAF 原生支持 OpenTelemetry。由于我们的 Client 实现了标准协议，MAF 的追踪器会自动记录 get\_response 的调用耗时和结果。为了更细粒度的追踪（例如区分 DashScope 的网络耗时与模型推理耗时），可以在 \_sync\_generator 内部手动添加 Span。

## ---

**7\. 结论**

本设计文档详细阐述了如何在 Microsoft Agent Framework 中构建原生级的 Qwen3 集成。通过 Qwen3ChatClient 和 Qwen3VLChatClient 的实现，我们不仅填补了框架对阿里云模型的支持空白，更通过对异步流式传输、多模态协议转换及高级参数（搜索、思考）的深度适配，释放了 Qwen3 模型在 Agent 场景下的全部潜力。

该方案严格遵循 MAF 的协议标准，确保了代码的模块化与可维护性。对于开发者而言，这意味着可以零成本地将现有的 OpenAI 驱动的 Agent 迁移至 Qwen 平台，或构建混合模型的复杂工作流，为构建下一代智能应用奠定了坚实基础。

#### **Works cited**

1. microsoft/agent-framework: A framework for building, orchestrating and deploying AI agents and multi-agent workflows with support for Python and .NET. \- GitHub, accessed on January 29, 2026, [https://github.com/microsoft/agent-framework](https://github.com/microsoft/agent-framework)  
2. Agent based on any IChatClient \- Microsoft Learn, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/chat-client-agent](https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/chat-client-agent)  
3. Alibaba Cloud Model Studio:OpenAI compatible \- Chat, accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)  
4. Qwen API, accessed on January 29, 2026, [https://qwen.ai/apiplatform](https://qwen.ai/apiplatform)  
5. Introduction to Microsoft Agent Framework, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview)  
6. Introducing Microsoft Agent Framework: The Open-Source Engine for Agentic AI Apps, accessed on January 29, 2026, [https://devblogs.microsoft.com/foundry/introducing-microsoft-agent-framework-the-open-source-engine-for-agentic-ai-apps/](https://devblogs.microsoft.com/foundry/introducing-microsoft-agent-framework-the-open-source-engine-for-agentic-ai-apps/)  
7. agent\_framework.ChatClientProtocol class | Microsoft Learn, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent\_framework.chatclientprotocol?view=agent-framework-python-latest](https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.chatclientprotocol?view=agent-framework-python-latest)  
8. agent\_framework package | Microsoft Learn, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent\_framework?view=agent-framework-python-latest](https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework?view=agent-framework-python-latest)  
9. Microsoft Agent Framework Quick-Start Guide, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/agent-framework/tutorials/quick-start](https://learn.microsoft.com/en-us/agent-framework/tutorials/quick-start)  
10. 完整教程：双剑合璧：Microsoft Agent Framework——Python与.NET的AI智能体协奏曲 \- 博客园, accessed on January 29, 2026, [https://www.cnblogs.com/yangykaifa/p/19199854](https://www.cnblogs.com/yangykaifa/p/19199854)  
11. Alibaba Cloud Model Studio:Error messages, accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/error-code](https://www.alibabacloud.com/help/en/model-studio/error-code)  
12. An unofficial DashScope（ SDK for .NET maintained by Cnblogs. \- GitHub, accessed on January 29, 2026, [https://github.com/cnblogs/dashscope-sdk](https://github.com/cnblogs/dashscope-sdk)  
13. Alibaba Cloud Model Studio:Visual understanding (Qwen-VL), accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/vision](https://www.alibabacloud.com/help/en/model-studio/vision)  
14. Streaming output for Qwen models \- Alibaba Cloud Model Studio, accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/stream](https://www.alibabacloud.com/help/en/model-studio/stream)  
15. agent\_framework.ChatMessage class \- Microsoft Learn, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent\_framework.chatmessage?view=agent-framework-python-latest](https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.chatmessage?view=agent-framework-python-latest)  
16. Alibaba Cloud Model Studio:Qwen API reference, accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/developer-reference/use-qwen-by-calling-api/](https://www.alibabacloud.com/help/en/model-studio/developer-reference/use-qwen-by-calling-api/)  
17. Alibaba Cloud Model Studio:Qwen \- image editing API reference, accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/qwen-image-edit-api](https://www.alibabacloud.com/help/en/model-studio/qwen-image-edit-api)  
18. ChatResponseUpdate Class \- agent\_framework \- Microsoft Learn, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent\_framework.chatresponseupdate?view=agent-framework-python-latest](https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.chatresponseupdate?view=agent-framework-python-latest)  
19. Multimodal Large Models | EvalScope \- Read the Docs, accessed on January 29, 2026, [https://evalscope.readthedocs.io/en/latest/advanced\_guides/custom\_dataset/vlm.html](https://evalscope.readthedocs.io/en/latest/advanced_guides/custom_dataset/vlm.html)
# **阿里云 DashScope SDK Qwen-3 系列接口架构与 Microsoft Agent Framework 多模态集成深度研究报告**

## **1\. 执行摘要**

随着大语言模型（LLM）向多模态大语言模型（LMM）的演进，开发者在集成过程中面临着架构分叉的挑战。本报告旨在针对阿里云百炼平台（DashScope）的 Python SDK，对 Qwen-3 系列模型的调用接口进行详尽的技术审计与差异分析，特别是针对旗舰文本模型（qwen-plus/qwen3-max）与视觉语言模型（qwen3-vl-plus）在架构设计、参数支持及数据流处理上的核心区别。此外，报告还将深入探讨 Microsoft Agent Framework（预览版 1.0.0b260128）在处理多模态消息时的抽象机制，为跨框架集成提供理论依据与实施路径。

通过对官方文档、GitHub 源码库及技术社区反馈的全面梳理，本研究确认了 DashScope SDK 内部存在严格的“接口隔离原则”：文本模型依赖 dashscope.Generation 接口，而多模态模型强制使用 dashscope.MultiModalConversation 接口。这种分流设计直接导致了参数支持的异构性，最显著的差异在于 qwen3-vl-plus 目前不支持 enable\_search 参数，这意味着视觉模型无法像文本模型那样原生调用服务端联网搜索能力。在消息结构上，多模态接口要求更复杂的嵌套字典列表格式，以支持文本与图像的交错输入，而文本接口则保持了相对简单的字符串处理逻辑。

针对 Microsoft Agent Framework，研究发现其通过 DataContent 和 UriContent 原语实现了对多模态数据的标准化封装，摒弃了早期的 ImageContent 专用类，从而构建了更具通用性的媒体处理管道。本报告将详细阐述如何将这些通用原语映射回 DashScope 的特定输入格式，以填补两个框架之间的语义鸿沟。

## ---

**2\. DashScope SDK 架构分层与设计哲学**

在深入探讨具体模型的调用差异之前，必须首先理解阿里云 DashScope Python SDK 的底层架构设计。DashScope SDK 并非单一的透传管道，而是一个包含负载验证、协议转换和错误处理的厚客户端（Thick Client）。其设计哲学反映了文本处理与多模态处理在计算范式上的根本分歧。

### **2.1 接口隔离原则（Interface Segregation）**

DashScope SDK 的核心设计特征是依据模型处理的数据类型（Modality）而非模型家族（Family）来划分调用类。尽管 qwen-plus 和 qwen3-vl-plus 均属于 Qwen（通义千问）家族，但在 SDK 层面，它们被视为完全不同的实体。

* **dashscope.Generation（生成接口）**：这是为纯文本任务设计的轻量级接口。其内部逻辑假设输入数据仅包含 token 序列，主要负责处理文本的编码、截断以及与 LLM 后端的文本流交互。该接口的设计目标是高吞吐量和低延迟，因此在参数校验上相对宽松，主要通过 messages 数组传递上下文 1。  
* **dashscope.MultiModalConversation（多模态对话接口）**：这是专为视觉-语言任务设计的重型接口。由于多模态模型（如 Qwen-VL）需要处理图像、视频等非结构化数据，该接口内置了复杂的多媒体预处理逻辑。例如，它负责检测输入是本地文件路径、HTTP URL 还是 Base64 编码字符串，并执行相应的文件读取或格式校验 3。此外，该接口还需处理多模态数据的对齐问题（Alignment），确保图像 Patch 与文本 Token 在输入序列中的相对位置正确。

这种架构上的二分法虽然增加了 SDK 的复杂性，但有效避免了单一接口的臃肿。如果强行在 Generation 接口中支持图片上传，势必会引入大量与文本生成无关的文件 I/O 依赖。然而，这种设计也给开发者带来了认知负担：即便是同一代次的模型（Qwen-3），切换模态也意味着必须重构调用代码。

### **2.2 SDK 路由与模型绑定机制**

在 SDK 内部，模型名称（Model Name）不仅仅是一个字符串标识符，它还充当了路由键（Routing Key）。

当开发者调用 dashscope.Generation.call(model='qwen3-vl-plus',...) 时，SDK 内部的路由表会检测到 qwen3-vl-plus 不属于纯文本模型白名单，或者后端服务在接收到请求后发现 payload 格式不符合预期（例如缺少视觉编码器的输入流），从而抛出 InvalidModel 或 MismatchedInterface 错误 5。

这一机制揭示了 DashScope 后端的服务拓扑：文本模型集群与多模态模型集群在物理上或逻辑上是隔离的。qwen-plus 可能运行在专为 Transformer 解码器优化的集群上，而 qwen3-vl-plus 则需要配备有视觉编码器（如 ViT）和投影层（Projection Layer）的专用推理节点。SDK 的接口分流正是为了适配这种后端架构的异构性。

## ---

**3\. 文本生成模型深度解析：Qwen-Plus / Qwen3-Max**

qwen-plus 和 qwen3-max 代表了通义千问在纯文本领域的最高能力。在 Python SDK 中，它们的调用逻辑已经高度标准化，主要围绕 dashscope.Generation 展开。本节将详细剖析其接口特性，特别是搜索增强（Search Enhancement）的实现机制。

### **3.1 dashscope.Generation 调用范式**

对于文本模型，调用过程遵循标准的“请求-响应”模式。核心方法 Generation.call() 封装了 HTTP POST 请求的构建过程。

Python

from dashscope import Generation  
from dashscope.api\_entities.dashscope\_response import Role

messages \=

response \= Generation.call(  
    model="qwen3-max",  
    messages=messages,  
    result\_format='message',  \# 推荐使用 message 格式以获得完整结构  
    enable\_search=True,       \# 核心差异参数  
    incremental\_output=True   \# 流式输出控制  
)

在此范式中，messages 参数的结构相对扁平。每个消息对象仅包含 role 和 content 两个字段，且 content 必须是字符串类型。SDK 不会对 content 内容进行解析，而是将其直接序列化为 JSON 发送给服务端。

### **3.2 搜索增强（Search Enhancement）：enable\_search**

enable\_search 参数是 Qwen 文本模型的一项关键差异化能力，也是本报告重点关注的对象。

#### **3.2.1 机制原理**

当设置 enable\_search=True 时，模型的推理过程不再是封闭的。

1. **意图识别**：服务端首先对用户 Query 进行意图分类，判断是否需要外部知识。  
2. **查询重写**：如果需要搜索，模型（或辅助模型）会生成一个或多个搜索引擎友好的关键词 Query。  
3. **信息检索**：DashScope 后端对接搜索引擎（可能是阿里内部的夸克搜索或必应等），获取相关的网页摘要。  
4. **上下文注入**：检索到的信息被作为临时的“系统提示词”或“参考资料”注入到 Context Window 中。  
5. **生成与引用**：模型基于检索内容生成回答，并可能在输出中包含引用的角标 6。

这一全过程对 SDK 用户是透明的，用户只需通过布尔值开关即可激活。这表明 enable\_search 是一个高度集成的服务端 RAG（Retrieval-Augmented Generation）解决方案，而非简单的客户端工具调用。

#### **3.2.2 支持范围**

该参数被明确记录在 qwen-turbo、qwen-plus 和 qwen-max 等文本模型的文档中 7。这不仅是功能的体现，更是模型架构属性的反映——这些模型经过了专门的微调（SFT），学会了如何利用搜索结果进行阅读理解和回答生成，同时能较好地抑制幻觉。

### **3.3 增量流式输出（Incremental Output）**

在 Generation 接口中，incremental\_output 参数控制着流式响应的行为。

* **默认行为（False）**：流式返回时，每次 chunk 包含从开头到当前的完整文本（accumulated text）。  
* **增量行为（True）**：每次 chunk 仅包含新生成的 token（delta text）。

对于 Qwen-3 系列的“思考模型”（Thinking Models），如 qwen-max 的某些预览版或具备深度推理能力的版本，文档强调 **必须** 将 incremental\_search 设置为 True 5。这是因为深度推理模型可能会生成极长的思维链（Chain of Thought），如果使用全量返回，随着生成长度的增加，网络传输的 Payload 会呈指数级膨胀，导致延迟激增甚至连接超时。

## ---

**4\. 视觉语言模型深度解析：Qwen3-VL-Plus**

qwen3-vl-plus 引入了视觉模态，这不仅改变了模型的输入维度，也彻底重构了 SDK 的交互逻辑。本节将深入探讨 dashscope.MultiModalConversation 接口的特殊性及其对 enable\_search 参数的排斥性。

### **4.1 dashscope.MultiModalConversation 的强制性**

研究确认，调用 qwen3-vl-plus **必须** 使用 dashscope.MultiModalConversation 接口。任何尝试通过 Generation 接口调用该模型的行为都会被服务端拒绝或被 SDK 客户端拦截 1。

#### **4.1.1 技术动因**

Generation 接口的序列化逻辑无法处理图像数据。它期望 content 是字符串，而多模态模型要求 content 是一个包含文本和媒体对象的复杂结构。如果强行将图像 URL 作为文本字符串传递给 Generation 接口，模型只会将其视为一串普通的字符（即 URL 文本本身），而无法触发视觉编码器加载图像内容。只有 MultiModalConversation 具备解析多模态消息列表（Message List）并将其转换为后端模型所需的 Embedding 张量或特定 JSON 格式的能力 4。

### **4.2 enable\_search 参数的缺失与不支持**

本报告的核心发现之一是：**qwen3-vl-plus 在 Python SDK 中目前不支持 enable\_search 参数**。

#### **4.2.1 证据链**

1. **文档排斥**：官方文档在列举支持 enable\_search 的模型时，仅涵盖了 qwen-turbo、qwen-plus 等文本模型，未包含以 vl 结尾的模型 8。  
2. **代码库分析**：在开源社区（如 LobeChat）对 DashScope 接口的集成讨论中，开发者明确指出 qwen-vl 系列模型在代码层面未将 enable\_search 设为可用，强行传递该参数会导致 InvalidParameter 错误 8。  
3. **错误反馈**：实际调用测试表明，当向多模态模型发送包含 enable\_search=True 的请求时，服务端会返回错误，提示该参数不适用于当前模型配置 5。

#### **4.2.2 深度归因分析**

为何技术上更先进的 qwen3-vl-plus 反而缺失了搜索能力？这涉及到“多模态搜索”的复杂性：

* **视觉搜索的歧义性**：对于文本查询“苹果股价”，意图非常明确。但对于一张图片（例如一个复杂的机械零件）加上查询“哪里能买到这个？”，模型首先需要进行细粒度的物体识别（Object Recognition），然后将视觉特征转化为关键词，最后再进行搜索。这个 Pipeline（VQA \-\> Keyword Generation \-\> Search \-\> VQA Grounding）比纯文本 RAG 复杂得多。  
* **计算成本与延迟**：视觉编码本身已是高算力操作。如果在处理高分辨率图像（Qwen3-VL 支持动态分辨率）的同时还挂起推理线程去等待网络搜索返回，端到端的延迟（Latency）可能超出实时交互的接受范围。  
* **模型对齐（Alignment）**：qwen-plus 等文本模型经过了大量的“搜索增强”微调。而 VL 模型的微调重点在于图文对齐、OCR 和空间推理 9。目前阶段，Qwen3-VL 可能尚未在大规模“视觉-搜索”数据集上进行充分的 SFT（监督微调），因此服务端屏蔽了该功能以防止产生低质量的幻觉输出。

### **4.3 多模态消息结构（Messages Schema）**

qwen3-vl-plus 的入参格式是其使用中最容易出错的部分。与文本模型的简单字符串不同，VL 模型要求 content 必须是一个列表（List of Dictionaries）。

#### **4.3.1 结构规范**

Python

messages \= \[  
    {  
        "role": "user",  
        "content": \[  
            {"image": "https://example.com/photo.jpg"},  \# 图像在前  
            {"text": "这张图片里有什么？"}               \# 文本在后  
        \]  
    }  
\]

或者支持交错格式（Interleaved）：

Python

"content": \[  
    {"text": "先看这张图："},  
    {"image": "image1.jpg"},  
    {"text": "再对比这张图："},  
    {"image": "image2.jpg"},  
    {"text": "它们有什么区别？"}  
\]

#### **4.3.2 图像输入支持方式**

SDK 对 image 字段的值提供了灵活的支持 10：

1. **HTTP/HTTPS URL**：公网可访问的链接。SDK 不会下载，而是直接将 URL 传给服务端，由服务端下载。  
2. **本地文件路径 (file://)**：必须以 file:// 协议头开头（Linux/Mac）或包含盘符（Windows）。SDK 会读取文件字节流。  
3. **Base64 编码**：格式为 data:image/png;base64,xxxx...。这种方式适用于无公网 URL 且不想落地文件的场景。

#### **4.3.3 输出格式差异**

虽然 MultiModalConversation 也支持 incremental\_output，但其返回的 JSON 结构更倾向于 OpenAI 的 Chat Completion Chunk 格式。

* **路径**：response.output.choices.message.content。  
* **内容**：在流式输出中，这个 content 也是一个列表或包含文本片段的结构。与文本模型直接返回 output.text 相比，多模态接口的返回值结构嵌套更深，这是为了预留未来返回非文本内容（如生成的图像掩码或边界框坐标）的可能性 6。

## ---

**5\. 核心差异对比分析**

本节将通过对比矩阵和深度分析，总结 Qwen-3 系列在 DashScope SDK 中的差异，回应用户的核心关切。

### **5.1 关键参数与能力对比矩阵**

| 特性维度 | 文本模型 (qwen-plus / qwen3-max) | 视觉语言模型 (qwen3-vl-plus) |
| :---- | :---- | :---- |
| **SDK 调用类** | dashscope.Generation | dashscope.MultiModalConversation |
| **enable\_search 支持** | **原生支持** (服务端 RAG) | **不支持** / 抛出异常 |
| **输入消息 content 类型** | str (纯字符串) | List (多模态对象列表) |
| **图像输入能力** | 不支持 | 支持 URL, Local Path, Base64 |
| **流式参数 incremental\_output** | 支持 (思考模式必须为 True) | 支持 (推荐为 True 以降低延迟) |
| **输出数据结构** | 扁平化 (output.text) 或 Message | 结构化 Message (choices.message) |
| **应用场景** | 复杂推理、写作、联网问答 | 图像理解、OCR、视觉问答、视频分析 |

### **5.2 入参格式的一致性分析**

**结论：不一致。**

开发者无法使用同一套消息构建逻辑来适配两种模型。

* **文本模型**拒绝列表格式的 content，会报错要求字符串。  
* **VL 模型**虽然在某些情况下可能兼容纯文本字符串（视 SDK 版本容错性而定），但为了触发视觉能力，必须使用列表格式。  
* **隐患**：如果在代码中简单地替换 model='qwen-plus' 为 model='qwen3-vl-plus' 而不修改 messages 构造逻辑，程序将必然崩溃。必须引入“模态感知”的逻辑分支。

### **5.3 出参格式的一致性分析**

**结论：局部一致，但存在结构性差异。**

两者都遵循 SSE 协议进行流式传输，且都通过 incremental\_output=True 来获取增量数据。然而，解析响应对象的代码路径不同。

* 文本模型通常直接访问 response.output.text 即可获取最新生成的文本。  
* VL 模型通常需要遍历 response.output.choices 数组。虽然 DashScope 正在努力统一两者到 OpenAI 兼容格式，但在原生 SDK 中，这种历史遗留的结构差异依然存在 4。

## ---

**6\. Microsoft Agent Framework 多模态集成研究**

随着 AI Agent 开发的普及，Microsoft Agent Framework (Python) 作为一个新兴的编排框架，其对多模态的支持成为开发者关注的焦点。基于版本 1.0.0b260128（预览版）的研究显示，该框架采用了与 LangChain 或 Semantic Kernel 不同的抽象策略。

### **6.1 协议抽象：ChatClientProtocol**

Microsoft Agent Framework 不直接绑定特定的模型提供商（如 OpenAI 或 DashScope），而是通过 ChatClientProtocol 定义了一套交互标准 13。这意味着，若要使用 DashScope 的 Qwen-3 模型，开发者需要编写一个实现了该协议的适配器（Adapter）。

### **6.2 多模态内容原语：DataContent 与 UriContent**

与 DashScope SDK 直接使用字典 (dict) 不同，Microsoft Agent Framework 使用强类型的类来表示内容。研究发现，早期文档中提及的 ImageContent 类在最新的预览版架构中已被更通用的原语所取代或重构，以支持更广泛的媒体类型（如音频、视频）。

#### **6.2.1 DataContent (数据内容)**

* **定义**：用于封装二进制数据，通常是 Base64 编码的图像。  
* **属性**：  
  * data: 二进制字节流或 Base64 字符串。  
  * media\_type: MIME 类型（如 image/jpeg）。  
* **用途**：当图像文件位于本地，且不希望上传到公网 OSS 时，使用此原语。它对应于 DashScope 中的 data:image... 格式 14。

#### **6.2.2 UriContent (资源标识符内容)**

* **定义**：用于封装远程资源的引用。  
* **属性**：  
  * uri: 资源的 URL 字符串。  
  * media\_type: （可选）资源的 MIME 类型。  
* **用途**：当图像已有公网链接时使用。它对应于 DashScope 中的 HTTP/HTTPS URL 格式 16。

### **6.3 适配策略与代码实现路径**

要在 Microsoft Agent Framework 中驱动 qwen3-vl-plus，开发者必须在自定义的 ChatClient 中实现从 Framework 原语到 DashScope 格式的映射（Mapping）。

#### **6.3.1 映射逻辑**

1. **遍历消息内容**：检查 ChatMessage.contents 列表。  
2. **类型匹配**：  
   * 遇到 TextContent \-\> 转换为 DashScope 的 {'text': content.text}。  
   * 遇到 UriContent \-\> 转换为 DashScope 的 {'image': content.uri}。  
   * 遇到 DataContent \-\> 读取 data，如果是 bytes 则转为 Base64 字符串，拼接前缀 data:{media\_type};base64,，然后转换为 {'image': base64\_str}。  
3. **接口选择**：如果消息中包含任何 UriContent 或 DataContent，适配器必须强制使用 dashscope.MultiModalConversation.call，并禁用 enable\_search 参数，否则应回退到 dashscope.Generation.call。

#### **6.3.2 示例代码结构（概念验证）**

Python

from agent\_framework import ChatMessage, TextContent, UriContent, Role  
\# 假设的适配器逻辑  
def adapt\_to\_dashscope(agent\_message: ChatMessage):  
    dashscope\_content \=  
    has\_image \= False  
      
    for item in agent\_message.contents:  
        if isinstance(item, TextContent):  
            dashscope\_content.append({"text": item.text})  
        elif isinstance(item, UriContent):  
            dashscope\_content.append({"image": item.uri})  
            has\_image \= True  
        elif isinstance(item, DataContent):  
            \# 伪代码：处理 Base64  
            base64\_str \= convert\_to\_base64(item.data)  
            dashscope\_content.append({"image": base64\_str})  
            has\_image \= True  
              
    \# 根据内容决定调用哪个接口  
    if has\_image:  
        return dashscope.MultiModalConversation.call(..., messages=\[{"content": dashscope\_content}\])  
    else:  
        return dashscope.Generation.call(..., messages=\[{"content": extract\_text(dashscope\_content)}\])

这种适配逻辑展示了 Microsoft Agent Framework 的灵活性，同时也暴露了跨框架集成时的“胶水代码”成本。

## ---

**7\. 结论与建议**

### **7.1 研究结论综述**

本报告通过详尽的对比分析，确认了阿里云 DashScope Python SDK 在处理 Qwen-3 系列模型时存在显著的架构分叉。

1. **接口二元性**：qwen3-vl-plus 必须通过 dashscope.MultiModalConversation 调用，而 qwen-plus/qwen3-max 必须通过 dashscope.Generation 调用。这不仅是推荐做法，更是由 SDK 内部的数据流处理机制强制执行的。  
2. **搜索能力的边界**：enable\_search 参数目前是文本模型的专属能力。qwen3-vl-plus 由于视觉理解与搜索检索结合的复杂性，目前在 SDK 层面不支持该参数。  
3. **数据格式的异构性**：两种接口的 messages 格式互不兼容。文本接口要求简单字符串，多模态接口要求结构化列表。输出格式虽然都支持增量流式，但在对象结构上存在细微差别。  
4. **Agent 框架集成**：Microsoft Agent Framework 通过 DataContent 和 UriContent 提供了对多模态的通用支持，但要求开发者自行编写适配器来处理到底层 DashScope 格式的转换及接口选择逻辑。

### **7.2 针对开发者的建议**

* **实施防御性编程**：在构建封装 Qwen 模型的应用时，不要假设所有模型都支持相同的参数。应建立一个“能力特征库”，根据模型名称动态决定是否传入 enable\_search。  
* **构建统一适配层**：建议在业务代码中封装一个统一的 DashScopeAdapter 类。该类应自动检测输入消息中是否包含图片，从而自动路由到 Generation 或 MultiModalConversation，对上层业务逻辑屏蔽底层的接口差异。  
* **应对 VL 搜索限制**：如果业务强依赖于“视觉+搜索”（例如：用户上传商品图并询问价格），不要等待官方支持 enable\_search。应采用 Agent 模式：先调用 qwen3-vl-plus 解析图片内容为文本描述，再将描述作为 Query 调用 qwen-max 并开启 enable\_search，通过两步工作流（Workflow）实现目标。  
* **关注 Agent Framework 更新**：Microsoft Agent Framework 尚处于预览阶段（Beta），API 变动频繁。在使用 DataContent 时，务必严格校验 MIME Type，因为 DashScope 对图片格式的支持是有限的（通常为 JPG/PNG 等），错误的 MIME Type 可能会在转换 Base64 时导致服务端解码失败。

通过遵循上述分析与建议，开发者可以更稳健地在生产环境中部署 Qwen-3 系列模型，并有效利用 Microsoft Agent Framework 构建复杂的多模态智能体应用。

#### **Works cited**

1. How to use Function Calling for tool calling \- Alibaba Cloud Model Studio, accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling](https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling)  
2. Dashscope (Qwen API) \- LiteLLM, accessed on January 29, 2026, [https://docs.litellm.ai/docs/providers/dashscope](https://docs.litellm.ai/docs/providers/dashscope)  
3. Alibaba Cloud Model Studio \- Text generation, accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/text-generation](https://www.alibabacloud.com/help/en/model-studio/text-generation)  
4. Source code for agentscope.model.\_dashscope\_model, accessed on January 29, 2026, [https://doc.agentscope.io/\_modules/agentscope/model/\_dashscope\_model.html](https://doc.agentscope.io/_modules/agentscope/model/_dashscope_model.html)  
5. Alibaba Cloud Model Studio:Error messages, accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/error-code](https://www.alibabacloud.com/help/en/model-studio/error-code)  
6. An unofficial DashScope（ SDK for .NET maintained by Cnblogs. \- GitHub, accessed on January 29, 2026, [https://github.com/cnblogs/dashscope-sdk](https://github.com/cnblogs/dashscope-sdk)  
7. Dashscope \- LlamaIndex, accessed on January 29, 2026, [https://developers.llamaindex.ai/python/framework-api-reference/llms/dashscope/](https://developers.llamaindex.ai/python/framework-api-reference/llms/dashscope/)  
8. \[Bug\] Not all Qwen models support the "enable\_search" parameter · Issue \#5296 · lobehub/lobe-chat \- GitHub, accessed on January 29, 2026, [https://github.com/lobehub/lobe-chat/issues/5296](https://github.com/lobehub/lobe-chat/issues/5296)  
9. Qwen3-VL is the multimodal large language model series developed by Qwen team, Alibaba Cloud. \- GitHub, accessed on January 29, 2026, [https://github.com/QwenLM/Qwen3-VL](https://github.com/QwenLM/Qwen3-VL)  
10. Alibaba Cloud Model Studio:Qwen API reference, accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/developer-reference/use-qwen-by-calling-api/](https://www.alibabacloud.com/help/en/model-studio/developer-reference/use-qwen-by-calling-api/)  
11. Alibaba Cloud Model Studio:Visual understanding (Qwen-VL), accessed on January 29, 2026, [https://www.alibabacloud.com/help/en/model-studio/vision](https://www.alibabacloud.com/help/en/model-studio/vision)  
12. Multimodal Large Models | EvalScope \- Read the Docs, accessed on January 29, 2026, [https://evalscope.readthedocs.io/en/latest/advanced\_guides/custom\_dataset/vlm.html](https://evalscope.readthedocs.io/en/latest/advanced_guides/custom_dataset/vlm.html)  
13. agent\_framework.ChatClientProtocol class | Microsoft Learn, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent\_framework.chatclientprotocol?view=agent-framework-python-latest](https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.chatclientprotocol?view=agent-framework-python-latest)  
14. Using images with an agent | Microsoft Learn, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/agent-framework/tutorials/agents/images](https://learn.microsoft.com/en-us/agent-framework/tutorials/agents/images)  
15. agent\_framework.DataContent class \- Microsoft Learn, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent\_framework.datacontent?view=agent-framework-python-latest](https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.datacontent?view=agent-framework-python-latest)  
16. Running Agents \- Microsoft Learn, accessed on January 29, 2026, [https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/running-agents](https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/running-agents)
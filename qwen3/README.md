# Qwen3 Chat Client for Microsoft Agent Framework

本目录包含为Microsoft Agent Framework (MAF) 开发的阿里云通义千问Qwen3系列模型的自定义Chat Client实现。

## 项目状态

✅ **当前阶段**: 核心功能实现完成 (Phase 3 Completed)

- [x] 需求分析
- [x] 架构设计
- [x] 基础架构搭建
- [x] 推理模型 (qwen-plus/max) 实现
- [x] 视觉模型 (qwen-vl-plus) 实现
- [x] 深度研究模型 (qwen-deep-research) 实现
- [x] 自动化研究编排器 (AutoResearch)
- [ ] 完整测试覆盖
- [ ] 文档完善

## 核心目标

让MAF能够原生调用Qwen3模型，并保留所有高级特性：

### 支持的模型

| 模型 | 用途 | 特性 |
|-----|------|------|
| **qwen-plus** | 主推理引擎 | 思考模式、联网搜索、长上下文 |
| **qwen-max** | 高级推理 | 更强的思考能力 |
| **qwen3-vl-plus** | 视觉分析 | K线图分析、OCR、图像理解 |
| **qwen-vl-max** | 高级视觉 | 更精确的视觉推理 |
| **qwen-deep-research** | 深度研究 | 自主进行长程深度搜索与研究 |

### 核心特性

#### 推理模型特有参数

- ✅ `enable_thinking` - 开启思维链推理
- ✅ `enable_search` - 原生联网搜索能力
- ✅ `seed` - 可复现的随机种子
- ✅ `repetition_penalty` - 重复惩罚

#### 视觉模型特有参数

- ✅ `min_pixels` / `max_pixels` - 图像分辨率控制
- ✅ 支持 URL 或 Base64（本地文件需调用侧先转 Base64）

## 架构设计

### 为什么不能用OpenAI兼容模式？

当前项目使用OpenAI兼容模式调用Qwen（见 `test_qwen3_thinking.py`），但这种方式有**严重局限**：

```python
# ❌ OpenAI兼容模式的局限
completion = client.chat.completions.create(
    model="qwen3-vl-plus",
    extra_body={
        'enable_thinking': True,        # ⚠️ 非标准参数
        'enable_search': True           # ⚠️ 不保证生效
    }
)
```

**问题**：
1. 参数传递不可靠（依赖 `extra_body` 黑盒）
2. 无类型检查和IDE提示
3. 错误处理不明确
4. 无法利用MAF的中间件能力

### 自定义Chat Client的优势

**我们的解决方案：使用DashScope原生SDK**

本项目使用 `dashscope.Generation.call()` 而非OpenAI兼容模式：

```python
# ✅ 原生MAF集成 + DashScope原生API
from qwen3 import QwenChatClient, QwenChatOptions
from agent_framework import ChatAgent

client = QwenChatClient(
    model_id="qwen-plus"
)

agent = ChatAgent(
    chat_client=client,
    name="QwenAssistant"
)

# 类型安全的参数
options = QwenChatOptions(
    enable_search=True,  # ✅ 联网搜索
    temperature=0.7
)

result = await agent.run(
    "分析A股市场趋势",
    additional_chat_options=options
)

# 注意：如果需要启用思考模式（enable_thinking=True），
# 必须使用 agent.run_stream() 而非 agent.run()
```

**优势**：
- ✅ 完全类型安全（IDE智能提示）
- ✅ 自动获得MAF中间件支持（日志、追踪、限流）
- ✅ 统一的错误处理
- ✅ Token使用统计
- ✅ 与其他MAF Agent无缝集成

## 集成状态与分析 (Status Note)

**⚠️ 当前状态：未启用 (Idle)**

经过详细的代码依赖分析与技术评估，本模块 (`@qwen3`) 目前并未被主业务逻辑（`stock_analyzer`）引用。系统目前继续沿用 OpenAI 兼容模式（通过 `stock_analyzer/llm_client.py` 调用 DashScope 的 `/compatible-mode/v1` 端点）。

**未启用原因分析：**

1.  **MAF 框架的耦合性**：
    Microsoft Agent Framework (`agent-framework`) 核心高度依赖 OpenAI 的接口规范。虽然 `qwen3` 试图通过继承 `BaseChatClient` 来适配 MAF，但在实际集成中，涉及流式响应块结构、Tool Call 格式转换等深层行为差异，导致维护自定义 Client 的成本目前高于直接使用 OpenAI 兼容层。

2.  **问题的自动消解**：
    最初开发本模块的动力之一是解决旧版 `qwen-plus` 在 OpenAI 兼容层下无法同时开启 Thinking 和 JSON Mode 的问题。然而，随着 `qwen3.5-plus` 的发布以及阿里云网关的升级，这一兼容性问题已在服务端得到修复（详见 `stock_analyzer/docs/tech_note_qwen3.5_plus_compatibility.md`）。因此，迁移到原生 SDK 的紧迫性大幅降低。

3.  **异步桥接的复杂性**：
    DashScope SDK 是同步设计，本模块通过线程池和队列实现了异步桥接。相比之下，`openai` 库提供原生异步支持，在高并发场景（如 Deep Research）下表现更为成熟稳定。

**结论**：
本模块作为一个功能完备的 DashScope 原生 SDK 封装层被保留在代码库中，作为“未来架构”或“备用方案”。如果未来遇到 DashScope 原生 SDK 独有的功能需求（如特殊的视觉参数微调），可随时启用。

## 文件结构

```
qwen3/
├── README.md                    # 本文件
├── config.py                    # 全局配置
├── qwen_options.py              # TypedDict配置类
├── qwen_client.py               # 推理模型Client
├── qwen_vl_client.py            # 视觉模型Client
├── qwen_deep_research_client.py # 深度研究模型Client (新增)
├── auto_research.py             # 自动化研究编排器 (新增)
├── utils.py                     # 工具函数
├── exceptions.py                # 自定义异常
├── __init__.py                  # 包导出
│
├── tests/                       # 测试代码
│   ├── test_qwen_client.py
│   ├── test_qwen_vl_client.py
│   ├── test_deep_research_integration.py
│   └── test_integration.py
│
├── examples/                    # 示例代码
│   ├── basic_chat.py
│   ├── thinking_mode.py
│   ├── search_enhanced.py
│   └── vision_analysis.py
│
└── ../docs/qwen3/               # 设计与说明文档
    ├── 需求评估与设计文档.md
    ├── API端点技术说明.md
    ├── 开发任务清单.md
    ├── 快速开始指南.md
    └── ...
```

## 开发计划

### Phase 1: 基础架构 (已完成)

- [x] 创建所有文件框架
- [x] 实现 `qwen_options.py`
- [x] 实现 `exceptions.py`
- [x] 实现 `utils.py`

### Phase 2: 推理模型 (已完成)

- [x] 实现 `QwenChatClient`
- [x] 消息格式转换
- [x] 异步流式响应
- [x] 思考模式支持
- [x] 联网搜索支持

### Phase 3: 视觉模型 (已完成)

- [x] 实现 `QwenVLChatClient`
- [x] 多模态消息转换
- [x] 图像处理（URL/Base64）

### Phase 4: 测试 (进行中)

- [ ] 单元测试（覆盖率 > 80%）
- [ ] 集成测试
- [ ] 性能测试

### Phase 5: 文档与示例 (进行中)

- [ ] API文档
- [ ] 使用示例
- [ ] 故障排查指南

## 技术要点

### API端点选择：原生 vs 兼容模式

**⚠️ 重要架构决策**

DashScope提供两套API端点：

| 类型 | 端点路径 | 使用方式 | 本项目选择 |
|-----|---------|---------|-----------|
| **原生API** | `/api/v1/services/aigc/text-generation/generation` | `dashscope.Generation.call()` | ✅ 使用 |
| **兼容模式** | `/compatible-mode/v1/chat/completions` | OpenAI SDK | ❌ 不使用 |

**我们的实现**：
```python
import dashscope

# ✅ 使用原生SDK，默认中国站端点
response = dashscope.Generation.call(
    model="qwen-plus",
    enable_thinking=True,      # ✅ 直接传递，无需extra_body
    enable_search=True
)

# ❌ 不使用OpenAI兼容模式
# client = OpenAI(base_url="...compatible-mode/v1")  # 我们不这样做
```

### 异步桥接策略

DashScope SDK是同步的，需要桥接到MAF的异步架构：

```python
# 使用线程池 + asyncio队列
async def _inner_get_streaming_response(self, ...):
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def _producer():
        for resp in dashscope.Generation.call(stream=True, ...):
            loop.call_soon_threadsafe(queue.put_nowait, resp)

    threading.Thread(target=_producer, daemon=True).start()

    while True:
        item = await queue.get()
        yield ChatResponseUpdate(...)
```

### 思考模式处理

```python
# DashScope返回两个字段
if hasattr(delta, "reasoning_content"):
    # 思考过程
    thinking_content = delta.reasoning_content

if delta.content:
    # 最终答案
    answer_content = delta.content
```

### 多模态转换

```python
# MAF格式
ChatMessage(
    role=Role.USER,
    contents=[
        TextContent(text="分析这张K线图"),
        ImageContent(url="https://...")
    ]
)

# ↓ 转换为 DashScope格式

{
    "role": "user",
    "content": [
        {"text": "分析这张K线图"},
        {"image": "https://..."}
    ]
}
```

## 环境配置

### 1. 安装依赖

在 `pyproject.toml` 中添加：

```toml
dependencies = [
    "dashscope>=1.20.0",
]
```

运行：
```bash
uv sync
```

### 2. 配置环境变量

在 `.env` 中添加：

```bash
# 仅允许 API Key 放在 .env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxx
```

### 3. 验证配置

```python
import os
from dotenv import load_dotenv

load_dotenv()
assert os.getenv("DASHSCOPE_API_KEY"), "API Key未配置"
```

### 4. 配置参数（config.py）

除 API Key 外的**所有可变参数**都放在 `config.py` 中集中管理：

```python
# config.py
DEFAULT_MODEL_ID = "qwen-plus"          # 默认模型
DEFAULT_TEMPERATURE = 0.7               # 温度
DEFAULT_MAX_TOKENS = 2000               # 最大输出 Token
DEFAULT_TOP_P = 0.9                     # Top-p
DEFAULT_ENABLE_SEARCH = True            # 默认是否启用搜索
REQUEST_TIMEOUT_S = 60                  # 请求超时（秒）
MAX_RETRIES = 3                         # 最大重试次数
```

## 使用示例

### 基础对话

```python
from qwen3 import QwenChatClient
from agent_framework import ChatAgent

client = QwenChatClient(model_id="qwen-plus")
agent = ChatAgent(chat_client=client, name="Assistant")

result = await agent.run("你好，介绍一下你自己")
print(result.text)
```

### 启用思考模式

⚠️ **重要**：思考模式必须使用流式响应，否则会返回400错误。

```python
from qwen3 import QwenChatClient, QwenChatOptions
from agent_framework import ChatAgent

client = QwenChatClient(model_id="qwen-max")
agent = ChatAgent(chat_client=client, name="DeepThinker")

options = QwenChatOptions(
    enable_thinking=True,
    temperature=0.6
)

# ✅ 正确：使用流式响应
print("Assistant: ", end="", flush=True)
async for update in agent.run_stream(
    "证明根号2是无理数",
    additional_chat_options=options
):
    if update.text:
        print(update.text, end="", flush=True)
print()  # 换行
```

**为什么必须流式？**
- 思考过程长度不可控，可能生成数千Token
- 非流式调用会因超时导致连接中断
- DashScope API强制要求 `enable_thinking=True` 时 `stream=True`

### 联网搜索

```python
options = QwenChatOptions(
    enable_search=True,  # 开启搜索
    temperature=0.7
)

result = await agent.run(
    "2026年1月的A股市场走势如何？",
    additional_chat_options=options
)

# 获取搜索引用
search_info = result.messages[0].additional_properties.get("search_info")
```

### K线图分析

```python
from qwen3 import QwenVLChatClient
from agent_framework import ChatMessage, Role, TextContent, ImageContent

client = QwenVLChatClient(model_id="qwen3-vl-plus")
agent = ChatAgent(chat_client=client, name="ChartAnalyzer")

# ✅ 使用 MAF 原生格式
message = ChatMessage(
    role=Role.USER,
    contents=[
        ImageContent(url="https://example.com/600482.SH_kline.png"),
        TextContent(text="分析这张K线图的威科夫形态")
    ]
)

result = await agent.run([message])
```

**格式说明**：
- ✅ 使用 `ImageContent` 和 `TextContent`（MAF原生类型）
- ❌ 不要使用 `{"type": "image_url", ...}`（那是OpenAI SDK格式）
- 内部转换由 `QwenVLChatClient` 自动处理
- 本地图片请在调用侧先转为 Base64（或 data URI）再传入

## 资源监控

### Token统计

所有Client自动记录Token使用：

```python
result = await agent.run(query, additional_chat_options=options)

if result.usage:
    print(f"输入Token: {result.usage.input_tokens}")
    print(f"输出Token: {result.usage.output_tokens}")
    print(f"总计: {result.usage.total_tokens}")
```

## 故障排查

### 问题1: "enable_thinking must be set to false for non-streaming calls"

**原因**: 思考模式必须使用流式响应

**解决**:
```python
# ❌ 错误
result = await agent.run(query, enable_thinking=True)

# ✅ 正确
async for update in agent.run_stream(query, enable_thinking=True):
    print(update.text, end="")
```

### 问题2: 流式输出重复文本

**原因**: `incremental_output` 未设置

**解决**: Client已自动设置，如果仍有问题请检查代码

### 问题3: InvalidApiKey错误

**原因**: API Key 无效或未正确配置

**解决**:
```python
# 检查 API Key 是否正确
client = QwenChatClient(
    api_key="sk-..."
)
```

## 贡献指南

本项目欢迎贡献！请参考：

1. Fork项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

**代码规范**：
- 所有函数必须有类型标注
- 公开API必须有docstring
- 测试覆盖率 > 80%

## 许可证

本项目与主项目保持一致的许可证。

## 参考资料

- [需求评估与设计文档](../docs/qwen3/需求评估与设计文档.md)
- [Microsoft Agent Framework文档](https://learn.microsoft.com/en-us/agent-framework)
- [DashScope API参考](https://www.alibabacloud.com/help/en/model-studio)
- [Qwen3技术博客](https://qwenlm.github.io)

## 联系方式

有问题或建议？请提交Issue或联系项目维护者。

---

**最后更新**: 2026-01-29
**文档版本**: v1.1
**项目阶段**: 核心功能实现完成
# 股票推荐系统 Step 2 详细设计说明书

## 文档信息
| 版本 | 日期 | 作者 | 说明 |
| :--- | :--- | :--- | :--- |
| v1.0 | 2026-02-04 | Codex | 基于概要设计 v1.0 编写 |

---

## 1. 模块概述

**重要说明**：Step1 和 Step2 属于**同一个模块** `analysis_llm`，仅按开发阶段划分。所有代码都位于 `analysis_llm/` 根目录下，通过不同的类和函数来区分功能，而非创建子目录或使用 "step2" 命名。

Step 2 阶段负责接收 Step 1 生成的结构化数据（新闻、板块、K线），通过多智能体协作（Magentic Pattern）生成最终的"推荐持有评分"与"概要原因"。

### 1.1 核心目标
- **生成**: 基于多维数据生成量化评分 (0-10) 和深度理由 (100-1000字)。
- **质检**: 通过 Reviewer Agent 进行逻辑自洽性和事实完整性审查。
- **闭环**: 实现自动化的"生成 -> 审阅 -> 重试"流程。

### 1.2 模块结构与命名规范

**代码组织**：
```
analysis_llm/
├── models.py          # 包含 Step1Output 和 HoldRecommendation（新增）
├── workflow.py        # 包含 Step1 函数与 ScoringWorkflow 类（新增）
├── prompts.py         # 包含 Step1 Prompts 与 Step2 Prompts（新增）
├── config.py          # 共享配置，Step2 配置为增量添加
├── agents.py          # Step1 的 Agent 定义
├── tools.py           # Step1 的工具函数
└── utils.py           # 共享工具函数
```

**命名规范**：
- 使用**功能性命名**而非阶段性命名
- Step2 新增类：`ScoringWorkflow`（位于 `workflow.py`）
- Step2 输出模型：`HoldRecommendation`（而非 ~~`Step2Output`~~）
- Step2 配置变量：`MODEL_SCORE_AGENT`（区别于 Step1 的 `MODEL_NEWS_AGENT`）

**向后兼容**：
- ✅ 所有 Step2 代码为**纯增量添加**
- ✅ 不修改 Step1 已有代码
- ✅ Step1 和 Step2 可以**独立运行**

### 1.3 独立运行方式

**Step1（数据收集与分析）**：
```python
from analysis_llm.workflow import execute_step1
from analysis_llm.models import Step1Output

# 运行 Step1（内部使用 ConcurrentBuilder 并发执行）
step1_output = await execute_step1("603080.SH")
```

**Step2（评分与推荐）**：
```python
from analysis_llm.workflow import ScoringWorkflow
from analysis_llm.models import HoldRecommendation

# 运行 Step2（输入是 Step1 的输出）
scoring_wf = ScoringWorkflow()
recommendation = await scoring_wf.run(step1_output)
```

**完整流程**：
```python
# Step1 → Step2 顺序执行
from analysis_llm.workflow import execute_step1, ScoringWorkflow

# Step1: 函数式调用
step1_output = await execute_step1("603080.SH")

# Step2: OOP 调用
scoring_wf = ScoringWorkflow()
recommendation = await scoring_wf.run(step1_output)
```

### 1.4 技术依赖与参考文档

**核心框架**：
- **MAF (Magentic Agent Framework)**: `agent_framework>=1.0.0b260130`
- **DashScope API**: 阿里云大模型服务（用于 Manager 和 ScoreAgent）
- **DeepSeek API**: DeepSeek 官方 API（用于 ReviewAgent）

**关键技术文档**：

本详细设计依赖以下技术文档，开发时**必须参考**：

1. **MAF 与 DashScope/DeepSeek 集成技术说明**
   - 文档路径：`docs/analysis_llm/tech_note_maf_dashscope_integration.md`
   - 包含内容：
     - MAF `options` 参数的正确传递方式
     - JSON Mode (`response_format`) 的配置方法
     - 原生搜索 (`enable_search`) 的配置方法
     - DashScope 和 DeepSeek API 的兼容性说明
     - 超时配置和错误处理
   - **重要性**：错误的 `options` 传参会导致 JSON Mode 或搜索功能失效

2. **Step 1 详细设计**
   - 文档路径：`docs/analysis_llm/step1_detailed_design.md`
   - 包含内容：Step1 的输出格式规范（Step2 的输入）

3. **概要设计**
   - 文档路径：`docs/analysis_llm/step2概要设计说明书.md`
   - 包含内容：Step2 的整体架构和设计原则

**开发提醒**：
- 在实现 Section 5.2（创建 Agents）时，务必参考 `tech_note_maf_dashscope_integration.md`
- 不要凭经验或猜测配置 `options` 参数，否则可能导致功能失效

---

## 2. 配置管理 (`analysis_llm/config.py`)

**文件位置**：`analysis_llm/config.py`（复用现有文件）

**修改方式**：在现有配置基础上，**增量添加** Step 2 专用配置项，不影响 Step1 已有配置。

### 配置分类

**复用 Step1 已有配置**（无需重复声明）：
```python
# 这些配置在 Step1 中已经定义，Step2 直接复用
# DASHSCOPE_API_KEY        - Step1 和 Step2 都使用 DashScope
# DASHSCOPE_BASE_URL       - DashScope API 端点
# 其他 Step1 的配置...
```

**Step2 新增配置**：
```python
# --- Step 2 Configuration ---

# Model Selection (Independent of Step 1)
# Manager: 负责调度，需强推理能力
MODEL_MANAGER = "qwen-plus"
# ScoreAgent: 负责生成，需搜索 + 推理
MODEL_SCORE_AGENT = "qwen-max"
# ReviewAgent: 负责质检，需强逻辑 (使用 DeepSeek API)
MODEL_REVIEW_AGENT = "deepseek-chat"

# Workflow Constraints
MAX_ITERATIONS = 10  # Magentic 循环上限 (约 5 轮 Review)

# Prompt Constraints
SUMMARY_REASON_MIN_CHARS = 100
SUMMARY_REASON_MAX_CHARS = 1000

# DeepSeek API Configuration (新增)
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# Timeout Configuration (新增，或复用 Step1 的同名配置)
API_TIMEOUT = 60.0  # 秒，用于所有 API 调用
```

**配置说明**：
- `DASHSCOPE_BASE_URL`：**复用 Step1 配置**，不重复定义
- `DEEPSEEK_BASE_URL`：**新增配置**，Step2 专用（ReviewAgent 使用 DeepSeek）
- `API_TIMEOUT`：新增配置，统一超时配置（如果 Step1 已有同名配置则复用）
- 需要在 `.env` 文件中新增 `DEEPSEEK_API_KEY`（`DASHSCOPE_API_KEY` 已在 Step1 中配置）

**重要参考文档**：
- 关于 MAF 与 DashScope/DeepSeek 集成的详细说明，请参考：`docs/analysis_llm/tech_note_maf_dashscope_integration.md`
- 该文档包含 `options` 参数的正确传递方式、JSON Mode 和原生搜索的配置方法

---

## 3. 数据模型 (`analysis_llm/models.py`)

**文件位置**：`analysis_llm/models.py`（复用现有文件）

**修改方式**：在现有模型基础上，**增量添加** Step 2 的数据模型，不影响 Step1 已有模型（如 `Step1Output`、`NewsAnalysis` 等）。

### 3.1 HoldRecommendation
最终输出模型，用于承载持有推荐评分结果。

**命名说明**：使用更具业务含义的类名 `HoldRecommendation`（而非泛泛的 `Step2Output`）。

**自动填充字段说明**：
- `data_type`: 通过 Literal 默认值自动设置为 `"hold_recommendation"`，确保类型安全且无需手动传入
- `timestamp`: 通过 `default_factory` 在对象创建时自动生成 UTC 时间戳，保证时间的准确性和一致性

**必要导入**：
```python
from datetime import datetime, timezone
from typing import Literal
from pydantic import Field
```

**模型定义**：
```python
class HoldRecommendation(StrictBaseModel):
    data_type: Literal["hold_recommendation"] = "hold_recommendation"
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="生成时间 (UTC ISO 8601)"
    )
    stock_code: str = Field(..., description="股票代码")
    stock_name: str = Field(..., description="股票名称（允许空字符串，不影响后续流程）")
    hold_score: float = Field(..., ge=0, le=10, description="推荐持有评分 (0-10)")
    summary_reason: str = Field(
        ...,
        min_length=config.SUMMARY_REASON_MIN_CHARS,
        max_length=config.SUMMARY_REASON_MAX_CHARS,
        description="推荐原因摘要"
    )
```

**设计优势**：
1. 减少调用时的重复代码，提升开发效率
2. 防止 `data_type` 被意外填错
3. 确保 `timestamp` 总是在对象创建的精确时刻生成
4. 符合 Pydantic 最佳实践和单一职责原则

### 3.2 ReviewResult (Reviewer 输出)
用于 ReviewerAgent 的结构化输出。

```python
class ReviewResult(StrictBaseModel):
    stock_code: str
    passed: bool = Field(..., description="是否通过质检")
    reason: str = Field(..., description="拒绝理由或通过说明")
```

---

## 4. Prompt 模板 (`analysis_llm/prompts.py`)

**文件位置**：`analysis_llm/prompts.py`（复用现有文件）

**修改方式**：在现有 Prompt 基础上，**增量添加** Step 2 的 Prompt 模板，不影响 Step1 已有 Prompts。

### Prompt 模板约定

**占位符机制**：
- Prompt 模板中使用 `{stock_code}` 占位符，在运行时动态替换为实际的股票代码
- JSON 示例中的大括号使用**双大括号**转义（`{{` 和 `}}`），避免与占位符语法冲突
- 替换逻辑在创建 Agent 时执行（参见 Section 5.2）

**示例**：
```python
# Prompt 模板（双大括号转义 JSON）
SCORE_AGENT_SYSTEM = """...
{{
    "stock_code": "{stock_code}",  # 单大括号是占位符
    "hold_score": 7.5,
    ...
}}
"""
```

---

### 4.1 ScoreAgent System Prompt
```python
SCORE_AGENT_SYSTEM = """...
**输出要求**:
- 必须输出合法的 JSON 对象。
- `summary_reason` 必须详实，逻辑自洽，字数严格控制在 **100-1000 字**。
- JSON 格式：
{{
    "stock_code": "{stock_code}",
    "hold_score": 7.5,
    "summary_reason": "..."
}}
"""
```

### 4.2 ReviewAgent System Prompt
```python
REVIEW_AGENT_SYSTEM = """...
**输出格式示例**：

通过时：
{{
    "stock_code": "{stock_code}",
    "passed": true,
    "reason": ""
}}

不通过时：
{{
    "stock_code": "{stock_code}",
    "passed": false,
    "reason": "分数与理由不一致：理由描述利空因素，但给出了 8 分的高分，建议降低评分至 5 分以下"
}}
"""
```

**设计说明：为什么 ReviewAgent 不需要搜索功能**

| 方面 | 说明 |
|------|------|
| **API 限制** | DeepSeek API 不支持内置搜索功能（`enable_search` 参数无效） |
| **职责定位** | ReviewAgent 负责**逻辑审核**，而非事实核查或信息补充 |
| **审核依据** | 基于 Step1 输入数据（已包含充分信息）和 ScoreAgent 输出 |
| **检查内容** | 逻辑自洽性、是否有明显矛盾、完整性 |

**关键区别**：
- **ScoreAgent**：需要搜索补充最新信息（如近期新闻、实时数据）
- **ReviewAgent**：检查逻辑和一致性，接受新增补充

**如何处理 ScoreAgent 的新增事实**：

| 场景 | ReviewAgent 判断 | 说明 |
|------|-----------------|------|
| **新增补充** | ✅ 接受 | ScoreAgent 搜索到的最新信息（Step1 中没有） |
| **明显矛盾** | ❌ 拒绝 | 理由与 Step1 数据方向相反（如把负面说成正面） |
| **逻辑错误** | ❌ 拒绝 | 不合常识或逻辑不自洽 |

**示例**：
- ✅ **接受新增**: Step1 显示"上月营收 100 亿"，ScoreAgent 说"根据最新财报，本月营收增至 120 亿" → 新增补充，接受
- ❌ **拒绝矛盾**: Step1 显示"营收下降 20%"，ScoreAgent 却说"业绩大幅增长" → 方向矛盾，拒绝
- ❌ **拒绝幻觉**: ScoreAgent 说"公司昨日登陆火星" → 明显不合常识，拒绝

**审核重点**：
- 不是检查"数据是否在 Step1 中"
- 而是检查"理由的逻辑是否自洽"和"是否有明显矛盾"

**信任模型**：
- 信任 ScoreAgent 的搜索能力（DashScope 原生搜索）
- ReviewAgent 关注逻辑审核，而非验证每个事实细节

---

### 4.3 Manager Instructions（质量闭环控制）

Manager 是 Magentic 编排的核心，负责任务分配和流程控制。为确保 ReviewAgent 必经环节，需要给 Manager 注入明确的流程控制指令。

```python
MANAGER_INSTRUCTIONS = """你是一个严格的工作流管理器，负责协调股票评分与审阅流程。

**你的职责**：
1. **任务分配**：将任务分配给合适的 Agent（ScoreAgent 或 ReviewAgent）
2. **质量控制**：确保所有评分输出都经过 ReviewAgent 的严格审核
3. **闭环管理**：若审核不通过（passed=false），必须要求 ScoreAgent 根据反馈修改

**关键原则（必须严格遵守）**：
- ReviewAgent 是必经环节，不可跳过
- ReviewAgent 拥有一票否决权
- 只有审核通过（passed=true）才能结束流程
- 审核失败时必须将 ReviewAgent 的 reason 字段完整传递给 ScoreAgent

**禁止行为**：
- 不得在未经 ReviewAgent 批准的情况下直接输出结果
- 不得忽略 ReviewAgent 的否决意见
- 不得在达到最大迭代次数前放弃质量控制

你的目标是通过严格的质量闭环，确保最终输出的评分报告既准确又可靠。
"""
```

**设计说明**：
- **双重保障**：Manager Instructions + Task 约束，确保流程可控
- **明确职责**：让 Manager 理解自己是质量守门员，而非简单的任务分发器
- **强调闭环**：通过"必须"、"不得"等强制性语言，确保 Reviewer 必经环节

---

### 4.4 Prompt 占位符使用说明

#### 占位符列表

| 占位符 | 替换时机 | 替换值来源 | 使用位置 |
|--------|---------|----------|---------|
| `{stock_code}` | 创建 Agent 时 | `step1_output.news.stock_code` | SCORE_AGENT_SYSTEM, REVIEW_AGENT_SYSTEM |

#### 转义规则

**JSON 大括号必须转义**：
- ✅ **正确**：`{{"stock_code": "{stock_code}"}}`（双大括号转义 JSON）
- ❌ **错误**：`{"stock_code": "{stock_code}"}`（会被 `.format()` 误识别为占位符）

**转义前后对比**：

```python
# 模板（使用双大括号转义 JSON）
SCORE_AGENT_SYSTEM = """...
{{
    "stock_code": "{stock_code}",
    "hold_score": 7.5
}}
"""

# 调用 .format(stock_code="603080.SH") 后
"""...
{
    "stock_code": "603080.SH",
    "hold_score": 7.5
}
"""
```

#### 为什么使用动态替换

| 方面 | 优势 |
|------|------|
| **精确性** | LLM 明确知道正在评估的股票代码，减少混淆 |
| **一致性** | 确保输出的 stock_code 与输入严格一致 |
| **可靠性** | 避免 LLM 输出占位符字面量（如 `{stock_code}`） |
| **可读性** | Agent 收到的 Prompt 更具体、更清晰 |

#### 替换逻辑位置

占位符替换在**创建 ChatAgent 时**执行，参见 Section 5.2 中的实现代码：

```python
# 获取股票代码
stock_code = step1_output.news.stock_code

# 创建 Agent 时动态替换占位符
score_agent = ChatAgent(
    name="ScoreAgent",
    chat_client=self.score_client,
    instructions=SCORE_AGENT_SYSTEM.format(stock_code=stock_code),  # 动态替换
    options={...}
)
```

**重要提醒**：
- 如果忘记调用 `.format()`，LLM 会收到字面量 `{stock_code}`
- 如果 JSON 大括号未转义，`.format()` 会报错或产生意外结果

---

## 5. 工作流实现 (`analysis_llm/workflow.py`)

**文件位置**：`analysis_llm/workflow.py`（复用现有文件）

**修改方式**：在现有文件末尾**增量添加** `ScoringWorkflow` 类及其辅助方法。保留 Step 1 的 `execute_step1` 函数。

### 5.1 设计模式说明：Wrapper 类

`ScoringWorkflow` 是一个 **Wrapper 类**，封装了 MAF `MagenticBuilder` 的构建和执行过程。这种设计有以下优势：

1. **状态管理**：将 AsyncOpenAI 客户端、MAF 客户端等作为实例属性，避免重复创建。
2. **逻辑封装**：将复杂的 Agent 创建、Workflow 构建、结果提取封装在类方法中。
3. **可测试性**：支持在 `__init__` 中注入 Mock 对象进行单元测试。

**与 Step1 的对比**：

| 特性 | Step1 (`execute_step1`) | Step2 (`ScoringWorkflow`) |
| :--- | :--- | :--- |
| **范式** | 函数式：一次性构建执行 | OOP：封装 MAF 构建过程 |
| **复杂度** | 适合简单并发场景 | 适合复杂闭环编排 |
| **状态** | 无需状态管理 | 需要管理客户端、配置等状态 |

### 5.2 模块导入与日志初始化

```python
"""评分与审阅编排工作流"""

import os
import json
import asyncio
from datetime import datetime, timezone
from openai import AsyncOpenAI
from agent_framework import MagenticBuilder, StandardMagenticManager, ChatAgent
from agent_framework.openai import OpenAIChatClient
from pydantic import ValidationError

from .utils import init_logging
from . import config
from .models import Step1Output, HoldRecommendation
from .prompts import SCORE_AGENT_SYSTEM, REVIEW_AGENT_SYSTEM, MANAGER_INSTRUCTIONS

# 初始化日志
logger = init_logging()
```

### 5.3 核心类 `ScoringWorkflow`

```python
class ScoringWorkflow:
    def __init__(self, 
                 dashscope_client: AsyncOpenAI | None = None, 
                 deepseek_client: AsyncOpenAI | None = None):
        """
        初始化评分工作流。
        
        Args:
            dashscope_client: 可选的 DashScope AsyncOpenAI 实例（用于测试注入）
            deepseek_client: 可选的 DeepSeek AsyncOpenAI 实例（用于测试注入）
        """
        logger.info("初始化 Step2 Workflow")

        # 1. 验证并读取 API Keys (如果未注入 Client)
        if not dashscope_client:
            ds_key = os.getenv("DASHSCOPE_API_KEY")
            if not ds_key:
                logger.error("DASHSCOPE_API_KEY 环境变量未设置")
                raise EnvironmentError("DASHSCOPE_API_KEY is required for Step2")
            
            # 初始化底层 DashScope Client
            self._dashscope_client = AsyncOpenAI(
                api_key=ds_key,
                base_url=config.DASHSCOPE_BASE_URL,
                timeout=config.API_TIMEOUT
            )
        else:
            self._dashscope_client = dashscope_client

        if not deepseek_client:
            dp_key = os.getenv("DEEPSEEK_API_KEY")
            if not dp_key:
                logger.error("DEEPSEEK_API_KEY 环境变量未设置")
                raise EnvironmentError("DEEPSEEK_API_KEY is required for Step2")
            
            # 初始化底层 DeepSeek Client
            self._deepseek_client = AsyncOpenAI(
                api_key=dp_key,
                base_url=config.DEEPSEEK_BASE_URL,
                timeout=config.API_TIMEOUT
            )
        else:
            self._deepseek_client = deepseek_client

        # 2. 初始化 MAF Clients
        self.manager_client = OpenAIChatClient(
            model_id=config.MODEL_MANAGER,
            async_client=self._dashscope_client
        )
        self.score_client = OpenAIChatClient(
            model_id=config.MODEL_SCORE_AGENT,
            async_client=self._dashscope_client
        )
        self.review_client = OpenAIChatClient(
            model_id=config.MODEL_REVIEW_AGENT,
            async_client=self._deepseek_client
        )
        logger.debug(f"ReviewAgent Client 初始化完成 - 模型: {config.MODEL_REVIEW_AGENT}")

        logger.info("Step2 Workflow 初始化完成")

    async def run(self, step1_output: Step1Output) -> HoldRecommendation:
        stock_code = step1_output.news.stock_code
        logger.info(f"开始 Step2 评分流程 - 股票: {stock_code}")

        try:
            # 1. 准备输入上下文
            context_str = step1_output.model_dump_json()
            logger.debug(f"Step1 输入数据大小: {len(context_str)} 字符")

            # 2. 创建 Agents
            # 重要：options 参数的传递方式必须严格参考技术文档
            # 参见：docs/analysis_llm/tech_note_maf_dashscope_integration.md
            logger.debug("创建 ScoreAgent 和 ReviewAgent")

            # 获取股票代码（用于 Prompt 占位符替换）
            stock_code = step1_output.news.stock_code

            score_agent = ChatAgent(
                name="ScoreAgent",
                chat_client=self.score_client,
                # 动态替换 Prompt 中的 {stock_code} 占位符
                # 参见 Section 4.4 - Prompt 占位符使用说明
                instructions=SCORE_AGENT_SYSTEM.format(stock_code=stock_code),
                # 开启 JSON Mode + 原生搜索
                # JSON Mode: 强制结构化输出，确保返回合法 JSON
                # enable_search: 启用 DashScope 原生联网搜索功能
                options={
                    "response_format": {"type": "json_object"},
                    "extra_body": {"enable_search": True}
                }
            )

            review_agent = ChatAgent(
                name="ReviewAgent",
                chat_client=self.review_client,
                # 动态替换 Prompt 中的 {stock_code} 占位符
                # 参见 Section 4.4 - Prompt 占位符使用说明
                instructions=REVIEW_AGENT_SYSTEM.format(stock_code=stock_code),
                # 开启 JSON Mode（DeepSeek API）
                # 注意：不启用搜索功能，因为：
                # 1. DeepSeek API 不支持 enable_search
                # 2. ReviewAgent 只需要基于输入数据进行逻辑审核，不需要搜索外部信息
                # 参见 Section 4.2 - 为什么 ReviewAgent 不需要搜索功能
                options={"response_format": {"type": "json_object"}}
            )

            # 3. 构建 Magentic Workflow（注入 Manager Instructions）
            logger.debug("构建 Magentic 工作流")
            workflow = (
                MagenticBuilder()
                .with_manager(
                    manager=StandardMagenticManager(
                        chat_client=self.manager_client,
                        instructions=MANAGER_INSTRUCTIONS  # 注入质量控制指令
                    )
                )
                .participants([score_agent, review_agent])
                .max_iterations(config.MAX_ITERATIONS)
                .build()
            )

            # 4. 执行（明确流程约束，确保闭环机制）
            logger.info(f"启动 Magentic 编排 - 最大迭代: {config.MAX_ITERATIONS}")

            # 构造包含流程约束的任务描述
            task = (
                f"请根据以下 Step1 数据生成股票投资评分报告。\n\n"
                f"数据内容：\n{context_str}\n\n"
                f"**流程约束（必须严格遵守）**：\n"
                f"1. 首先让 ScoreAgent 生成评分报告初稿（包含 hold_score 和 summary_reason）\n"
                f"2. 然后必须让 ReviewAgent 审核初稿（返回 passed 和 reason 字段）\n"
                f"3. 如果 ReviewAgent 返回 passed=false，必须将 reason 反馈给 ScoreAgent 进行修改\n"
                f"4. 重复步骤 2-3，直到 ReviewAgent 返回 passed=true\n"
                f"5. 只有在 passed=true 的情况下才能输出最终结果\n\n"
                f"注意：ReviewAgent 拥有一票否决权，不得跳过审核环节。"
            )

            # 执行 Workflow（可能抛出超时或迭代超限异常）
            try:
                result = await workflow.run(task)
                logger.info("Magentic 工作流执行完成")
            except RuntimeError as e:
                # MAF 可能在达到最大迭代时抛出 RuntimeError
                if "iteration" in str(e).lower() or "max" in str(e).lower():
                    logger.error(f"Magentic 工作流达到最大迭代次数 ({config.MAX_ITERATIONS})")
                    logger.debug(f"迭代超限详情: {str(e)}", exc_info=True)
                    raise RuntimeError(
                        f"Step2 consensus failed for {stock_code}. "
                        f"ScoreAgent and ReviewAgent could not reach agreement within {config.MAX_ITERATIONS} iterations. "
                        "This may indicate conflicting evaluation criteria or data quality issues."
                    ) from e
                else:
                    # 其他 RuntimeError，继续抛出
                    raise

            # 5. 提取与清洗结果
            logger.debug("提取评分结果")
            try:
                final_json = self._extract_result(result)
                logger.info(f"评分生成完成 - 分数: {final_json['hold_score']:.2f}")
                logger.debug(f"评分理由摘要: {final_json['summary_reason'][:100]}...")
            except ValueError as e:
                # _extract_result 抛出 ValueError 说明没有找到有效输出
                # 可能是循环耗尽但未达成共识
                logger.error(f"未找到有效的评分结果 - {stock_code}")
                logger.debug(f"结果提取失败详情: {str(e)}", exc_info=True)
                raise RuntimeError(
                    f"Step2 failed to produce valid output for {stock_code}. "
                    f"No valid ScoreAgent output found after workflow execution. "
                    "This may indicate consensus failure or workflow timeout."
                ) from e
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失败 - {stock_code}")
                logger.debug(f"JSON 错误详情: {str(e)}", exc_info=True)
                raise

            # 6. 最终封装（data_type 和 timestamp 由模型自动填充）
            stock_name = step1_output.news.stock_name or step1_output.sector.stock_name

            # 记录 stock_name 为空的告警（但不阻断流程）
            if not stock_name:
                logger.warning(
                    f"stock_name 为空 - {stock_code}: "
                    "Step1 的 news.stock_name 和 sector.stock_name 都为空。"
                    "这不影响评分流程，但可能影响下游系统的显示。"
                )
                stock_name = ""  # 显式赋值空字符串

            output = HoldRecommendation(
                stock_code=stock_code,
                stock_name=stock_name,  # 允许为空字符串
                hold_score=final_json["hold_score"],
                summary_reason=final_json["summary_reason"]
            )
            logger.info(f"Step2 完成 - {stock_code}: {output.hold_score:.2f}分")

            return output

        except asyncio.TimeoutError as e:
            logger.error(f"Step2 执行超时 - {stock_code}: API 调用超过 {config.API_TIMEOUT} 秒")
            logger.debug(f"超时详情: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"Step2 generation timeout for {stock_code}. "
                f"API call exceeded {config.API_TIMEOUT} seconds. "
                "Please retry later or check network connectivity."
            ) from e

        except ValidationError as e:
            logger.error(f"Pydantic 校验失败 - {stock_code}")
            logger.debug(f"校验错误详情: {e.json()}")
            raise

        except Exception as e:
            # 捕获所有其他异常（包括 openai.APITimeoutError 等）
            # 检查是否是超时相关错误
            if "timeout" in str(e).lower():
                logger.error(f"检测到超时相关错误 - {stock_code}: {str(e)}")
                logger.debug("超时堆栈", exc_info=True)
                raise RuntimeError(f"Timeout error in Step2 for {stock_code}") from e

            # 其他未预期异常
            logger.error(f"Step2 执行异常 - {stock_code}: {str(e)}")
            logger.debug("异常堆栈", exc_info=True)
            raise
```

### 5.3 stock_name 填充策略

采用两层回退：优先使用 `news.stock_name`，若为空则使用 `sector.stock_name`。**允许最终结果为空字符串**。

**设计依据**：
- `stock_code` 是核心标识符，有它即可完成后续所有流程
- `stock_name` 为辅助字段，即使为空也不影响业务逻辑
- 如果两者都为空，只在日志中记录 **WARNING 级别告警**，但不阻断流程
- 保持代码简洁，避免不必要的异常处理

**实现示例**：
```python
# 在 run 方法中，6. 最终封装之前
stock_name = step1_output.news.stock_name or step1_output.sector.stock_name

# 记录告警但不阻断
if not stock_name:
    logger.warning(
        f"stock_name 为空 - {stock_code}: "
        "Step1 的 news.stock_name 和 sector.stock_name 都为空。"
        "这不影响评分流程，但可能影响下游系统的显示。"
    )
    stock_name = ""  # 显式赋值空字符串

# 继续正常流程
output = HoldRecommendation(
    stock_code=stock_code,
    stock_name=stock_name,  # 允许为空
    hold_score=final_json["hold_score"],
    summary_reason=final_json["summary_reason"]
)
```

### 5.4 结果提取逻辑 (`_extract_result`)

#### 5.4.1 核心挑战

在 Magentic 闭环模式下，`workflow.run()` 返回的结果包含整个交互历史：
- 可能有多轮 "Score -> Review -> Score" 交互
- 中间产物包括：被否决的草稿、Review 的反馈意见、修改后的版本
- 我们只需要：**最后一个由 ScoreAgent 生成且通过审核的 JSON**

**与 Step1 的区别**：
- Step1：单次 LLM 调用，直接读取结果
- Step2：多轮交互，需要从结果中筛选最终版本

**MAF 结果类型区分**：

根据 MAF 框架的实现，`workflow.run()` 可能返回不同类型的结果对象：

1. **事件流 (`result.events`)**：
   - 包含完整的交互历史（消息、工具调用、Agent 响应等）
   - 每个事件包含 `executor_id`、`agent_name`、`content` 等元数据
   - 需要倒序遍历，找到最后一个来自 ScoreAgent 的事件

2. **输出列表 (`result.get_outputs()`)**：
   - 已经过滤/提取的最终输出结果
   - 不包含详细的事件元数据（如 `executor_id`）
   - 可以直接取最后一个有效输出

3. **高级 API (`result.final_output`)**：
   - 框架直接提供的最终结果
   - 优先使用（如果存在）

**提取策略**：根据 `result` 对象的可用属性，按优先级依次尝试不同的提取方法，确保在各种 MAF 版本下都能正常工作。

#### 5.4.2 实现代码

**主方法：`_extract_result`**

```python
def _extract_result(self, result) -> dict:
    """
    从 Magentic Workflow 结果中提取最终的评分 JSON。

    根据 result 的类型采用不同的提取策略：
    1. 优先使用高级 API (final_output)
    2. 如果有事件流 (events)，倒序查找 ScoreAgent 的最后输出
    3. 如果有输出列表 (get_outputs())，直接取最后一个有效输出
    4. 尝试迭代 result 对象本身，根据元素类型判断是事件流还是输出列表

    Args:
        result: Magentic WorkflowRunResult 对象

    Returns:
        dict: 包含 hold_score 和 summary_reason 的字典

    Raises:
        ValueError: 未找到有效输出或格式不支持
        json.JSONDecodeError: JSON 解析失败
    """
    logger.debug("开始提取 Magentic 工作流结果")

    # 策略 1：使用框架的高级 API
    if hasattr(result, 'final_output') and result.final_output:
        logger.debug("使用 result.final_output 提取结果")
        try:
            return self._parse_and_validate(result.final_output)
        except Exception as e:
            logger.warning(f"final_output 解析失败: {e}")

    # 策略 2：从事件流中提取（适用于完整的交互历史）
    if hasattr(result, 'events') and result.events:
        logger.debug(f"从事件流中提取结果，共 {len(result.events)} 个事件")
        return self._extract_from_events(result.events)

    # 策略 3：从输出列表中提取（适用于已过滤的输出）
    if hasattr(result, 'get_outputs'):
        outputs = result.get_outputs()
        if outputs:
            logger.debug(f"从输出列表中提取结果，共 {len(outputs)} 个输出")
            return self._extract_from_outputs(outputs)

    # 策略 4：尝试迭代 result 对象本身
    if hasattr(result, '__iter__'):
        items = list(result)
        if items:
            logger.debug(f"从可迭代对象中提取结果，共 {len(items)} 个元素")
            # 判断是事件流还是输出列表
            first_item = items[0]
            if hasattr(first_item, 'executor_id') or hasattr(first_item, 'agent_name'):
                return self._extract_from_events(items)
            else:
                return self._extract_from_outputs(items)

    logger.error(f"无法从 result 对象提取结果，类型: {type(result)}")
    raise ValueError("Workflow result format not supported")


def _extract_from_events(self, events: list) -> dict:
    """
    从事件流中倒序查找 ScoreAgent 的最后输出。

    事件流包含完整的交互历史，每个事件有 executor_id/agent_name 等元数据。
    我们需要倒序遍历，找到最后一个来自 ScoreAgent 的有效输出。

    Args:
        events: 事件对象列表

    Returns:
        dict: 验证通过的数据字典

    Raises:
        ValueError: 未找到有效的 ScoreAgent 输出
    """
    logger.debug("倒序遍历事件流，查找 ScoreAgent 的最终输出")

    for idx, event in enumerate(reversed(events)):
        event_idx = len(events) - idx - 1
        logger.debug(f"检查事件 [{event_idx}]: {type(event)}")

        # 识别 ScoreAgent 的输出
        is_score_agent = False
        if hasattr(event, 'executor_id') and event.executor_id == "ScoreAgent":
            is_score_agent = True
        elif hasattr(event, 'agent_name') and event.agent_name == "ScoreAgent":
            is_score_agent = True
        elif hasattr(event, 'source') and 'ScoreAgent' in str(event.source):
            is_score_agent = True

        if not is_score_agent:
            logger.debug(f"事件 [{event_idx}] 不是 ScoreAgent 的输出，跳过")
            continue

        logger.debug(f"事件 [{event_idx}] 来自 ScoreAgent，尝试解析")

        # 提取内容
        content = self._get_content(event)
        if not content:
            logger.debug(f"事件 [{event_idx}] 内容为空，跳过")
            continue

        # 尝试解析和验证
        try:
            data = self._parse_and_validate(content)
            logger.info(f"成功从事件 [{event_idx}] 提取结果：hold_score={data['hold_score']}")
            return data
        except Exception as e:
            logger.warning(f"事件 [{event_idx}] 解析失败: {e}")
            continue

    # 如果循环结束仍未找到，抛出异常
    logger.error("未在事件流中找到有效的 ScoreAgent 输出")
    raise ValueError("No valid ScoreAgent output found in events")


def _extract_from_outputs(self, outputs: list) -> dict:
    """
    从输出列表中提取最后一个有效输出。

    输出列表已经过滤/提取，不包含详细的事件元数据。
    我们直接倒序尝试解析每个输出，找到第一个有效的即可。

    Args:
        outputs: 输出对象/字符串列表

    Returns:
        dict: 验证通过的数据字典

    Raises:
        ValueError: 未找到有效输出
    """
    logger.debug("从输出列表中提取最后一个有效输出")

    # 倒序尝试解析每个输出
    for idx, output in enumerate(reversed(outputs)):
        output_idx = len(outputs) - idx - 1
        logger.debug(f"尝试解析输出 [{output_idx}]: {type(output)}")

        try:
            # 使用统一的内容提取逻辑
            content = self._get_content(output)
            if not content:
                logger.warning(f"输出 [{output_idx}] 无法提取内容")
                continue

            data = self._parse_and_validate(content)
            logger.info(f"成功从输出 [{output_idx}] 提取结果：hold_score={data['hold_score']}")
            return data
        except Exception as e:
            logger.warning(f"输出 [{output_idx}] 解析失败: {e}")
            continue

    # 如果循环结束仍未找到，抛出异常
    logger.error("未在输出列表中找到有效输出")
    raise ValueError("No valid output found in outputs list")


def _get_content(self, obj) -> str:
    """
    从对象中提取文本内容（通用方法，适用于事件、输出、消息等）。

    支持多种常见的内容属性：data, content, text，以及字典和字符串。
    按优先级依次尝试，确保兼容 MAF 各种类型的返回对象。

    Args:
        obj: 任意对象（事件、输出、ChatMessage 等）

    Returns:
        str: 提取的内容文本，如果无法提取则返回 None
    """
    # 如果已经是字典，转为 JSON 字符串
    if isinstance(obj, dict):
        return json.dumps(obj)
    # 如果是字符串，直接返回
    elif isinstance(obj, str):
        return obj
    # 尝试常见的内容属性（按优先级）
    elif hasattr(obj, 'data'):
        return obj.data
    elif hasattr(obj, 'content'):
        return obj.content
    elif hasattr(obj, 'text'):
        return obj.text
    # 无法提取
    return None


def _parse_and_validate(self, content) -> dict:
    """
    解析并验证 ScoreAgent 的输出内容。

    Args:
        content: 原始内容（可能是字符串、字典等）

    Returns:
        dict: 验证通过的数据字典

    Raises:
        ValueError: 数据不符合预期格式
        json.JSONDecodeError: JSON 解析失败
    """
    # 如果已经是字典，直接使用
    if isinstance(content, dict):
        data = content
    # 如果是字符串，尝试解析 JSON
    elif isinstance(content, str):
        # 清理可能的 markdown 代码块标记
        content = content.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()

        data = json.loads(content)
    else:
        raise ValueError(f"Unsupported content type: {type(content)}")

    # 验证必需字段
    if 'hold_score' not in data:
        raise ValueError("Missing required field: hold_score")
    if 'summary_reason' not in data:
        raise ValueError("Missing required field: summary_reason")

    # 验证字段类型和范围
    hold_score = data['hold_score']
    if not isinstance(hold_score, (int, float)):
        raise ValueError(f"hold_score must be numeric, got {type(hold_score)}")
    if not (0 <= hold_score <= 10):
        raise ValueError(f"hold_score must be in [0, 10], got {hold_score}")

    summary_reason = data['summary_reason']
    if not isinstance(summary_reason, str):
        raise ValueError(f"summary_reason must be string, got {type(summary_reason)}")
    if len(summary_reason) < config.SUMMARY_REASON_MIN_CHARS:
        raise ValueError(
            f"summary_reason too short: {len(summary_reason)} chars "
            f"(min: {config.SUMMARY_REASON_MIN_CHARS})"
        )
    if len(summary_reason) > config.SUMMARY_REASON_MAX_CHARS:
        raise ValueError(
            f"summary_reason too long: {len(summary_reason)} chars "
            f"(max: {config.SUMMARY_REASON_MAX_CHARS})"
        )

    logger.debug("内容验证通过")
    return data
```

#### 5.4.3 设计说明

**多策略适配**：

为了适配 MAF 不同版本和不同的结果对象实现，采用**按优先级依次尝试**的策略：

1. **策略 1 - 高级 API (`final_output`)**：
   - 如果框架直接提供 `final_output`，优先使用
   - 最简洁高效，无需手动遍历

2. **策略 2 - 事件流 (`events`)**：
   - 适用于包含完整交互历史的结果对象
   - 需要倒序查找，识别 ScoreAgent 的输出
   - 通过 `executor_id`、`agent_name`、`source` 等元数据识别

3. **策略 3 - 输出列表 (`get_outputs()`)**：
   - 适用于已过滤/提取的输出列表
   - 直接取最后一个有效输出，无需检查来源
   - **关键区别**：输出列表不包含事件元数据，不能用事件流的识别逻辑

4. **策略 4 - 迭代对象**：
   - 兜底方案，尝试直接迭代 `result`
   - 根据第一个元素的属性判断是事件流还是输出列表
   - 自动选择对应的处理逻辑

**事件流 vs 输出列表**：

| 特性 | 事件流 (`events`) | 输出列表 (`get_outputs()`) |
|------|------------------|---------------------------|
| 内容 | 完整交互历史（消息、工具调用、Agent 响应） | 已提取的最终输出 |
| 元数据 | 包含 `executor_id`, `agent_name`, `source` 等 | 通常不包含详细元数据 |
| 提取逻辑 | 需要识别 ScoreAgent 并倒序查找 | 直接取最后一个有效输出 |
| 适用场景 | 多轮交互，有中间被否决的版本 | 框架已完成筛选，直接获取结果 |

**为什么倒序查找**：
- Magentic 闭环中可能有多轮 "Score -> Review -> Score"
- 中间的 Score 输出可能被 Reviewer 否决
- 最后一个 ScoreAgent 的输出一定是通过审核的最终版本

**容错与鲁棒性**：
- **多重识别**：通过多种属性识别 ScoreAgent 输出（`executor_id`、`agent_name`、`source`）
- **统一内容提取**：使用 `_get_content()` 方法统一处理各种对象类型：
  - 支持 `dict`, `str` 直接类型
  - 支持 `.data`, `.content`, `.text` 属性（覆盖 `ChatMessage` 等 MAF 常见类型）
  - 避免代码重复，确保事件流和输出列表使用相同的提取逻辑
- **容错解析**：支持字典、字符串、带 markdown 标记的 JSON
- **严格验证**：验证必需字段、类型、范围、长度
- **详细日志**：每个步骤都有 DEBUG 日志，便于排查问题
- **明确错误**：如果所有策略都失败，抛出 `ValueError` 并提示可能原因

#### 5.4.4 在 run 方法中的使用

```python
# 5. 提取与清洗结果
logger.debug("提取评分结果")
try:
    final_json = self._extract_result(result)
    logger.info(f"评分生成完成 - 分数: {final_json['hold_score']:.2f}")
    logger.debug(f"评分理由摘要: {final_json['summary_reason'][:100]}...")
except ValueError as e:
    logger.error(f"结果提取失败: {e}")
    raise
except json.JSONDecodeError as e:
    logger.error(f"JSON 解析失败: {e}")
    raise
```

### 5.5 闭环机制说明

#### 5.5.1 双重保障机制

为确保 ReviewAgent 必经环节且拥有一票否决权，Step2 采用**双重保障**策略：

1. **Manager Instructions（管理器层面）**
   - 在创建 `StandardMagenticManager` 时注入 `MANAGER_INSTRUCTIONS`
   - 明确告知 Manager 其质量控制职责
   - 强调 ReviewAgent 是必经环节，不可跳过

2. **Task 约束（任务层面）**
   - 在 `workflow.run(task)` 时提供详细的流程约束
   - 明确说明"生成 -> 审核 -> 重试"的步骤顺序
   - 强调只有 `passed=true` 才能输出结果

**设计优势**：
- 不依赖框架的隐式行为，通过显式指令完全控制流程
- 即使 Manager 模型能力不足，Task 约束也能起到兜底作用
- 符合"显式优于隐式"的工程原则

#### 5.5.2 闭环触发与终止条件

**触发条件（进入重试循环）**：
- ReviewAgent 返回 `{"passed": false, "reason": "..."}`
- Manager 识别到 `passed=false` 信号
- Manager 将 `reason` 字段完整传递给 ScoreAgent
- ScoreAgent 根据反馈修改并重新生成

**终止条件（退出循环）**：
- ✅ **正常终止**：ReviewAgent 返回 `{"passed": true, "reason": ""}`
- ❌ **异常终止**：达到 `MAX_ITERATIONS` 上限（约 10 次迭代，相当于 5 轮审核）

#### 5.5.3 流程示意图

```
输入 Step1 数据
    ↓
Manager 收到任务（包含流程约束）
    ↓
Manager 分配任务给 ScoreAgent
    ↓
ScoreAgent 生成初稿 → 返回给 Manager
    ↓
Manager 强制要求 ReviewAgent 审核（必经环节）
    ↓
ReviewAgent 审核 → 返回 {"passed": ?, "reason": "..."}
    ↓
    ├─→ passed=true → 输出最终结果 ✅
    │
    └─→ passed=false → Manager 捕捉信号
            ↓
        Manager 将 reason 反馈给 ScoreAgent
            ↓
        ScoreAgent 根据反馈修改
            ↓
        （返回审核步骤，重复直到通过或达到上限）
```

#### 5.5.4 可观测性

通过日志可以追踪完整的闭环过程：
- **INFO 级别**：记录每次 Magentic 启动和完成
- **DEBUG 级别**：记录 Agent 交互细节（如果框架支持）
- **最终结果**：记录最终分数和是否经过多轮修改

#### 5.5.5 与概要设计的对应

完全符合概要设计 Section 4.2 的要求：
- ✅ "Manager 不得跳过 Reviewer 直接输出结果"
- ✅ "Reviewer 拥有一票否决权"
- ✅ "Manager 捕捉 `passed: false` 信号，将 reason 发送给 ScoreAgent 进行重试"
- ✅ "通过设置 max_iterations 来防止死循环"

---

## 6. 日志策略（复用 Step1 基础设施）

### 6.1 初始化规范

**严格遵循概要设计 Section 9 的规定**：在 `analysis_llm/workflow.py` 模块开头通过 `analysis_llm.utils.init_logging()` 初始化 Logger。

```python
from .utils import init_logging
logger = init_logging()
```

### 6.2 日志输出配置

- **日志文件**：共享输出至 `logs/analysis_llm.log`（与 Step1 统一）
- **Console 级别**：INFO - 仅输出关键进度和最终结果
- **File 级别**：DEBUG - 记录详细的 Agent 思考过程、Reviewer 建议及重试上下文

### 6.3 关键记录点

| 位置 | 级别 | 内容 |
|------|------|------|
| `__init__` | INFO | Workflow 初始化完成 |
| `__init__` | DEBUG | 各 Agent 的模型配置 |
| `run` 开始 | INFO | 开始评分流程 + stock_code |
| `run` 输入 | DEBUG | Step1 输入数据大小 |
| Agent 创建 | DEBUG | Agent 创建日志 |
| Workflow 构建 | DEBUG | Magentic 工作流构建 |
| Magentic 启动 | INFO | 编排开始 + 最大迭代数 |
| Magentic 完成 | INFO | 编排完成 |
| 结果提取 | DEBUG | 最终 JSON 内容片段 |
| 评分生成 | INFO | 最终分数 + stock_code |
| 异常捕获 | ERROR | 错误信息 + 堆栈 (DEBUG) |

### 6.4 设计优势

- **全链路追踪**：与 Step1 共享日志文件，方便排查跨步骤问题
- **可观测性**：通过 DEBUG 级别可查看 Agent 内部推理过程和 Manager 决策
- **问题定位**：异常时可快速定位是 ScoreAgent 还是 ReviewAgent 阶段失败
- **统一规范**：确保整个 analysis_llm 模块的日志格式和级别一致

---

## 7. 异常处理

### 7.1 异常类型与处理策略

#### 完整异常分类表

| 异常类型 | 触发场景 | 捕获位置 | 处理策略 | 对外抛出 | 用户指导 |
|---------|---------|---------|---------|---------|---------|
| `EnvironmentError` | API Keys 缺失 | `__init__` | 记录 ERROR，阻止实例化 | 直接抛出 | 检查 .env 配置 |
| `asyncio.TimeoutError` | 异步操作超时 | `run` (外层) | 记录 ERROR + DEBUG，包装为 RuntimeError | 包装后抛出 | 稍后重试或检查网络 |
| `openai.APITimeoutError` | OpenAI SDK 超时 | `run` (外层) | 检测字符串 "timeout"，包装为 RuntimeError | 包装后抛出 | 稍后重试或检查网络 |
| `RuntimeError` (含 "iteration") | 循环耗尽，共识失败 | `run` (workflow.run 后) | 记录 ERROR，说明 Score 和 Review 未达成共识 | 重新抛出（含上下文） | 检查数据质量或评分标准 |
| `ValueError` (from `_extract_result`) | 未找到有效的 ScoreAgent 输出 | `run` (结果提取时) | 记录 ERROR，说明生成失败 | 包装为 RuntimeError | 可能是共识失败或超时 |
| `json.JSONDecodeError` | JSON 解析失败 | `run` (结果提取时) | 记录 ERROR + DEBUG | 直接抛出 | Agent 输出格式错误 |
| `ValidationError` | Pydantic 校验失败 | `run` (创建 HoldRecommendation 时) | 记录 ERROR + DEBUG | 直接抛出 | 数据不符合模型约束 |
| 其他异常（含 "timeout"） | 其他超时相关错误 | `run` (外层) | 检测字符串，包装为 RuntimeError | 包装后抛出 | 稍后重试 |
| 其他异常 | 未预期错误 | `run` (外层) | 记录 ERROR + 堆栈 | 直接抛出 | 查看日志排查 |

#### 关键异常详解

**1. 超时处理（Timeout Handling）**

**问题**：Step2 调用两家 API（DashScope + DeepSeek）+ 搜索，网络链路长，超时概率高。

**策略**：
- 捕获 `asyncio.TimeoutError` 和检测字符串 "timeout"
- 记录详细日志（包括 `config.API_TIMEOUT` 配置值）
- 包装为 `RuntimeError`，提供有意义的错误消息
- 提示用户重试或检查网络连接

**示例错误消息**：
```
Step2 generation timeout for 603080.SH.
API call exceeded 60.0 seconds.
Please retry later or check network connectivity.
```

**2. 搜索降级（Search Fallback）**

**问题**：ScoreAgent 搜索失败时如何处理？

**策略**：优雅降级，不硬性失败
- 在 `SCORE_AGENT_SYSTEM` prompt 中添加降级说明
- 告知 Agent：搜索失败时基于 Step1 数据评分
- Step1 已提供详尽数据，搜索是"锦上添花"而非必需
- 无需复杂的异常捕获，让 Agent 自己处理

**好处**：
- 保持流程健壮性
- 符合"优雅降级"原则
- 简化异常处理逻辑

**参见**：Section 4.1 中更新后的 `SCORE_AGENT_SYSTEM`

**3. 循环超限处理（Iteration Limit）**

**问题**：`MaxIterationsReachedError` 是假设的异常，MAF 实际行为可能不同。

**策略**：不依赖特定异常，而是检查结果有效性
- 捕获 `RuntimeError` 并检查是否包含 "iteration" 或 "max" 关键字
- 如果 `_extract_result` 抛出 `ValueError`，说明没有有效输出
- 记录详细日志，说明可能是共识失败
- 提供有意义的错误消息

**示例错误消息**：
```
Step2 consensus failed for 603080.SH.
ScoreAgent and ReviewAgent could not reach agreement within 10 iterations.
This may indicate conflicting evaluation criteria or data quality issues.
```

**4. 结果提取失败**

**触发条件**：
- `_extract_result` 遍历所有事件后未找到有效的 ScoreAgent 输出
- 可能原因：循环耗尽但未达成共识、Workflow 意外终止

**处理**：
- 捕获 `ValueError`
- 包装为 `RuntimeError`，说明生成失败
- 提示可能是共识失败或超时

### 7.2 异常记录规范

所有异常必须遵循以下日志规范：
- **ERROR 级别**：记录异常类型和核心信息（面向运维人员）
- **DEBUG 级别**：记录完整堆栈跟踪（`exc_info=True`，面向开发人员）

参见 Section 5.2 中 `run` 方法的 `except` 块示例。

---

## 7.3 Step2 内部校验机制

### 设计原则

**信任上游，关注自身**：
- Step2 **无条件信任** Step1 的输出，不对输入数据进行校验
- Step1 的 Checker 已经确保了数据完整性和业务逻辑正确性
- Step2 只校验自己生成的数据是否符合输出规范

**避免过度设计**：
- 遵循单一职责原则，不重复上游的校验逻辑
- 降低模块间耦合度
- 简化代码，提高可维护性

### 校验分层架构

Step2 包含三层校验机制，确保最终输出的质量和合规性：

#### 第一层：环境层校验（`__init__` 阶段）

**目的**：确保运行环境配置正确，在实例化时即发现问题

**校验内容**：
- 验证 `DASHSCOPE_API_KEY` 环境变量是否设置
- 验证 `DEEPSEEK_API_KEY` 环境变量是否设置

**位置**：`ScoringWorkflow.__init__()` 方法

**失败处理**：
- 抛出 `EnvironmentError`，阻止实例化
- 记录 ERROR 级别日志

**参见**：Section 5.2 核心类实现

#### 第二层：解析层校验（结果提取阶段）

**目的**：确保 Agent 输出符合预期格式和业务规则

**校验内容**：
1. **必需字段检查**：`hold_score` 和 `summary_reason` 必须存在
2. **类型检查**：
   - `hold_score` 必须是数值类型（int 或 float）
   - `summary_reason` 必须是字符串类型
3. **范围检查**：`hold_score` 必须在 [0, 10] 范围内
4. **长度检查**：`summary_reason` 必须在 [100, 1000] 字符范围内

**位置**：`ScoringWorkflow._parse_and_validate()` 方法

**失败处理**：
- 抛出 `ValueError`（字段/类型/范围/长度错误）
- 抛出 `json.JSONDecodeError`（JSON 解析失败）
- 记录 DEBUG 级别日志，继续尝试下一个候选结果

**参见**：Section 5.4.2 `_parse_and_validate` 实现

#### 第三层：模型层校验（对象创建阶段）

**目的**：最终的数据结构完整性校验（纵深防御）

**校验内容**：
- Pydantic 自动校验所有字段类型
- `hold_score`: `ge=0, le=10` 约束（Field 级别）
- `summary_reason`: `min_length=100, max_length=1000` 约束（Field 级别）
- `data_type` 和 `timestamp` 自动填充校验

**位置**：`HoldRecommendation` Pydantic 模型定义

**失败处理**：
- 抛出 `ValidationError`
- 记录 ERROR 级别日志并重新抛出

**参见**：Section 3.1 数据模型定义

### 校验覆盖矩阵

| 校验项 | 环境层 | 解析层 | 模型层 | 说明 |
|--------|--------|--------|--------|------|
| API Keys 存在性 | ✅ | - | - | 启动时检查 |
| 必需字段 | - | ✅ | ✅ | 双重保障 |
| 字段类型 | - | ✅ | ✅ | 双重保障 |
| hold_score 范围 [0, 10] | - | ✅ | ✅ | 双重保障 |
| summary_reason 长度 [100, 1000] | - | ✅ | ✅ | 双重保障 |
| data_type 固定值 | - | - | ✅ | 自动填充 |
| timestamp 生成 | - | - | ✅ | 自动填充 |

**说明**：解析层和模型层的校验存在重复，这是有意为之的**纵深防御**策略。即使某一层失效，另一层也能捕获问题，确保数据质量。

### 为什么不校验 Step1 输入

**原则说明**：

1. **单一职责原则**：
   - Step1 负责数据收集和质量保证
   - Step2 负责评分生成和输出规范
   - 各司其职，避免职责重叠

2. **避免重复校验**：
   - Step1 的 Checker 已经确保了 `stock_code`、`stock_name` 等字段的完整性
   - Step2 重复校验会增加代码复杂度，却无实际价值

3. **降低耦合度**：
   - Step2 不需要了解 Step1 的内部逻辑和校验规则
   - 便于两个模块独立演进和测试

4. **简化代码**：
   - 减少不必要的防御性编程
   - 提高代码可读性和可维护性

**信任边界**：
- Step2 的信任边界是 Step1 的输出
- 如果 Step1 输出有问题，应该在 Step1 阶段修复，而不是在 Step2 打补丁

---

## 8. 环境配置 (.env)

### 8.1 必需的环境变量

Step2 需要以下环境变量（应在项目根目录的 `.env` 文件中配置）：

```bash
# DashScope API (阿里云 - 用于 Manager 和 ScoreAgent)
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  # 可选，有默认值

# DeepSeek API (用于 ReviewAgent)
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1  # 可选，有默认值
```

### 8.2 .env.sample 示例

建议在项目根目录维护 `.env.sample` 文件，包含以下内容：

```bash
# ======================
# Step 2 Configuration
# ======================

# DashScope API (阿里云)
DASHSCOPE_API_KEY=your_dashscope_api_key_here
# DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  # 可选

# DeepSeek API
DEEPSEEK_API_KEY=your_deepseek_api_key_here
# DEEPSEEK_BASE_URL=https://api.deepseek.com/v1  # 可选
```

### 8.3 配置验证

- 在 `ScoringWorkflow.__init__()` 中会自动验证 API Keys 是否设置
- 若缺失，会抛出 `EnvironmentError` 并记录详细日志
- 建议在部署前通过单元测试验证配置完整性

---

## 9. 运行与测试指南

### 9.1 单独运行 Step2

**前提条件**：已有 Step1 的输出数据（`Step1Output` 对象或 JSON 文件）

**方式一：直接调用**
```python
import asyncio
from analysis_llm.workflow import ScoringWorkflow
from analysis_llm.models import Step1Output, HoldRecommendation

async def run_scoring(step1_output: Step1Output) -> HoldRecommendation:
    """运行评分流程"""
    workflow = ScoringWorkflow()
    result = await workflow.run(step1_output)
    return result

# 使用示例
if __name__ == "__main__":
    # 加载 Step1 输出
    with open("step1_output.json") as f:
        step1_data = json.load(f)
    step1_output = Step1Output(**step1_data)

    # 运行 Step2
    recommendation = asyncio.run(run_scoring(step1_output))
    print(f"Hold Score: {recommendation.hold_score}")
```

**方式二：通过脚本**
```bash
# 创建 scripts/run_scoring.py
python scripts/run_scoring.py --input step1_output.json --output recommendation.json
```

### 9.2 运行完整流程

```python
import asyncio
from analysis_llm.workflow import execute_step1, ScoringWorkflow
from analysis_llm.models import HoldRecommendation

async def run_full_pipeline(stock_code: str) -> HoldRecommendation:
    """运行完整的分析和评分流程"""

    # Step1: 数据收集与分析（并发执行 news/sector/kline）
    # execute_step1 内部使用 ConcurrentBuilder 并发执行三个 Agent
    step1_output = await execute_step1(stock_code)

    # Step2: 评分与推荐
    scoring_wf = ScoringWorkflow()
    recommendation = await scoring_wf.run(step1_output)

    return recommendation

# 使用示例
if __name__ == "__main__":
    result = asyncio.run(run_full_pipeline("603080.SH"))
    print(result.model_dump_json(indent=2))
```

**说明**：
- Step1 使用 `execute_step1()` 函数，而非单独的 Workflow 类
- `execute_step1()` 内部使用 `ConcurrentBuilder` 并发执行 `create_news_agent()`, `create_sector_agent()`, `create_kline_agent()`
- 返回的 `Step1Output` 已经包含了 `news`, `sector`, `kline` 三个字段

### 9.3 单元测试

**测试 Step2 独立功能**：
```python
# tests/test_scoring_workflow.py
import pytest
from analysis_llm.workflow import ScoringWorkflow
from analysis_llm.models import Step1Output, HoldRecommendation

@pytest.mark.asyncio
async def test_scoring_workflow():
    """测试评分工作流"""
    # 准备测试数据（Step1 输出）
    step1_output = Step1Output(...)  # 使用模拟数据

    # 运行 Step2
    workflow = ScoringWorkflow()
    result = await workflow.run(step1_output)

    # 验证结果
    assert isinstance(result, HoldRecommendation)
    assert 0 <= result.hold_score <= 10
    assert len(result.summary_reason) >= 100
```

### 9.4 向后兼容性验证

**确保不影响 Step1**：
```python
# tests/test_backward_compatibility.py
import pytest
from analysis_llm.workflow import execute_step1, ScoringWorkflow
from analysis_llm.models import Step1Output, HoldRecommendation

@pytest.mark.asyncio
async def test_step1_still_works():
    """确保 Step1 的 execute_step1 函数仍然可用"""
    # Step1 应该能够正常运行
    stock_code = "603080.SH"
    step1_output = await execute_step1(stock_code)

    # 验证 Step1 输出结构
    assert isinstance(step1_output, Step1Output)
    assert step1_output.news is not None
    assert step1_output.sector is not None
    assert step1_output.kline is not None

@pytest.mark.asyncio
async def test_step2_does_not_break_step1():
    """确保 Step2 代码不影响 Step1 的执行"""
    # 导入 Step2 的类
    from analysis_llm.workflow import ScoringWorkflow

    # Step1 仍然可以正常运行
    stock_code = "603080.SH"
    step1_output = await execute_step1(stock_code)

    # Step2 也可以正常运行
    scoring_wf = ScoringWorkflow()
    recommendation = await scoring_wf.run(step1_output)

    assert isinstance(recommendation, HoldRecommendation)

def test_step1_models_unchanged():
    """确保 Step1 的模型仍然可用"""
    from analysis_llm.models import Step1Output, NewsAnalysis, SectorAnalysis, KlineAnalysis

    # 模型类仍然存在
    assert Step1Output is not None
    assert NewsAnalysis is not None
```

### 9.5 配置隔离验证

**确保配置不冲突**：
```python
def test_config_isolation():
    """验证 Step1 和 Step2 的配置互不影响"""
    from analysis_llm import config  # 导入 config 模块

    # Step1 配置
    assert hasattr(config, 'MODEL_NEWS')
    assert hasattr(config, 'MODEL_CHECKER')

    # Step2 配置（新增）
    assert hasattr(config, 'MODEL_MANAGER')
    assert hasattr(config, 'MODEL_SCORE_AGENT')
    assert hasattr(config, 'MODEL_REVIEW_AGENT')

    # 配置值不同
    assert config.MODEL_NEWS != config.MODEL_MANAGER
```

---

*文档生成时间：2026-02-04*

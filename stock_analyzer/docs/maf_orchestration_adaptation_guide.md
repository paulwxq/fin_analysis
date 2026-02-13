# 基于 MAF ConcurrentBuilder 的工作流改造指南

本文档详细说明了如何将现有的 Module A、B、C 模块进行适配性改造，以便使用 Microsoft Agent Framework (MAF) 的 `ConcurrentBuilder` 进行原生并行编排。

## 1. 核心适配原理

MAF `ConcurrentBuilder` 在 `1.0.0b260130` 版本中具有以下特性，我们的改造必须遵循这些约束：

1.  **输入广播制**：工作流入口输入会被分发器（Dispatcher）原样广播给所有参与者。
2.  **输入类型约束**：分发器只支持 `AgentExecutorRequest`、`str` 或 `ChatMessage`。
3.  **结果混合制**：聚合器（Aggregator）会同时收到自定义 `Executor` 的直接返回对象和 `ChatAgent` 的 `AgentExecutorResponse` 对象。

---

## 2. 改造步骤说明

### 2.1 定义统一任务载荷 (WorkflowTask)

在 `stock_analyzer/workflow_models.py` 中定义一个通用的 Pydantic 模型，用于在模块间传递参数。

```python
from pydantic import BaseModel

class WorkflowTask(BaseModel):
    symbol: str
    name: str
    industry: str
```

### 2.2 改造 Module A 为自定义 Executor

Module A 目前是纯 Python 同步代码。我们需要创建一个 `ModuleAExecutor` 类来承载逻辑。

*   **文件**：建议新建 `stock_analyzer/module_a_executor.py`
*   **关键逻辑**：
    *   继承 `Executor` 基类。
    *   实现 `@handler` 方法，接收 `AgentExecutorRequest`。
    *   使用 `asyncio.to_thread` 执行原有的同步采集函数。

```python
class ModuleAExecutor(Executor):
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AKShareData]) -> None:
        # 1. 从消息中提取 JSON 字符串并解析
        task = WorkflowTask.model_validate_json(request.messages[0].text)
        # 2. 调用原有的同步逻辑
        result = await asyncio.to_thread(collect_akshare_data, task.symbol, task.name)
        # 3. 通过 ctx 发送结构化结果
        await ctx.send_message(result)
```

### 2.3 适配 Module B & C (ChatAgent)

由于 `ChatAgent` 已经符合 MAF 协议，不需要修改代码类定义。但在工作流启动时，我们需要将 `WorkflowTask` 转化为一段能够引导 Agent 的指令。

*   **输入方式**：工作流主入口传入 `task.model_dump_json()`。
*   **Agent 行为**：Agent 会收到该 JSON 字符串作为首条消息。由于我们的 Prompt 中已经要求 Agent 分析特定股票，它们会自动从这段消息中提取代码和名称。

### 2.4 实现自定义聚合器 (Aggregator)

这是编排的核心，负责收集 A/B/C 的结果并进行类型转换。

*   **文件**：`stock_analyzer/workflow_aggregator.py`
*   **职责**：
    1.  遍历 `list[Any]` 结果。
    2.  识别 `AKShareData` (Module A)。
    3.  识别 `AgentExecutorResponse` (Module B/C)，从中提取 JSON 并解析为 `WebResearchResult` 和 `TechnicalAnalysisResult`。
    4.  **熔断检查**：若任一模块为 `None` 或解析失败，抛出异常。

---

## 3. 工作流组装实现 (workflow.py)

使用 `ConcurrentBuilder` 进行最终串联：

```python
from agent_framework._workflows._concurrent import ConcurrentBuilder

async def run_maf_workflow(raw_symbol: str):
    # 1. Pre-step: 查找股票信息 (lookup_stock_info)
    # 2. 构造任务载荷消息
    task = WorkflowTask(symbol=symbol, name=name, industry=industry)
    request = AgentExecutorRequest(
        messages=[ChatMessage(role=Role.USER, text=task.model_dump_json())]
    )

    # 3. 组装并行阶段
    builder = ConcurrentBuilder()
    builder.participants([
        ModuleAExecutor(id="module_a"),
        create_web_research_agent(), # 返回 ChatAgent
        create_technical_agent()     # 返回 ChatAgent
    ])
    builder.with_aggregator(StockAnalysisAggregator())
    
    parallel_wf = builder.build()

    # 4. 运行并获取聚合后的字典
    run_result = await parallel_wf.run(request)
    parallel_data = run_result.get_outputs()[0]

    # 5. 串行执行 Module D
    return await run_chief_analysis(..., **parallel_data)
```

---

## 4. 变更风险与对策

| 风险点 | 对策 |
| :--- | :--- |
| **类型校验失败** | 确保所有自定义 Executor 的 Handler 显式声明接收 `AgentExecutorRequest`。 |
| **Agent 输出非 JSON** | 聚合器必须复用 `llm_helpers.extract_json_str` 进行稳健提取。 |
| **重试机制** | 利用 `ConcurrentBuilder` 的 `with_checkpointing` 特性，为长时间运行的搜网任务提供持久化保障。 |

## 5. 后续计划

1.  创建 `workflow_models.py` 定义共享输入模型。
2.  实现 `ModuleAExecutor` 包装类。
3.  编写 `StockAnalysisAggregator` 聚合逻辑。
4.  在 `run_workflow.py` 中切换到此 MAF 原生模式。

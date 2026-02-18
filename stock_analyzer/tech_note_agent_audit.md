# Tech Note: Stock Analyzer Agent & LLM 审计报告

**日期**：2026-02-17  
**状态**：Active  
**涉及范围**：Module B, C, D

---

## 1. 概览
本报告对 `stock_analyzer` 系统内所有的 LLM Agent 进行归档记录，用于指导后续模型升级（如 Qwen 3.5 替换）和性能调优。

## 2. Agent 架构
系统共包含 5 个独立的 ChatAgent 实例，均基于 Microsoft Agent Framework 封装。

### 2.1 基础任务 Agent (非 Thinking)
这些 Agent 负责快速的文本转换与提取，通常使用性价比更高的 Plus 模型。

*   **query_generator**
    *   模型变量：`MODEL_QUERY_AGENT` (qwen-plus)
    *   参数：`temperature: 0.5`, `json_mode: True`
    *   场景：多轮搜索关键词生成
*   **knowledge_extractor**
    *   模型变量：`MODEL_EXTRACT_AGENT` (qwen-plus)
    *   参数：`temperature: 0.2`, `json_mode: True`
    *   场景：网页摘要提取

### 2.2 深度推理 Agent (Thinking Enabled)
这些 Agent 负责研报生成与投资判定，必须开启 Thinking 以保证决策质量。

*   **report_generator** (Module B)
*   **technical_analyst** (Module C)
*   **chief_analyst** (Module D)
    *   模型变量：`MODEL_REPORT_AGENT` / `MODEL_TECHNICAL_AGENT` / `MODEL_CHIEF_AGENT`
    *   默认模型：`qwen3-max` (推荐升级为 `qwen3.5-plus`)
    *   核心参数：
        *   `extra_body`: `{"enable_thinking": True}`
        *   `response_format`: `{"type": "json_object"}`
        *   `stream`: `True` (由 `llm_helpers` 强制驱动)

## 3. 运行规范
1.  **JSON Mode**: 所有 Agent 必须使用 API 级别的 JSON Mode 结合 Pydantic 校验。
2.  **Streaming**: 开启 Thinking 的 Agent **禁止**使用非流式调用，以防 DashScope 网关超时。
3.  **Fallback**: Module B 和 C 具备 Fallback 机制，当 LLM 失败时会返回低置信度的结构化对象，而非阻塞流程。

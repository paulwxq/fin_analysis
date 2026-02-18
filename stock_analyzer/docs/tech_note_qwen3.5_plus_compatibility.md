# Tech Note: Qwen3.5-Plus Thinking & JSON Mode 兼容性实测结论

**日期**：2026-02-17  
**状态**：已验证 (Verified)  
**涉及模块**：Module B, Module C, Module D

---

## 1. 背景与动机

在之前的版本中，阿里云百炼的 `qwen-plus` 模型存在一个局限：无法同时启用 `enable_thinking`（思维链）和 API 级别的 `json_object`（JSON 模式）。尝试同时传递这两个参数会导致网关返回 400 错误。因此，系统在需要推理能力时必须切换到 `qwen3-max`。

随着 `qwen3.5-plus` 的发布，我们需要确认该新型号是否已解决此兼容性问题，以便在保持高性能推理的同时优化 Token 成本。

## 2. 实验设计

我们在 `stock_analyzer/tests/` 目录下执行了三阶段探测：
1. **基础兼容性探测** (`probe_qwen35_plus.py`)：验证非流式状态下同时传递参数是否报错。
2. **流式字段分离验证** (`probe_qwen35_plus_stream.py`)：验证在 Thinking 模式下，`reasoning_content` 是否与 JSON `content` 物理分离。
3. **MAF 框架集成验证** (`test_qwen35_plus_maf.py`)：验证模型在 Microsoft Agent Framework 封装下，能否通过 `call_agent_with_model` 正常工作并完成 Pydantic 校验。

## 3. 实验结论

实测证明，**`qwen3.5-plus` 已完美支持 Thinking 与 JSON Mode 的共存**。

| 测试维度 | 表现 | 结论 |
| :--- | :--- | :--- |
| **参数共存** | 同时传递 `enable_thinking` 和 `json_object` 无报错 | **完全兼容** |
| **字段分离** | 推理流进入 `reasoning_content`，正文流为纯净 JSON | **行为符合预期** |
| **流式稳定性** | 在流式输出下响应平滑，未出现截断或格式污染 | **高可靠** |
| **框架适配** | MAF `ChatAgent` 配合 Pydantic 校验一次性通过 | **可直接替换** |

## 4. 实施建议

### 4.1 模型升级
鉴于 `qwen3.5-plus` 的兼容性飞跃，建议在 `config.py` 中将 `MODEL_REPORT_AGENT` 或 `MODEL_CHIEF_AGENT` 可选地切换为 `qwen3.5-plus` 以平衡成本与效果。

### 4.2 保持流式调用
虽然兼容性已解决，但开启 Thinking 会显著增加响应延迟。为了规避 DashScope 网关的 600s 超时硬限制，**必须继续坚持 `stream=True` 的调用策略**（已由 `llm_helpers.call_agent_with_model` 封装）。

### 4.3 提示词微调
由于 `qwen3.5-plus` 指令遵循度极高，建议在 JSON Mode 下的 System Prompt 中明确指定所需的英文键名（Keys），以确保 Pydantic 模型校验的成功率。

## 5. 参考脚本
- `stock_analyzer/tests/probe_qwen35_plus.py`
- `stock_analyzer/tests/probe_qwen35_plus_stream.py`
- `stock_analyzer/tests/test_qwen35_plus_maf.py`

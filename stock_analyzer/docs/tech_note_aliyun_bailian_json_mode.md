# Tech Note: 阿里云百炼第三方模型 JSON Mode 兼容性实测结论

**日期**：2026-02-12  
**状态**：已验证 (Verified)  
**涉及模块**：Module B, Module C, Module D

---

## 1. 背景与动机

在 `stock_analyzer` 的开发过程中，我们广泛使用了 Microsoft Agent Framework (MAF) 及其对 `response_format={"type": "json_object"}` 的依赖。

根据阿里云百炼官方 Native 文档，部分第三方模型（如 GLM, Kimi, MiniMax, DeepSeek）可能标注为“不支持结构化输出”。为了验证这些模型在 **OpenAI 兼容端点** (`/compatible-mode/v1`) 下的真实表现，我们进行了一次定向探测实验。

## 2. 实验设计

- **测试环境**：阿里云百炼 OpenAI 兼容接口。
- **测试模型**：`glm-4.7`, `kimi-k2.5`, `MiniMax-M2.1`, `deepseek-v3.2`。
- **测试用例**：
    1. **强制 JSON 参数测试**：调用 API 时携带 `response_format={"type": "json_object"}`，观察网关是否报错及输出是否为合法 JSON。
    2. **自然 JSON 输出测试**：不携带参数，仅在 Prompt 中要求 JSON，观察输出是否包含 Markdown 代码块或杂质。

## 3. 实验结论

实验结果出乎意料，四个主流第三方模型在百炼网关层均表现出极佳的兼容性：

| 模型标识符 | 支持 `json_object` 参数 | 自然输出质量 | 结论 |
| :--- | :---: | :--- | :--- |
| **`glm-4.7`** | **YES** | 完美 Raw JSON | 完全兼容 |
| **`kimi-k2.5`** | **YES** | 完美 Raw JSON | 完全兼容 |
| **`MiniMax-M2.1`** | **YES** | 完美 Raw JSON | 完全兼容 |
| **`deepseek-v3.2`** | **YES** | 完美 Raw JSON | 完全兼容 |

**核心发现**：
阿里云百炼的 OpenAI 兼容网关似乎已经对这些模型做了协议转换或指令注入。即使官方 Native SDK 文档保守标注不支持，但在使用 OpenAI 协议调用时，**它们完全支持结构化输出模式**。

## 4. 对项目的意义与实施建议

### 4.1 维持现有 Agent 配置
目前的 `agents.py` 默认开启了 `response_format={"type": "json_object"}`。基于实测，我们可以放心在该项目中使用上述模型，无需担心因参数不支持导致的 400 报错。

### 4.2 保持“双重解析”逻辑
虽然实测结果理想，但 `stock_analyzer/llm_helpers.py` 中的 `extract_json_str` 仍应保留：
- **理由**：该函数通过正则兼容了 ```json ... ``` 代码块。即便未来网关策略变动或模型偶尔“幻觉”出 Markdown 标签，系统仍能稳定解析出 Pydantic 对象。

### 4.3 配置文件优化
建议在 `.env` 或 `config.py` 中保留模型切换的灵活性。对于 Module D（首席分析师），鉴于其逻辑复杂性（一票否决权等），在全量投喂模式下优先推荐 `qwen-max` 或 `deepseek-v3.2` 级别的高逻辑性能模型。

## 5. 实验代码参考
详见测试文件：`stock_analyzer/tests/test_json_mode_probe.py`。

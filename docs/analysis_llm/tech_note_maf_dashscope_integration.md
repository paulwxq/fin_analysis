# 技术纪要：MAF 与 DashScope (Qwen) 高级特性集成验证

## 1. 测试背景
在使用 Microsoft Agent Framework (MAF) 结合 DashScope (OpenAI 兼容模式) 开发股票推荐系统时，我们需要验证能否开启 Qwen 模型特有的原生功能，如**联网搜索**和**API 级结构化输出 (JSON Mode)**。

## 2. 测试环境
- **框架**: `agent_framework` (python-1.0.0b260130)
- **模型**: `qwen-plus` / `qwen-max`
- **接口**: OpenAI 兼容端点 (`/compatible-mode/v1`)

## 3. 关键发现：传参机制
通过测试发现，MAF 的 `ChatAgent.run()` 方法通过 `options` 参数向下层 Client 传递配置。若要成功透传非 OpenAI 标准的扩展参数，必须遵循以下格式：

```python
# 正确的传参方式
response = await agent.run(
    message=query,
    options={
        "extra_body": {"enable_search": True},      # 开启原生搜索
        "response_format": {"type": "json_object"}  # 强制 JSON 输出
    }
)
```

**错误注意**：直接在 `run()` 中使用 `extra_body=...` 作为关键字参数 (kwargs) 会被 MAF 过滤，导致功能失效。

## 4. 验证结果 (2026-02-04)

### 4.1 原生联网搜索 (Native Search)
- **测试用例**: 询问当前时间点之后的特定地点天气（杭州明天天气）。
- **结果**: **成功**。模型返回了实时天气数据及来源，证明 `enable_search` 参数已生效并成功触发了 DashScope 的实时搜索插件。
- **意义**: 在需要补充最新市场咨询时，可直接开启此功能，无需手动实现 Tavily/Serper 的 Tools 调用（在某些简单场景下）。

### 4.2 结构化输出 (JSON Mode)
- **测试用例**: 要求输出包含特定字段的 JSON。
- **结果**: **成功**。模型返回了纯净的 JSON 字符串，**不带** Markdown 代码块 (` ```json `)。
- **意义**: 极大提升了自动化解析的稳定性，降低了对正则清洗函数 (`extract_json_str`) 的依赖。

## 5. 扩展验证：DeepSeek API 集成 (2026-02-04)

我们同样验证了 MAF 对 DeepSeek API (`deepseek-chat`) 的兼容性，结果如下：

### 5.1 结构化输出 (JSON Mode)
- **参数**: `options={"response_format": {"type": "json_object"}}`
- **结果**: **成功**。模型返回纯净 JSON。
- **关键约束**: DeepSeek 强制要求 Prompt 中必须包含 **"json"** 关键词，否则 API 会直接返回 `400 Bad Request`。这与 DashScope 的宽容策略不同，开发时需严格遵守。

### 5.2 思考模式 (Thinking)
- **测试模型**: `deepseek-chat` (V3)
- **结果**: 默认**不输出** `<think>` 标签。若需思维链，可能需切换至 `deepseek-reasoner` (R1) 或特定参数。

## 6. 项目后续应用建议

### 6.1 Step 2 (Hold Recommendation)
- **推荐策略**: 在 `ScoreAgent` 和 `ReviewAgent` 中全面启用 `response_format: {"type": "json_object"}`。
- **收益**: 确保 Step 2 最终输出结果的高可靠性，减少因格式错误导致的重试。

### 5.2 搜索策略选择
- **多维度深度搜索**: 建议继续使用 Step 1 中实现的 `web_search` 工具（对接 Tavily/Serper），因为手动 Tool 控制能提供更精准的关键词降级和结果筛选。
- **实时事实核录**: 在 Review 阶段，若需要对某个特定事实进行快速核录，可开启 `enable_search` 简化开发。

---
*文档版本：v1.0*  
*记录人：Gemini CLI Agent*

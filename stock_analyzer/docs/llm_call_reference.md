# LLM 调用参考表

项目中所有 LLM 调用的汇总，便于快速查阅各 agent 的模型配置、参数和调用位置。

## 调用总表

| # | Agent 名 | 创建函数 | 创建位置 | 调用函数 | 调用位置 | 配置变量 | 默认模型 | temperature | response_format | Stream | Thinking |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `query_generator` | `create_query_agent()` | `agents.py:15` | `generate_serp_queries()` | `deep_research.py:37` | `MODEL_QUERY_AGENT` | `qwen3.5-plus` | 0.5 | json_object | 否 | 否 |
| 2 | `knowledge_extractor` | `create_extract_agent()` | `agents.py:28` | `process_serp_result()` | `deep_research.py:77` | `MODEL_EXTRACT_AGENT` | `qwen3.5-plus` | 0.2 | json_object | 否 | 否 |
| 3 | `report_generator` | `create_report_agent()` | `agents.py:40` | `generate_report()` | `deep_research.py:249` | `MODEL_REPORT_AGENT` | `qwen3.5-plus` | 0.3 | json_object | 是 (`REPORT_USE_STREAM`) | 是 |
| 4 | `technical_analyst` | `create_technical_agent()` | `agents.py:55` | `run_technical_analysis()` | `module_c_technical.py:699` | `MODEL_TECHNICAL_AGENT` | `qwen3.5-plus` | 0.2 | json_object | 是 (`TECH_USE_STREAM`) | 是 |
| 5 | `chief_analyst` | `create_chief_agent()` | `agents.py:69` | `run_chief_analysis()` | `module_d_chief.py:312` | `MODEL_CHIEF_AGENT` | `qwen3.5-plus` | 0.2 | json_object | 是 (`CHIEF_USE_STREAM`) | 是 |

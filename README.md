# fin_analysis
这是一个面向中国 股票的简单的量化分析平台，包含数据加载、选股与多阶段 LLM 分析等模块。将 A 股 1 分钟 K 线从 zip 文件批量加载到 TimescaleDB；选股层：实现“平底锅”形态筛选（SQL 粗筛 + Python 趋势精细筛选）。通过多 Agent（agent-framework）并行做 K 线、新闻、板块分析，并接入 Qwen 大模型对 K 线图表做视觉评分，最终给出买入/持有建议。

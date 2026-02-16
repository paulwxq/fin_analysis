# fin_analysis

面向 A 股的量化分析与多阶段 LLM 分析项目，覆盖：
- 1 分钟行情入库（PostgreSQL/TimescaleDB）
- 平底锅形态筛选（SQL + Python）
- K 线可视化输出
- 基于图像与多源信息的 LLM 评分/决策

## 模块说明

### 1) `load_data`
- 作用：导入 1 分钟前复权数据、初始化表结构、维护加载日志、聚合月线。
- 主要数据表：`stock_1min_qfq`、`load_log`、`stock_monthly_kline`。
- 技术栈：`psycopg`、PostgreSQL、TimescaleDB（hypertable、continuous aggregate）。

### 2) `selection`
- 作用：平底锅预筛选（SQL 粗筛 + Python 精筛），结果写入预选表。
- 主要输出表：`stock_flatbottom_preselect`。
- 技术栈：`pandas`、`numpy`、`scipy`、PostgreSQL。
- 与 `load_data` 关系：代码层直接依赖 `load_data.db` 和 `load_data.stock_code`。

### 3) `visualization`
- 作用：读取月线数据绘制 K 线图，输出 `output/{code}_kline.png`。
- 可从 `stock_flatbottom_preselect` 批量读取代码，也可直接传入代码/文件。
- 技术栈：`pandas`、`mplfinance`、PostgreSQL。
- 与 `load_data` 关系：代码层直接依赖 `load_data.db` 和 `load_data.stock_code`。

### 4) `refinement_llm`
- 作用：批量读取 K 线图片做视觉打分，写入细化结果表。
- 主要输入：默认 `./output/*_kline.png`。
- 主要输出表：`public.stock_flatbottom_refinement`。
- 技术栈：`agent-framework`、OpenAI 兼容客户端、`tenacity`、`psycopg`。

### 5) `analysis_llm`
- 作用：两阶段多 Agent 分析。
- Step1：并发执行 新闻/板块/K线 三个 Agent（含 Checker 重试机制），输出结构化 `Step1Output`。
- Step2：`ScoreAgent` + `ReviewAgent` 在 Manager 调度下做闭环评审，输出持有评分与理由。
- 主要输入：`output/{code}_kline.png`（K 线图）+ 搜索数据（Tavily/Serper）。
- 技术栈：`agent-framework`、`openai`（兼容 DashScope/DeepSeek）、`pydantic`、`httpx`。
- 注意：`analysis_llm` 不会调用 `refinement_llm`，两者是独立流程。

### 6) `stock_analyzer`
- 作用：A/B/C/D 全流程投研编排（从股票代码到最终投研结论）。
- A/B/C/D 模块定义：
  - Module A（`module_a_akshare.py`）：AKShare 结构化数据采集。采集公司信息、财务指标、估值、资金流等多主题数据，输出 `AKShareData`。
  - Module B（`module_b_websearch.py`）：Web 深度研究。围绕新闻、竞争力、行业前景、风险、券商观点等主题做检索与归纳，输出 `WebResearchResult`。
  - Module C（`module_c_technical.py`）：技术分析。拉取月线数据并计算指标（MA/MACD/RSI/KDJ/BOLL），结合 LLM 形成技术面结论，输出 `TechnicalAnalysisResult`。
  - Module D（`module_d_chief.py`）：首席综合决策。汇总 A/B/C 结果，执行业务规则校验，输出最终报告 `FinalReport`。
- 典型中间产物（`output/`）：
  - `{symbol}_akshare_data.json`
  - `{symbol}_web_research.json`
  - `{symbol}_technical_analysis.json`
  - `{symbol}_final_report.json`
- 技术栈：`akshare`、`pandas`、`pandas-ta`、`agent-framework`、`openai`、`tavily`、`pydantic`。

### 7) `qwen3`
- 作用：Qwen 客户端封装层（文本、视觉、deep-research）。
- 技术栈：`dashscope`、`agent-framework`。

### 8) `tests`
- 作用：项目级单元测试与集成测试。
- 技术栈：`pytest`、`pytest-asyncio`。

## 依赖关系（代码层）

当前核心跨模块导入关系：
- `selection` -> `load_data`
- `visualization` -> `load_data`

其他核心模块（`refinement_llm`、`analysis_llm`、`stock_analyzer`、`qwen3`）在代码层相对独立。

## 运行链路（数据流层）

### 链路 A：筛选 + 图像细化评分（典型）
1. `load_data`：分钟数据入库并聚合月线  
2. `selection`：生成 `stock_flatbottom_preselect`  
3. `visualization`：输出 `output/*_kline.png`  
4. `refinement_llm`：读取图片并写入 `stock_flatbottom_refinement`

### 链路 B：多 Agent 综合评分（独立于 refinement）
1. 准备 `output/{code}_kline.png`（可由 `visualization` 生成）  
2. `analysis_llm` Step1：新闻/板块/K线并发分析  
3. `analysis_llm` Step2：评分与审核闭环，输出最终持有建议

### 链路 C：全流程投研（独立主线）
1. 输入：股票代码（支持 `600519` / `600519.SH` / `SH600519`）。  
2. 工作流先查询股票基础信息（名称、行业）。  
3. 并行运行 Module A/B/C：
   - A：结构化基本面与市场数据采集
   - B：网络研究与舆情归纳
   - C：技术指标计算与技术面解读
4. 执行熔断检查：若 A/B/C 任一模块失败，则中止并报错（避免带病进入综合结论）。
5. A/B/C 通过后，执行 Module D：
   - 合并三路结果
   - 进行规则校验与可信度约束
   - 生成最终投资建议报告
6. 输出：`output/{symbol}_final_report.json`（可选保留 A/B/C 中间 JSON 以便复盘）。

#### 链路 C 运行方式
- 全流程一条命令：
  - `.venv/bin/python3 stock_analyzer/run_workflow.py <symbol>`
- 单模块调试：
  - A：`.venv/bin/python3 stock_analyzer/run_module_a.py <symbol> <name>`
  - B：`.venv/bin/python3 stock_analyzer/run_module_b.py <symbol> <name> <industry>`
  - C：`.venv/bin/python3 stock_analyzer/run_module_c.py <symbol> <name>`
  - D：`.venv/bin/python3 stock_analyzer/run_module_d.py <symbol> <name> <akshare_json> <web_json> <technical_json>`

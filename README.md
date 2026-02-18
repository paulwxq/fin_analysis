# fin_analysis

面向 A 股的量化分析与多阶段 LLM 分析项目，覆盖：
- 1 分钟行情入库（PostgreSQL/TimescaleDB）
- 平底锅形态筛选（SQL + Python）
- K 线可视化输出
- 基于图像与多源信息的 LLM 评分/决策

## 项目结构

```
fin_analysis/
├── data_infra/                      # 数据基础设施（入库、聚合、压缩）
├── flatbottom_pipeline/            # 平底锅筛选流水线
│   ├── run_pipeline.py             #   统一编排入口
│   ├── selection/                  #   规则筛选
│   ├── visualization/              #   K 线图生成
│   ├── refinement_llm/             #   LLM 视觉评分
│   └── tests/                      #   流水线测试
├── analysis_llm/                   # 多 Agent 综合评分（独立链路）
├── stock_analyzer/                 # 全流程投研（独立链路）
├── qwen3/                          # Qwen 客户端封装层
├── tests/                          # data_infra 及其他模块测试
└── output/                         # 共享输出目录
```

## 模块说明

### 1) `data_infra`（数据基础设施）
- 作用：项目公共数据基础设施层，涵盖数据入库、聚合加工、存储压缩及公共工具。
  - **入库**：导入 1 分钟前复权数据，初始化表结构，维护加载日志（`main.py`、`loader.py`）。
  - **聚合**：基于 TimescaleDB 持续聚合生成月线视图（`aggregate.py`）。
  - **压缩**：TimescaleDB chunk 手动压缩（`compress_manual.py`）。
  - **公共工具**：数据库连接池（`db.py`）、A 股代码标准化（`stock_code.py`）。
- 主要数据表：`stock_1min_qfq`、`load_log`、`stock_monthly_kline`。
- 技术栈：`psycopg`、PostgreSQL、TimescaleDB（hypertable、continuous aggregate）。

### 2) `flatbottom_pipeline`
平底锅筛选流水线，包含 3 个子模块：

- **`selection`**：平底锅预筛选（SQL 粗筛 + Python 精筛），结果写入 `stock_flatbottom_preselect`。
- **`visualization`**：读取月线数据绘制 K 线图，输出 `output/{code}_kline.png`。
- **`refinement_llm`**：批量读取 K 线图片做视觉打分，写入 `stock_flatbottom_refinement`。
- **`run_pipeline.py`**：统一编排入口，支持按阶段执行和前置条件检查。

`selection` 和 `visualization` 依赖 `data_infra.db` 和 `data_infra.stock_code`（公共数据基础设施）。
`refinement_llm` 完全自包含，无外部模块依赖。

### 3) `analysis_llm`
- 作用：两阶段多 Agent 分析。
- Step1：并发执行 新闻/板块/K线 三个 Agent（含 Checker 重试机制），输出结构化 `Step1Output`。
- Step2：`ScoreAgent` + `ReviewAgent` 在 Manager 调度下做闭环评审，输出持有评分与理由。
- 主要输入：`output/{code}_kline.png`（K 线图）+ 搜索数据（Tavily/Serper）。
- 技术栈：`agent-framework`、`openai`（兼容 DashScope/DeepSeek）、`pydantic`、`httpx`。
- 注意：`analysis_llm` 不会调用 `refinement_llm`，两者是独立流程。

### 4) `stock_analyzer`
- 作用：A/B/C/D 全流程投研编排（从股票代码到最终投研结论）。
- A/B/C/D 模块定义：
  - Module A（`module_a_akshare.py`）：AKShare 结构化数据采集。
  - Module B（`module_b_websearch.py`）：Web 深度研究。
  - Module C（`module_c_technical.py`）：技术分析。
  - Module D（`module_d_chief.py`）：首席综合决策。
- 技术栈：`akshare`、`pandas`、`pandas-ta`、`agent-framework`、`openai`、`tavily`、`pydantic`。

### 5) `qwen3`
- 作用：Qwen 客户端封装层（文本、视觉、deep-research）。
- 技术栈：`dashscope`、`agent-framework`。

## 依赖关系（代码层）

```
flatbottom_pipeline.selection ──→ data_infra.db, data_infra.stock_code
flatbottom_pipeline.visualization ──→ data_infra.db, data_infra.stock_code
flatbottom_pipeline.refinement_llm ──→ （无外部模块依赖）
analysis_llm / stock_analyzer / qwen3 ──→ （各自独立）
```

## 运行链路（数据流层）

### 链路 A：筛选 + 图像细化评分（典型）

```bash
# 前置：数据入库并聚合月线
python -m data_infra.main
python -m data_infra.aggregate

# 一键运行完整流水线
python -m flatbottom_pipeline.run_pipeline --step all

# 或分步执行
python -m flatbottom_pipeline.run_pipeline --step select   # → stock_flatbottom_preselect
python -m flatbottom_pipeline.run_pipeline --step plot     # → output/*_kline.png
python -m flatbottom_pipeline.run_pipeline --step refine   # → stock_flatbottom_refinement
```

### 链路 B：多 Agent 综合评分（独立于 refinement）
1. 准备 `output/{code}_kline.png`（可由 `visualization` 生成）
2. `analysis_llm` Step1：新闻/板块/K线并发分析
3. `analysis_llm` Step2：评分与审核闭环，输出最终持有建议

### 链路 C：全流程投研（独立主线）

```bash
# 全流程一条命令
.venv/bin/python3 stock_analyzer/run_workflow.py <symbol>
```

1. 并行运行 Module A/B/C（结构化数据 + 网络研究 + 技术分析）
2. 熔断检查：若 A/B/C 任一模块失败则中止
3. Module D：合并三路结果，生成最终投资建议报告
4. 输出：`output/{symbol}_final_report.json`

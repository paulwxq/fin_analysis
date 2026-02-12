# Module A/B/C/D 运行手册（简版）

## 1. 前置准备

- 在项目根目录执行命令：`/opt/fin_analysis`
- 建议使用虚拟环境：`.venv`
- 配置文件位置：`stock_analyzer/config.py`
- 环境变量加载：`python-dotenv`，会自动读取项目根目录 `.env`
- 日志文件默认路径：`logs/stock_analyzer.log`

关键环境变量（建议放 `.env`）：

- `DASHSCOPE_API_KEY`：模块 B/C 的 LLM 调用必需
- `TAVILY_API_KEY`：模块 B 的联网搜索必需
- `DASHSCOPE_BASE_URL`：默认已配置，可不改

LLM 参数与模块对应关系（`stock_analyzer/config.py`）：

- Module A：无 LLM（纯 AKShare 数据采集）
- Module B：
  - `MODEL_QUERY_AGENT`
  - `MODEL_EXTRACT_AGENT`
  - `MODEL_REPORT_AGENT`
- Module C：
  - `MODEL_TECHNICAL_AGENT`
- Module D：
  - `MODEL_CHIEF_AGENT`

## 2. 运行 Module A（AKShare 数据采集）

命令：

```bash
.venv/bin/python stock_analyzer/run_module_a.py <symbol> <name>
```

示例：

```bash
.venv/bin/python stock_analyzer/run_module_a.py 600519.SH 贵州茅台
```

参数：

- `symbol`：股票代码，支持 `600519` / `600519.SH` / `SH600519`
- `name`：股票名称

输出文件：

- `output/{normalized_symbol}_akshare_data.json`
- 例如：`output/600519_akshare_data.json`

Module A 重点配置（`stock_analyzer/config.py`）：

- `AKSHARE_CALL_INTERVAL`
- `AKSHARE_CALL_TIMEOUT`
- `AKSHARE_TIMEOUT_RETRIES`
- `AKSHARE_FINANCIAL_PERIODS`
- `AKSHARE_FUND_FLOW_DAYS`

## 3. 运行 Module B（Web Deep Research）

命令：

```bash
.venv/bin/python stock_analyzer/run_module_b.py <symbol> <name> <industry>
```

示例：

```bash
.venv/bin/python stock_analyzer/run_module_b.py 600519.SH 贵州茅台 白酒
```

参数：

- `symbol`：股票代码（建议直接传 `600519.SH`，便于识别）
- `name`：股票名称
- `industry`：行业名（如 `白酒`）

输出文件：

- `output/{symbol}_web_research.json`
- 例如：`output/600519.SH_web_research.json`

Module B 重点配置（`stock_analyzer/config.py`）：

- `MODEL_QUERY_AGENT`
- `MODEL_EXTRACT_AGENT`
- `MODEL_REPORT_AGENT`
- `DEFAULT_BREADTH`
- `DEFAULT_DEPTH`
- `TOPIC_CONCURRENCY_LIMIT`
- `TAVILY_MAX_RESULTS`
- `TAVILY_TIMEOUT`

## 4. 运行 Module C（月线技术分析）

命令：

```bash
.venv/bin/python stock_analyzer/run_module_c.py <symbol> <name>
```

示例：

```bash
.venv/bin/python stock_analyzer/run_module_c.py 600519.SH 贵州茅台
```

参数：

- `symbol`：股票代码，支持 `600519` / `600519.SH` / `SH600519`
- `name`：股票名称

输出文件：

- `output/{normalized_symbol}_technical_analysis.json`
- 例如：`output/600519_technical_analysis.json`

Module C 重点配置（`stock_analyzer/config.py`）：

- `MODEL_TECHNICAL_AGENT`
- `TECH_START_DATE`
- `TECH_ADJUST`
- `TECH_AGENT_LOOKBACK_MONTHS`
- `TECH_MIN_MONTHS`
- `TECH_LONG_TREND_MIN_MONTHS`
- `TECH_MA_SHORT` / `TECH_MA_MID` / `TECH_MA_LONG` / `TECH_MA_TREND`
- `TECH_RSI_LENGTH` / `TECH_BOLL_LENGTH` / `TECH_KDJ_K` / `TECH_KDJ_D` / `TECH_KDJ_SMOOTH`

## 5. 运行 Module D（最终综合分析）

命令：

```bash
.venv/bin/python stock_analyzer/run_module_d.py \
  <symbol> <name> <akshare_json_path> <web_json_path> <technical_json_path>
```

示例：

```bash
.venv/bin/python stock_analyzer/run_module_d.py \
  600519.SH 贵州茅台 \
  output/600519_akshare_data.json \
  output/600519.SH_web_research.json \
  output/600519_technical_analysis.json
```

参数：

- `symbol`：股票代码，支持 `600519` / `600519.SH` / `SH600519`
- `name`：股票名称
- `akshare_json_path`：模块 A 输出文件路径
- `web_json_path`：模块 B 输出文件路径
- `technical_json_path`：模块 C 输出文件路径

输出文件：

- `output/{normalized_symbol}_final_report.json`
- 例如：`output/600519_final_report.json`

Module D 重点配置（`stock_analyzer/config.py`）：

- `MODEL_CHIEF_AGENT`
- `CHIEF_INPUT_MAX_CHARS_TOTAL`
- `CHIEF_OUTPUT_RETRIES`

## 6. 推荐执行顺序

```bash
.venv/bin/python stock_analyzer/run_module_a.py 600519.SH 贵州茅台
.venv/bin/python stock_analyzer/run_module_b.py 600519.SH 贵州茅台 白酒
.venv/bin/python stock_analyzer/run_module_c.py 600519.SH 贵州茅台
.venv/bin/python stock_analyzer/run_module_d.py \
  600519.SH 贵州茅台 \
  output/600519_akshare_data.json \
  output/600519.SH_web_research.json \
  output/600519_technical_analysis.json
```

说明：

- A/C 输出文件名会归一化为 `600519_*`
- B 输出文件名保留传入 symbol（如 `600519.SH_*`）

# 股票推荐系统 Step 1 详细设计文档

## 文档版本信息

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| v1.1 | 2026-02-02 | Gemini | 将确认细节缝合至各章节；完善日志、搜索与图片规则 |

## 1. 设计概述

本阶段主要实现股票数据的并行收集与清洗。系统利用 Microsoft Agent Framework (MAF) 的并发能力，结合 Pydantic 进行严格的数据结构验证，并引入 Tavily 搜索工具增强数据获取能力。

### 1.1 关键技术选型
*   **开发语言**: Python 3.12+
*   **Agent 框架**: Microsoft Agent Framework (python-1.0.0b260130)
*   **模型服务**: 阿里云 DashScope (通过自定义 `qwen3` 模块调用)
*   **数据验证**: Pydantic V2
*   **搜索引擎**: Tavily API
*   **日志系统**: Python标准 `logging` (Console + File 双输出)

### 1.2 目录结构
代码将位于 `analysis_llm/` 目录下（扁平化结构，不创建子目录）：

```text
analysis_llm/
├── config.py           # 配置定义 (模型名称, 重试次数, 路径等)
├── models.py           # Pydantic 数据模型 (输入/输出/校验Schema)
├── prompts.py          # 所有 Agent 的 System Prompt 模板
├── tools.py            # Tavily 搜索工具封装
├── utils.py            # 通用工具 (图片加载, 日志初始化, JSON清洗)
├── merger.py           # 数据合并逻辑 (SimpleMerger)
├── agents.py           # Agent 与 Checker 的具体实现 (含 Pydantic 校验逻辑)
├── workflow.py         # ConcurrentBuilder 编排与执行入口
└── main.py             # 调试/启动脚本
```

---

## 2. 数据模型设计 (models.py)

使用 Pydantic 定义严格的 JSON Schema。

### 2.1 基础枚举与类型
```python
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal

class TrendEnum(str, Enum):
    UP = "上升"
    DOWN = "下降"
    OSCILLATE = "震荡"

class BuySuggestionEnum(str, Enum):
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    HOLD = "持有"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"
```

### 2.2 单元数据模型

#### 2.2.1 新闻数据 (NewsData)
```python
from typing import Annotated
from . import config  # 引入配置模块

class NewsData(BaseModel):
    data_type: Literal["news"] = Field(..., description="数据类型标识")
    stock_code: str
    stock_name: str = Field(..., description="股票名称")
    # 使用 Annotated 明确列表项数限制，并关联配置项
    # 注意: 在 Pydantic V2 中，List 类型的 max_length 参数表示列表的最大项数
    positive_news: Annotated[List[str], Field(..., max_length=config.NEWS_LIMIT_POS, description=f"正面新闻列表 (最多{config.NEWS_LIMIT_POS}项)")]
    negative_news: Annotated[List[str], Field(..., max_length=config.NEWS_LIMIT_NEG, description=f"负面新闻列表 (最多{config.NEWS_LIMIT_NEG}项)")]
    news_summary: str = Field(..., description="综合摘要")
    sentiment_score: float = Field(..., ge=-1.0, le=1.0, description="情绪得分 -1~1")

    @field_validator('positive_news', 'negative_news')
    def check_item_content_length(cls, v):
        limit = config.NEWS_ITEM_MAX_CHARS
        for news in v:
            if len(news) > limit:
                raise ValueError(f"单条新闻摘要长度超过{limit}字符")
        return v
```

#### 2.2.2 板块数据 (SectorData)
```python
class SectorData(BaseModel):
    data_type: Literal["sector"] = Field(..., description="数据类型标识")
    stock_code: str
    stock_name: str = Field(..., description="股票名称")
    sector_name: str = Field(..., description="板块名称")
    heat_index: float = Field(..., ge=0, le=100, description="热度指数 0-100")
    trend: TrendEnum = Field(..., description="趋势方向")
    capital_flow: str = Field(..., description="资金流向描述")
```

#### 2.2.3 K线数据 (KLineData)
```python
class TechnicalIndicators(BaseModel):
    MACD: float = Field(..., description="MACD指标值")
    RSI: float = Field(..., description="RSI指标值")
    KDJ_K: float = Field(..., description="KDJ_K指标值")

class KLineData(BaseModel):
    data_type: Literal["kline"] = Field(..., description="数据类型标识")
    stock_code: str
    technical_indicators: TechnicalIndicators = Field(..., description="技术指标集合")
    support_level: float = Field(..., description="支撑位价格")
    resistance_level: float = Field(..., description="阻力位价格")
    trend_analysis: str = Field(..., description="趋势分析文本")
    buy_suggestion: BuySuggestionEnum = Field(..., description="买入建议枚举")
```

#### 2.2.4 汇总输出 (Step1Output)
```python
class Step1Output(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 格式的时间戳 (UTC)")
    news: NewsData = Field(..., description="新闻收集单元结果")
    sector: SectorData = Field(..., description="板块分析单元结果")
    kline: KLineData = Field(..., description="K线分析单元结果")
```

---

## 3. 配置管理 (config.py)

模型名称与运行阈值记录在此。`.env` 仅存储 `DASHSCOPE_API_KEY` 和 `TAVILY_API_KEY`。

```python
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# 模型配置
MODEL_NEWS_AGENT = "qwen-plus"
MODEL_SECTOR_AGENT = "qwen-plus"
MODEL_KLINE_AGENT = "qwen-vl-max"

# Checker 模型 (混合校验模式)
MODEL_CHECKER_NEWS = "qwen-plus"
MODEL_CHECKER_SECTOR = "qwen-plus"
MODEL_CHECKER_KLINE = "qwen-plus"

# 业务约束配置
MAX_RETRIES = 3
NEWS_LIMIT_POS = 5            # 正面新闻最大条数
NEWS_LIMIT_NEG = 5            # 负面新闻最大条数
NEWS_ITEM_MAX_CHARS = 500     # 每条新闻摘要最大字符数

# 路径配置
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "analysis_llm.log")
IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")

# 日志配置
LOG_LEVEL_CONSOLE = logging.INFO
LOG_LEVEL_FILE = logging.DEBUG
```

---

## 4. Prompt 模板 (prompts.py)

### 4.1 News Agent
```python
NEWS_AGENT_SYSTEM = """你是一名专业的金融新闻分析师。
你的任务是利用搜索工具查询股票 {stock_code} 在过去12个月内的重要新闻。
你需要调用 Tavily 搜索工具获取信息。

输出必须严格遵守以下 JSON 格式：
{{
    "data_type": "news",
    "stock_code": "{stock_code}",
    "positive_news": ["摘要1", "摘要2"],
    "negative_news": ["摘要1", "摘要2"],
    "news_summary": "综合分析摘要...",
    "sentiment_score": 0.5
}}

约束要求：
1. 每条新闻必须是摘要形式，长度严格控制在 {max_chars} 字符以内。
2. 正面新闻列表最多包含 {limit_pos} 条最重要记录，负面新闻列表最多包含 {limit_neg} 条最重要记录。
3. 如果搜索结果不足，按实际数量返回。
"""
```

### 4.2 Sector Agent
```python
SECTOR_AGENT_SYSTEM = """你是一名资深的A股板块分析师。
请利用搜索工具分析股票 {stock_code} 所属的板块，以及该板块当前的热度和资金流向。

输出必须严格遵守以下 JSON 格式：
{{
    "data_type": "sector",
    "stock_code": "{stock_code}",
    "sector_name": "板块名称",
    "heat_index": 75.0,
    "trend": "上升",
    "capital_flow": "资金流向描述..."
}}

约束要求：
1. 'trend' 只能是以下值之一：上升, 下降, 震荡。
2. 'heat_index' 必须是 0 到 100 之间的数值。
"""
```

### 4.3 KLine Agent
```python
KLINE_AGENT_SYSTEM = """你是一名技术分析专家。
我将提供一张股票 {stock_code} 的 **月K线图**。请基于图片进行分析。

输出必须严格遵守以下 JSON 格式：
{{
    "data_type": "kline",
    "stock_code": "{stock_code}",
    "technical_indicators": {{
        "MACD": 0.0,
        "RSI": 0.0,
        "KDJ_K": 0.0
    }},
    "support_level": 0.0,
    "resistance_level": 0.0,
    "trend_analysis": "...",
    "buy_suggestion": "持有"
}}

约束要求：
1. 'buy_suggestion' 必须且只能是以下值之一：强烈买入, 买入, 持有, 卖出, 强烈卖出。
2. 你必须确认分析的是月线数据。
"""
```

### 4.4 Checkers System Prompts
虽然 Pydantic 负责结构校验，但 LLM Checker 用于对 Agent 输出进行逻辑规格复核。

```python
CHECKER_SYSTEM = """你是一名严格的数据规格质检员。
你需要检查输入的数据是否符合以下逻辑规格要求：
1. 必需字段是否存在且非空。
2. 股票代码 (stock_code) 是否与输入完全一致。
3. 枚举值 (trend, buy_suggestion) 是否在限定的中文范围内。
4. data_type 是否为合法值（news/sector/kline）。
5. 数值是否在预定义的业务区间内。

输出必须严格遵守以下 JSON 格式（注意：不要返回 Markdown 代码块，仅返回纯 JSON）。其中 `passed` 为布尔值，只能是 true 或 false：
{
    "passed": true,
    "reason": "如果失败，请提供具体的修改建议"
}

注意：你只负责规格和格式质量，不判断业务逻辑的对错。
"""
```

---

## 5. 执行单元实现细节 (agents.py)

### 5.1 KLineAnalysisUnit 的图片处理
*   **命名规则**：严格匹配 `output/{stock_code}_kline.png`（由 `config.IMAGE_DIR` 定义）。
*   **预检查逻辑**：
    1. 在 `run` 方法开始时，拼接路径并调用 `os.path.exists()`。
    2. 如果文件不存在，立即记录 ERROR 日志并抛出 `FileNotFoundError`。
    3. 严禁在没有图片的情况下调用视觉模型。

### 5.2 统一校验流程 (混合模式)
每个 Unit 内部执行：
1. **Agent 生成**：调用 LLM 获取结果（返回值为 `ChatResponse` 对象，其 `text` 为原始字符串）。
2. **JSON 提取与清洗**：调用 `utils.extract_json_str()` 从原始字符串中提取 JSON 块，并过滤掉 Markdown 标签或多余字符。
3. **Pydantic 校验**：
    *   将清洗后的 JSON 字符串传入 `pydantic_model.model_validate_json()`。
    *   如果不通过，捕获 `ValidationError`，并将错误详情转化为自然语言反馈给 Agent 进行 Retry。
4. **LLM Checker 校验**：
    *   Pydantic 通过后，构造包含 **上下文约束** 的 User Prompt，例如：
        `期望股票代码: {stock_code}\n待校验数据: {json_data}`
    *   将此 Prompt 发送给 Checker 进行规格复核。Checker 必须返回包含 `passed` 和 `reason` 的 JSON，且 `passed` 必须为布尔值（true/false）。

---

## 6. 工具层实现 (tools.py)

```python
from tavily import TavilyClient
import os

def search_market_news(query: str) -> str:
    """封装 Tavily API 搜索市场新闻"""
    api_key = os.getenv("TAVILY_API_KEY")
    client = TavilyClient(api_key=api_key)
    # 默认搜索深度 advanced 确保质量
    response = client.search(query, search_depth="advanced", max_results=10)
    return str(response)
```

---

## 7. 通用工具与日志设计 (utils.py)

### 7.1 日志初始化规范
模块 `analysis_llm` 的日志将同时发送到两个 Handler：
*   **Console Handler**: 设置级别为 `config.LOG_LEVEL_CONSOLE` (INFO)。输出简洁的任务状态。
*   **File Handler**: 设置级别为 `config.LOG_LEVEL_FILE` (DEBUG)。输出详细的交互 Payload 和异常堆栈。
*   **文件位置**: `./logs/analysis_llm.log`。

### 7.2 JSON 处理与清洗 (extract_json_str)
由于 Agent 返回的文本可能包含 Markdown 代码块（如 ` ```json ... ``` `）或冗余解释，`utils.py` 必须提供以下工具函数：
*   **函数名**: `extract_json_str(raw_text: str) -> str`
*   **功能**: 利用正则提取首个 JSON 块，移除 Markdown 标记，返回纯净的 JSON 字符串供 Pydantic 解析。

---

## 8. 数据合并器实现 (merger.py)
用于将三个 Agent 返回的离散数据合并为最终的结构化输出。

```python
import json
from typing import List
from datetime import datetime, timezone
from agent_framework import ChatMessage
from . import utils
from .models import Step1Output, NewsData, SectorData, KLineData

class SimpleMerger:
    @staticmethod
    def merge(results: List[ChatMessage]) -> Step1Output:
        """
        解析并发执行的结果列表，合并为 Step1Output 对象。
        识别逻辑：遍历结果，利用 Pydantic 尝试解析，根据特有字段识别归属。
        """
        news_data = None
        sector_data = None
        kline_data = None

        parsing_errors = []
        for msg in results:
            json_str = utils.extract_json_str(msg.text)
            try:
                payload = json.loads(json_str)
            except Exception as e:
                parsing_errors.append(f"JSON解析失败: {e}")
                continue

            data_type = payload.get("data_type")
            try:
                if data_type == "news":
                    news_data = NewsData.model_validate(payload)
                elif data_type == "sector":
                    sector_data = SectorData.model_validate(payload)
                elif data_type == "kline":
                    kline_data = KLineData.model_validate(payload)
                else:
                    parsing_errors.append(f"未知 data_type: {data_type}")
            except Exception as e:
                parsing_errors.append(f"{data_type} 校验失败: {e}")

        # 5. 完整性检查 (严格模式)
        if not all([news_data, sector_data, kline_data]):
            missing = []
            if not news_data: missing.append("NewsData")
            if not sector_data: missing.append("SectorData")
            if not kline_data: missing.append("KLineData")
            
            # 汇总错误原因，辅助排障
            detail_msg = "\n".join(parsing_errors)
            error_msg = f"Step 1 合并失败，缺失: {', '.join(missing)}\n解析详情:\n{detail_msg}"
            raise RuntimeError(error_msg)

        # 构造最终输出，自动打上 UTC 时间戳
        return Step1Output(
            timestamp=datetime.now(timezone.utc).isoformat(),
            news=news_data,
            sector=sector_data,
            kline=kline_data
        )
```

---

## 9. 流程编排与合并 (workflow.py)

严格遵循概要设计，使用 MAF 的 `ConcurrentBuilder` 进行并行编排。

### 9.1 单元适配 (Unit as Agent)
为了利用 `ConcurrentBuilder`，`DataCollectionUnit` 需表现为 MAF 的参与者 (Participant/Agent)。
*   **实现方式**：`DataCollectionUnit` 将继承或包装一个 `ChatAgent`。
*   **执行逻辑**：`ConcurrentBuilder` 广播任务时，三个 Unit 同时接收到 `stock_code`。
*   **内部闭环**：每个 Unit 内部独立完成 "Agent -> Checker -> Retry" 的循环，最终返回结构化数据。

### 9.2 编排逻辑
```python
from agent_framework import ConcurrentBuilder
from .agents import NewsSearchUnit, SectorAnalysisUnit, KLineAnalysisUnit
from .merger import SimpleMerger

async def execute_step1(stock_code: str):
    # 1. 初始化适配为 Agent 的三个 Unit
    news_unit = NewsSearchUnit()
    sector_unit = SectorAnalysisUnit()
    kline_unit = KLineAnalysisUnit()

    # 2. 使用 ConcurrentBuilder 构建并行工作流
    workflow = (
        ConcurrentBuilder()
        .participants([news_unit, sector_unit, kline_unit])
        .build()
    )

    # 3. 执行工作流
    # 广播 stock_code，三个 Unit 并行处理
    results = await workflow.run(stock_code)

    # 4. 数据合并
    # 调用 SimpleMerger 的静态方法进行合并
    return SimpleMerger.merge(results)
```

### 9.3 错误屏障
*   **严格模式**：`ConcurrentBuilder` 运行过程中，如果任一 Unit 抛出未捕获异常（如重试耗尽），Workflow 应捕获并根据策略终止，避免输出不完整数据。

---

## 10. 数据接口规范 (Output JSON Specification)

Step 1 最终输出一个标准的 JSON 对象，该对象通过 Pydantic 校验，确保所有必填字段的存在性和类型的正确性。

### 10.1 完整示例
```json
{
  "timestamp": "2026-02-02T10:30:00.123456+00:00",
  "news": {
    "data_type": "news",
    "stock_code": "603080.SH",
    "stock_name": "新疆火炬",
    "positive_news": [
      "2025-Q3营收增长15%，净利润超预期；具体数值为..."
    ],
    "negative_news": [
      "部分原材料价格上涨导致毛利微降，影响了..."
    ],
    "news_summary": "深度分析摘要（300-800字），涵盖基本面变化、市场情绪及潜在治理风险...",
    "sentiment_score": 0.5
  },
  "sector": {
    "data_type": "sector",
    "stock_code": "603080.SH",
    "stock_name": "新疆火炬",
    "sector_name": "燃气板块",
    "heat_index": 75.0,
    "trend": "上升",
    "capital_flow": "资金流向深度描述（200字以上），包含主力净流入额、大单占比及板块联动分析..."
  },
  "kline": {
    "data_type": "kline",
    "stock_code": "603080.SH",
    "technical_indicators": {
      "MACD": 1.2,
      "RSI": 55.0,
      "KDJ_K": 60.0
    },
    "support_level": 10.5,
    "resistance_level": 15.0,
    "trend_analysis": "K线走势深度解读（200字以上），结合关键点位、成交量及技术形态...",
    "buy_suggestion": "持有"
  }
}
```

### 10.2 核心字段约束对照表

| 路径 | 类型 | 核心约束 | 业务说明 |
| :--- | :--- | :--- | :--- |
| `timestamp` | string | ISO 8601 (UTC) | 结果生成的精确时间。 |
| `news.positive_news` | list[str] | 1-5 项, 单条 100-800 字 | 深度正面新闻摘要。 |
| `news.negative_news` | list[str] | 1-5 项, 单条 100-800 字 | 深度负面新闻摘要。 |
| `news.news_summary` | string | 100-800 字 | 过去 12 个月的深度综合概括。 |
| `news.sentiment_score`| float | -1.0 到 1.0 | 新闻面量化情绪分。 |
| `sector.heat_index` | float | 0.0 到 100.0 | 板块活跃度量化分。 |
| `sector.trend` | enum | 上升 / 下降 / 震荡 | 仅限中文枚举。 |
| `kline.buy_suggestion` | enum | 强烈买入 / 买入 / 持有 / 卖出 / 强烈卖出 | 仅限中文枚举。 |

---
*文档生成时间：2026-02-03*

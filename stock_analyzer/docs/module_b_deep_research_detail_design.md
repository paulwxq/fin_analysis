# 模块B：网络搜索与摘要（Deep Research）— 详细设计

## 一、模块概述

### 1.1 定位

模块B 是 `stock_analyzer` 的网络信息采集模块，负责通过 **Tavily Search API** 对目标股票进行多主题深度网络搜索，采用 **Deep Research 递归搜索**模式（每主题 `breadth=3, depth=2`），最终由 LLM 将所有搜索发现（learnings）整合为结构化的投资研究摘要。

### 1.2 输入输出

| | 说明 |
|------|------|
| **输入** | 股票代码（`symbol`）、股票名称（`name`）、所属行业（`industry`） |
| **输出** | `WebResearchResult`（Pydantic 模型对象） |

### 1.3 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| Python 版本 | **3.12+** | 项目要求（使用 PEP 695 泛型语法） |
| Agent 框架 | Microsoft Agent Framework `1.0.0b260130` | 与项目统一 |
| LLM | 阿里云 DashScope `qwen-plus` | 通过 OpenAI 兼容接口调用 |
| 网络搜索 | Tavily Search API | 返回结构化内容摘要，无需爬取 |
| 数据模型 | Pydantic v2 | 结构化输出校验 |
| 异步框架 | asyncio | 并发执行搜索 |

### 1.4 配置依赖

所有 API Key 来自项目根目录 `.env` 文件：

```
DASHSCOPE_API_KEY=sk-xxxx          # 阿里云 DashScope API Key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TAVILY_API_KEY=tvly-xxxx           # Tavily Search API Key
```

---

## 二、架构设计

### 2.1 整体流程

```
                          输入: symbol, name, industry
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   定义 5 个搜索主题 (topics)    │
                    └───────────────┬───────────────┘
                                    │
              ┌─────────┬───────────┼───────────┬─────────┐
              ▼         ▼           ▼           ▼         ▼
          ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
          │ T1    │ │ T2    │ │ T3    │ │ T4    │ │ T5    │
          │近期   │ │竞争   │ │行业   │ │风险   │ │机构   │
          │新闻   │ │优势   │ │前景   │ │事件   │ │观点   │
          └───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘
              │         │         │         │         │
              ▼         ▼         ▼         ▼         ▼
          deep_research(breadth=3, depth=2)  ×5 并行
              │
              │  每个主题内部递归：
              │  ┌─ 第1层: breadth=3, 生成3个查询 → Tavily搜索 → 提取learnings
              │  └─ 第2层: breadth=1, 每分支1个查询 → Tavily搜索 → 提取learnings
              │
              ▼
    ┌─────────────────────────────┐
    │  合并去重所有 learnings      │
    │  (~50-70 个独特知识点)       │
    └─────────────┬───────────────┘
                  ▼
    ┌─────────────────────────────┐
    │  report_agent (ChatAgent)   │
    │  综合生成结构化摘要报告       │
    │  → WebResearchResult        │
    └─────────────┬───────────────┘
                  ▼
    ┌─────────────────────────────┐
    │  强制降级检查                │
    │  如果 learnings < 5:        │
    │  search_confidence = "低"   │
    └─────────────┬───────────────┘
                  ▼
         返回 Pydantic 模型对象
         (调用方可选择是否保存为 JSON)
```

### 2.2 核心组件

| 组件 | 类型 | 职责 |
|------|------|------|
| `query_agent` | MAF `ChatAgent` | 根据研究主题 + 已有 learnings 生成搜索查询 |
| `extract_agent` | MAF `ChatAgent` | 从 Tavily 搜索结果中提取 learnings 和 follow-up questions |
| `report_agent` | MAF `ChatAgent` | 将所有 learnings 整合为结构化投资研究报告 |
| `tavily_search()` | 异步函数 | 封装 Tavily API 调用 |
| `deep_research()` | 异步递归函数 | 核心递归逻辑，编排搜索-提取-深入的循环 |
| `run_web_research()` | 异步入口函数 | 模块B对外入口，编排5个主题的并行 Deep Research |

### 2.3 设计原则

1. **Agent 职责单一**：每个 ChatAgent 只做一件事（生成查询 / 提取知识 / 写报告）
2. **不使用 Agent 工具调用**：Deep Research 的递归逻辑由 Python 代码控制，Agent 只负责文本推理，Tavily 搜索由代码直接调用
3. **所有 Agent 共享同一个 LLM Client**：复用 `OpenAIChatClient` 实例，减少连接开销
4. **结构化输出**：所有 Agent 输出均通过 `response_format: {"type": "json_object"}` + Pydantic 校验

### 2.4 并发控制策略

本模块采用**两级并发控制**：

#### 主题级别（显式控制）

```python
TOPIC_CONCURRENCY_LIMIT = 3  # 最多 3 个主题同时执行
```

- 使用 `asyncio.Semaphore` 显式控制
- 避免 5 个主题同时调用 Tavily 导致限流

#### 查询级别（隐式控制）

```python
DEFAULT_BREADTH = 3  # 第1层：每主题 3 个查询并发
DEFAULT_DEPTH = 2    # 第2层：breadth 减半为 1
```

- **不使用** Semaphore，依赖 `breadth` 参数自然控制
- 第1层：3 个查询并发（每主题）
- 第2层：1 个查询/分支（breadth 减半）
- **实际并发峰值**：3 个主题 × 3 个查询 = **9 个 Tavily 调用**

#### 为什么不需要查询级别 Semaphore？

| 理由 | 说明 |
|------|------|
| ✅ breadth 自然递减 | 3→1→1，越深并发越少 |
| ✅ 主题级别已限流 | 最多 3 个主题并行 |
| ✅ 峰值可控 | 9 个并发调用在 Tavily 承受范围内 |
| ✅ 简化代码 | 避免 Semaphore 在递归中传递 |

**如果遇到 Tavily 限流：** 可降低 `TOPIC_CONCURRENCY_LIMIT` 或 `DEFAULT_BREADTH`。

---

## 三、配置模块

### 3.1 config.py

```python
"""模块B配置"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── DashScope / Qwen ──
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL: str = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# ── Tavily ──
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

# ── 模型选择 ──
MODEL_QUERY_AGENT: str = "qwen-plus"     # 生成搜索查询
MODEL_EXTRACT_AGENT: str = "qwen-plus"   # 提取知识点
MODEL_REPORT_AGENT: str = "qwen-plus"    # 生成最终报告

# ── Deep Research 参数 ──
DEFAULT_BREADTH: int = 3     # 每轮并行查询数（第1层）
DEFAULT_DEPTH: int = 2       # 递归深度（层数）
TAVILY_MAX_RESULTS: int = 5  # 每次 Tavily 搜索返回的最大结果数

# ── 超时与并发 ──
API_TIMEOUT: float = 120.0           # LLM 调用超时（秒）
TAVILY_TIMEOUT: float = 30.0         # Tavily 调用超时（秒）
TOPIC_CONCURRENCY_LIMIT: int = 3     # 主题并行数上限（避免 Tavily 限流）
# 注：查询级别不需要额外限流，因为：
#   1. breadth 自然递减（3→1→1）控制了每层查询数
#   2. TOPIC_CONCURRENCY_LIMIT 限制了主题并行数
#   3. 实际并发峰值 = 3主题 × 3查询 = 9个 Tavily 调用（可接受）

# ── 日志配置 ──
LOG_LEVEL_CONSOLE: str = "INFO"      # 控制台日志级别
LOG_LEVEL_FILE: str = "DEBUG"        # 文件日志级别
LOG_FILE_PATH: str = "logs/stock_analyzer.log"  # 日志文件路径
```

### 3.2 日志配置

```python
"""日志配置 — 统一的日志管理器"""
import logging
import sys
from pathlib import Path
from stock_analyzer.config import (
    LOG_LEVEL_CONSOLE,
    LOG_LEVEL_FILE,
    LOG_FILE_PATH,
)


def setup_logger(name: str = "stock_analyzer") -> logging.Logger:
    """
    配置模块统一的日志记录器。
    
    特性：
    - 控制台输出：INFO 级别（可配置），格式简洁
    - 文件输出：DEBUG 级别（可配置），格式详细，包含时间、模块、行号
    - 自动创建日志目录
    
    Args:
        name: Logger 名称，默认 "stock_analyzer"
    
    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)
    
    # 避免重复配置
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)  # Logger 本身设为最低级别
    logger.propagate = False
    
    # ── 控制台 Handler（INFO 级别）──
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL_CONSOLE.upper()))
    console_formatter = logging.Formatter(
        fmt="%(levelname)s - %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # ── 文件 Handler（DEBUG 级别）──
    log_file = Path(LOG_FILE_PATH)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(getattr(logging, LOG_LEVEL_FILE.upper()))
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger


# 模块级别的默认 Logger
logger = setup_logger()
```

### 3.3 LLM Client 初始化

```python
"""LLM Client 工厂"""
from openai import AsyncOpenAI
from agent_framework.openai import OpenAIChatClient
from stock_analyzer.config import (
    DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, API_TIMEOUT,
    MODEL_QUERY_AGENT, MODEL_EXTRACT_AGENT, MODEL_REPORT_AGENT,
)


def create_openai_client() -> AsyncOpenAI:
    """创建共享的 AsyncOpenAI 客户端（DashScope 兼容模式）"""
    return AsyncOpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url=DASHSCOPE_BASE_URL,
        timeout=API_TIMEOUT,
    )


def create_chat_client(
    openai_client: AsyncOpenAI,
    model_id: str,
) -> OpenAIChatClient:
    """创建 MAF OpenAIChatClient"""
    return OpenAIChatClient(
        model_id=model_id,
        async_client=openai_client,
    )
```

---

## 四、Pydantic 数据模型

### 4.1 内部中间模型

```python
"""Deep Research 过程中使用的中间数据模型"""
from pydantic import BaseModel, Field


class SerpQuery(BaseModel):
    """LLM 生成的单个搜索查询"""
    query: str = Field(description="搜索引擎查询词，应具体且适合搜索引擎")
    research_goal: str = Field(description="该查询的研究目标，说明期望发现什么信息")


class SerpQueryList(BaseModel):
    """generate_serp_queries 的输出"""
    queries: list[SerpQuery] = Field(description="搜索查询列表")


class ProcessedResult(BaseModel):
    """process_serp_result 的输出：从搜索结果中提取的知识"""
    learnings: list[str] = Field(
        description="从搜索结果中提取的知识点，应信息密集，包含实体、数字、日期"
    )
    follow_up_questions: list[str] = Field(
        description="值得继续深入搜索的追问方向"
    )


class ResearchResult(BaseModel):
    """单个主题的 Deep Research 最终结果"""
    learnings: list[str] = Field(default_factory=list)
    visited_urls: list[str] = Field(default_factory=list)
```

### 4.2 模块输出模型

```python
"""模块B最终输出模型（与概要设计 v3.1 对齐）"""
from pydantic import BaseModel, Field
from typing import Literal


class NewsItem(BaseModel):
    """单条新闻"""
    title: str = Field(description="新闻标题")
    summary: str = Field(description="新闻内容摘要，50-100字")
    source: str = Field(description="信息来源")
    date: str = Field(description="新闻日期，格式 YYYY-MM-DD")
    importance: Literal["高", "中", "低"] = Field(description="重要性等级")


class NewsSummary(BaseModel):
    """新闻摘要，正面和负面分开"""
    positive: list[NewsItem] = Field(default_factory=list, description="正面新闻")
    negative: list[NewsItem] = Field(default_factory=list, description="负面新闻")
    neutral: list[NewsItem] = Field(default_factory=list, description="中性新闻")


class CompetitiveAdvantage(BaseModel):
    """公司竞争优势"""
    description: str = Field(
        max_length=500, 
        description="竞争优势综述（降级报告采用统一截断策略确保不超过此限制）"
    )
    moat_type: str = Field(description="护城河类型，如：品牌+渠道+科技")
    market_position: str = Field(description="市场地位描述")


class IndustryOutlook(BaseModel):
    """行业前景"""
    industry: str = Field(description="行业名称")
    outlook: str = Field(description="前景判断：乐观/中性偏积极/中性/中性偏消极/悲观")
    key_drivers: list[str] = Field(description="主要驱动因素")
    key_risks: list[str] = Field(description="主要风险因素")


class RiskEvents(BaseModel):
    """风险事件"""
    regulatory: str = Field(description="监管处罚情况")
    litigation: str = Field(description="诉讼情况")
    management: str = Field(description="管理层变动情况")
    other: str = Field(default="", description="其他风险")


class AnalystReport(BaseModel):
    """单条机构研报"""
    broker: str = Field(description="券商/机构名称")
    rating: str = Field(description="评级：买入/增持/中性/减持/卖出")
    target_price: float | None = Field(default=None, description="目标价")
    date: str = Field(description="研报日期")


class AnalystOpinions(BaseModel):
    """机构观点汇总"""
    buy_count: int = Field(default=0, description="买入/增持评级数量")
    hold_count: int = Field(default=0, description="中性/持有评级数量")
    sell_count: int = Field(default=0, description="减持/卖出评级数量")
    average_target_price: float | None = Field(default=None, description="平均目标价")
    recent_reports: list[AnalystReport] = Field(
        default_factory=list, description="近期研报列表"
    )


class SearchConfig(BaseModel):
    """搜索参数配置（结构化，避免裸 dict 的 KeyError 风险）"""
    topics_count: int = Field(description="搜索主题总数")
    breadth: int = Field(description="每主题每轮查询数")
    depth: int = Field(description="每主题递归深度")
    successful_topics: int = Field(description="成功主题数（有 learnings 的主题）")


class SearchMeta(BaseModel):
    """搜索元信息"""
    symbol: str
    name: str
    search_time: str
    search_config: SearchConfig = Field(description="搜索参数配置")
    total_learnings: int = Field(description="去重后的知识点总数")
    total_sources_consulted: int = Field(description="访问的信息源总数")
    raw_learnings: list[str] | None = Field(
        default=None,
        description="原始 learnings 列表（仅在降级报告时填充，便于后续人工分析）"
    )


class WebResearchResult(BaseModel):
    """模块B最终输出：网络深度搜索研究报告"""
    meta: SearchMeta
    news_summary: NewsSummary
    competitive_advantage: CompetitiveAdvantage
    industry_outlook: IndustryOutlook
    risk_events: RiskEvents
    analyst_opinions: AnalystOpinions
    search_confidence: Literal["高", "中", "低"] = Field(
        description="搜索信息的整体可信度"
    )
```

---

## 五、核心组件详细设计

### 5.1 Tavily Search 封装

```python
"""Tavily Search API 封装

⚠️ Tavily 异常导入规范（避免 NameError）：

【通用规则】适用于大多数 Tavily 异常：
- ✅ 正确：from tavily import InvalidAPIKeyError  →  使用 InvalidAPIKeyError
- ❌ 错误：from tavily import InvalidAPIKeyError  →  使用 tavily.InvalidAPIKeyError（NameError）

【特例规则】仅用于命名冲突（如 TimeoutError 与标准库重名）：
- 使用命名空间导入：from tavily import errors as tavily_errors  →  使用 tavily_errors.TimeoutError
- 注意：本项目 TimeoutError 已确认不启用，此规则仅供参考

📖 依据：官方源码 v0.7.21 https://github.com/tavily-ai/tavily-python/blob/38627afb7b88d8a57bad29380896210a9ae7badd/tavily/__init__.py
"""
import asyncio
import httpx  # ← 项目依赖 httpx，必须导入
from tavily import AsyncTavilyClient
# Tavily 异常类导入（✅ 已确认可用，基于官方源码 v0.7.21）
# 导入自 tavily.__init__.py（已重新导出自 tavily.errors）
# ⚠️ 注意：代码中使用时直接用类名，不要加 tavily. 前缀
from tavily import (
    InvalidAPIKeyError,
    MissingAPIKeyError, 
    BadRequestError,
    ForbiddenError,
    UsageLimitExceededError,
)

from stock_analyzer.config import TAVILY_API_KEY, TAVILY_MAX_RESULTS, TAVILY_TIMEOUT
from stock_analyzer.exceptions import TavilySearchError
from stock_analyzer.logger import logger

# ============================================================
# 异常分类：可重试 vs 不可重试
# ============================================================
# 
# 设计目标：所有网络层瞬时故障应重试，配置/逻辑错误不重试
# 
# 实施要求：
# 1. 根据项目实际依赖的 HTTP 库启用相应异常（不要留"可选"注释）
# 2. 如果 Tavily SDK 提供了特定异常类型，必须明确添加
# 3. 定期审查：新增依赖时同步更新此列表
# ============================================================

# 可重试异常：网络层瞬时故障（会自动重试 max_retries 次）
# 
# 注意：asyncio.TimeoutError 单独处理（有专门的 except 分支），不在此元组中
# 这样可以为超时异常提供更清晰的日志，并避免重复匹配
RETRYABLE_EXCEPTIONS = (
    # Python 标准库网络异常
    ConnectionError,       # 连接失败（含 ConnectionRefusedError, ConnectionResetError 等）
    OSError,               # 底层 I/O 错误（含部分网络错误）
    
    # ============================================================
    # 项目实际依赖：httpx (pyproject.toml 已确认)
    # ============================================================
    # 
    # ✅ 必须启用：项目依赖 httpx>=0.28.1
    httpx.ConnectError,         # httpx 连接错误（含 ConnectTimeout）
    httpx.NetworkError,         # httpx 网络错误（所有网络层错误的基类）
    httpx.TimeoutException,     # httpx 超时（ReadTimeout, WriteTimeout, PoolTimeout）
    httpx.RemoteProtocolError,  # 远程协议错误（如 HTTP/2 错误）
    
    # ============================================================
    # Tavily SDK 网络/超时异常（✅ 已确认，基于官方源码 v0.7.21）
    # 源码：github.com/tavily-ai/tavily-python/blob/38627afb7b88d8a57bad29380896210a9ae7badd/tavily/errors.py
    # ============================================================
    # 
    # ⚠️ 当前保持注释态：Tavily TimeoutError 与标准库 TimeoutError 重名
    # 
    # 如需启用，建议使用命名空间导入（⚠️ 仅此特例，不改变其他异常的通用导入规范）：
    # from tavily import errors as tavily_errors
    # tavily_errors.TimeoutError,     # Tavily 请求超时（命名空间写法避免与标准库冲突）
    # 
    # 💡 特例说明：该命名空间写法仅用于重名冲突场景，其他 Tavily 异常仍优先直接导入类名
    # 
    # ❌ NetworkError：在 Tavily SDK 中不存在（已从官方源码确认，不要添加）
)

# 不可重试异常：配置错误、API 错误（立即失败，不重试）
# 
# 用途：提供更明确的错误日志和分类
# 
# ============================================================
# 异常来源已确认（基于 Tavily SDK v0.7.21 官方源码）
# 源码位置：github.com/tavily-ai/tavily-python/blob/38627afb7b88d8a57bad29380896210a9ae7badd/tavily/errors.py
# 导入方式：from tavily import InvalidAPIKeyError, BadRequestError, ...
# ============================================================
NON_RETRYABLE_EXCEPTIONS = (
    # HTTP 层 API 错误
    httpx.HTTPStatusError,  # HTTP 4xx/5xx 状态码错误（项目依赖 httpx）
    
    # Tavily SDK 特定 API 错误（✅ 已确认可用，基于官方源码 v0.7.21）
    # ⚠️ 注意：必须使用直接导入的类名（见顶部 import 语句），不要使用 tavily.异常名
    InvalidAPIKeyError,       # API 密钥无效
    MissingAPIKeyError,       # 缺少 API 密钥
    BadRequestError,          # 请求格式错误
    ForbiddenError,           # 权限不足
    UsageLimitExceededError,  # 使用限制超出（配额不足）
)

# 模块级别单例
_tavily_client: AsyncTavilyClient | None = None


def get_tavily_client() -> AsyncTavilyClient:
    """获取 Tavily 客户端单例"""
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
    return _tavily_client


async def tavily_search(
    query: str,
    max_results: int = TAVILY_MAX_RESULTS,
    max_retries: int = 1,
) -> list[dict]:
    """
    调用 Tavily Search API 执行单次搜索，带超时和重试。

    Args:
        query: 搜索查询词
        max_results: 返回结果数上限
        max_retries: 失败后的最大重试次数（默认1次）

    Returns:
        搜索结果列表，每项包含:
        - title: str   页面标题
        - url: str     页面URL
        - content: str 页面内容摘要（Tavily 提取）
        - score: float 相关性评分

    Raises:
        TavilySearchError: 搜索失败（含重试后仍失败的情况）
    """
    client = get_tavily_client()
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            # 使用 asyncio.wait_for 实现超时控制
            response = await asyncio.wait_for(
                client.search(
                    query=query,
                    max_results=max_results,
                    search_depth="advanced",
                    include_answer=False,
                    include_raw_content=False,
                ),
                timeout=TAVILY_TIMEOUT,
            )
            results = response.get("results", [])
            
            if attempt > 0:
                logger.info(
                    f"Tavily search '{query[:50]}...' succeeded on retry {attempt}, "
                    f"returned {len(results)} results"
                )
            else:
                logger.info(
                    f"Tavily search '{query[:50]}...' returned {len(results)} results"
                )
            
            return results
            
        except asyncio.TimeoutError as e:
            # 单独处理超时异常，提供更清晰的日志
            # （不在 RETRYABLE_EXCEPTIONS 中，避免重复匹配）
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Tavily search '{query[:50]}...' timeout "
                    f"(attempt {attempt + 1}/{max_retries + 1}), retrying..."
                )
                await asyncio.sleep(2)  # 重试前等待2秒
            else:
                logger.error(
                    f"Tavily search '{query[:50]}...' timeout after {max_retries + 1} attempts"
                )
                
        except RETRYABLE_EXCEPTIONS as e:
            # 可重试的网络错误（使用模块级常量，便于统一管理）
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Tavily search '{query[:50]}...' network error: {type(e).__name__} "
                    f"(attempt {attempt + 1}/{max_retries + 1}), retrying..."
                )
                await asyncio.sleep(2)
            else:
                logger.error(
                    f"Tavily search '{query[:50]}...' failed after {max_retries + 1} attempts: {e}"
                )
        
        except NON_RETRYABLE_EXCEPTIONS as e:
            # 已知的不可重试异常（API 错误、配置错误）
            # 立即失败，提供明确的错误分类
            logger.error(
                f"Tavily search '{query[:50]}...' non-retryable API/config error: "
                f"{type(e).__name__}: {e}"
            )
            raise TavilySearchError(
                query=query,
                attempts=attempt + 1,
                cause=e
            ) from e
        
        except Exception as e:
            # 其他未预期异常（编程错误等）不重试，立即失败
            # 包括但不限于：
            # - 编程错误：KeyError, AttributeError, TypeError, ValueError
            # - 其他未分类异常
            #
            # 关键：封装为 TavilySearchError 对外抛出，原始异常通过 cause 保留
            logger.error(
                f"Tavily search '{query[:50]}...' unexpected error: "
                f"{type(e).__name__}: {e}"
            )
            raise TavilySearchError(
                query=query,
                attempts=attempt + 1,
                cause=e  # ← 保留原始异常，便于调试
            ) from e
    
    # 所有重试都失败
    raise TavilySearchError(
        query=query,
        cause=last_error,
        attempts=max_retries + 1,
    )
```

### 5.1.1 自定义异常类

在 `stock_analyzer/exceptions.py` 中定义：

```python
"""模块B自定义异常"""

class TavilySearchError(Exception):
    """Tavily 搜索异常"""
    def __init__(self, query: str, cause: Exception, attempts: int = 1):
        self.query = query
        self.cause = cause
        self.attempts = attempts
        super().__init__(
            f"Tavily search failed for '{query}' after {attempts} attempts: {cause}"
        )


class AgentCallError(Exception):
    """Agent 调用异常（包含 JSON 解析和 Pydantic 校验失败）"""
    def __init__(self, agent_name: str, cause: Exception):
        self.agent_name = agent_name
        self.cause = cause
        super().__init__(f"Agent '{agent_name}' call failed: {cause}")


class ReportGenerationError(Exception):
    """报告生成异常"""
    def __init__(self, symbol: str, cause: Exception, learnings_count: int):
        self.symbol = symbol
        self.cause = cause
        self.learnings_count = learnings_count
        super().__init__(
            f"Failed to generate report for {symbol} with {learnings_count} learnings: {cause}"
        )


class WebResearchError(Exception):
    """Web Research 整体流程异常"""
    pass
```

### 5.2 Agent 定义

三个 ChatAgent 实例：`query_agent`（生成查询）、`extract_agent`（提取知识）、`report_agent`（生成报告）。

#### 5.2.1 query_agent — 生成搜索查询

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

def create_query_agent(chat_client: OpenAIChatClient) -> ChatAgent:
    """
    创建搜索查询生成 Agent。

    职责：根据研究主题和已有 learnings，生成适合搜索引擎的查询词。
    输入：用户消息（包含主题和 learnings 的动态拼接提示词）
    输出：JSON 格式的 SerpQueryList
    """
    return ChatAgent(
        chat_client=chat_client,
        name="query_generator",
        instructions=QUERY_AGENT_SYSTEM_PROMPT,
        default_options={
            "temperature": 0.5,
            "response_format": {"type": "json_object"},
        },
    )
```

**系统提示词（`QUERY_AGENT_SYSTEM_PROMPT`）：**

```python
QUERY_AGENT_SYSTEM_PROMPT = """\
你是一位专业的 A 股金融研究员助手。你的唯一任务是：根据给定的研究主题和已有知识，
生成适合搜索引擎的查询词。

## 规则

1. 生成的查询词必须是中文，适合在 Google / Bing 等搜索引擎中使用
2. 每个查询词应具体、精准，避免过于笼统
3. 如果提供了已有知识点（learnings），你应该：
   - 避免搜索已知信息
   - 针对知识点中的缺失、不确定或值得深入的方向生成查询
   - 查询应比前一轮更具体、更有深度
4. 每个查询必须附带 research_goal，说明这条查询期望发现什么

## 输出格式

严格输出 JSON，格式如下：
```json
{
  "queries": [
    {
      "query": "搜索引擎查询词",
      "research_goal": "研究目标说明"
    }
  ]
}
```

不要输出任何 JSON 之外的内容。
"""
```

#### 5.2.2 extract_agent — 提取知识点

```python
def create_extract_agent(chat_client: OpenAIChatClient) -> ChatAgent:
    """
    创建知识点提取 Agent。

    职责：从 Tavily 搜索结果中提取结构化的知识点和追问方向。
    输入：用户消息（包含搜索查询和搜索结果内容）
    输出：JSON 格式的 ProcessedResult
    """
    return ChatAgent(
        chat_client=chat_client,
        name="knowledge_extractor",
        instructions=EXTRACT_AGENT_SYSTEM_PROMPT,
        default_options={
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
    )
```

**系统提示词（`EXTRACT_AGENT_SYSTEM_PROMPT`）：**

```python
EXTRACT_AGENT_SYSTEM_PROMPT = """\
你是一位专业的 A 股金融研究员助手。你的唯一任务是：从搜索结果中提取高质量的知识点，
并提出值得继续深入的追问方向。

## 知识点（learnings）提取规则

1. 每个知识点必须**信息密集**，包含具体的：
   - 实体名称（公司名、产品名、人名）
   - 数字（金额、百分比、数量）
   - 日期（具体到月份或季度）
2. 知识点之间不应重复
3. 优先提取与投资决策相关的信息
4. 忽略广告、推广、无实质内容的信息
5. 每次最多提取 **5 个**知识点

## 追问方向（follow_up_questions）规则

1. 追问应指向搜索结果未充分覆盖但有价值的方向
2. 追问应比当前搜索更深入、更具体
3. 每次最多提出 **3 个**追问

## 输出格式

严格输出 JSON，格式如下：
```json
{
  "learnings": [
    "知识点1：包含具体实体、数字、日期",
    "知识点2：信息密集且不重复"
  ],
  "follow_up_questions": [
    "追问方向1",
    "追问方向2"
  ]
}
```

不要输出任何 JSON 之外的内容。
"""
```

#### 5.2.3 report_agent — 生成最终报告

```python
def create_report_agent(chat_client: OpenAIChatClient) -> ChatAgent:
    """
    创建报告生成 Agent。

    职责：将所有 learnings 整合为结构化的投资研究报告。
    输入：用户消息（包含股票信息和全部 learnings）
    输出：JSON 格式的 WebResearchResult（不含 meta，meta 由代码填充）
    """
    return ChatAgent(
        chat_client=chat_client,
        name="report_generator",
        instructions=REPORT_AGENT_SYSTEM_PROMPT,
        default_options={
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        },
    )
```

**系统提示词（`REPORT_AGENT_SYSTEM_PROMPT`）：**

```python
REPORT_AGENT_SYSTEM_PROMPT = """\
你是一位资深的 A 股首席研究员。你的任务是：将多轮深度网络搜索中积累的知识点，
整合为一份结构化的投资研究摘要报告。

## 报告要求

1. **新闻分类**：将新闻类知识点按正面/负面/中性分类，每条包含标题、摘要、来源、日期、重要性
2. **竞争优势**：综合所有相关知识点，描述公司的核心竞争力、护城河类型、市场地位
3. **行业前景**：综合行业相关知识点，给出前景判断、驱动因素、风险因素
4. **风险事件**：整理监管处罚、诉讼、管理层变动等风险信息
5. **机构观点**：整理券商评级、目标价等信息
6. **可信度评估**：根据知识点的来源质量和一致性，给出整体可信度（高/中/低）

## 数据处理原则

- 如果某个字段缺乏足够的知识点支撑，应如实说明"信息不足"，不要编造
- 日期尽量精确到天，无法确定时写到月份
- 来源写媒体/网站名称，不要写 URL
- 数字保留原始精度，不要四舍五入

## 输出格式

严格输出 JSON，结构如下（不包含 meta 字段，meta 由系统自动填充）：

```json
{
  "news_summary": {
    "positive": [{"title": "", "summary": "", "source": "", "date": "", "importance": "高/中/低"}],
    "negative": [],
    "neutral": []
  },
  "competitive_advantage": {
    "description": "",
    "moat_type": "",
    "market_position": ""
  },
  "industry_outlook": {
    "industry": "",
    "outlook": "",
    "key_drivers": [],
    "key_risks": []
  },
  "risk_events": {
    "regulatory": "",
    "litigation": "",
    "management": "",
    "other": ""
  },
  "analyst_opinions": {
    "buy_count": 0,
    "hold_count": 0,
    "sell_count": 0,
    "average_target_price": null,
    "recent_reports": []
  },
  "search_confidence": "高/中/低"
}
```

**注意：** 降级报告时，`meta.raw_learnings` 会包含所有原始知识点列表，便于后续人工分析。

不要输出任何 JSON 之外的内容。
"""
```

### 5.3 LLM 调用辅助函数

所有 Agent 的调用统一封装为辅助函数，负责调用 Agent、提取 JSON、校验 Pydantic 模型。

**关键改进：**
- `extract_json_str()` 使用"候选集 + 逐个验证"策略，支持多种复杂场景
- 优先验证标记为 `json` 的代码块，然后是无标签块，最后是整段文本
- 从后往前验证（LLM 通常把最终结果放在最后），使用 `itertools.chain()` 正确连接两个 `reversed()` 迭代器
- 无需强制 LLM 仅输出纯 JSON，大幅提升了鲁棒性

```python
"""
Agent 调用辅助函数

注意：异常类必须从 exceptions.py 导入，确保示例代码可直接运行
"""
from pydantic import BaseModel, ValidationError
from agent_framework import ChatAgent
from stock_analyzer.logger import logger
from stock_analyzer.exceptions import AgentCallError  # ← 必须导入，否则运行时 NameError


def extract_json_str(text: str) -> str:
    """
    从 LLM 响应文本中提取 JSON 字符串。
    
    策略（按优先级）：
    1. 尝试整段文本作为 JSON 解析（最快路径）
    2. 提取所有 fenced code blocks，优先验证 ```json 标签的，然后验证无标签的
    3. 从后往前验证（LLM 通常把最终结果放在最后）
    4. 如果都失败，抛出 ValueError
    
    支持的格式：
    - 直接 JSON: {"key": "value"}
    - Markdown 包裹: ```json\n{"key": "value"}\n```
    - 前置文字: Here is...\n```json\n{"key": "value"}\n```
    - 多个代码块: 取最后一个有效的 JSON 块
    
    注意：使用 itertools.chain 连接两个 reversed 迭代器，
    因为 Python 中 reversed() 返回的迭代器对象不支持 + 运算符。
    """
    import json
    import re
    from itertools import chain
    
    text = text.strip()
    
    # 1. 尝试整段文本（最快路径）
    try:
        json.loads(text)
        return text
    except Exception:
        pass
    
    # 2. 提取所有 fenced code blocks
    FENCE_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_-]*)\s*\n(?P<body>[\s\S]*?)```", re.MULTILINE)
    blocks = list(FENCE_RE.finditer(text))
    
    if blocks:
        json_blocks = []  # 明确标记为 json 的块
        plain_blocks = []  # 无标签的块
        
        for match in blocks:
            lang = (match.group("lang") or "").strip().lower()
            body = match.group("body").strip()
            
            if lang == "json":
                json_blocks.append(body)
            elif lang == "":
                plain_blocks.append(body)
        
        # 从后往前验证（优先 json 标签，再尝试 plain）
        # 使用 itertools.chain 连接两个 reversed 迭代器
        for candidate in chain(reversed(json_blocks), reversed(plain_blocks)):
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                continue
    
    # 3. 如果都失败，抛出异常
    raise ValueError("No valid JSON found in model output")


# ============================================================
# ⚠️ 关键实施要点：itertools.chain 的使用
# ============================================================
# 1. reversed() 返回的是迭代器对象，不支持 + 运算符
# 2. 必须使用 itertools.chain() 来连接多个迭代器
# 3. 错误示例：for x in reversed(list1) + reversed(list2)  # ❌ TypeError
# 4. 正确示例：for x in chain(reversed(list1), reversed(list2))  # ✅
# ============================================================


async def call_agent_with_model[T: BaseModel](
    agent: ChatAgent,
    message: str,
    model_cls: type[T],
) -> T:
    """
    调用 ChatAgent 并解析为 Pydantic 模型。
    
    注意：使用 PEP 695 泛型语法（Python 3.12+），
    与项目 pyproject.toml 的 requires-python = ">=3.12" 要求一致。

    Args:
        agent: MAF ChatAgent 实例
        message: 用户消息
        model_cls: 期望的 Pydantic 输出模型

    Returns:
        解析后的 Pydantic 模型实例

    Raises:
        AgentCallError: Agent 调用或解析失败
    """
    thread = agent.get_new_thread()

    try:
        response = await agent.run(
            message=message,
            thread=thread,
        )
        raw_text = response.text
        json_str = extract_json_str(raw_text)
        result = model_cls.model_validate_json(json_str)
        return result

    except ValidationError as e:
        # Pydantic v2: model_validate_json() 对所有验证失败都抛出 ValidationError
        # 包括：JSON 格式错误、字段缺失、类型不匹配、约束违反等
        logger.error(
            f"Agent '{agent.name}' validation failed: {e.error_count()} errors\n"
            f"First error: {e.errors()[0] if e.errors() else 'unknown'}"
        )
        raise AgentCallError(agent_name=agent.name, cause=e) from e
    except Exception as e:
        logger.error(f"Agent '{agent.name}' call failed: {e}")
        raise AgentCallError(agent_name=agent.name, cause=e) from e
```

### 5.4 generate_serp_queries — 生成搜索查询

```python
async def generate_serp_queries(
    query_agent: ChatAgent,
    query: str,
    num_queries: int,
    learnings: list[str],
) -> list[SerpQuery]:
    """
    调用 query_agent 生成搜索查询。

    提示词动态拼接逻辑：
    - 始终包含研究主题（query）
    - 始终包含所需查询数量（num_queries）
    - 有 learnings 时追加历史知识上下文，引导 Agent 生成更深入的查询
    - 无 learnings 时（第一轮），Agent 自由发散

    Args:
        query_agent: MAF ChatAgent (query_generator)
        query: 当前研究主题或追问方向
        num_queries: 需要生成的查询数量
        learnings: 已有的知识点列表（前几轮累积）

    Returns:
        搜索查询列表
    """
    # ── 动态拼接用户消息 ──
    user_message = f"请为以下研究主题生成 {num_queries} 个搜索查询。\n\n"
    user_message += f"<topic>\n{query}\n</topic>\n"

    if learnings:
        user_message += (
            "\n以下是前几轮研究中已获得的知识点，"
            "请据此生成更有针对性的查询，避免搜索已知信息：\n"
            "<learnings>\n"
        )
        for learning in learnings:
            user_message += f"- {learning}\n"
        user_message += "</learnings>\n"

    # ── 调用 Agent ──
    result = await call_agent_with_model(
        agent=query_agent,
        message=user_message,
        model_cls=SerpQueryList,
    )

    # 截断到请求数量（LLM 可能多生成）
    return result.queries[:num_queries]
```

**提示词演进示例：**

| 轮次 | learnings 数量 | 用户消息关键内容 |
|------|---------------|-----------------|
| 第1轮 | 0 | `<topic>平安银行 近期新闻...</topic>` |
| 第2轮 | ~9 | `<topic>Previous research goal: ...\nFollow-up: ...</topic>\n<learnings>9条</learnings>` |
| 第3轮 | ~18 | `<topic>Previous research goal: ...\nFollow-up: ...</topic>\n<learnings>18条</learnings>` |

### 5.5 process_serp_result — 提取知识点

```python
async def process_serp_result(
    extract_agent: ChatAgent,
    query: str,
    search_results: list[dict],
) -> ProcessedResult:
    """
    调用 extract_agent 从 Tavily 搜索结果中提取知识点和追问方向。

    Args:
        extract_agent: MAF ChatAgent (knowledge_extractor)
        query: 本次搜索使用的查询词
        search_results: Tavily 返回的搜索结果列表

    Returns:
        ProcessedResult（learnings + follow_up_questions）
    """
    # ── 将搜索结果格式化为提示词 ──
    if not search_results:
        return ProcessedResult(learnings=[], follow_up_questions=[])

    contents_parts: list[str] = []
    for r in search_results:
        content = r.get("content", "")
        url = r.get("url", "")
        title = r.get("title", "")
        if content:
            contents_parts.append(
                f'<source title="{title}" url="{url}">\n{content}\n</source>'
            )

    if not contents_parts:
        return ProcessedResult(learnings=[], follow_up_questions=[])

    contents_text = "\n\n".join(contents_parts)

    user_message = (
        f"以下是针对查询 <query>{query}</query> 的搜索结果。\n"
        f"请从中提取关键知识点和值得追问的方向。\n\n"
        f"<search_results>\n{contents_text}\n</search_results>"
    )

    # ── 调用 Agent ──
    result = await call_agent_with_model(
        agent=extract_agent,
        message=user_message,
        model_cls=ProcessedResult,
    )

    return result
```

### 5.6 deep_research — 核心递归函数

递归的 Deep Research 逻辑实现：每次调用生成 breadth 个查询，执行搜索和知识提取，然后对每个 follow-up 递归调用。

**返回值说明：**
- 总是返回 `ResearchResult` 对象
- 如果所有查询都失败（查询生成失败、搜索失败、提取失败等），会返回空的 `learnings` 列表
- 调用方（`run_web_research()`）会通过 `len(result.learnings) > 0` 判断主题是否真正成功

```python
import asyncio
from stock_analyzer.logger import logger


async def deep_research(
    query_agent: ChatAgent,
    extract_agent: ChatAgent,
    query: str,
    breadth: int,
    depth: int,
    learnings: list[str] | None = None,
    visited_urls: list[str] | None = None,
) -> ResearchResult:
    """
    对单个研究主题执行递归深度搜索。

    算法流程：
    1. 调用 query_agent 生成 breadth 个搜索查询
    2. 对每个查询：
       a. 调用 tavily_search 执行搜索
       b. 调用 extract_agent 提取 learnings 和 follow_up_questions
       c. 如果 depth > 1：构造新的 query（基于 follow_up_questions），递归调用
    3. 合并所有分支的 learnings 并去重

    参数递减规则：
    - breadth: 每深入一层减半 → max(1, breadth // 2)
    - depth: 每深入一层减1 → depth - 1
    - 当 depth == 1 时为最后一层，不再递归

    Args:
        query_agent: 搜索查询生成 Agent
        extract_agent: 知识点提取 Agent
        query: 研究主题或追问方向
        breadth: 当前层的并行查询数
        depth: 剩余递归深度
        learnings: 前几轮累积的知识点
        visited_urls: 前几轮已访问的 URL

    Returns:
        ResearchResult（合并去重后的 learnings + visited_urls）
        注意：如果所有查询都失败，可能返回空的 learnings 列表，
        调用方需通过 len(result.learnings) > 0 判断主题是否真正成功
    """
    if learnings is None:
        learnings = []
    if visited_urls is None:
        visited_urls = []

    logger.info(
        f"deep_research: depth={depth}, breadth={breadth}, "
        f"existing_learnings={len(learnings)}, query='{query[:80]}...'"
    )

    # ── Step 1: 生成搜索查询 ──
    try:
        serp_queries = await generate_serp_queries(
            query_agent=query_agent,
            query=query,
            num_queries=breadth,
            learnings=learnings,
        )
    except AgentCallError:
        logger.warning("Failed to generate SERP queries, returning current learnings")
        # 注意：如果 learnings 为空，run_web_research() 会将此主题标记为失败
        return ResearchResult(learnings=learnings, visited_urls=visited_urls)

    all_learnings = list(learnings)
    all_urls = list(visited_urls)

    # ── Step 2: 对每个查询执行搜索和提取 ──
    #     同层查询并行执行（无需额外限流，breadth 自然控制并发数）

    async def process_single_query(serp_query: SerpQuery) -> ResearchResult:
        """处理单个搜索查询（搜索 → 提取 → 可能递归）"""
        branch_learnings = list(all_learnings)
        branch_urls = list(all_urls)

        # 2a. Tavily 搜索
        try:
            search_results = await tavily_search(serp_query.query)
        except TavilySearchError:
            logger.warning(f"Tavily search failed for '{serp_query.query}', skipping")
            # 返回当前分支的 learnings（可能为空）
            return ResearchResult(learnings=branch_learnings, visited_urls=branch_urls)

        # 收集 URL
        for r in search_results:
            url = r.get("url", "")
            if url:
                branch_urls.append(url)

        # 2b. 提取知识点
        try:
            processed = await process_serp_result(
                extract_agent=extract_agent,
                query=serp_query.query,
                search_results=search_results,
            )
            branch_learnings.extend(processed.learnings)
        except AgentCallError:
            logger.warning(f"Knowledge extraction failed for '{serp_query.query}'")
            processed = ProcessedResult(learnings=[], follow_up_questions=[])

        # ── Step 3: 判断是否继续深入 ──
        new_depth = depth - 1
        new_breadth = max(1, breadth // 2)

        if new_depth > 0 and processed.follow_up_questions:
            # Step 4: 递归 — 构造新查询，基于 follow-up questions
            next_query = (
                f"Previous research goal: {serp_query.research_goal}\n"
                f"Follow-up research directions:\n"
                + "\n".join(f"- {q}" for q in processed.follow_up_questions)
            )

            deeper_result = await deep_research(
                query_agent=query_agent,
                extract_agent=extract_agent,
                query=next_query,
                breadth=new_breadth,
                depth=new_depth,
                learnings=branch_learnings,
                visited_urls=branch_urls,
            )
            return deeper_result

        return ResearchResult(learnings=branch_learnings, visited_urls=branch_urls)

    # 并行执行所有分支（无需 Semaphore，breadth 参数已控制并发数）
    tasks = [process_single_query(sq) for sq in serp_queries]
    branch_results = await asyncio.gather(*tasks, return_exceptions=True)

    # ── Step 5: 合并所有分支结果 ──
    merged_learnings: set[str] = set()
    merged_urls: set[str] = set()

    for result in branch_results:
        if isinstance(result, ResearchResult):
            merged_learnings.update(result.learnings)
            merged_urls.update(result.visited_urls)
        elif isinstance(result, asyncio.CancelledError):
            # 取消异常必须向上传播，不能被吞掉
            logger.warning("Branch task was cancelled, propagating CancelledError")
            raise result
        elif isinstance(result, Exception):
            logger.error(f"Branch failed with exception: {result}")
        # 跳过失败的分支

    logger.info(
        f"deep_research complete: depth={depth}, "
        f"total_learnings={len(merged_learnings)}, total_urls={len(merged_urls)}"
    )

    return ResearchResult(
        learnings=list(merged_learnings),
        visited_urls=list(merged_urls),
    )
```

**递归执行树（单主题，breadth=3, depth=2）：**

```
第1层 (depth=2, breadth=3)
├── 查询A ──→ Tavily ──→ 提取 learnings + follow_ups
│   └── 第2层 (depth=1, breadth=1)
│       └── 查询A-1 ──→ Tavily ──→ 提取 (depth=0, 停止)
├── 查询B ──→ Tavily ──→ 提取 learnings + follow_ups
│   └── 第2层 (depth=1, breadth=1)
│       └── 查询B-1 ──→ Tavily ──→ 提取 (depth=0, 停止)
└── 查询C ──→ Tavily ──→ 提取 learnings + follow_ups
    └── 第2层 (depth=1, breadth=1)
        └── 查询C-1 ──→ Tavily ──→ 提取 (depth=0, 停止)

Tavily 总调用: 3 + 3 = 6
LLM 总调用: 1(生成查询) + 3(提取) + 3(生成查询) + 3(提取) = 10
```

### 5.7 generate_report — 最终报告生成

```python
async def generate_report(
    report_agent: ChatAgent,
    symbol: str,
    name: str,
    industry: str,
    learnings: list[str],
) -> dict:
    """
    调用 report_agent 将所有 learnings 整合为结构化报告。

    Args:
        report_agent: 报告生成 Agent
        symbol: 股票代码
        name: 股票名称
        industry: 所属行业
        learnings: 去重后的全部知识点

    Returns:
        报告 JSON dict（不含 meta 字段）
    """
    user_message = (
        f"请为股票 {symbol} {name}（{industry}行业）"
        f"生成结构化的网络深度搜索研究报告。\n\n"
        f"以下是通过多轮深度搜索积累的全部 {len(learnings)} 个知识点：\n\n"
        f"<learnings>\n"
    )
    for i, learning in enumerate(learnings, 1):
        user_message += f"{i}. {learning}\n"
    user_message += "</learnings>\n"

    # 调用 Agent — 这里使用标准 json.loads 而不是 Pydantic 模型，
    # 因为 report_agent 输出的 JSON 不含 meta 字段，
    # meta 由调用方填充后再组装为 WebResearchResult
    try:
        thread = report_agent.get_new_thread()
        response = await report_agent.run(message=user_message, thread=thread)
        raw_text = response.text
        json_str = extract_json_str(raw_text)
        report_dict = json.loads(json_str)  # 使用标准 json.loads，不是 Pydantic
        return report_dict
    except json.JSONDecodeError as e:
        # json.loads() 抛出 JSONDecodeError（标准库异常）
        logger.error(f"Report generation failed: invalid JSON - {e}")
        raise ReportGenerationError(
            symbol=symbol, 
            cause=e,
            learnings_count=len(learnings)
        ) from e
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise ReportGenerationError(
            symbol=symbol,
            cause=e,
            learnings_count=len(learnings)
        ) from e
```

---

## 六、模块入口 — run_web_research

**注意：** 异常类统一定义于 `stock_analyzer/exceptions.py`，各模块仅 import，不重复定义。

```python
import asyncio
import json
from datetime import datetime
from stock_analyzer.logger import logger
from stock_analyzer.exceptions import (
    WebResearchError,
    ReportGenerationError,
)


async def run_web_research(
    symbol: str,
    name: str,
    industry: str,
    breadth: int = DEFAULT_BREADTH,
    depth: int = DEFAULT_DEPTH,
) -> WebResearchResult:
    """
    模块B 对外入口：对指定股票执行网络深度搜索，返回结构化研究报告。

    流程：
    1. 初始化 LLM 客户端和 3 个 Agent
    2. 定义 5 个搜索主题
    3. 并行执行 5 个主题的 deep_research
    4. 合并去重所有 learnings
    5. 调用 report_agent 生成最终报告（失败时使用降级报告）
    6. 组装 meta 信息，强制降级检查（learnings < 5 时置信度标记为"低"）
    7. 返回 WebResearchResult

    Args:
        symbol: 股票代码（纯6位数字）
        name: 股票名称
        industry: 所属行业
        breadth: 每主题每轮查询数（默认3）
        depth: 每主题递归深度（默认2）

    Returns:
        WebResearchResult（Pydantic 模型对象）
        
    注意：
        本函数只返回模型对象，不自动保存为JSON文件。
        如需保存，调用方应使用：
        result.model_dump_json() 或 json.dumps(result.model_dump())
    """
    start_time = datetime.now()
    logger.info(f"Starting web research for {symbol} {name} ({industry})")

    # ── Step 1: 初始化 ──
    openai_client = create_openai_client()

    query_client = create_chat_client(openai_client, MODEL_QUERY_AGENT)
    extract_client = create_chat_client(openai_client, MODEL_EXTRACT_AGENT)
    report_client = create_chat_client(openai_client, MODEL_REPORT_AGENT)

    query_agent = create_query_agent(query_client)
    extract_agent = create_extract_agent(extract_client)
    report_agent = create_report_agent(report_client)

    # ── Step 2: 定义搜索主题 ──
    topics = [
        (
            f"{name}（股票代码{symbol}）近期重大新闻，"
            f"包括正面和负面影响股价的事件"
        ),
        (
            f"{name} 核心竞争力分析，护城河类型，"
            f"在{industry}行业中的市场地位和竞争优势"
        ),
        (
            f"{industry}行业发展前景，政策环境，市场趋势，"
            f"行业增长驱动力和主要风险"
        ),
        (
            f"{name} 风险事件，包括监管处罚、诉讼纠纷、"
            f"管理层变动、财务风险等负面信息"
        ),
        (
            f"{name} 券商研报、机构评级、目标价、"
            f"分析师对该股的投资观点和评级变化"
        ),
    ]

    # ── Step 3: 并行执行 Deep Research ──
    semaphore = asyncio.Semaphore(TOPIC_CONCURRENCY_LIMIT)

    async def research_topic(topic: str) -> ResearchResult:
        async with semaphore:
            return await deep_research(
                query_agent=query_agent,
                extract_agent=extract_agent,
                query=topic,
                breadth=breadth,
                depth=depth,
            )

    tasks = [research_topic(topic) for topic in topics]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # ── Step 4: 合并去重 + 成功率检查 ──
    all_learnings: set[str] = set()
    all_urls: set[str] = set()

    for i, result in enumerate(results):
        if isinstance(result, ResearchResult):
            all_learnings.update(result.learnings)
            all_urls.update(result.visited_urls)
            logger.info(
                f"Topic {i+1} completed: "
                f"{len(result.learnings)} learnings, "
                f"{len(result.visited_urls)} urls"
            )
        elif isinstance(result, asyncio.CancelledError):
            # 取消异常必须向上传播，不能被吞掉
            logger.warning(f"Topic {i+1} was cancelled, propagating CancelledError")
            raise result
        elif isinstance(result, Exception):
            logger.error(f"Topic {i+1} failed: {result}")

    unique_learnings = list(all_learnings)
    unique_urls = list(all_urls)

    # 成功主题数统计（必须是 ResearchResult 且有有效 learnings）
    successful_topics = sum(
        1 for r in results 
        if isinstance(r, ResearchResult) and len(r.learnings) > 0
    )
    
    # 全部主题失败保护
    if successful_topics == 0:
        raise WebResearchError(
            f"All {len(topics)} topics failed, cannot generate report for {symbol}"
        )
    
    # 知识点数量过少警告（后续会在 Step 6 强制标记为低置信度）
    if len(unique_learnings) < 5:
        logger.warning(
            f"Only {len(unique_learnings)} learnings collected "
            f"({successful_topics}/{len(topics)} topics succeeded), "
            f"report quality may be low"
        )

    logger.info(
        f"All topics done: {len(unique_learnings)} unique learnings, "
        f"{len(unique_urls)} unique urls, "
        f"{successful_topics}/{len(topics)} topics succeeded"
    )

    # ── Step 5: 生成最终报告（带降级处理）──
    is_fallback = False
    try:
        report_dict = await generate_report(
            report_agent=report_agent,
            symbol=symbol,
            name=name,
            industry=industry,
            learnings=unique_learnings,
        )
    except ReportGenerationError as e:
        logger.error(f"Report generation failed, using fallback: {e}")
        # 降级：返回基础结构，标记为低可信度
        is_fallback = True
        report_dict = _create_fallback_report(
            learnings=unique_learnings,
            error_message=str(e.cause)
        )

    # ── Step 6: 组装 meta 并构建最终输出 ──
    meta = SearchMeta(
        symbol=symbol,
        name=name,
        search_time=start_time.isoformat(),
        search_config=SearchConfig(
            topics_count=len(topics),
            breadth=breadth,
            depth=depth,
            successful_topics=successful_topics,  # 记录成功主题数
        ),
        total_learnings=len(unique_learnings),
        total_sources_consulted=len(unique_urls),
        raw_learnings=unique_learnings if is_fallback else None,  # 降级时保存原始 learnings
    )

    report_dict["meta"] = meta.model_dump()
    
    # 强制降级逻辑：learnings 过少时，强制标记为低置信度
    if len(unique_learnings) < 5:
        logger.warning(f"Forcing search_confidence to '低' due to insufficient learnings: {len(unique_learnings)}")
        report_dict["search_confidence"] = "低"
    
    try:
        final_result = WebResearchResult.model_validate(report_dict)
    except Exception as e:
        logger.error(f"Final result validation failed: {e}")
        raise WebResearchError(
            f"Failed to validate final report for {symbol}: {e}"
        ) from e

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"Web research completed in {elapsed:.1f}s")

    return final_result


def _create_fallback_report(learnings: list[str], error_message: str) -> dict:
    """
    当报告生成失败时，创建降级报告。
    
    返回最小化的报告结构。原始 learnings 列表不在此处返回，
    而是由 run_web_research() 在组装 meta 时填充到 meta.raw_learnings 字段。
    
    注意：
    - 采用"拼接后统一截断"策略，确保 description 最终长度 <= 500 字符
    - 逻辑简单清晰，易于测试和维护
    """
    # 拼接 base_msg 和 error_message
    base_msg = f"报告生成失败，共收集到 {len(learnings)} 条信息，请查看原始数据。错误："
    description = base_msg + error_message
    
    # 统一截断：确保最终长度不超过 500
    if len(description) > 500:
        description = description[:497] + "..."
    
    return {
        "news_summary": {
            "positive": [],
            "negative": [],
            "neutral": [],
        },
        "competitive_advantage": {
            "description": description,  # 最终长度保证 <= 500
            "moat_type": "未知",
            "market_position": "未知",
        },
        "industry_outlook": {
            "industry": "未知",
            "outlook": "未知",
            "key_drivers": [],
            "key_risks": [],
        },
        "risk_events": {
            "regulatory": "报告生成失败",
            "litigation": "报告生成失败",
            "management": "报告生成失败",
            "other": f"原始learnings数量: {len(learnings)}",
        },
        "analyst_opinions": {
            "buy_count": 0,
            "hold_count": 0,
            "sell_count": 0,
            "average_target_price": None,
            "recent_reports": [],
        },
        "search_confidence": "低",
    }
```

---

## 七、完整执行示例

### 7.1 场景设置

**输入：** `symbol="000001"`, `name="平安银行"`, `industry="银行"`
**参数：** `breadth=3, depth=2`

### 7.2 主题 T1（近期新闻）执行过程

#### 第1层 (depth=2, breadth=3)

**generate_serp_queries 输入：**

```
请为以下研究主题生成 3 个搜索查询。

<topic>
平安银行（股票代码000001）近期重大新闻，包括正面和负面影响股价的事件
</topic>
```

**generate_serp_queries 输出：**

```json
{
  "queries": [
    {
      "query": "平安银行 2025年 最新消息 业绩",
      "research_goal": "了解平安银行最新的业绩表现和经营动态"
    },
    {
      "query": "平安银行 利好 利空 重大事件 2025",
      "research_goal": "搜索近期影响股价的正面和负面事件"
    },
    {
      "query": "平安银行 股价 异动 公告",
      "research_goal": "查找近期股价异动相关公告和市场反应"
    }
  ]
}
```

**Tavily 搜索（3次并行）→ extract_agent 提取（3次并行）**

**提取结果（示例，查询A）：**

```json
{
  "learnings": [
    "平安银行2024年全年净利润445.1亿元，同比增长2.1%，营收1600亿元同比下降8.5%",
    "平安银行2024年零售AUM突破4.2万亿元，信用卡流通卡量超6500万张",
    "平安银行2024Q4不良贷款率1.06%，较Q3下降2个基点，拨备覆盖率261%"
  ],
  "follow_up_questions": [
    "平安银行营收下降8.5%的主要原因是什么？",
    "平安银行零售转型对利润贡献如何？",
    "平安银行房地产贷款敞口规模及风险状况？"
  ]
}
```

**第1层 learnings 累计：** ~9 个（3 个查询 × ~3 个 learnings）

#### 第2层 (depth=1, breadth=1)

3 个分支各自独立递归，每个分支生成 1 个更精准的查询。

**分支A → generate_serp_queries 输入（带 learnings）：**

```
请为以下研究主题生成 1 个搜索查询。

<topic>
Previous research goal: 了解平安银行最新的业绩表现和经营动态
Follow-up research directions:
- 平安银行营收下降8.5%的主要原因是什么？
- 平安银行零售转型对利润贡献如何？
- 平安银行房地产贷款敞口规模及风险状况？
</topic>

以下是前几轮研究中已获得的知识点，请据此生成更有针对性的查询，避免搜索已知信息：
<learnings>
- 平安银行2024年全年净利润445.1亿元，同比增长2.1%，营收1600亿元同比下降8.5%
- 平安银行2024年零售AUM突破4.2万亿元，信用卡流通卡量超6500万张
- ... (共约9条)
</learnings>
```

**generate_serp_queries 输出：**

```json
{
  "queries": [
    {
      "query": "平安银行 2024年报 营收下降原因 净息差 手续费收入",
      "research_goal": "深入了解营收下降的具体构成因素"
    }
  ]
}
```

**第2层 learnings 累计：** ~18 个（去重后 ~15 个）

**depth 降为 0，停止递归。**

### 7.3 所有主题完成后合并

| 主题 | 原始 learnings | 去重后 |
|------|---------------|--------|
| T1 近期新闻 | ~18 | ~15 |
| T2 竞争优势 | ~18 | ~14 |
| T3 行业前景 | ~18 | ~16 |
| T4 风险事件 | ~18 | ~12 |
| T5 机构观点 | ~18 | ~13 |
| **合并** | ~90 | **~60** |

### 7.4 生成最终报告

**report_agent 输入（节选）：**

```
请为股票 000001 平安银行（银行行业）生成结构化的网络深度搜索研究报告。

以下是通过多轮深度搜索积累的全部 60 个知识点：

<learnings>
1. 平安银行2024年全年净利润445.1亿元，同比增长2.1%，营收1600亿元同比下降8.5%
2. 平安银行2024年零售AUM突破4.2万亿元，信用卡流通卡量超6500万张
3. 平安银行2024Q4不良贷款率1.06%，较Q3下降2个基点，拨备覆盖率261%
... 共60条 ...
</learnings>
```

**report_agent 输出：** 结构化 JSON → 解析为 `WebResearchResult`

---

## 八、异常处理设计

### 8.1 异常分类与处理策略

| 异常类型 | 来源 | 处理策略 | 说明 |
|---------|------|---------|------|
| `TavilySearchError` | Tavily API 调用失败 | 跳过该查询分支，继续其他分支 | 封装所有 Tavily 相关异常 |
| **可重试异常** | | | **异常分派优化** |
| `asyncio.TimeoutError` | `asyncio.wait_for()` 超时 | **单独 except 分支**，自动重试1次 | ⚠️ 不在 `RETRYABLE_EXCEPTIONS` 元组中（避免重复） |
| `ConnectionError` | 网络连接失败（标准库） | 在 `tavily_search()` 内自动重试1次 | ✅ 在 `RETRYABLE_EXCEPTIONS` 中 |
| `OSError` | 网络 I/O 错误（标准库） | 在 `tavily_search()` 内自动重试1次 | ✅ 在 `RETRYABLE_EXCEPTIONS` 中 |
| `httpx.NetworkError` | HTTP 网络错误 | 在 `tavily_search()` 内自动重试1次 | ✅ **已启用**，项目依赖 httpx>=0.28.1 |
| `httpx.ConnectError` | HTTP 连接错误 | 在 `tavily_search()` 内自动重试1次 | ✅ **已启用**，项目依赖 httpx>=0.28.1 |
| `httpx.TimeoutException` | HTTP 超时 | 在 `tavily_search()` 内自动重试1次 | ✅ **已启用**，项目依赖 httpx>=0.28.1 |
| `httpx.RemoteProtocolError` | HTTP/2 协议错误 | 在 `tavily_search()` 内自动重试1次 | ✅ **已启用**，项目依赖 httpx>=0.28.1 |
| **不可重试异常（NON_RETRYABLE_EXCEPTIONS）** | | | **独立分支处理** |
| `httpx.HTTPStatusError` | HTTP 4xx/5xx 状态码错误 | 不重试，独立分支记录日志并立即失败 | ✅ **已启用**，项目依赖 httpx>=0.28.1 |
| `InvalidAPIKeyError` | API 密钥错误 | 不重试，独立分支记录日志并立即失败 | ✅ **已启用**，v0.7.21 @ 38627af |
| `MissingAPIKeyError` | 缺少 API 密钥 | 不重试，独立分支记录日志并立即失败 | ✅ **已启用**，v0.7.21 @ 38627af |
| `BadRequestError` | 请求格式错误 | 不重试，独立分支记录日志并立即失败 | ✅ **已启用**，v0.7.21 @ 38627af |
| `ForbiddenError` | 权限不足 | 不重试，独立分支记录日志并立即失败 | ✅ **已启用**，v0.7.21 @ 38627af |
| `UsageLimitExceededError` | 使用限制超出 | 不重试，独立分支记录日志并立即失败 | ✅ **已启用**，v0.7.21 @ 38627af |
| **已确认但不启用的异常** | | | **保持注释态** |
| ~~`TimeoutError`~~ (Tavily) | ~~超时错误~~ | 保持注释态 | ⚠️ **已确认但不启用**，与标准库重名 |
| ~~`NetworkError`~~ (Tavily) | ~~网络错误~~ | N/A | ❌ **不存在**，在 Tavily SDK v0.7.21 源码中未找到 |
| **其他异常（通用 Exception 分支）** | | | |
| 编程错误（`KeyError` 等） | 代码缺陷 | N/A | **不重试**，通用分支处理 |
| 其他未预期异常 | 未分类 | N/A | **不重试**，通用分支处理 |

**图例说明：**
- ✅ **已启用/已确认可用**：已在代码中的异常处理配置（`RETRYABLE_EXCEPTIONS` 或 `NON_RETRYABLE_EXCEPTIONS`）明确定义，项目依赖已满足，**不要删除**
- ❌ **不存在/不启用**：经官方源码确认不存在该异常类型，或因命名冲突等原因不启用
- ~~删除线~~：表示该异常不可用或不应使用

**\* 实施说明（httpx 异常 - 已强制启用）：**
1. ✅ **项目依赖已满足**：`httpx>=0.28.1`（见 `pyproject.toml`）
2. ✅ **代码中已导入**：`import httpx`（必须保留）
3. ✅ **异常配置已完成**：
   - `RETRYABLE_EXCEPTIONS` 中已包含 `httpx.ConnectError`, `httpx.NetworkError`, `httpx.TimeoutException`, `httpx.RemoteProtocolError`
   - `NON_RETRYABLE_EXCEPTIONS` 中已包含 `httpx.HTTPStatusError`
4. ⚠️ **维护注意**：不要删除 httpx 相关异常，否则网络错误不会重试或 API 错误处理不当

**\*\* 实施说明（Tavily SDK 异常 - ✅ 已启用建议启用的子集）：**

**确认来源：** 基于 [Tavily SDK v0.7.21 官方源码](https://github.com/tavily-ai/tavily-python/blob/38627afb7b88d8a57bad29380896210a9ae7badd/tavily/errors.py)（commit `38627af`，2026-01-28）

**异常配置已完成：**
1. ✅ **导入语句**：已添加 `from tavily import InvalidAPIKeyError, BadRequestError, ForbiddenError, MissingAPIKeyError, UsageLimitExceededError`（共5个）
2. ✅ **NON_RETRYABLE_EXCEPTIONS 元组**：已启用5个建议启用的 Tavily 异常（见上表）
3. ⚠️ **已确认但不启用**：TimeoutError（与标准库重名，使用 `asyncio.TimeoutError` 替代）
4. ✅ **独立 except 分支**：在 `tavily_search()` 中存在 `except NON_RETRYABLE_EXCEPTIONS` 分支，位于 `except Exception` 之前

**🔒 硬性规则（避免实施歧义）：**
- **若官方源码确认存在 且 推荐启用**：
  - 添加到 `RETRYABLE_EXCEPTIONS` 或 `NON_RETRYABLE_EXCEPTIONS` 元组
  - 若使用注释模板则取消注释，直接实施时可跳过注释步骤
  - 确保在文件顶部添加相应的 `import` 或 `from ... import` 语句
- **若官方源码确认存在 但 不建议启用**（如与标准库重名）：
  - **保持注释态**，在注释中说明不启用原因（见 `TimeoutError` 示例）
  - 不添加到异常元组，不导入
- **若官方源码确认不存在该异常类**：
  - **删除注释**（或标注 ❌ 不存在）
  - **不新增捕获分支**，统一由通用 `except Exception` 分支兜底
- **禁止"猜测性添加"**：所有异常类必须经官方文档或源码确认后才能启用，且需评估是否适合启用

**命名规范说明（✅ 基于官方文档 v0.7.21）：**

**通用规则（适用于大多数 Tavily 异常）：**
- ✅ **推荐写法**：`from tavily import InvalidAPIKeyError` + 直接使用 `InvalidAPIKeyError`
- ❌ **不推荐**：`import tavily` + 使用 `tavily.InvalidAPIKeyError`（会导致代码冗长）
- ❌ **错误写法**：`from tavily import InvalidAPIKeyError` + 使用 `tavily.InvalidAPIKeyError`（会导致 `NameError`）

**⚠️ 特例规则（仅用于命名冲突场景）：**
- 当异常名与 Python 标准库重名（如 `TimeoutError`）时，使用命名空间写法避免歧义：
  ```python
  from tavily import errors as tavily_errors  # 导入命名空间
  # 使用时：tavily_errors.TimeoutError（区别于标准库 TimeoutError）
  ```
- **适用场景**：仅 `TimeoutError` 一个异常（其他 Tavily 异常无重名问题）
- **注意**：本项目已确认 `TimeoutError` 不启用，此规则仅供参考

**📖 官方依据：**
- [tavily/__init__.py @ 38627af](https://github.com/tavily-ai/tavily-python/blob/38627afb7b88d8a57bad29380896210a9ae7badd/tavily/__init__.py)

**特别说明（不存在或不启用的异常）：**
- ⚠️ `TimeoutError`（Tavily SDK）：虽存在但与标准库重名，**不启用**（使用 `asyncio.TimeoutError` 即可）
  - 📄 源码确认：[tavily/errors.py @ 38627af, L21-L23](https://github.com/tavily-ai/tavily-python/blob/38627afb7b88d8a57bad29380896210a9ae7badd/tavily/errors.py#L21-L23)
  - 💡 **特例说明**：如需启用此异常，应使用命名空间导入（`from tavily import errors as tavily_errors` + `tavily_errors.TimeoutError`），这是唯一需要命名空间的异常，其他 Tavily 异常仍遵循通用规范（直接导入类名）
- ❌ `NetworkError`（Tavily SDK）：**不存在**于官方源码中（已通过完整源码确认），不要添加（使用 httpx 异常即可）
  - 📄 源码确认：[tavily/errors.py @ 38627af](https://github.com/tavily-ai/tavily-python/blob/38627afb7b88d8a57bad29380896210a9ae7badd/tavily/errors.py)（完整文件无此类）

---

### 8.1.1 LLM 与结果组装异常

| 异常类型 | 触发场景 | 处理策略 | 备注 |
|---------|---------|---------|------|
| `pydantic.ValidationError` | LLM 返回的 JSON 无效或不符合模型 | 在 `call_agent_with_model()` 内捕获，抛出 `AgentCallError` | Pydantic v2 统一异常（含 JSON 格式错误） |
| `json.JSONDecodeError` | 报告生成时 JSON 格式错误 | 抛出 `ReportGenerationError`，触发降级报告 | `generate_report()` 特例，使用 `json.loads()` |
| `AgentCallError` | LLM 调用失败（汇总异常） | 跳过该步骤，使用空结果 | 由 `call_agent_with_model()` 抛出 |
| `ReportGenerationError` | 报告生成失败 | 使用降级报告（`_create_fallback_report`） | 保留已收集的 learnings |
| `WebResearchError` | 最终校验失败 | 抛出异常，终止流程 | 无法降级（如所有主题失败） |

**说明：**
1. **`json.JSONDecodeError`** 仅出现在 `generate_report()` 中，因为该函数使用标准库 `json.loads()` 而非 Pydantic。其他所有 LLM 调用均使用 `call_agent_with_model()` + `model_validate_json()`，只会抛出 `ValidationError`（Pydantic v2）。
2. **`RETRYABLE_EXCEPTIONS`** 元组定义在 `tavily_client.py` 中，可根据项目实际使用的 HTTP 库（httpx、aiohttp 等）灵活调整。
3. **异常层次**：底层异常（如 `ValidationError`）被封装为业务异常（如 `AgentCallError`），便于上层统一处理。

### 8.2 核心原则

1. **不中断整体流程**：单个查询或分支的失败不应导致整个模块失败
2. **尽量返回部分结果**：即使只有 2/5 个主题成功，也应生成报告
3. **报告生成降级**：如果 LLM 生成报告失败，使用 `_create_fallback_report()` 返回基础结构
4. **自动重试**：Tavily 搜索失败时自动重试 1 次（含超时），2 秒间隔
5. **统一异常处理**：Pydantic v2 统一使用 `ValidationError`（包含 JSON 格式错误），通过 `error_type` 区分具体原因
6. **取消异常传播**：`asyncio.CancelledError` 必须向上传播，不应被当作普通失败吞掉（关键语义：用户取消 vs 任务失败）
7. **详细日志**：所有异常记录到 `logs/stock_analyzer.log`，包含重试信息和 `error_type`
8. **成功率记录**：在 `meta.search_config.successful_topics` 中记录成功主题数（用于质量评估）

### 8.2.1 Pydantic v2 异常处理说明

**重要：** Pydantic v2 的 `model_validate_json()` 对所有验证失败**统一抛出 `ValidationError`**，包括：

| 失败场景 | 示例输入 | ValidationError.errors()[0]['type'] |
|---------|---------|-------------------------------------|
| JSON 格式错误 | `{invalid json` | `'json_invalid'` |
| 字段缺失 | `{}` 缺少必填字段 | `'missing'` |
| 类型不匹配 | `{"score": "abc"}` 应为 float | `'float_parsing'` |
| 约束违反 | `{"score": 15}` 但限制 `le=10` | `'less_than_equal'` |

**与 Pydantic v1 的区别：**
- ❌ **Pydantic v1**：JSON 格式错误时抛出 `json.JSONDecodeError`
- ✅ **Pydantic v2**：所有错误统一为 `ValidationError`，通过 `error_type` 区分

**特殊情况：`generate_report()` 函数**

该函数使用标准库 `json.loads()` 而非 Pydantic 的 `model_validate_json()`，因为其返回的 JSON 不含 `meta` 字段，需要由调用方填充后再组装为完整的 `WebResearchResult`。因此这里**仍然需要捕获 `JSONDecodeError`**：

```python
# generate_report() — 特殊情况，使用 json.loads
try:
    json_str = extract_json_str(raw_text)
    report_dict = json.loads(json_str)  # ← 不是 Pydantic，仍需捕获 JSONDecodeError
    return report_dict
except json.JSONDecodeError as e:
    raise ReportGenerationError(...) from e
except Exception as e:
    raise ReportGenerationError(...) from e
```

**其他 Agent 调用（call_agent_with_model）：**

```python
from pydantic import ValidationError

try:
    result = model_cls.model_validate_json(json_str)  # ← Pydantic v2
except ValidationError as e:
    # 统一捕获，通过 error_type 区分具体错误
    logger.error(
        f"Validation failed: {e.error_count()} errors, "
        f"first error type: {e.errors()[0]['type']}"
    )
```

**日志示例：**

```
# JSON 格式错误
ERROR - Agent 'query_generator' validation failed: 1 errors
First error: {'type': 'json_invalid', 'loc': (), 'msg': 'Invalid JSON'}

# 字段类型错误
ERROR - Agent 'knowledge_extractor' validation failed: 2 errors
First error: {'type': 'float_parsing', 'loc': ('score',), 'msg': 'Input should be a valid number'}

# 字段缺失
ERROR - Agent 'report_generator' validation failed: 5 errors
First error: {'type': 'missing', 'loc': ('news_summary',), 'msg': 'Field required'}
```

**优势：**
- ✅ 错误信息更结构化（`type`、`loc`、`msg`）
- ✅ 便于统计和监控（按 `error_type` 分类）
- ✅ 便于针对性优化提示词

**注意：** `generate_report()` 使用标准库 `json.loads()` 而非 Pydantic，因此仍需捕获 `json.JSONDecodeError`。

### 8.3 降级策略详解

#### 8.3.1 主题级别降级（已在主流程实现）

**位置：** `run_web_research()` Step 4

```python
# 统计成功主题数（必须是 ResearchResult 且有有效 learnings）
successful_topics = sum(
    1 for r in results 
    if isinstance(r, ResearchResult) and len(r.learnings) > 0
)

# 全部主题失败保护 ← 关键保护逻辑
if successful_topics == 0:
    raise WebResearchError(
        f"All {len(topics)} topics failed, cannot generate report for {symbol}"
    )

# 知识点数量过少警告
if len(unique_learnings) < 5:
    logger.warning(
        f"Only {len(unique_learnings)} learnings collected "
        f"({successful_topics}/{len(topics)} topics succeeded), "
        f"report quality may be low"
    )
    # 仍然尝试生成报告，后续会在 Step 6 强制标记 search_confidence = "低"
```

**成功判定标准：**
- 主题必须同时满足：
  1. 返回 `ResearchResult` 对象（类型正确）
  2. `len(r.learnings) > 0`（有有效知识点）
- **关键修复**：避免把"返回空结果的失败主题"误判为成功

**逻辑说明：**
- ✅ **全部失败（0/5）**：所有主题返回空 learnings，抛出 `WebResearchError`，终止流程
- ⚠️ **部分失败（1-4/5）**：继续，但记录日志和成功率
- ⚠️ **知识点过少（< 5 条）**：记录警告，继续生成报告，在 Step 6 强制覆盖置信度为 "低"

**记录到 meta：** `search_config.successful_topics` 字段

#### 8.3.2 报告生成级别降级（已在主流程实现）

**位置：** `run_web_research()` Step 5 + Step 6

```python
# Step 5: generate_report 失败时的降级处理
is_fallback = False
try:
    report_dict = await generate_report(
        report_agent=report_agent,
        symbol=symbol,
        name=name,
        industry=industry,
        learnings=unique_learnings,
    )
except ReportGenerationError as e:
    logger.error(f"Report generation failed, using fallback: {e}")
    is_fallback = True
    # 使用降级报告（返回最小化结构）
    report_dict = _create_fallback_report(
        learnings=unique_learnings,
        error_message=str(e.cause)
    )

# Step 6: 组装 meta 时，降级报告需要填充 raw_learnings
meta = SearchMeta(
    # ...
    raw_learnings=unique_learnings if is_fallback else None,  # 仅降级时保存
)
```

**降级数据流向：**
```
降级触发 → _create_fallback_report() 返回最小化结构
          ↓
          设置 is_fallback = True
          ↓
          meta.raw_learnings = unique_learnings（60条原始知识点）
          ↓
          最终 JSON 中 meta.raw_learnings 包含完整数据
```

**降级报告特点：**
- 保留所有收集到的 learnings 在 `meta.raw_learnings` 字段（便于后续人工分析）
- 返回最小化的结构化数据（**空列表/默认值，如 `news_summary.positive = []`**）
- `search_confidence` 标记为 "低"
- 在 `competitive_advantage.description` 中说明降级原因（已截断到 500 字符）
- **关键识别标志**：`meta.raw_learnings is not None`

#### 8.3.3 置信度强制降级（已在主流程实现）

**位置：** `run_web_research()` Step 6（meta 组装后）

```python
# 在 meta 组装完成、最终校验之前
report_dict["meta"] = meta.model_dump()

# 强制降级逻辑：learnings 过少时，强制标记为低置信度
if len(unique_learnings) < 5:
    logger.warning(f"Forcing search_confidence to '低' due to insufficient learnings: {len(unique_learnings)}")
    report_dict["search_confidence"] = "低"

# 最终 Pydantic 校验
final_result = WebResearchResult.model_validate(report_dict)
```

**触发条件：**
- `len(unique_learnings) < 5`（无论 Agent 返回的置信度是什么）

**作用：**
- 强制覆盖 `search_confidence` 为 "低"，确保数据质量标识准确
- 避免 LLM 基于少量数据自信地给出"高"或"中"置信度

#### 8.3.4 最终校验失败（已在主流程实现）

**位置：** `run_web_research()` Step 6

```python
# Pydantic 校验失败时无法降级，直接抛出异常
try:
    final_result = WebResearchResult.model_validate(report_dict)
except Exception as e:
    logger.error(f"Final result validation failed: {e}")
    raise WebResearchError(
        f"Failed to validate final report for {symbol}: {e}"
    ) from e
```

**原因：** 如果连降级报告都无法通过 Pydantic 校验，说明数据结构严重错误，无法继续。

---

### 8.4 超时与重试策略

#### 8.4.1 Tavily 搜索超时控制

**实现位置：** `tavily_search()` 函数

```python
# 使用 asyncio.wait_for 实现超时控制
response = await asyncio.wait_for(
    client.search(...),
    timeout=TAVILY_TIMEOUT,  # 30秒
)
```

**超时配置：** `TAVILY_TIMEOUT = 30.0` 秒（config.py）

#### 8.4.2 自动重试机制

**策略：** 失败后自动重试 1 次（共 2 次尝试）

**可重试异常（Retryable）- 网络层瞬时故障：**

**设计目标：** 所有网络层瞬时故障都应重试，确保系统对临时网络问题的鲁棒性。

**实施要求：** 
1. ✅ 根据项目实际依赖明确启用相应异常（httpx 异常已全部启用）
2. ✅ Tavily SDK 异常已确认并启用**建议启用的子集**（基于官方源码 v0.7.21）
   - 已启用：5个异常（InvalidAPIKeyError, MissingAPIKeyError, BadRequestError, ForbiddenError, UsageLimitExceededError）
   - 已确认但不启用：TimeoutError（与标准库重名）
3. ⚠️ 新增依赖时及时更新此列表

| 异常类型 | 来源 | 说明 | 实施状态 |
|---------|------|------|---------|
| `asyncio.TimeoutError` | `asyncio.wait_for()` | asyncio 超时 | ✅ **单独处理**（不在 RETRYABLE_EXCEPTIONS 中） |
| `ConnectionError` | 标准库 | 网络连接失败 | ✅ 已启用 |
| `OSError` | 标准库 | 网络 I/O 错误 | ✅ 已启用 |
| `httpx.ConnectError` | httpx 库 | HTTP 连接错误 | ✅ **已启用**（项目依赖 httpx>=0.28.1） |
| `httpx.NetworkError` | httpx 库 | HTTP 网络错误 | ✅ **已启用**（项目依赖 httpx>=0.28.1） |
| `httpx.TimeoutException` | httpx 库 | HTTP 超时 | ✅ **已启用**（项目依赖 httpx>=0.28.1） |

**不可重试异常（Non-Retryable）- API 业务错误或编程错误：**

| 异常类型 | 来源 | 原因 | 状态 |
|---------|------|------|------|
| `httpx.HTTPStatusError` | httpx 库 | HTTP 4xx/5xx 状态码错误 | ✅ 已启用 |
| `InvalidAPIKeyError` | Tavily SDK | API 密钥无效（配置问题） | ✅ 已确认可用（v0.7.21 @ 38627af） |
| `MissingAPIKeyError` | Tavily SDK | 缺少 API 密钥（配置问题） | ✅ 已确认可用（v0.7.21 @ 38627af） |
| `BadRequestError` | Tavily SDK | 请求格式错误（代码问题） | ✅ 已确认可用（v0.7.21 @ 38627af） |
| `ForbiddenError` | Tavily SDK | 权限不足 | ✅ 已确认可用（v0.7.21 @ 38627af） |
| `UsageLimitExceededError` | Tavily SDK | 使用限制超出（配额不足） | ✅ 已确认可用（v0.7.21 @ 38627af） |
| `KeyError`, `AttributeError` | 代码缺陷 | 编程错误（必须修复） | N/A（编程错误） |
| 其他 `Exception` | 未预期 | 需要排查根因 | N/A（通用捕获） |

**注：** 
1. **httpx 异常**：项目已依赖 `httpx>=0.28.1`（见 `pyproject.toml`），代码中**必须** `import httpx` 并启用 httpx 异常。✅ **已完成**
2. **Tavily SDK 异常**：✅ **已启用建议启用的子集**（基于官方源码 v0.7.21，commit `38627af`）
   - **已启用（5个）**：InvalidAPIKeyError, BadRequestError, ForbiddenError, MissingAPIKeyError, UsageLimitExceededError
   - **已确认但不启用（1个）**：TimeoutError（与标准库重名，使用 `asyncio.TimeoutError` 替代）
   - **标准导入方式**：
     ```python
     from tavily import InvalidAPIKeyError, BadRequestError, ForbiddenError, MissingAPIKeyError, UsageLimitExceededError
     ```
   - 📖 **可追溯性链接**：[tavily/errors.py @ 38627af](https://github.com/tavily-ai/tavily-python/blob/38627afb7b88d8a57bad29380896210a9ae7badd/tavily/errors.py)

**重试间隔：** 2 秒（`await asyncio.sleep(2)`）

**设计原则：**
1. **网络层瞬时故障**（连接失败、超时）→ **重试**（可能恢复）
2. **API 业务错误**（密钥错误、请求格式错误）→ **不重试**（需要修改配置或代码）
3. **编程错误**（KeyError 等）→ **不重试**，立即抛出（避免掩盖缺陷）

**代码实现（推荐）：**

```python
# 在文件开头定义可重试异常元组（可根据实际使用的库调整）
# 
# 注意：asyncio.TimeoutError 不在此元组中，它有专门的 except 分支，
# 以便提供更明确的超时日志和独立的重试控制
RETRYABLE_EXCEPTIONS = (
    ConnectionError,       # 标准库连接错误
    OSError,               # 标准库 I/O 错误（包含 TimeoutError 子类）
    # ✅ httpx 异常（项目依赖 httpx>=0.28.1，必须启用）
    httpx.ConnectError,
    httpx.NetworkError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
)

# 重试循环
for attempt in range(max_retries + 1):
    try:
        response = await asyncio.wait_for(...)
        return results  # ✅ 成功，直接返回
    
    except asyncio.TimeoutError as e:
        # ✅ 单独处理超时（清晰的日志，不在 RETRYABLE_EXCEPTIONS 中）
        last_error = e
        if attempt < max_retries:
            logger.warning(f"Timeout (attempt {attempt + 1}/{max_retries + 1}), retrying...")
            await asyncio.sleep(2)
        else:
            logger.error(f"Timeout after {max_retries + 1} attempts")
    
    except RETRYABLE_EXCEPTIONS as e:
        # 网络层错误，可重试
        last_error = e
        if attempt < max_retries:
            logger.warning(f"Retryable error: {type(e).__name__}, retrying...")
            await asyncio.sleep(2)
        else:
            logger.error(f"Failed after {max_retries + 1} attempts: {e}")
    
    except NON_RETRYABLE_EXCEPTIONS as e:
        # ❌ 已知的不可重试异常（API 错误、配置错误）
        logger.error(f"Non-retryable API/config error: {type(e).__name__}: {e}")
        raise TavilySearchError(query=query, attempts=attempt + 1, cause=e) from e
    
    except Exception as e:
        # ❌ 其他未预期异常（编程错误等）
        logger.error(f"Unexpected error: {type(e).__name__}: {e}")
        raise TavilySearchError(query=query, attempts=attempt + 1, cause=e) from e

# 循环结束，所有重试都失败
raise TavilySearchError(query=query, attempts=max_retries + 1, cause=last_error)
```

**实施建议（四层异常处理结构）：**
1. **第一层**：`except asyncio.TimeoutError` - 超时异常单独处理，提供明确的超时日志
2. **第二层**：`except RETRYABLE_EXCEPTIONS` - 网络层瞬时故障，可重试
3. **第三层**：`except NON_RETRYABLE_EXCEPTIONS` - API/配置错误，不重试，明确分类
4. **第四层**：`except Exception` - 其他未预期异常（编程错误），不重试
5. ✅ 根据项目实际使用的 HTTP 库（httpx）调整 `RETRYABLE_EXCEPTIONS`（已完成）
6. ✅ Tavily SDK 建议启用的异常类（经官方源码确认的5个）已添加到 `NON_RETRYABLE_EXCEPTIONS` 元组中
7. ✅ 代码注释清晰，说明了哪些异常可重试、哪些不可重试及原因
8. 🔒 **硬性规则**：所有第三方 SDK 异常必须经官方文档/源码确认后才能添加，且需评估是否适合启用（如避免与标准库重名）

#### 8.4.3 实施建议：根据实际依赖调整异常类型

**基础实现（仅标准库异常）：**
```python
# 注意：asyncio.TimeoutError 不在此元组中（有专门的 except 分支）
RETRYABLE_EXCEPTIONS = (
    ConnectionError,  # 标准库连接错误
    OSError,          # 标准库 I/O 错误（包含 TimeoutError 子类）
)
```

**项目当前配置（已使用 httpx>=0.28.1，优化后无重复）：**
```python
import httpx  # ← 必须导入
# Tavily 异常导入（✅ 官方推荐方式，基于 v0.7.21）
from tavily import (
    InvalidAPIKeyError,
    MissingAPIKeyError,
    BadRequestError,
    ForbiddenError,
    UsageLimitExceededError,
)

# 注意：asyncio.TimeoutError 不在此元组中（有单独的 except 分支）
RETRYABLE_EXCEPTIONS = (
    ConnectionError,         # 标准库连接错误
    OSError,                 # 标准库 I/O 错误
    # ✅ httpx 异常（已启用，不要删除）
    httpx.ConnectError,      # 更精确的连接错误
    httpx.NetworkError,      # HTTP 网络错误（基类）
    httpx.TimeoutException,  # HTTP 超时
    httpx.RemoteProtocolError,  # HTTP/2 协议错误
)

# 不可重试异常：API 错误、配置错误（立即失败）
# 注意：此元组会在代码中使用，提供明确的错误分类
NON_RETRYABLE_EXCEPTIONS = (
    httpx.HTTPStatusError,   # HTTP 4xx/5xx 状态码错误（已启用）
    # Tavily SDK 特定异常（✅ 已确认并启用，基于官方源码 v0.7.21）
    # 🔒 硬性规则：仅添加经官方源码确认存在的异常类，不存在时保持注释态或删除
    # ⚠️ 注意：使用直接导入的类名（见上方 import），不使用 tavily.异常名
    InvalidAPIKeyError,
    MissingAPIKeyError,
    BadRequestError,
    ForbiddenError,
    UsageLimitExceededError,
)
```

**关键设计原则：**
1. ⚠️ **`asyncio.TimeoutError` 不在 `RETRYABLE_EXCEPTIONS` 中**：使用单独的 `except asyncio.TimeoutError` 分支处理，提供更清晰的超时日志
2. ⚠️ **不包含标准库 `TimeoutError`**：因为它是 `OSError` 的子类（Python 3.3+），已被 `OSError` 覆盖，无需单独列出
3. ✅ **只包含真正需要重试的网络层异常**：避免过宽的异常捕获

**实施步骤：**
1. ✅ **确认项目依赖**：检查 `pyproject.toml` 已安装 `httpx>=0.28.1`（已满足）
2. ✅ **确认代码导入**：确认 `tavily_client.py` 中已存在并保留 `import httpx`
3. ✅ **确认异常元组配置**：验证 `RETRYABLE_EXCEPTIONS` 中：
   - ✅ 包含所有 httpx 异常（`httpx.ConnectError`, `httpx.NetworkError`, `httpx.TimeoutException`, `httpx.RemoteProtocolError`）
   - ⚠️ **不包含** `asyncio.TimeoutError`（它有单独的 `except` 分支）
4. ✅ **确认异常处理顺序**：代码中有单独的 `except asyncio.TimeoutError` 分支（在 `except RETRYABLE_EXCEPTIONS` 之前）
5. ✅ **测试验证**：确保网络错误会重试、超时会重试、API 错误不重试

**🔒 通用硬性规则（避免实施歧义）：**
- **添加异常的前提**：必须先查看官方文档或源码，确认异常类型确实存在**且适合启用**
- **确认存在但不建议启用时**：保持注释态，在注释中说明原因（如与标准库重名）
- **确认不存在时的处理**：删除注释行或标注 ❌ 不存在，依赖通用 `except Exception` 分支兜底
- **严禁猜测性添加**：不要基于"可能有"、"应该有"或"其他库有"等理由添加未经确认的异常类
- **维护原则**：定期审查第三方 SDK 版本更新，确认异常类型变化及启用建议

#### 8.4.4 日志输出示例

**首次成功：**
```
INFO - Tavily search '平安银行 最新消息...' returned 5 results
```

**重试后成功：**
```
WARNING - Tavily search '平安银行 最新消息...' timeout (attempt 1/2), retrying...
INFO - Tavily search '平安银行 最新消息...' succeeded on retry 1, returned 5 results
```

**全部失败：**
```
WARNING - Tavily search '平安银行 最新消息...' failed: ConnectError (attempt 1/2), retrying...
ERROR - Tavily search '平安银行 最新消息...' failed after 2 attempts: ConnectError
```

#### 8.4.4 LLM 调用超时

**配置：** `API_TIMEOUT = 120.0` 秒

LLM 调用的超时由 `AsyncOpenAI` 客户端内置处理：

```python
AsyncOpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
    timeout=API_TIMEOUT,  # 120秒
)
```

**不需要手动 `wait_for`**，SDK 已实现超时控制。

---

### 8.5 容错层级总结

| 层级 | 失败场景 | 处理策略 | 代码位置 |
|------|---------|---------|---------|
| 1️⃣ 查询级别 | 单个 Tavily 查询失败 | 跳过，继续其他查询 | `deep_research()` |
| 2️⃣ 主题级别 | 1-4个主题失败（返回空 learnings） | 警告，继续处理 | `run_web_research()` Step 4 |
| 🚫 全部主题失败 | 5个主题全部返回空 learnings | **抛出异常，终止** | `run_web_research()` Step 4 |
| ⚠️ 知识点过少 | learnings < 5 | 继续处理，**强制覆盖** `search_confidence = "低"` | `run_web_research()` Step 6 |
| 3️⃣ 报告生成级别 | LLM 生成报告失败 | **降级报告**（置信度 "低"，新闻列表为空，`raw_learnings` 保存原始数据） | `run_web_research()` Step 5 |
| 🚫 最终校验失败 | Pydantic 校验失败 | **抛出异常，终止** | `run_web_research()` Step 6 |

---

## 九、文件结构

模块B的代码文件规划（在 `stock_analyzer/` 目录下）：

```
stock_analyzer/
├── module_b_websearch.py       # 模块B主入口：run_web_research()
├── deep_research.py            # 核心递归逻辑：deep_research()
│                                 generate_serp_queries()
│                                 process_serp_result()
├── tavily_client.py            # Tavily API 封装：tavily_search()
│                                 RETRYABLE_EXCEPTIONS 常量
├── agents.py                   # Agent 工厂：create_query_agent() 等
├── prompts.py                  # 所有提示词常量
├── models.py                   # Pydantic 数据模型（含 SearchConfig）
├── llm_helpers.py              # LLM 调用辅助：call_agent_with_model()
│                                 extract_json_str() (⚠️ 使用 itertools.chain)
├── exceptions.py               # 自定义异常类
├── logger.py                   # 日志配置：setup_logger()
└── config.py                   # 配置常量
```

| 文件 | 核心内容 | 依赖 |
|------|---------|------|
| `module_b_websearch.py` | `run_web_research()` 入口 | 所有其他文件 |
| `deep_research.py` | `deep_research()` 递归函数 | `tavily_client`, `llm_helpers`, `models`, `logger` |
| `tavily_client.py` | `tavily_search()` | `tavily-python`, `config`, `logger` |
| `agents.py` | Agent 工厂函数 | `agent_framework`, `prompts`, `config` |
| `prompts.py` | 3 个系统提示词 | 无 |
| `models.py` | 全部 Pydantic 模型 | `pydantic` |
| `llm_helpers.py` | `call_agent_with_model()` | `agent_framework`, `logger` |
| `logger.py` | `setup_logger()` 日志配置 | `logging`, `config` |
| `config.py` | 环境变量、参数常量 | `dotenv` |

---

## 十、搜索规模与资源估算

### 10.1 单次分析的调用量

**参数设置：** `breadth=3, depth=2`（默认配置）

| 指标 | 计算方式 | 数值 |
|------|---------|------|
| 搜索主题数 | 固定 | 5 |
| 每主题 Tavily 调用 | 第1层3次 + 第2层3次 = 6 | 6 |
| 总 Tavily 调用 | 5 × 6 | **30** |
| 每主题 LLM 调用（生成查询） | 第1层1次 + 第2层3次 = 4 | 4 |
| 每主题 LLM 调用（提取知识） | 第1层3次 + 第2层3次 = 6 | 6 |
| 总 LLM 调用（不含报告） | 5 × (4 + 6) | **50** |
| 报告生成 LLM 调用 | 1 | **1** |
| **总 LLM 调用** | 50 + 1 | **51** |

### 10.2 Token 消耗估算（参考）

> **说明：** 以下 Token 消耗为估算值，仅供成本评估参考。实际代码中不进行 Token 计算。

| 调用类型 | 单次 input tokens | 单次 output tokens | 总次数 | 总 tokens |
|---------|-------------------|--------------------|----|-----------|
| 生成查询（无 learnings） | ~300 | ~200 | 5 | ~2,500 |
| 生成查询（带 learnings） | ~800 | ~150 | 15 | ~14,250 |
| 提取知识 | ~1,500 | ~300 | 30 | ~54,000 |
| 生成报告 | ~6,000 | ~1,500 | 1 | ~7,500 |
| **总计** | — | — | **51** | **~78,250** |

**成本估算（qwen-plus 定价参考）：**

根据表格分项计算：
- 输入 tokens：300×5 + 800×15 + 1,500×30 + 6,000×1 = **64,500 tokens**
- 输出 tokens：200×5 + 150×15 + 300×30 + 1,500×1 = **13,750 tokens**
- 总计：64,500 + 13,750 = **78,250 tokens** ✓

成本计算：
- 输入成本：0.8元/百万tokens × 0.0645M ≈ **0.052元**
- 输出成本：2元/百万tokens × 0.01375M ≈ **0.028元**
- **单次分析预估总成本：约 0.08 元**

### 10.3 耗时估算

| 阶段 | 耗时 | 说明 |
|------|------|------|
| 5个主题并行 Deep Research | 40-80秒 | 受 Tavily 响应速度和 LLM 延迟影响 |
| 报告生成 | 8-15秒 | 单次 LLM 调用，输入较长 |
| **总计** | **50-95秒** | 取决于网络条件和 API 响应速度 |

---

## 十一、测试策略

**注意：** 断言异常类型时，应使用 `stock_analyzer.exceptions` 中定义的异常类，确保与模块实现保持一致。

### 11.1 单元测试

| 测试项 | 测试方法 |
|--------|---------|
| `extract_json_str()` | 纯函数测试，覆盖 7 种场景：直接 JSON、markdown 包裹、前置文字、**多代码块（取最后有效）**、无效输入抛异常。**注意**：实现中使用 `itertools.chain()` 而非 `+` 运算符连接 `reversed()` 迭代器 |
| `setup_logger()` | 验证日志文件创建、控制台和文件日志级别 |
| `_create_fallback_report()` | 测试降级报告结构、字段长度限制、**统一截断策略**（拼接后截断到500字符）、**空新闻列表验证**。**重要**：不断言整句中文文案，只断言关键要素（包含数量、包含错误、长度<=500、超长时...），避免文案微调导致假失败 |
| `successful_topics` 统计逻辑 | 测试空 learnings 的 ResearchResult 不计入成功数 |
| 降级报告识别 | 验证通过 `meta.raw_learnings is not None` 识别降级报告 |
| `SearchConfig` 结构化访问 | 测试 `meta.search_config.successful_topics` 属性访问（避免 dict KeyError） |
| `tavily_search()` 异常处理 | **两层断言测试**：①外层 `pytest.raises(TavilySearchError)`；②内层验证 `exc.value.cause` 是原始异常。测试可重试异常会重试，不可重试异常立即失败 |
| `asyncio.CancelledError` 传播 | **使用 `@pytest.mark.asyncio`**，测试 gather 结果中的 `CancelledError` 会向上传播而非被吞掉。Mock 返回值类型必须与函数契约一致（`tavily_search` 返回 `list[dict]`） |
| Pydantic 模型校验 | 测试合法和非法输入的解析结果（包含 `raw_learnings` 可选字段） |

### 11.2 集成测试（Mock）

| 测试项 | Mock 对象 | 验证点 |
|--------|----------|--------|
| `generate_serp_queries` | Mock `ChatAgent.run()` | 提示词拼接逻辑、输出解析 |
| `process_serp_result` | Mock `ChatAgent.run()` | 搜索结果格式化、learnings 提取 |
| `deep_research` | Mock `tavily_search` + Agent | 递归深度控制、breadth 递减、合并去重 |
| `run_web_research` | Mock 所有外部调用 | 主题并行、降级处理、`meta.raw_learnings` 填充、learnings < 5 时强制 `search_confidence = "低"`、**空 learnings 主题不计入成功数** |

**关键测试场景：空结果主题统计**

```python
# tests/test_successful_topics_counting.py
def test_successful_topics_excludes_empty_results():
    """测试空 learnings 的主题不计入成功数"""
    results = [
        ResearchResult(learnings=["data1", "data2"], visited_urls=["url1"]),  # 成功
        ResearchResult(learnings=[], visited_urls=[]),  # 失败（空结果）
        ResearchResult(learnings=["data3"], visited_urls=["url2"]),  # 成功
        ResearchResult(learnings=[], visited_urls=["url3"]),  # 失败（空结果）
        Exception("Failed"),  # 异常
    ]
    
    successful_topics = sum(
        1 for r in results 
        if isinstance(r, ResearchResult) and len(r.learnings) > 0
    )
    
    assert successful_topics == 2, "Only 2 topics with non-empty learnings should be counted"


def test_all_topics_empty_triggers_error():
    """测试所有主题返回空结果时触发异常"""
    results = [
        ResearchResult(learnings=[], visited_urls=[]) for _ in range(5)
    ]
    
    successful_topics = sum(
        1 for r in results 
        if isinstance(r, ResearchResult) and len(r.learnings) > 0
    )
    
    assert successful_topics == 0
    # 在实际代码中，这会触发 WebResearchError


@pytest.mark.asyncio
async def test_deep_research_cancel_propagates():
    """
    测试 deep_research 中 CancelledError 会向上传播而非被吞掉
    
    场景：模拟 tavily_search 被取消，验证取消异常会传播到调用方
    
    关键：Mock 对象必须满足实际代码契约（response.text），避免在无关位置提前失败
    """
    from unittest.mock import AsyncMock, patch
    from types import SimpleNamespace
    
    # Mock Agent 对象（返回值必须有 .text 属性，匹配主逻辑契约）
    mock_query_agent = AsyncMock()
    mock_query_agent.name = "query_agent"
    # ✅ 正确：使用 SimpleNamespace 模拟带 .text 属性的响应对象
    mock_query_agent.run.return_value = SimpleNamespace(
        text='```json\n{"queries": ["q1", "q2", "q3"]}\n```'
    )
    # ❌ 错误：直接返回字符串会在 response.text 访问时失败
    # mock_query_agent.run.return_value = '...'
    
    mock_extract_agent = AsyncMock()
    mock_extract_agent.name = "extract_agent"
    
    # 关键：patch 的路径应该是使用它的模块路径，而非定义它的模块路径
    # 假设 deep_research 在 stock_analyzer.deep_research 模块中
    with patch('stock_analyzer.deep_research.tavily_search') as mock_tavily:
        # 模拟第2个查询被取消（返回值类型应为 list[dict]，不是 {"results": ...}）
        mock_tavily.side_effect = [
            [{"url": "url1", "content": "content1"}],  # 第1个成功
            asyncio.CancelledError("Task cancelled"),  # 第2个被取消
            [{"url": "url2", "content": "content2"}],  # 第3个（不会执行）
        ]
        
        with pytest.raises(asyncio.CancelledError):
            await deep_research(
                query_agent=mock_query_agent,       # ✅ 正确参数名
                extract_agent=mock_extract_agent,   # ✅ 正确参数名
                query="测试主题",                    # ✅ query 而非 topic
                breadth=3,
                depth=1
            )


@pytest.mark.asyncio
async def test_run_web_research_cancel_propagates():
    """
    测试 run_web_research 中 CancelledError 会向上传播而非被吞掉
    
    场景：模拟某个主题研究被取消，验证取消异常会传播到调用方
    
    注意：本测试 mock 的是 deep_research 函数本身，无需 mock Agent 响应对象
    """
    from unittest.mock import AsyncMock, patch
    
    # 关键：patch 的路径应该是使用它的模块路径
    with patch('stock_analyzer.module_b_websearch.deep_research') as mock_research:
        # 模拟第2个主题被取消
        mock_research.side_effect = [
            ResearchResult(learnings=["data1"], visited_urls=["url1"]),  # 主题1成功
            asyncio.CancelledError("Topic cancelled"),  # 主题2被取消
            ResearchResult(learnings=["data2"], visited_urls=["url2"]),  # 主题3（不会执行）
        ]
        
        with pytest.raises(asyncio.CancelledError):
            await run_web_research(
                symbol="000001",
                name="平安银行",
                industry="银行",
                breadth=3,
                depth=1
            )


def test_extract_json_str_comprehensive():
    """测试 extract_json_str 的多种场景"""
    import pytest
    
    # 场景1：直接 JSON（最快路径）
    result1 = extract_json_str('{"key": "value"}')
    assert result1 == '{"key": "value"}'
    
    # 场景2：标准 markdown 包裹
    result2 = extract_json_str('```json\n{"key": "value"}\n```')
    assert result2 == '{"key": "value"}'
    
    # 场景3：前置解释文字
    result3 = extract_json_str('Here is the result:\n```json\n{"key": "value"}\n```')
    assert result3 == '{"key": "value"}'
    
    # 场景4：多个代码块，取最后一个有效的
    result4 = extract_json_str(
        'Here is my thinking:\n'
        '```text\n'
        'Some explanation...\n'
        '```\n'
        'And here is the result:\n'
        '```json\n'
        '{"queries": ["q1", "q2"]}\n'
        '```'
    )
    assert result4 == '{"queries": ["q1", "q2"]}'
    
    # 场景5：多个 json 代码块，取最后一个
    result5 = extract_json_str(
        '```json\n{"draft": true}\n```\n'
        'Let me revise:\n'
        '```json\n{"final": true}\n```'
    )
    assert result5 == '{"final": true}'
    
    # 场景6：无代码块，直接是 JSON（整段文本验证）
    result6 = extract_json_str('  {"key": "value"}  ')
    assert result6 == '{"key": "value"}'
    
    # 场景7：全部无效，抛出异常
    with pytest.raises(ValueError, match="No valid JSON found"):
        extract_json_str('This is not JSON at all')


### 11.1.1 降级报告测试最佳实践

**重要原则：不断言整句中文文案，断言关键要素**

**背景：** 降级报告的错误描述是用户可见的提示文案，可能会根据产品需求微调（如改进措辞、调整格式等）。如果测试断言整句文案，任何文案调整都会导致测试失败，产生"假失败"。

**最佳实践：**

| ❌ 不推荐（脆弱） | ✅ 推荐（稳定） |
|-----------------|---------------|
| `assert "报告生成失败（共收集 3 条学习点）：" in desc` | `assert str(len(learnings)) in desc  # 包含数量`<br>`assert error_msg in desc  # 包含错误` |
| `assert desc == "报告生成失败，共收集到 3 条信息..."` | `assert len(desc) <= 500`<br>`assert error_msg in desc` |

**应断言的关键要素：**
1. ✅ **长度限制**：`assert len(desc) <= 500`
2. ✅ **包含数量**：`assert str(len(learnings)) in desc`（推荐，避免硬编码）
3. ✅ **包含错误信息**：`assert error_message in desc`
4. ✅ **超长截断标志**：`assert desc.endswith("...")`（当超长时）
5. ❌ **不断言具体文案**：避免 `assert "报告生成失败（共收集 X 条学习点）：" in desc`
6. ❌ **不使用硬编码数字**：避免 `assert "3" in desc`（改用 `str(len(learnings))`）

**示例对比：**

```python
# ❌ 反例（伪代码）：不要断言完整中文文案 + 硬编码数字
# bad_assert = 'assert "报告生成失败（共收集 3 条学习点）：Connection timeout" in desc'

# ✅ 稳定的断言（只验证关键要素，使用表达式）
learnings = ["data1", "data2", "data3"]
error_msg = "Connection timeout"
report = _create_fallback_report(learnings, error_msg)
desc = report["competitive_advantage"]["description"]

assert len(desc) <= 500
assert str(len(learnings)) in desc  # 使用表达式，不硬编码 "3"
assert error_msg in desc
```

---

### 11.1.2 降级报告测试示例

```python
def test_fallback_report_empty_news_is_valid():
    """测试降级报告允许空新闻列表"""
    fallback_report = _create_fallback_report(
        learnings=["data1", "data2"],
        error_message="LLM output invalid JSON"
    )
    
    # 降级报告的新闻列表应该为空
    assert fallback_report["news_summary"]["positive"] == []
    assert fallback_report["news_summary"]["negative"] == []
    assert fallback_report["news_summary"]["neutral"] == []
    
    # 这是预期行为，不应在 E2E 测试中视为失败


def test_fallback_report_description_length_boundary():
    """
    测试 _create_fallback_report() 的 description 长度控制
    
    测试场景：
    1. 短错误信息：不截断
    2. 超长错误信息：截断到 500 字符
    3. 最终长度始终 <= 500
    
    注意：不断言整句中文文案，只断言关键要素，避免文案微调导致假失败
    """
    # 场景1：短错误信息，不需要截断
    learnings = ["data1", "data2", "data3"]
    short_error = "Connection timeout"
    report = _create_fallback_report(learnings, short_error)
    desc = report["competitive_advantage"]["description"]
    
    # 断言关键要素，而非整句文案
    assert len(desc) <= 500  # 长度限制
    assert str(len(learnings)) in desc  # 包含数量（使用表达式，避免硬编码）
    assert "Connection timeout" in desc  # 包含错误信息
    
    # 场景2：超长错误信息，需要截断
    long_error = "E" * 1000
    report2 = _create_fallback_report(learnings, long_error)
    desc2 = report2["competitive_advantage"]["description"]
    assert len(desc2) == 500  # 刚好截断到 500
    assert desc2.endswith("...")  # 超长时以 ... 结尾
    assert str(len(learnings)) in desc2  # 包含数量（使用表达式，避免硬编码）
    
    # 场景3：大量 learnings，超长错误
    many_learnings = ["x"] * 9999
    report3 = _create_fallback_report(many_learnings, long_error)
    desc3 = report3["competitive_advantage"]["description"]
    assert len(desc3) == 500
    assert desc3.endswith("...")
```

### 11.3 端到端测试

**注意：** 测试中导入的异常类型应从 `stock_analyzer.exceptions` 模块导入，确保与实际实现一致。

```python
# tests/test_module_b_e2e.py
import asyncio
from stock_analyzer.module_b_websearch import run_web_research
from stock_analyzer.exceptions import WebResearchError


async def test_web_research_e2e():
    """
    端到端测试：对平安银行执行完整深度搜索（使用真实 API）
    
    注意：测试需要容忍降级报告场景，降级报告会返回空新闻列表，
    这是预期行为，不应视为测试失败。
    """
    result = await run_web_research(
        symbol="000001",
        name="平安银行",
        industry="银行",
        # 使用默认参数 breadth=3, depth=2
    )
    assert result.meta.symbol == "000001"
    assert result.meta.total_learnings > 0
    assert result.search_confidence in ("高", "中", "低")
    
    # 检查是否为降级报告（判断依据：是否填充了 raw_learnings）
    is_fallback = result.meta.raw_learnings is not None
    
    if is_fallback:
        # 降级报告场景：允许空新闻列表，验证 raw_learnings 存在
        assert len(result.meta.raw_learnings) == result.meta.total_learnings
        assert result.search_confidence == "低", "Fallback report must have '低' confidence"
        # 降级报告可能返回空新闻列表，不做强制要求
    else:
        # 正常报告场景：必须有新闻内容（包括 neutral）
        total_news = (
            len(result.news_summary.positive) + 
            len(result.news_summary.negative) + 
            len(result.news_summary.neutral)
        )
        assert total_news > 0, \
            "Non-fallback report must have news items (positive/negative/neutral)"
    
    # 验证强制降级逻辑：如果 learnings < 5，必须标记为 "低"
    if result.meta.total_learnings < 5:
        assert result.search_confidence == "低", \
            f"Expected '低' confidence for {result.meta.total_learnings} learnings"
    
    # 验证 successful_topics 统计（必须有 learnings 才算成功）
    successful_topics = result.meta.search_config.successful_topics
    assert 0 < successful_topics <= 5, "successful_topics should be in range (0, 5]"
    assert result.meta.total_learnings > 0, "If any topic succeeded, total_learnings must > 0"


if __name__ == "__main__":
    asyncio.run(test_web_research_e2e())
```

---

## 十二、使用示例

### 12.1 基础调用

```python
from stock_analyzer.module_b_websearch import run_web_research

# 执行深度搜索
result = await run_web_research(
    symbol="000001",
    name="平安银行",
    industry="银行",
)

# result 是 WebResearchResult 对象
print(f"总评分可信度: {result.search_confidence}")
print(f"正面新闻数量: {len(result.news_summary.positive)}")
print(f"成功主题数: {result.meta.search_config.successful_topics}/{result.meta.search_config.topics_count}")
```

### 12.2 保存为 JSON 文件

```python
import json
from pathlib import Path

# 方式1：使用 Pydantic 的 model_dump_json()（推荐）
json_str = result.model_dump_json(indent=2, ensure_ascii=False)
output_file = Path(f"output/{result.meta.symbol}_web_research.json")
output_file.parent.mkdir(parents=True, exist_ok=True)
output_file.write_text(json_str, encoding="utf-8")

# 方式2：使用标准 json 库
with open(f"output/{result.meta.symbol}_web_research.json", "w", encoding="utf-8") as f:
    json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
```

### 12.3 与其他模块集成

```python
# 在主流程中调用模块B
async def analyze_stock_complete(symbol: str, name: str, industry: str):
    # 模块A：AKShare 数据采集（略）
    akshare_data = collect_akshare_data(symbol, name)
    
    # 模块B：网络深度搜索
    web_research = await run_web_research(symbol, name, industry)
    
    # 模块C：技术分析（略）
    technical_analysis = analyze_technical(symbol, name)
    
    # 模块D：首席分析师综合判断（略）
    final_report = generate_final_report(
        akshare_data,
        web_research.model_dump(),  # 转为 dict 传递
        technical_analysis,
    )
    
    # 保存所有结果
    save_results(symbol, web_research, final_report)
```

### 12.4 降级场景处理

```python
try:
    result = await run_web_research(symbol, name, industry)
    
    # 检查质量
    if result.search_confidence == "低":
        logger.warning(f"搜索质量低：{result.meta.total_learnings} learnings")
        
        # 判断是否为降级报告（报告生成失败时触发）
        if result.meta.raw_learnings is not None:
            logger.warning(f"检测到降级报告（报告生成失败），已保存 {len(result.meta.raw_learnings)} 条原始 learnings")
            
            # 降级报告的新闻列表会是空的，这是预期行为
            news_count = (
                len(result.news_summary.positive) + 
                len(result.news_summary.negative) + 
                len(result.news_summary.neutral)
            )
            if news_count == 0:
                logger.info("降级报告未包含结构化新闻摘要，请查看原始 learnings")
            
            # 保存到独立文件供人工分析
            import json
            with open(f"output/{symbol}_raw_learnings.json", "w", encoding="utf-8") as f:
                json.dump(result.meta.raw_learnings, f, ensure_ascii=False, indent=2)
            logger.info(f"原始 learnings 已保存到 output/{symbol}_raw_learnings.json")
    
    # 检查成功率
    success_rate = (
        result.meta.search_config.successful_topics 
        / result.meta.search_config.topics_count
    )
    if success_rate < 0.6:
        logger.warning(f"仅 {success_rate:.0%} 主题成功，报告质量可能受影响")
    
except WebResearchError as e:
    logger.error(f"Web research 完全失败: {e}")
    # 使用空占位符或跳过该模块
    result = None
```

---

*文档版本：v1.0*
*最后更新：2026年2月*
*对应概要设计：stock-analysis-design-v3.1.md 第四章*

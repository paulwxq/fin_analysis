# 模块A：AKShare 数据采集 — 详细设计文档

## 一、概述

### 1.1 定位

模块A 是 `stock_analyzer` 的结构化数据采集模块，负责通过 **AKShare** 调用东方财富等数据源接口，获取目标股票的基本面、估值、资金流向、股东结构等 **12 个主题**的结构化数据，整理后输出为 `AKShareData`（Pydantic 模型对象）。

**核心特征：** 纯 Python 代码，不涉及 AI/Agent。

### 1.2 输入输出

| | 说明 |
|------|------|
| **输入** | 股票代码（`symbol`，纯6位数字）、股票名称（`name`） |
| **输出** | `AKShareData`（Pydantic 模型对象） |

### 1.3 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| Python 版本 | **3.12+** | 项目要求（见 `pyproject.toml`） |
| 数据源 | AKShare `>=1.18.22` | 开源 A 股数据接口（底层爬虫） |
| 数据处理 | pandas `>=2.3.3` | DataFrame 操作 |
| 数据校验 | Pydantic `>=2.12.5` | 输出结构化校验 |
| 日志 | `stock_analyzer.logger` | 与项目统一（控制台 + 文件） |
| 配置 | `stock_analyzer.config` | 与项目统一（环境变量驱动） |

### 1.4 设计原则

1. **纯代码实现**：不使用 AI/Agent，AKShare 返回结构化数据，直接解析拼接即可
2. **容错优先**：任何单个主题采集失败不中断整体流程，记录错误继续执行
3. **串行调用**：AKShare 底层是爬虫，并行调用易触发 IP 封禁，必须串行 + 间隔
4. **统一代码转换**：封装 `format_symbol()` 工具函数解决 AKShare 不同函数的代码格式不一致问题
5. **共享基础设施**：复用 `config.py`、`logger.py`、`exceptions.py`，与模块B保持一致

---

## 二、架构设计

### 2.1 核心组件

| 组件 | 类型 | 职责 |
|------|------|------|
| `AKShareCollector` | 主类 | 编排12个主题的数据采集，统一异常处理和结果组装 |
| `format_symbol()` | 工具函数 | 股票代码格式转换（纯6位 / 小写前缀 / 大写前缀） |
| `get_market()` | 工具函数 | 返回市场标识（`sh` / `sz`） |
| `AKShareData` | Pydantic 模型 | 输出数据结构定义和校验 |
| `collect_akshare_data()` | 入口函数 | 模块A对外入口，创建 Collector 并执行采集 |

### 2.2 数据流图

```
输入：symbol="000001", name="平安银行"
           │
           ▼
    ┌──────────────────────────────┐
    │   collect_akshare_data()     │  ← 模块A入口函数
    │                              │
    │   创建 AKShareCollector      │
    │   调用 collector.collect()   │
    └──────────────┬───────────────┘
                   │
                   ▼
    ┌──────────────────────────────┐
    │   AKShareCollector.collect() │
    │                              │
    │   串行执行12个主题采集：      │
    │                              │
    │   ① 公司基本信息             │  ← ak.stock_individual_info_em
    │          ↓ (间隔3秒)         │
    │   ② 实时行情快照             │  ← ak.stock_zh_a_spot_em
    │          ↓ (间隔3秒)         │
    │   ③ 财务分析指标             │  ← ak.stock_financial_analysis_indicator
    │          ↓ (间隔3秒)         │
    │   ④ 估值历史数据             │  ← ak.stock_a_lg_indicator
    │          ↓ (间隔3秒)         │
    │   ⑤ 行业估值对比             │  ← ak.stock_zh_valuation_comparison_em
    │          ↓ (间隔3秒)         │
    │   ⑥ 个股资金流向             │  ← ak.stock_individual_fund_flow
    │          ↓ (间隔3秒)         │
    │   ⑦ 板块资金流向             │  ← ak.stock_board_industry_fund_flow_rank_em
    │          ↓ (间隔3秒)         │
    │   ⑧ 北向资金持仓             │  ← ak.stock_hsgt_hold_stock_em
    │          ↓ (间隔3秒)         │
    │   ⑨ 股东户数                 │  ← ak.stock_zh_a_gdhs_detail_em
    │          ↓ (间隔3秒)         │
    │   ⑩ 分红历史                 │  ← ak.stock_history_dividend
    │          ↓ (间隔3秒)         │
    │   ⑪ 业绩预告                 │  ← ak.stock_yjyg_em
    │          ↓ (间隔3秒)         │
    │   ⑫ 股权质押                 │  ← ak.stock_gpzy_pledge_ratio_em
    │                              │
    └──────────────┬───────────────┘
                   │ 组装结果
                   ▼
         AKShareData（Pydantic 对象）
```

### 2.3 文件结构

```
stock_analyzer/
├── config.py                      # 共享配置（需新增模块A配置项）
├── logger.py                      # 共享日志
├── exceptions.py                  # 共享异常（需新增模块A异常类）
├── models.py                      # 共享模型（现有模块B模型，保持不变）
├── module_a_models.py             # 🆕 模块A Pydantic 数据模型
├── module_a_akshare.py            # 🆕 模块A 主逻辑（AKShareCollector + 入口函数）
├── utils.py                       # 🆕 工具函数（format_symbol, get_market, normalize_symbol 等）
├── run_module_a.py                # 🆕 模块A 命令行运行脚本（独立测试用）
└── docs/
    └── module_a_akshare_detail_design.md  # 🆕 本文档
```

---

## 三、配置设计

### 3.1 新增配置项

在现有 `config.py` 中新增模块A专用配置：

```python
# ============================================================
# 模块A：AKShare 数据采集配置
# ============================================================

# AKShare 调用间隔（秒），避免触发数据源 IP 封禁
AKSHARE_CALL_INTERVAL: float = float(os.getenv("AKSHARE_CALL_INTERVAL", "3.0"))

# AKShare 单次调用超时（秒）
AKSHARE_CALL_TIMEOUT: float = float(os.getenv("AKSHARE_CALL_TIMEOUT", "30.0"))

# 财务指标取最近 N 期数据
AKSHARE_FINANCIAL_PERIODS: int = int(os.getenv("AKSHARE_FINANCIAL_PERIODS", "8"))

# 资金流向取最近 N 个交易日
AKSHARE_FUND_FLOW_DAYS: int = int(os.getenv("AKSHARE_FUND_FLOW_DAYS", "5"))

# 股东户数取最近 N 期
AKSHARE_SHAREHOLDER_PERIODS: int = int(os.getenv("AKSHARE_SHAREHOLDER_PERIODS", "4"))

# 分红历史取最近 N 年
AKSHARE_DIVIDEND_YEARS: int = int(os.getenv("AKSHARE_DIVIDEND_YEARS", "5"))

# 连续超时熔断阈值：连续 N 次超时后中止采集
AKSHARE_MAX_CONSECUTIVE_TIMEOUTS: int = int(os.getenv("AKSHARE_MAX_CONSECUTIVE_TIMEOUTS", "3"))

# 全市场数据缓存 TTL（秒）：同一轮批量分析中复用全量查询结果
AKSHARE_MARKET_CACHE_TTL_SEC: int = int(os.getenv("AKSHARE_MARKET_CACHE_TTL_SEC", "300"))
```

### 3.2 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `AKSHARE_CALL_INTERVAL` | `3.0` | 每次 AKShare API 调用之间的等待时间（秒） |
| `AKSHARE_CALL_TIMEOUT` | `30.0` | 单次 AKShare API 调用的超时上限（秒） |
| `AKSHARE_FINANCIAL_PERIODS` | `8` | 财务指标取最近几期（季报），8期约等于2年 |
| `AKSHARE_FUND_FLOW_DAYS` | `5` | 资金流向明细取最近几个交易日 |
| `AKSHARE_SHAREHOLDER_PERIODS` | `4` | 股东户数取最近几期报告 |
| `AKSHARE_DIVIDEND_YEARS` | `5` | 分红历史取最近几年 |
| `AKSHARE_MAX_CONSECUTIVE_TIMEOUTS` | `3` | 连续超时熔断阈值，达到后中止采集 |
| `AKSHARE_MARKET_CACHE_TTL_SEC` | `300` | 全市场接口缓存有效期（秒），批量分析时复用 |

### 3.3 日志配置

复用现有 `logger.py`，模块A内部统一使用：

```python
from stock_analyzer.logger import logger
```

---

## 四、股票代码格式转换

### 4.1 问题背景

> ⚠️ 这是 AKShare 最大的坑之一：不同函数要求的股票代码格式不同。

| 格式 | 示例 | 使用的函数 |
|------|------|-----------|
| 纯6位数字 (`bare`) | `"000001"` | `stock_individual_info_em`, `stock_zh_a_hist`, `stock_news_em`, `stock_financial_analysis_indicator`, `stock_a_lg_indicator`, `stock_zh_a_gdhs_detail_em` |
| 小写前缀 (`lower`) | `"sz000001"` | `stock_history_dividend` |
| 大写前缀 (`upper`) | `"SZ000001"` | `stock_zh_valuation_comparison_em` |
| 代码+市场参数 | `stock="000001"`, `market="sz"` | `stock_individual_fund_flow` |

### 4.2 市场判定规则

```python
def get_market(code: str) -> str:
    """
    根据股票代码判断所属市场。

    Args:
        code: 纯6位数字股票代码

    Returns:
        "sh" 或 "sz"

    规则：
    - 6 开头 → 上海证券交易所 (sh)
    - 0、3 开头 → 深圳证券交易所 (sz)
    - 其他 → 默认 sz（含 002 中小板、300 创业板）
    """
    return "sh" if code.startswith("6") else "sz"
```

### 4.3 格式转换函数

```python
def format_symbol(code: str, style: str) -> str:
    """
    统一股票代码格式转换。

    Args:
        code: 纯6位数字股票代码，如 "000001"
        style: 目标格式
            - "bare"  → "000001"
            - "lower" → "sz000001"
            - "upper" → "SZ000001"

    Returns:
        转换后的股票代码

    Raises:
        ValueError: code 不是6位数字，或 style 不合法
    """
    if not code.isdigit() or len(code) != 6:
        raise ValueError(f"Invalid stock code: '{code}', expected 6-digit string")
    
    market = get_market(code)
    
    if style == "bare":
        return code
    elif style == "lower":
        return f"{market}{code}"
    elif style == "upper":
        return f"{market.upper()}{code}"
    else:
        raise ValueError(f"Unknown style: '{style}', expected 'bare'/'lower'/'upper'")
```

### 4.4 命令行代码清洗函数

用户从命令行传入的股票代码可能带有交易所后缀（如 `600519.SH`、`000001.SZ`），
需要在入口层统一清洗为纯6位数字：

```python
import re

# 匹配多种常见格式：600519.SH / 600519.sh / SH600519 / sh600519 / 600519
_SYMBOL_RE = re.compile(
    r"^(?:(?P<prefix>[A-Za-z]{2})(?P<code1>\d{6}))$"    # SH600519
    r"|^(?:(?P<code2>\d{6})(?:[.\-](?P<suffix>[A-Za-z]{2,4}))?)$"  # 600519 / 600519.SH
)


def normalize_symbol(raw: str) -> str:
    """
    从各种常见格式中提取纯6位数字股票代码。

    支持格式：
        "600519"      → "600519"
        "600519.SH"   → "600519"
        "600519.sh"   → "600519"
        "SH600519"    → "600519"
        "sh600519"    → "600519"

    Args:
        raw: 原始股票代码字符串

    Returns:
        纯6位数字代码

    Raises:
        ValueError: 无法从输入中解析出合法的6位代码
    """
    raw = raw.strip()
    m = _SYMBOL_RE.match(raw)
    if m:
        code = m.group("code1") or m.group("code2")
        if code and len(code) == 6:
            return code
    raise ValueError(
        f"Cannot normalize symbol: '{raw}'. "
        f"Expected formats: 600519 / 600519.SH / SH600519"
    )
```

### 4.5 各主题使用的代码格式

| 主题 | AKShare 函数 | 代码格式 | 调用示例 |
|------|-------------|---------|---------|
| ① 公司基本信息 | `stock_individual_info_em` | `bare` | `symbol="000001"` |
| ② 实时行情 | `stock_zh_a_spot_em` | 无参数（全市场） | 返回后按代码过滤 |
| ③ 财务指标 | `stock_financial_analysis_indicator` | `bare` | `stock="000001"` |
| ④ 估值历史 | `stock_a_lg_indicator` | `bare` | `stock="000001"` |
| ⑤ 行业估值对比 | `stock_zh_valuation_comparison_em` | `upper` | `symbol="SZ000001"` |
| ⑥ 个股资金流向 | `stock_individual_fund_flow` | `bare` + `market` | `stock="000001"`, `market="sz"` |
| ⑦ 板块资金流向 | `stock_board_industry_fund_flow_rank_em` | 无参数（全市场） | 返回后按行业过滤 |
| ⑧ 北向资金持仓 | `stock_hsgt_hold_stock_em` | 无参数（全市场） | 返回后按代码过滤 |
| ⑨ 股东户数 | `stock_zh_a_gdhs_detail_em` | `bare` | `symbol="000001"` |
| ⑩ 分红历史 | `stock_history_dividend` | `lower` | `symbol="sz000001"` |
| ⑪ 业绩预告 | `stock_yjyg_em` | 无参数（按日期查全市场） | 返回后按代码过滤 |
| ⑫ 股权质押 | `stock_gpzy_pledge_ratio_em` | 无参数（全市场） | 返回后按代码过滤 |

---

## 五、异常处理设计

### 5.1 异常类定义

在 `stock_analyzer/exceptions.py` 中新增模块A专用异常：

```python
# ============================================================
# 模块A：AKShare 数据采集异常
# ============================================================

class AKShareError(Exception):
    """AKShare 数据采集异常基类。"""
    pass


class AKShareAPIError(AKShareError):
    """单个 AKShare API 调用失败。

    用于记录某个主题的采集失败，不中断整体流程。
    """

    def __init__(self, topic: str, func_name: str, cause: Exception):
        self.topic = topic
        self.func_name = func_name
        self.cause = cause
        super().__init__(
            f"AKShare API failed for topic '{topic}' "
            f"(func: {func_name}): {cause}"
        )


class AKShareDataEmptyError(AKShareError):
    """AKShare API 返回空数据。

    某些情况下 API 调用成功但返回 None 或空 DataFrame。
    """

    def __init__(self, topic: str, func_name: str):
        self.topic = topic
        self.func_name = func_name
        super().__init__(
            f"AKShare returned empty data for topic '{topic}' "
            f"(func: {func_name})"
        )


class AKShareCollectionError(AKShareError):
    """模块A 整体采集终止异常。

    触发场景：
    1) 所有主题均采集失败；
    2) 连续超时达到熔断阈值。
    """

    def __init__(self, symbol: str, errors: list[str]):
        self.symbol = symbol
        self.errors = errors
        super().__init__(
            f"AKShare collection aborted for {symbol}: "
            f"{len(errors)} errors"
        )
```

### 5.2 异常处理策略

| 场景 | 处理方式 | 保护层 | topic_status |
|------|---------|--------|-------------|
| 单个 API 调用失败 | 记录错误，跳过该主题 | `safe_call()` | `failed` |
| API 返回空数据 | 记录警告，字段为 `None` | `safe_call()` | `failed` |
| 全市场数据中列名变化 | 记录错误，返回空 DataFrame | `_safe_filter()` | `failed` |
| 全市场数据中未找到目标股票（A类） | 返回结构化"未命中"结果 | 业务层判断 | **`ok`**（见下方说明） |
| 全市场数据中未找到目标股票（B类） | 记录警告，返回 `None` | 业务层判断 | `failed`（见下方说明） |
| API 成功但无业务数据 | 返回 `available=False` 等结构化结果 | 业务层 | **`no_data`** |
| 解析阶段非预期异常 | 记录错误，跳过该主题 | `_safe_collect()` | `failed` |
| 所有主题均失败 | 抛出 `AKShareCollectionError` | `collect()` 主流程 | — |
| 网络超时（单次） | 记录错误，跳过（软超时） | `safe_call()` 中 `FutureTimeoutError` | `failed` |
| 连续超时达到熔断阈值 | 抛出 `AKShareCollectionError`，中止采集 | `safe_call()` 熔断逻辑 | — |

> **"未找到目标股票"分类说明：**
>
> 全市场接口返回数据后未匹配到目标股票，需按业务语义区分两类：
>
> | 类型 | 判定标准 | 典型主题 | topic_status | 返回值 |
> |------|---------|---------|-------------|--------|
> | **A类：未命中本身是有效结论** | 名单型接口，"不在列表"有明确业务含义 | northbound（不持有）、pledge_ratio（无质押） | `ok` | 结构化结果（如 `held=False`） |
> | **B类：未命中意味着数据缺失** | 按代码应唯一命中的接口，未命中属于异常 | realtime_quote（停牌/退市） | `failed` | `None` |
>
> 各主题的"未命中"归属由 `_collect_*()` 方法内部决定，不在 `_safe_filter()` 层一刀切。

### 5.3 `AKShareCollector` 类与 `safe_call()` 方法

以下代码块对应 `module_a_akshare.py` 文件。开头的 import 区块是该文件的**完整导入清单**，
第六章所有 `_collect_*()` 方法均属于此类，共享此 import 区块。

```python
"""Module A: AKShare structured data collection."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, datetime

import akshare as ak
import pandas as pd

from stock_analyzer.config import (
    AKSHARE_CALL_INTERVAL,
    AKSHARE_CALL_TIMEOUT,
    AKSHARE_DIVIDEND_YEARS,
    AKSHARE_FINANCIAL_PERIODS,
    AKSHARE_FUND_FLOW_DAYS,
    AKSHARE_MARKET_CACHE_TTL_SEC,
    AKSHARE_MAX_CONSECUTIVE_TIMEOUTS,
    AKSHARE_SHAREHOLDER_PERIODS,
)
from stock_analyzer.exceptions import AKShareCollectionError
from stock_analyzer.logger import logger
from stock_analyzer.module_a_models import AKShareData, AKShareMeta
from stock_analyzer.utils import format_symbol, get_market


class AKShareMarketCache:
    """全市场 DataFrame 缓存（跨股票复用）。"""

    def __init__(self, ttl_sec: int = AKSHARE_MARKET_CACHE_TTL_SEC):
        self.ttl_sec = ttl_sec
        self._store: dict[str, tuple[float, pd.DataFrame]] = {}

    def get(self, key: str) -> pd.DataFrame | None:
        item = self._store.get(key)
        if item is None:
            return None
        ts, df = item
        if time.time() - ts > self.ttl_sec:
            self._store.pop(key, None)
            return None
        # 返回副本，避免调用方修改缓存对象
        return df.copy(deep=True)

    def set(self, key: str, df: pd.DataFrame) -> None:
        self._store[key] = (time.time(), df.copy(deep=True))


class AKShareCollector:
    """AKShare 数据采集器，带统一异常处理和调用间隔控制。"""

    # 主题状态常量
    STATUS_OK = "ok"              # 采集成功，有业务数据
    STATUS_NO_DATA = "no_data"    # 采集成功，但无业务数据（如确实无业绩预告）
    STATUS_FAILED = "failed"      # 采集失败（API 异常/超时/列名变化等）

    def __init__(
        self,
        symbol: str,
        name: str,
        market_cache: AKShareMarketCache | None = None,
    ):
        self.symbol = symbol
        self.name = name
        self.errors: list[str] = []
        self.topic_status: dict[str, str] = {}  # 每个主题的采集状态
        self._last_call_time: float = 0.0
        self._consecutive_timeouts: int = 0     # 连续超时计数器
        self.market_cache = market_cache or AKShareMarketCache()

    def _wait_interval(self) -> None:
        """确保与上次 AKShare 调用之间有足够间隔，避免 IP 封禁。"""
        elapsed = time.time() - self._last_call_time
        if elapsed < AKSHARE_CALL_INTERVAL:
            wait = AKSHARE_CALL_INTERVAL - elapsed
            logger.debug(f"Rate limit: waiting {wait:.1f}s before next AKShare call")
            time.sleep(wait)

    def safe_call(
        self,
        topic: str,
        func,
        *args,
        **kwargs,
    ) -> pd.DataFrame | None:
        """
        安全调用 AKShare 函数，带软超时控制与连续超时熔断。

        - 自动执行调用间隔等待
        - 通过 ThreadPoolExecutor 实现软超时（AKSHARE_CALL_TIMEOUT）
        - 连续超时达到 AKSHARE_MAX_CONSECUTIVE_TIMEOUTS 时触发熔断
        - 捕获所有异常，记录到 self.errors
        - 返回 DataFrame 或 None（失败时）

        Args:
            topic: 数据主题名称（用于日志和错误记录）
            func: AKShare 函数对象
            *args, **kwargs: 传递给 func 的参数

        Returns:
            成功时返回 DataFrame，失败或数据为空时返回 None

        Raises:
            AKShareCollectionError: 连续超时次数达到熔断阈值时抛出

        超时机制说明（⚠️ 软超时）：
            AKShare 底层走 HTTP 请求（同步），无法用 asyncio.wait_for()。
            使用 ThreadPoolExecutor 提交到线程池，通过 future.result(timeout=...)
            限制主线程的等待时间。

            **重要限制：**
            - 这是"软超时"：超时后主线程立即恢复执行，但底层线程中的
              HTTP 请求无法被强制终止，会继续运行直到自然结束。
            - 使用 shutdown(wait=False) 避免 executor 退出时阻塞主线程。
            - 如果需要"硬超时"（强制终止底层调用），需改用子进程隔离
              方案（multiprocessing + Process.kill()），但实现复杂度较高，
              当前场景（AKShare HTTP 请求通常有自身的 socket 超时）下
              软超时已能满足需求。

        线程堆积风险与防护（⚠️）：
            每次超时后底层线程仍在后台运行，连续超时会导致线程短时堆积。
            本方法采用以下防护策略：
            a) 全流程串行调用——同一时刻只有 1 个 safe_call 在执行；
            b) 调用间隔（AKSHARE_CALL_INTERVAL，默认 3s）天然限速；
            c) 连续超时熔断——连续 N 次（AKSHARE_MAX_CONSECUTIVE_TIMEOUTS，
               默认 3）超时后抛出 AKShareCollectionError，中止采集；
            d) 生产环境建议监控 threading.active_count()，对线程数设告警。

            最坏堆积数量 = AKSHARE_MAX_CONSECUTIVE_TIMEOUTS（默认 3 个线程），
            这些线程在底层 HTTP 请求完成或 socket 超时后会自然回收，
            不会无限增长。

        执行器生命周期策略（设计权衡）：
            safe_call() 每次调用都会创建一个新的 ThreadPoolExecutor(max_workers=1)，
            而不是复用全局单线程 executor。这样做的目的：
            1) 软超时后将“卡住任务”隔离在当前调用上下文，不阻塞后续调用提交；
            2) 避免共享单线程池下，单个卡住任务导致后续任务排队连锁超时。
            代价是每次调用有轻微创建/销毁开销。鉴于模块A单轮调用量约 12~15 次，
            该开销可接受，优先保证超时隔离与可恢复性。
        """
        func_name = func.__name__
        self._wait_interval()

        # 设计说明：每次调用独立创建 executor，避免共享单线程池被卡住任务“堵死”。
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            logger.info(f"Fetching [{topic}] via {func_name}...")
            self._last_call_time = time.time()

            future = executor.submit(func, *args, **kwargs)
            df = future.result(timeout=AKSHARE_CALL_TIMEOUT)

            # 调用成功，重置连续超时计数器
            self._consecutive_timeouts = 0

            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                msg = f"{topic}: 返回数据为空 ({func_name})"
                self.errors.append(msg)
                logger.warning(msg)
                return None

            logger.info(
                f"[{topic}] fetched successfully: "
                f"{len(df)} rows via {func_name}"
            )
            return df

        except FutureTimeoutError:
            self._consecutive_timeouts += 1
            msg = (
                f"{topic}: 调用超时（>{AKSHARE_CALL_TIMEOUT}s）({func_name})"
                f" [连续超时 {self._consecutive_timeouts}/"
                f"{AKSHARE_MAX_CONSECUTIVE_TIMEOUTS}]"
            )
            self.errors.append(msg)
            logger.error(msg)

            # 熔断：连续超时达到阈值，中止采集
            if self._consecutive_timeouts >= AKSHARE_MAX_CONSECUTIVE_TIMEOUTS:
                breaker_msg = (
                    f"连续超时 {self._consecutive_timeouts} 次，"
                    f"达到熔断阈值，中止采集"
                )
                logger.critical(breaker_msg)
                raise AKShareCollectionError(
                    self.symbol, self.errors + [breaker_msg]
                )

            return None
        except KeyboardInterrupt:
            raise  # 不吞没用户中断
        except Exception as e:
            # 非超时异常不累加连续超时计数（网络非超时错误可能是偶发的）
            msg = f"{topic}: {type(e).__name__} - {str(e)[:200]} ({func_name})"
            self.errors.append(msg)
            logger.error(msg)
            return None
        finally:
            # wait=False：不等待底层线程结束，主线程立即继续。
            # 底层线程会在 HTTP 请求自然结束后被回收。
            executor.shutdown(wait=False)

    def safe_call_market_cached(
        self,
        cache_key: str,
        topic: str,
        func,
        *args,
        **kwargs,
    ) -> pd.DataFrame | None:
        """带缓存的全市场调用：命中缓存则直接返回，未命中才请求。"""
        cached = self.market_cache.get(cache_key)
        if cached is not None:
            logger.info(f"[{topic}] cache hit: {cache_key}")
            return cached

        df = self.safe_call(topic, func, *args, **kwargs)
        if df is not None:
            self.market_cache.set(cache_key, df)
            logger.info(f"[{topic}] cache set: {cache_key}, rows={len(df)}")
        return df

    def _safe_filter(
        self,
        df: pd.DataFrame,
        column: str,
        value: str,
        topic: str,
        *,
        method: str = "eq",
    ) -> pd.DataFrame:
        """
        防御性 DataFrame 列过滤。

        先检查列是否存在，不存在时记录错误并返回空 DataFrame，
        避免 KeyError 穿透到主流程。

        Args:
            df: 待过滤的 DataFrame
            column: 目标列名（中文列名，可能随 AKShare 版本变化）
            value: 过滤值
            topic: 所属主题名（用于错误日志）
            method: 过滤方式
                - "eq"       → df[df[column] == value]
                - "contains"  → df[df[column].str.contains(value, regex=False)]

        Returns:
            过滤后的 DataFrame（列不存在时返回空 DataFrame）
        """
        if column not in df.columns:
            msg = (
                f"{topic}: 预期列 '{column}' 不存在，"
                f"实际列名: {list(df.columns)[:10]}"
            )
            self.errors.append(msg)
            logger.warning(msg)
            return df.iloc[0:0]  # 返回同结构的空 DataFrame

        if method == "eq":
            return df[df[column] == value]
        elif method == "contains":
            return df[df[column].str.contains(value, na=False, regex=False)]
        else:
            msg = (
                f"{topic}: 未知过滤方式 method='{method}'，"
                "回退到 'eq' 精确匹配"
            )
            self.errors.append(msg)
            logger.warning(msg)
            return df[df[column] == value]

    def _safe_collect(
        self,
        topic: str,
        collect_func,
        *args,
        **kwargs,
    ):
        """
        安全包装解析逻辑，并自动维护 topic_status。

        safe_call() 仅保护 AKShare API 调用，本方法保护解析阶段：
        捕获 _collect_*() 内部的一切非预期异常（如 KeyError、TypeError），
        确保"单主题失败不中断整体流程"。

        状态标记规则：
        - _collect_*() 正常返回非 None 且未预设状态 → STATUS_OK
        - _collect_*() 正常返回 None → STATUS_FAILED
        - _collect_*() 内部已设置过 topic_status（如 no_data）→ 保持不变
        - _collect_*() 抛异常 → STATUS_FAILED

        Args:
            topic: 主题名（用于错误日志和状态跟踪）
            collect_func: _collect_* 方法
            *args, **kwargs: 传递给 collect_func 的参数

        Returns:
            collect_func 的返回值，或 None（异常时）
        """
        try:
            result = collect_func(*args, **kwargs)
            # 如果 _collect_*() 内部没有预设状态，自动标记
            if topic not in self.topic_status:
                self.topic_status[topic] = (
                    self.STATUS_OK if result is not None else self.STATUS_FAILED
                )
            return result
        except (KeyboardInterrupt, AKShareCollectionError):
            raise  # 熔断异常和用户中断不吞没，向上传播
        except Exception as e:
            msg = f"{topic}(解析阶段): {type(e).__name__} - {str(e)[:200]}"
            self.errors.append(msg)
            logger.error(msg)
            self.topic_status[topic] = self.STATUS_FAILED
            return None
```

---

## 六、12 个数据主题详细设计

> **阅读说明：** 以下所有 `_collect_*()` / `_parse_*()` / `_safe_float()` 等方法均属于
> `AKShareCollector` 类（定义于 5.3 节），共享 5.3 节开头的 import 区块。
> 各代码片段省略了 `import` 和 `class` 声明以减少冗余。

### 6.1 主题① 公司基本信息

**AKShare 函数：** `ak.stock_individual_info_em(symbol)`

**入参格式：** `bare`（纯6位数字）

**返回格式：** DataFrame，两列 `(item, value)`，约 15-20 行

**⚠️ 列名注意：** `item` / `value` 是 `stock_individual_info_em` 的接口特有英文列名（区别于多数中文列接口）。解析前需先校验列存在；若版本变更导致列名变化，应记录 warning 并降级为该主题失败（返回 `None`）。

**返回字段示例：**
```
         item                value
0       总市值        2156.80亿
1     流通市值        2156.80亿
2        行业               银行
3     上市时间        1991-04-03
4      总股本      194.06亿
5     流通股      194.06亿
...
```

**采集入口（`_collect_company_info`）：**

```python
def _collect_company_info(self) -> dict | None:
    """采集公司基本信息。"""
    df = self.safe_call(
        "company_info",
        ak.stock_individual_info_em,
        symbol=self.symbol,
    )
    if df is None:
        return None

    # 该接口是 item-value 结构，先校验关键列是否存在
    required_cols = {"item", "value"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        msg = (
            "company_info: 缺少关键列 "
            f"{sorted(missing_cols)}，无法解析 item-value 结构"
        )
        self.errors.append(msg)
        logger.warning(msg)
        return None

    # 解析阶段异常由 _safe_collect() 兜底
    return self._parse_company_info(df)
```

**解析逻辑（`_parse_company_info` + `_parse_number`）：**

```python
def _parse_company_info(self, df: pd.DataFrame) -> dict:
    """将 item-value 格式的 DataFrame 解析为字典。"""
    info = {}
    lookup = dict(zip(df["item"], df["value"]))

    info["industry"] = str(lookup.get("行业", ""))
    info["listing_date"] = str(lookup.get("上市时间", ""))

    # 数值字段：统一换算到"亿"（_parse_number 会自动识别"万/亿"单位）
    info["total_market_cap"] = self._parse_number(lookup.get("总市值"), target_unit="亿")
    info["circulating_market_cap"] = self._parse_number(lookup.get("流通市值"), target_unit="亿")
    info["total_shares"] = self._parse_number(lookup.get("总股本"), target_unit="亿")
    info["circulating_shares"] = self._parse_number(lookup.get("流通股"), target_unit="亿")

    return info

@staticmethod
def _parse_number(value, target_unit: str = "亿") -> float | None:
    """解析 AKShare 返回的数值字段（可能含中文单位），统一换算到目标单位。

    AKShare 不同接口返回的数值可能带"亿"或"万"单位，本方法会
    识别单位并换算到 target_unit，避免量级错误。

    Args:
        value: 原始值（str / float / None）
        target_unit: 目标单位，"亿" 或 "万"，默认 "亿"

    示例（target_unit="亿"）：
        "2156.80亿" → 2156.80   （同单位，直接取数）
        "194.06亿"  → 194.06
        "19406万"   → 1.9406    （万 → 亿，÷ 10000）
        "3.5"       → 3.5       （无单位，假定已是目标单位）
        "-"          → None
        None         → None
    """
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s in ("", "-", "--", "nan"):
        return None

    # 识别单位并提取数值
    multiplier = 1.0
    if s.endswith("亿"):
        s = s[:-1]
        if target_unit == "万":
            multiplier = 10000.0   # 亿 → 万
    elif s.endswith("万"):
        s = s[:-1]
        if target_unit == "亿":
            multiplier = 0.0001    # 万 → 亿
    # 无单位：假定已是目标单位，multiplier 保持 1.0

    try:
        return round(float(s) * multiplier, 4)
    except (ValueError, TypeError):
        return None
```

### 6.2 主题② 实时行情快照

**AKShare 函数：** `ak.stock_zh_a_spot_em()`

**入参格式：** 无参数（返回全市场 5000+ 只股票）

**⚠️ 注意：** 必须从结果中按股票代码过滤

**返回字段（筛选后）：**
| DataFrame 列名 | 输出字段 | 说明 |
|----------------|---------|------|
| `最新价` | `price` | 当前价格 |
| `涨跌幅` | `change_pct` | 当日涨跌幅(%) |
| `成交量` | `volume` | 成交量（手） |
| `成交额` | `turnover` | 成交额（元） |
| `市盈率-动态` | `pe_ttm` | 动态市盈率 |
| `市净率` | `pb` | 市净率 |
| `换手率` | `turnover_rate` | 换手率(%) |
| `量比` | `volume_ratio` | 量比 |
| `60日涨跌幅` | `change_60d_pct` | 近60日涨跌幅(%) |
| `年初至今涨跌幅` | `change_ytd_pct` | 年初至今涨跌幅(%) |

**解析逻辑：**

```python
def _collect_realtime_quote(self) -> dict | None:
    """采集实时行情快照。"""
    df = self.safe_call_market_cached(
        "stock_zh_a_spot_em",
        "realtime_quote",
        ak.stock_zh_a_spot_em,
    )
    if df is None:
        return None

    row = self._safe_filter(df, "代码", self.symbol, "realtime_quote")
    if row.empty:
        msg = f"realtime_quote: 全市场数据中未找到 {self.symbol}"
        self.errors.append(msg)
        logger.warning(msg)
        return None

    r = row.iloc[0]
    return {
        "price": self._safe_float(r.get("最新价")),
        "change_pct": self._safe_float(r.get("涨跌幅")),
        "volume": self._safe_float(r.get("成交量")),
        "turnover": self._safe_float(r.get("成交额")),
        "pe_ttm": self._safe_float(r.get("市盈率-动态")),
        "pb": self._safe_float(r.get("市净率")),
        "turnover_rate": self._safe_float(r.get("换手率")),
        "volume_ratio": self._safe_float(r.get("量比")),
        "change_60d_pct": self._safe_float(r.get("60日涨跌幅")),
        "change_ytd_pct": self._safe_float(r.get("年初至今涨跌幅")),
    }

@staticmethod
def _safe_float(value) -> float | None:
    """安全转换为 float，处理各种非法值。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

@staticmethod
def _safe_int(value) -> int | None:
    """安全转换为 int，处理千分位和浮点字符串。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).replace(",", "").strip()
    if s in ("", "-", "--", "nan"):
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None
```

### 6.3 主题③ 财务分析指标

**AKShare 函数：** `ak.stock_financial_analysis_indicator(stock)`

**入参格式：** `bare`（参数名是 `stock`，不是 `symbol`）

**返回格式：** DataFrame，65+ 列财务指标，按报告期排列

**关键字段提取：**
| DataFrame 列名 | 输出字段 | 说明 |
|----------------|---------|------|
| `报告期` | `report_date` | 报告期日期 |
| `摊薄每股收益(元)` | `eps` | 每股收益 |
| `每股净资产_调整后(元)` | `net_asset_per_share` | 每股净资产 |
| `净资产收益率_摊薄(%)` | `roe` | ROE（摊薄） |
| `销售毛利率(%)` | `gross_margin` | 毛利率 |
| `销售净利率(%)` | `net_margin` | 净利率 |
| `营业总收入同比增长率(%)` | `revenue_growth` | 营收增长率 |
| `归属母公司股东的净利润同比增长率(%)` | `profit_growth` | 净利润增长率 |
| `资产负债率(%)` | `debt_ratio` | 资产负债率 |
| `流动比率` | `current_ratio` | 流动比率 |

**⚠️ 注意：** 银行股部分指标（如毛利率、流动比率）可能为空，属于正常情况。
**⚠️ 排序注意：** 不依赖 AKShare 返回顺序。需先按报告期显式降序，再取最近 N 期。

**解析逻辑：**

```python
def _collect_financial_indicators(self) -> list[dict] | None:
    """采集财务分析指标（取最近 N 期）。"""
    df = self.safe_call(
        "financial_indicators",
        ak.stock_financial_analysis_indicator,
        stock=self.symbol,
    )
    if df is None:
        return None

    # 显式排序后再截取，避免依赖 AKShare 默认返回顺序
    if "报告期" in df.columns:
        df = (
            df.assign(_report_date=pd.to_datetime(df["报告期"], errors="coerce"))
            .sort_values("_report_date", ascending=False, na_position="last")
            .drop(columns=["_report_date"])
        )
    else:
        msg = "financial_indicators: 缺少列 '报告期'，按原始顺序截取最近N期"
        self.errors.append(msg)
        logger.warning(msg)

    # 取最近 N 期
    df = df.head(AKSHARE_FINANCIAL_PERIODS)

    results = []
    for _, row in df.iterrows():
        results.append({
            "report_date": str(row.get("报告期", "")),
            "eps": self._safe_float(row.get("摊薄每股收益(元)")),
            "net_asset_per_share": self._safe_float(
                row.get("每股净资产_调整后(元)")
            ),
            "roe": self._safe_float(row.get("净资产收益率_摊薄(%)")),
            "gross_margin": self._safe_float(row.get("销售毛利率(%)")),
            "net_margin": self._safe_float(row.get("销售净利率(%)")),
            "revenue_growth": self._safe_float(
                row.get("营业总收入同比增长率(%)")
            ),
            "profit_growth": self._safe_float(
                row.get("归属母公司股东的净利润同比增长率(%)")
            ),
            "debt_ratio": self._safe_float(row.get("资产负债率(%)")),
            "current_ratio": self._safe_float(row.get("流动比率")),
        })

    return results
```

### 6.4 主题④ 估值历史数据

**AKShare 函数：** `ak.stock_a_lg_indicator(stock)`

**入参格式：** `bare`（参数名是 `stock`）

**返回格式：** DataFrame，**英文列名**（AKShare 少数使用英文列名的函数）

**关键列：** `trade_date`, `pe`, `pe_ttm`, `pb`, `ps`, `ps_ttm`, `dv_ratio`, `dv_ttm`, `total_mv`
**⚠️ 排序注意：** 不依赖 AKShare 返回顺序。需先按 `trade_date` 显式升序，再取 `iloc[-1]` 作为当前值。

**核心计算 — 历史分位数：**

```python
def _collect_valuation_history(self) -> dict | None:
    """采集估值历史数据，计算当前估值的历史分位数。"""
    df = self.safe_call(
        "valuation_history",
        ak.stock_a_lg_indicator,
        stock=self.symbol,
    )
    if df is None:
        return None

    # 显式排序后再取“最新值”，避免依赖 AKShare 默认返回顺序
    if "trade_date" in df.columns:
        df = (
            df.assign(_trade_date=pd.to_datetime(df["trade_date"], errors="coerce"))
            .sort_values("_trade_date", ascending=True, na_position="last")
            .drop(columns=["_trade_date"])
        )
    else:
        msg = "valuation_history: 缺少列 'trade_date'，按原始顺序计算当前值与分位数"
        self.errors.append(msg)
        logger.warning(msg)

    # 取最新一行作为当前值
    latest = df.iloc[-1]

    current_pe_ttm = self._safe_float(latest.get("pe_ttm"))
    current_pb = self._safe_float(latest.get("pb"))

    # 计算分位数（列缺失时仅降级该字段，不让整个主题失败）
    pe_series = df.get("pe_ttm")
    if pe_series is None:
        msg = "valuation_history: 缺少列 'pe_ttm'，pe_percentile 置为 None"
        self.errors.append(msg)
        logger.warning(msg)
        pe_percentile = None
    else:
        pe_percentile = self._calc_percentile(pe_series, latest.get("pe_ttm"))

    pb_series = df.get("pb")
    if pb_series is None:
        msg = "valuation_history: 缺少列 'pb'，pb_percentile 置为 None"
        self.errors.append(msg)
        logger.warning(msg)
        pb_percentile = None
    else:
        pb_percentile = self._calc_percentile(pb_series, latest.get("pb"))

    # 生成简要描述
    pe_desc = self._percentile_description("PE", pe_percentile)
    pb_desc = self._percentile_description("PB", pb_percentile)

    return {
        "current_pe_ttm": current_pe_ttm,
        "current_pb": current_pb,
        "pe_percentile": pe_percentile,
        "pb_percentile": pb_percentile,
        "current_ps_ttm": self._safe_float(latest.get("ps_ttm")),
        "current_dv_ttm": self._safe_float(latest.get("dv_ttm")),
        "history_summary": f"{pe_desc}；{pb_desc}",
    }

@staticmethod
def _calc_percentile(series: pd.Series, current_value) -> float | None:
    """计算当前值在历史序列中的百分位数。

    Returns:
        百分位数（0-100），或 None（数据不足时）
    """
    # 先数值化，避免字符串/混合类型比较导致分位数错误
    clean = pd.to_numeric(series, errors="coerce").dropna()
    current_numeric = pd.to_numeric(current_value, errors="coerce")
    if len(clean) < 10 or pd.isna(current_numeric):
        return None
    rank = (clean < float(current_numeric)).sum()
    return round(rank / len(clean) * 100, 1)

@staticmethod
def _percentile_description(indicator: str, percentile: float | None) -> str:
    """根据分位数生成描述。"""
    if percentile is None:
        return f"{indicator}历史分位数据不足"
    if percentile < 20:
        level = "极低位置（历史底部区域）"
    elif percentile < 40:
        level = "偏低位置"
    elif percentile < 60:
        level = "中等位置"
    elif percentile < 80:
        level = "偏高位置"
    else:
        level = "极高位置（历史顶部区域）"
    return f"{indicator}历史分位{percentile}%，处于{level}"
```

### 6.5 主题⑤ 行业估值对比

**AKShare 函数：** `ak.stock_zh_valuation_comparison_em(symbol)`

**入参格式：** `upper`（大写前缀，如 `"SZ000001"`）

```python
def _collect_valuation_vs_industry(self) -> dict | None:
    """采集行业估值对比数据。"""
    upper_symbol = format_symbol(self.symbol, "upper")
    df = self.safe_call(
        "valuation_vs_industry",
        ak.stock_zh_valuation_comparison_em,
        symbol=upper_symbol,
    )
    if df is None:
        return None

    # 提取个股和行业的 PE/PB 对比
    # ⚠️ 注意：该函数返回的列名可能随 AKShare 版本变化，需要做防御性解析
    row = df.iloc[0] if len(df) > 0 else {}
    return {
        "stock_pe": self._safe_float(row.get("个股PE")),
        "industry_avg_pe": self._safe_float(row.get("行业PE(平均)")),
        "industry_median_pe": self._safe_float(row.get("行业PE(中位数)")),
        "stock_pb": self._safe_float(row.get("个股PB")),
        "industry_avg_pb": self._safe_float(row.get("行业PB(平均)")),
        "relative_valuation": self._judge_relative_valuation(
            self._safe_float(row.get("个股PE")),
            self._safe_float(row.get("行业PE(平均)")),
        ),
    }

@staticmethod
def _judge_relative_valuation(
    stock_pe: float | None, industry_pe: float | None
) -> str:
    """判断个股估值相对行业的位置。"""
    # PE<=0（亏损）时不做相对估值比较，避免产生误导性结论
    if stock_pe is None or industry_pe is None or stock_pe <= 0 or industry_pe <= 0:
        return "数据不足，无法判断"
    ratio = stock_pe / industry_pe
    if ratio < 0.8:
        return "明显低于行业平均"
    elif ratio < 0.95:
        return "略低于行业平均"
    elif ratio < 1.05:
        return "接近行业平均"
    elif ratio < 1.2:
        return "略高于行业平均"
    else:
        return "明显高于行业平均"
```

### 6.6 主题⑥ 个股资金流向

**AKShare 函数：** `ak.stock_individual_fund_flow(stock, market)`

**入参格式：** `bare` + `market` 参数

**窗口说明：**
- `recent_days` 明细窗口由 `AKSHARE_FUND_FLOW_DAYS` 控制（展示用）；
- `summary` 固定输出 `5日` 与 `10日` 汇总（与下游 schema 字段名对齐）；
- 若历史数据不足 5/10 日，对应汇总字段置 `None` 并记录 warning，避免“3日数据被标注为5日汇总”。
**⚠️ 排序注意：** 不依赖 AKShare 返回顺序。需先按 `日期` 显式升序，再使用 `tail()` 取最近 N 日。

```python
def _collect_fund_flow(self) -> dict | None:
    """采集个股资金流向数据。"""
    market = get_market(self.symbol)
    df = self.safe_call(
        "fund_flow",
        ak.stock_individual_fund_flow,
        stock=self.symbol,
        market=market,
    )
    if df is None:
        return None

    # 显式排序后再做 tail，避免依赖 AKShare 默认返回顺序
    if "日期" in df.columns:
        df = (
            df.assign(_flow_date=pd.to_datetime(df["日期"], errors="coerce"))
            .sort_values("_flow_date", ascending=True, na_position="last")
            .drop(columns=["_flow_date"])
        )
    else:
        msg = "fund_flow: 缺少列 '日期'，按原始顺序计算明细与汇总"
        self.errors.append(msg)
        logger.warning(msg)

    # 取最近 N 天明细
    recent = df.tail(AKSHARE_FUND_FLOW_DAYS)
    detail = []
    for _, row in recent.iterrows():
        detail.append({
            "date": str(row.get("日期", "")),
            "main_net_inflow": self._safe_float(row.get("主力净流入-净额")),
            "main_net_inflow_pct": self._safe_float(
                row.get("主力净流入-净占比")
            ),
        })

    # 汇总统计（固定 5日/10日窗口，与 schema 保持一致）
    summary_5d_window = 5
    summary_10d_window = 10
    main_col = "主力净流入-净额"
    total_5d = None
    total_10d = None
    if main_col in df.columns:
        if len(df) >= summary_5d_window:
            total_5d = self._safe_float(
                df.tail(summary_5d_window)[main_col].sum()
            )
        else:
            msg = (
                f"fund_flow: 历史数据不足 {summary_5d_window} 日，"
                "main_net_inflow_5d_total 置为 None"
            )
            self.errors.append(msg)
            logger.warning(msg)

        if len(df) >= summary_10d_window:
            total_10d = self._safe_float(
                df.tail(summary_10d_window)[main_col].sum()
            )
        else:
            msg = (
                f"fund_flow: 历史数据不足 {summary_10d_window} 日，"
                "main_net_inflow_10d_total 置为 None"
            )
            self.errors.append(msg)
            logger.warning(msg)
    else:
        msg = "fund_flow: 缺少列 '主力净流入-净额'，汇总字段置为 None"
        self.errors.append(msg)
        logger.warning(msg)

    trend = self._judge_fund_flow_trend(total_5d, total_10d)

    return {
        "recent_days": detail,
        "summary": {
            "main_net_inflow_5d_total": total_5d,
            "main_net_inflow_10d_total": total_10d,
            "trend": trend,
        },
    }

@staticmethod
def _judge_fund_flow_trend(
    total_5d: float | None, total_10d: float | None
) -> str:
    """根据资金流向趋势生成描述。"""
    parts = []
    if total_5d is not None:
        direction = "净流入" if total_5d >= 0 else "净流出"
        parts.append(f"近5日主力{direction}")
    if total_10d is not None:
        direction = "净流入" if total_10d >= 0 else "净流出"
        parts.append(f"近10日整体{direction}")
    return "，".join(parts) if parts else "数据不足"
```

### 6.7 主题⑦ 板块资金流向

**AKShare 函数：**
- `ak.stock_board_industry_fund_flow_rank_em(indicator="今日")`
- `ak.stock_board_concept_fund_flow_rank_em(indicator="今日")`

**⚠️ 注意：** 需要先知道目标股票所属行业（从主题①获取），再从全市场板块数据中查找。
**⚠️ 匹配注意：** 行业匹配优先 `eq` 精确命中，未命中才回退 `contains`（并记录 warning）。
**⚠️ 排序注意：** 热门概念 Top5 优先按显式排名列排序；若无排名列，按 `今日主力净流入-净额` 降序排序，再截取前 5。

```python
def _collect_sector_flow(self, industry: str) -> dict | None:
    """采集板块资金流向数据。

    Args:
        industry: 目标股票所属行业名称（从主题①获取）
    """
    result: dict = {}

    # 行业板块资金流向
    df_industry = self.safe_call_market_cached(
        "stock_board_industry_fund_flow_rank_em:今日",
        "sector_flow_industry",
        ak.stock_board_industry_fund_flow_rank_em,
        indicator="今日",
    )
    if df_industry is not None and industry:
        # 先精确匹配，避免“白酒/白酒Ⅱ”等相似名称误命中
        match = self._safe_filter(
            df_industry, "名称", industry,
            "sector_flow_industry", method="eq",
        )
        if match.empty:
            fuzzy_match = self._safe_filter(
                df_industry, "名称", industry,
                "sector_flow_industry", method="contains",
            )
            if not fuzzy_match.empty:
                hit_name = str(fuzzy_match.iloc[0].get("名称", ""))
                msg = (
                    f"sector_flow_industry: 行业 '{industry}' 未精确命中，"
                    f"回退到包含匹配并命中 '{hit_name}'"
                )
                self.errors.append(msg)
                logger.warning(msg)
                match = fuzzy_match
        if not match.empty:
            row = match.iloc[0]
            result["industry_name"] = industry

            # 排名获取优先级：
            # 1) 若存在显式排名列，优先使用该列；
            # 2) 否则回退到“当前 DataFrame 顺序”的行位置（reset_index 后）+1。
            rank_col = None
            for c in ("排名", "序号", "名次"):
                if c in df_industry.columns:
                    rank_col = c
                    break

            if rank_col is not None:
                rank_val = self._safe_float(row.get(rank_col))
                result["industry_rank"] = (
                    int(rank_val) if rank_val is not None else None
                )
            else:
                # 这里的排名语义是“按当前返回顺序的相对位置”，不依赖原始 index
                pos_df = df_industry.reset_index(drop=True)
                matched_name = str(row.get("名称", ""))
                pos_match = self._safe_filter(
                    pos_df, "名称", matched_name,
                    "sector_flow_industry", method="eq",
                )
                if pos_match.empty and matched_name:
                    pos_match = self._safe_filter(
                        pos_df, "名称", matched_name,
                        "sector_flow_industry", method="contains",
                    )
                result["industry_rank"] = (
                    int(pos_match.index[0]) + 1 if not pos_match.empty else None
                )

            result["industry_net_inflow_today"] = self._safe_float(
                row.get("今日主力净流入-净额")
            )
        else:
            msg = (
                f"sector_flow_industry: 行业 '{industry}' 在板块数据中"
                "精确和模糊匹配均未命中"
            )
            self.errors.append(msg)
            logger.warning(msg)
            result["industry_name"] = industry
            result["industry_rank"] = None
            result["industry_net_inflow_today"] = None

    # 概念板块（获取全市场热门概念 Top 5）
    df_concept = self.safe_call_market_cached(
        "stock_board_concept_fund_flow_rank_em:今日",
        "sector_flow_concept",
        ak.stock_board_concept_fund_flow_rank_em,
        indicator="今日",
    )
    if df_concept is not None:
        # 显式排序后再截取 Top5，避免依赖 AKShare 默认返回顺序
        concept_sorted = df_concept
        concept_rank_col = None
        for c in ("排名", "序号", "名次"):
            if c in df_concept.columns:
                concept_rank_col = c
                break

        if concept_rank_col is not None:
            concept_sorted = (
                df_concept.assign(
                    _rank_num=pd.to_numeric(df_concept[concept_rank_col], errors="coerce")
                )
                .sort_values("_rank_num", ascending=True, na_position="last")
                .drop(columns=["_rank_num"])
            )
        elif "今日主力净流入-净额" in df_concept.columns:
            concept_sorted = (
                df_concept.assign(
                    _inflow_num=pd.to_numeric(df_concept["今日主力净流入-净额"], errors="coerce")
                )
                .sort_values("_inflow_num", ascending=False, na_position="last")
                .drop(columns=["_inflow_num"])
            )
        else:
            msg = (
                "sector_flow_concept: 缺少排序列（排名/序号/名次/今日主力净流入-净额），"
                "按原始顺序截取 Top5"
            )
            self.errors.append(msg)
            logger.warning(msg)

        top5 = concept_sorted.head(5)
        result["hot_concepts_top5"] = [
            {
                "name": str(row.get("名称", "")),
                "net_inflow": self._safe_float(row.get("今日主力净流入-净额")),
            }
            for _, row in top5.iterrows()
        ]
    # df_concept 为 None 时不强行写入空列表：
    # 让 result 保持“真实采集成功语义”，避免在两路 API 都失败时被误判为 STATUS_OK

    return result if result else None
```

### 6.8 主题⑧ 北向资金持仓

**AKShare 函数：** `ak.stock_hsgt_hold_stock_em(market="北向", indicator="今日排行")`

**⚠️ 特别注意：** 2024年8月起，北向资金个股披露规则有变，数据可能不完整。

```python
def _collect_northbound(self) -> dict | None:
    """采集北向资金持仓数据。"""
    df = self.safe_call_market_cached(
        "stock_hsgt_hold_stock_em:北向:今日排行",
        "northbound",
        ak.stock_hsgt_hold_stock_em,
        market="北向",
        indicator="今日排行",
    )
    if df is None:
        return None

    # 从全市场数据中查找目标股票
    row = self._safe_filter(df, "代码", self.symbol, "northbound")
    if row.empty:
        # ✅ 这里返回非 None 是正确的：API 成功、数据完整，
        #    "不在持仓名单"本身就是有价值的查询结论（≠ 采集失败）。
        #    与 earnings_forecast 的 "available=False" 不同：
        #    后者是"所有 API 都没返回目标数据"，属于采集失败。
        return {
            "held": False,
            "shares_held": None,
            "market_value": None,
            "change_pct": None,
            "note": "未在北向资金持仓名单中找到（可能未持有或披露规则限制）",
        }

    r = row.iloc[0]
    return {
        "held": True,
        "shares_held": self._safe_float(r.get("持股数量")),
        "market_value": self._safe_float(r.get("持股市值")),
        "change_pct": self._safe_float(r.get("持股数量变化-增减比例")),
        "note": "北向资金披露规则2024年8月后有变化，数据仅供参考",
    }
```

### 6.9 主题⑨ 股东户数

**AKShare 函数：** `ak.stock_zh_a_gdhs_detail_em(symbol)`

**入参格式：** `bare`

**⚠️ 排序注意：** 不依赖 AKShare 返回顺序。需先按统计截止日显式降序，再取最近 N 期。

```python
def _collect_shareholder_count(self) -> list[dict] | None:
    """采集股东户数变化数据。"""
    df = self.safe_call(
        "shareholder_count",
        ak.stock_zh_a_gdhs_detail_em,
        symbol=self.symbol,
    )
    if df is None:
        return None

    # 显式排序后再截取，避免依赖 AKShare 默认返回顺序
    if "股东户数统计截止日" in df.columns:
        df = (
            df.assign(_stat_date=pd.to_datetime(df["股东户数统计截止日"], errors="coerce"))
            .sort_values("_stat_date", ascending=False, na_position="last")
            .drop(columns=["_stat_date"])
        )
    else:
        msg = "shareholder_count: 缺少列 '股东户数统计截止日'，按原始顺序截取最近N期"
        self.errors.append(msg)
        logger.warning(msg)

    # 取最近 N 期
    df = df.head(AKSHARE_SHAREHOLDER_PERIODS)

    results = []
    for _, row in df.iterrows():
        results.append({
            "date": str(row.get("股东户数统计截止日", "")),
            "count": self._safe_int(row.get("股东户数-本次")),
            "change_pct": self._safe_float(row.get("股东户数-增减比例")),
        })

    return results
```

### 6.10 主题⑩ 分红历史

**AKShare 函数：** `ak.stock_history_dividend(symbol, indicator="分红")`

**入参格式：** `lower`（小写前缀，如 `"sz000001"`）

**⚠️ 排序注意：** 不依赖 AKShare 返回顺序。需先按时间显式降序，再取最近 N 年。

```python
def _collect_dividend_history(self) -> list[dict] | None:
    """采集分红历史数据。"""
    lower_symbol = format_symbol(self.symbol, "lower")
    df = self.safe_call(
        "dividend_history",
        ak.stock_history_dividend,
        symbol=lower_symbol,
        indicator="分红",
    )
    if df is None:
        return None

    # 显式排序后再截取，避免依赖 AKShare 默认返回顺序
    if "年度" in df.columns:
        # 兼容 "2023" / "2023-12-31" 等格式，提取 4 位年份后降序
        df = (
            df.assign(
                _year_num=pd.to_numeric(
                    df["年度"].astype(str).str.extract(r"(\d{4})", expand=False),
                    errors="coerce",
                )
            )
            .sort_values("_year_num", ascending=False, na_position="last")
            .drop(columns=["_year_num"])
        )
    elif "除权除息日" in df.columns:
        # 若无“年度”列，回退到除权除息日排序
        df = (
            df.assign(_ex_date=pd.to_datetime(df["除权除息日"], errors="coerce"))
            .sort_values("_ex_date", ascending=False, na_position="last")
            .drop(columns=["_ex_date"])
        )
    else:
        msg = "dividend_history: 缺少排序列（年度/除权除息日），按原始顺序截取"
        self.errors.append(msg)
        logger.warning(msg)

    # 取最近 N 年
    df = df.head(AKSHARE_DIVIDEND_YEARS)

    results = []
    for _, row in df.iterrows():
        results.append({
            "year": str(row.get("年度", "")),
            "dividend_per_share": self._safe_float(row.get("累计股息")),
            "ex_date": str(row.get("除权除息日", "")),
        })

    return results
```

### 6.11 主题⑪ 业绩预告

**AKShare 函数：** `ak.stock_yjyg_em(date)`

**入参格式：** 日期格式 `YYYYMMDD`（必须是季度末日期）

**⚠️ 注意：** 返回全市场数据，需自行筛选。

```python
def _collect_earnings_forecast(self) -> dict | None:
    """采集业绩预告数据。

    策略：从最近的季度末日期开始倒推查找，直到找到该股票的预告。

    状态判定：
    - 找到预告 → STATUS_OK + available=True
    - 至少有一次 API 成功返回但未匹配到 → STATUS_NO_DATA + available=False
    - 所有 API 调用均失败 → 返回 None（交给 _safe_collect 标记 STATUS_FAILED）
    """
    # 生成最近的季度末日期列表（倒序）
    quarter_ends = self._get_recent_quarter_ends(lookback=4)
    had_any_successful_fetch = False

    for qe_date in quarter_ends:
        df = self.safe_call_market_cached(
            f"stock_yjyg_em:{qe_date}",
            "earnings_forecast",
            ak.stock_yjyg_em,
            date=qe_date,
        )
        if df is None:
            continue

        # 至少有一次 API 成功拿到了全市场数据
        had_any_successful_fetch = True

        row = self._safe_filter(df, "股票代码", self.symbol, "earnings_forecast")
        if row.empty:
            continue

        r = row.iloc[0]
        self.topic_status["earnings_forecast"] = self.STATUS_OK
        return {
            "latest_period": qe_date,
            "forecast_type": str(r.get("业绩变动类型", "")),
            "forecast_range": str(r.get("预测内容", "")),
            "available": True,
        }

    if had_any_successful_fetch:
        # API 成功但该股票确实无业绩预告
        logger.info(
            f"earnings_forecast: 最近 {len(quarter_ends)} 个季度均未找到 "
            f"{self.symbol} 的业绩预告（API 正常，该股票无预告）"
        )
        self.topic_status["earnings_forecast"] = self.STATUS_NO_DATA
        return {
            "latest_period": None,
            "forecast_type": None,
            "forecast_range": None,
            "available": False,
        }
    else:
        # 所有 API 调用均失败 → 返回 None，_safe_collect 会标记 STATUS_FAILED
        logger.warning(
            f"earnings_forecast: {len(quarter_ends)} 次 API 调用全部失败"
        )
        return None

@staticmethod
def _get_recent_quarter_ends(
    lookback: int = 4,
    today: date | None = None,
) -> list[str]:
    """获取最近 N 个已过去的季度末日期（YYYYMMDD 格式，倒序）。

    算法：从当前年份开始，枚举所有季度末日期（12/31, 09/30, 06/30, 03/31），
    仅保留 <= today 的日期，取最近 lookback 个。

    Args:
        lookback: 返回的季度末日期个数
        today: 基准日期（默认 None 表示使用 date.today()，
               测试时可直接注入以避免 mock）

    示例（today = 2026-02-07, lookback = 4）：
        → ["20251231", "20250930", "20250630", "20250331"]
    """
    if today is None:
        today = date.today()

    # 季度末日期模板（月, 日），倒序排列
    _QUARTER_ENDS = [(12, 31), (9, 30), (6, 30), (3, 31)]

    results: list[str] = []
    year = today.year

    while len(results) < lookback:
        for q_month, q_day in _QUARTER_ENDS:
            qe_date = date(year, q_month, q_day)
            if qe_date <= today:
                results.append(f"{year}{q_month:02d}{q_day:02d}")
                if len(results) >= lookback:
                    break
        year -= 1

    return results
```

### 6.12 主题⑫ 股权质押

**AKShare 函数：** `ak.stock_gpzy_pledge_ratio_em()`

**⚠️ 注意：** 返回全市场数据，需自行筛选。

```python
def _collect_pledge_ratio(self) -> dict | None:
    """采集股权质押数据。"""
    df = self.safe_call_market_cached(
        "stock_gpzy_pledge_ratio_em",
        "pledge_ratio",
        ak.stock_gpzy_pledge_ratio_em,
    )
    if df is None:
        return None

    row = self._safe_filter(df, "股票代码", self.symbol, "pledge_ratio")
    if row.empty:
        # ✅ API 成功，不在列表 = 无质押，是有效查询结论，返回非 None
        return {"ratio_pct": 0.0, "pledged_shares": None, "risk_level": "低"}

    r = row.iloc[0]
    ratio = self._safe_float(r.get("质押比例"))
    risk = self._judge_pledge_risk(ratio)

    return {
        "ratio_pct": ratio,
        "pledged_shares": self._safe_float(r.get("质押股数")),
        "risk_level": risk,
    }

@staticmethod
def _judge_pledge_risk(ratio: float | None) -> str:
    """根据质押比例判断风险等级。"""
    if ratio is None or ratio < 10:
        return "低"
    elif ratio < 30:
        return "中"
    elif ratio < 50:
        return "高"
    else:
        return "极高"
```

---

## 七、Pydantic 数据模型

### 7.1 模型定义文件

在 `stock_analyzer/module_a_models.py` 中定义：

```python
"""Pydantic models for module A (AKShare data collection)."""

from typing import Literal

from pydantic import BaseModel, Field


# ============================================================
# 元数据
# ============================================================

class AKShareMeta(BaseModel):
    """采集元数据。"""
    symbol: str = Field(description="股票代码（纯6位数字）")
    name: str = Field(description="股票名称")
    query_time: str = Field(description="采集时间 ISO 格式")
    data_errors: list[str] = Field(
        default_factory=list,
        description="采集过程中遇到的错误列表",
    )
    successful_topics: int = Field(
        default=0,
        description="成功采集的主题数（ok + no_data，总共12个）",
    )
    topic_status: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "每个主题的采集状态。"
            "ok=有数据, no_data=成功但无业务数据, failed=失败"
        ),
    )


# ============================================================
# 各主题数据模型
# ============================================================

class CompanyInfo(BaseModel):
    """主题①：公司基本信息。"""
    industry: str = Field(default="", description="所属行业")
    listing_date: str = Field(default="", description="上市日期")
    total_market_cap: float | None = Field(
        default=None, description="总市值（亿元）"
    )
    circulating_market_cap: float | None = Field(
        default=None, description="流通市值（亿元）"
    )
    total_shares: float | None = Field(
        default=None, description="总股本（亿股）"
    )
    circulating_shares: float | None = Field(
        default=None, description="流通股（亿股）"
    )


class RealtimeQuote(BaseModel):
    """主题②：实时行情快照。"""
    price: float | None = Field(default=None, description="最新价")
    change_pct: float | None = Field(default=None, description="涨跌幅(%)")
    volume: float | None = Field(default=None, description="成交量")
    turnover: float | None = Field(default=None, description="成交额")
    pe_ttm: float | None = Field(default=None, description="动态市盈率")
    pb: float | None = Field(default=None, description="市净率")
    turnover_rate: float | None = Field(default=None, description="换手率(%)")
    volume_ratio: float | None = Field(default=None, description="量比")
    change_60d_pct: float | None = Field(
        default=None, description="60日涨跌幅(%)"
    )
    change_ytd_pct: float | None = Field(
        default=None, description="年初至今涨跌幅(%)"
    )


class FinancialIndicator(BaseModel):
    """主题③：单期财务分析指标。"""
    report_date: str = Field(description="报告期")
    eps: float | None = Field(default=None, description="每股收益(元)")
    net_asset_per_share: float | None = Field(
        default=None, description="每股净资产(元)"
    )
    roe: float | None = Field(default=None, description="ROE(%)")
    gross_margin: float | None = Field(
        default=None, description="毛利率(%)"
    )
    net_margin: float | None = Field(
        default=None, description="净利率(%)"
    )
    revenue_growth: float | None = Field(
        default=None, description="营收同比增长率(%)"
    )
    profit_growth: float | None = Field(
        default=None, description="净利润同比增长率(%)"
    )
    debt_ratio: float | None = Field(
        default=None, description="资产负债率(%)"
    )
    current_ratio: float | None = Field(
        default=None, description="流动比率"
    )


class ValuationHistory(BaseModel):
    """主题④：估值历史数据与分位数。"""
    current_pe_ttm: float | None = Field(default=None, description="当前PE(TTM)")
    current_pb: float | None = Field(default=None, description="当前PB")
    pe_percentile: float | None = Field(
        default=None, description="PE历史分位数(0-100)"
    )
    pb_percentile: float | None = Field(
        default=None, description="PB历史分位数(0-100)"
    )
    current_ps_ttm: float | None = Field(default=None, description="当前PS(TTM)")
    current_dv_ttm: float | None = Field(
        default=None, description="当前股息率(TTM,%)"
    )
    history_summary: str = Field(
        default="", description="估值分位描述"
    )


class ValuationVsIndustry(BaseModel):
    """主题⑤：行业估值对比。"""
    stock_pe: float | None = Field(default=None, description="个股PE")
    industry_avg_pe: float | None = Field(
        default=None, description="行业平均PE"
    )
    industry_median_pe: float | None = Field(
        default=None, description="行业中位数PE"
    )
    stock_pb: float | None = Field(default=None, description="个股PB")
    industry_avg_pb: float | None = Field(
        default=None, description="行业平均PB"
    )
    relative_valuation: str = Field(
        default="", description="相对估值判断"
    )


class FundFlowDay(BaseModel):
    """单日资金流向。"""
    date: str = Field(description="日期")
    main_net_inflow: float | None = Field(
        default=None, description="主力净流入(万元)"
    )
    main_net_inflow_pct: float | None = Field(
        default=None, description="主力净流入占比(%)"
    )


class FundFlowSummary(BaseModel):
    """资金流向汇总。"""
    main_net_inflow_5d_total: float | None = Field(
        default=None, description="近5日主力净流入合计(万元，不足5日则为None)"
    )
    main_net_inflow_10d_total: float | None = Field(
        default=None, description="近10日主力净流入合计(万元，不足10日则为None)"
    )
    trend: str = Field(default="", description="资金流向趋势描述")


class FundFlow(BaseModel):
    """主题⑥：个股资金流向。"""
    recent_days: list[FundFlowDay] = Field(default_factory=list)
    summary: FundFlowSummary = Field(default_factory=FundFlowSummary)


class HotConcept(BaseModel):
    """热门概念板块。"""
    name: str
    net_inflow: float | None = None


class SectorFlow(BaseModel):
    """主题⑦：板块资金流向。"""
    industry_name: str = Field(default="", description="所属行业名称")
    industry_rank: int | None = Field(
        default=None, description="行业板块资金流向排名"
    )
    industry_net_inflow_today: float | None = Field(
        default=None, description="行业板块今日主力净流入"
    )
    hot_concepts_top5: list[HotConcept] = Field(default_factory=list)


class Northbound(BaseModel):
    """主题⑧：北向资金持仓。"""
    held: bool = Field(default=False, description="是否在北向持仓名单中")
    shares_held: float | None = Field(
        default=None, description="持股数量"
    )
    market_value: float | None = Field(
        default=None, description="持股市值"
    )
    change_pct: float | None = Field(
        default=None, description="持股数量增减比例(%)"
    )
    note: str = Field(
        default="", description="备注（如披露规则变化提醒）"
    )


class ShareholderCount(BaseModel):
    """单期股东户数。"""
    date: str = Field(description="统计截止日")
    count: int | None = Field(default=None, description="股东户数（整数）")
    change_pct: float | None = Field(
        default=None, description="增减比例(%)"
    )


class DividendRecord(BaseModel):
    """单年分红记录。"""
    year: str = Field(description="年度")
    dividend_per_share: float | None = Field(
        default=None, description="累计股息(元/股)"
    )
    ex_date: str = Field(default="", description="除权除息日")


class EarningsForecast(BaseModel):
    """主题⑪：业绩预告。"""
    latest_period: str | None = Field(
        default=None, description="最新预告报告期"
    )
    forecast_type: str | None = Field(
        default=None, description="业绩变动类型"
    )
    forecast_range: str | None = Field(
        default=None, description="预测内容"
    )
    available: bool = Field(default=False, description="是否有业绩预告")


class PledgeRatio(BaseModel):
    """主题⑫：股权质押。"""
    ratio_pct: float | None = Field(
        default=None, description="质押比例(%)"
    )
    pledged_shares: float | None = Field(
        default=None, description="质押股数"
    )
    risk_level: Literal["低", "中", "高", "极高"] = Field(
        default="低", description="质押风险等级"
    )


# ============================================================
# 顶层输出模型
# ============================================================

class AKShareData(BaseModel):
    """模块A 最终输出。

    对应概要设计中 akshare_data.json 的结构。
    所有字段均为可选（None 表示采集失败或数据不可用）。
    """
    meta: AKShareMeta
    company_info: CompanyInfo | None = None
    realtime_quote: RealtimeQuote | None = None
    financial_indicators: list[FinancialIndicator] | None = None
    valuation_history: ValuationHistory | None = None
    valuation_vs_industry: ValuationVsIndustry | None = None
    fund_flow: FundFlow | None = None
    sector_flow: SectorFlow | None = None
    northbound: Northbound | None = None
    shareholder_count: list[ShareholderCount] | None = None
    dividend_history: list[DividendRecord] | None = None
    earnings_forecast: EarningsForecast | None = None
    pledge_ratio: PledgeRatio | None = None
```

---

## 八、主流程编排

### 8.1 `AKShareCollector.collect()` 方法

```python
def collect(self) -> AKShareData:
    """
    执行全部12个主题的数据采集，串行调用，带间隔控制。

    Returns:
        AKShareData Pydantic 对象

    Raises:
        AKShareCollectionError: 整体采集终止（所有主题失败或连续超时熔断）
    """
    # 注：datetime 已在模块顶层统一导入（见 5.3 节 import 区块），
    #     此处无需重复 import。

    results: dict = {}
    industry: str = ""

    # ── 主题①：公司基本信息（最先执行，因为后续主题需要行业信息）──
    # 注：所有 _collect_*() 均通过 _safe_collect() 包装，
    #     确保解析阶段的异常（如 KeyError、TypeError）不会中断主流程。
    info = self._safe_collect("company_info", self._collect_company_info)
    if info is not None:
        results["company_info"] = info
        industry = info.get("industry", "")

    # ── 主题②：实时行情快照 ──
    quote = self._safe_collect("realtime_quote", self._collect_realtime_quote)
    if quote is not None:
        results["realtime_quote"] = quote

    # ── 主题③：财务分析指标 ──
    financial = self._safe_collect(
        "financial_indicators", self._collect_financial_indicators
    )
    if financial is not None:
        results["financial_indicators"] = financial

    # ── 主题④：估值历史数据 ──
    valuation = self._safe_collect(
        "valuation_history", self._collect_valuation_history
    )
    if valuation is not None:
        results["valuation_history"] = valuation

    # ── 主题⑤：行业估值对比 ──
    vs_industry = self._safe_collect(
        "valuation_vs_industry", self._collect_valuation_vs_industry
    )
    if vs_industry is not None:
        results["valuation_vs_industry"] = vs_industry

    # ── 主题⑥：个股资金流向 ──
    fund = self._safe_collect("fund_flow", self._collect_fund_flow)
    if fund is not None:
        results["fund_flow"] = fund

    # ── 主题⑦：板块资金流向 ──
    sector = self._safe_collect(
        "sector_flow", self._collect_sector_flow, industry
    )
    if sector is not None:
        results["sector_flow"] = sector

    # ── 主题⑧：北向资金持仓 ──
    northbound = self._safe_collect("northbound", self._collect_northbound)
    if northbound is not None:
        results["northbound"] = northbound

    # ── 主题⑨：股东户数 ──
    shareholders = self._safe_collect(
        "shareholder_count", self._collect_shareholder_count
    )
    if shareholders is not None:
        results["shareholder_count"] = shareholders

    # ── 主题⑩：分红历史 ──
    dividends = self._safe_collect(
        "dividend_history", self._collect_dividend_history
    )
    if dividends is not None:
        results["dividend_history"] = dividends

    # ── 主题⑪：业绩预告 ──
    forecast = self._safe_collect(
        "earnings_forecast", self._collect_earnings_forecast
    )
    if forecast is not None:
        results["earnings_forecast"] = forecast

    # ── 主题⑫：股权质押 ──
    pledge = self._safe_collect("pledge_ratio", self._collect_pledge_ratio)
    if pledge is not None:
        results["pledge_ratio"] = pledge

    # ── 统计成功数 ──
    # 基于 topic_status 判定，不再依赖 "v is not None"。
    # 三种状态：
    #   STATUS_OK      → 采集成功，有业务数据（计入成功）
    #   STATUS_NO_DATA → 采集成功，但无业务数据（计入成功）
    #   STATUS_FAILED  → 采集失败（不计入成功）
    successful = sum(
        1 for s in self.topic_status.values()
        if s in (self.STATUS_OK, self.STATUS_NO_DATA)
    )
    failed = sum(
        1 for s in self.topic_status.values()
        if s == self.STATUS_FAILED
    )

    if successful == 0:
        raise AKShareCollectionError(self.symbol, self.errors)

    logger.info(
        f"AKShare collection completed for {self.symbol}: "
        f"{successful}/12 topics succeeded "
        f"({failed} failed, {len(self.errors)} errors)"
    )

    # ── 组装最终输出 ──
    return AKShareData(
        meta=AKShareMeta(
            symbol=self.symbol,
            name=self.name,
            query_time=datetime.now().isoformat(),
            data_errors=self.errors,
            successful_topics=successful,
            topic_status=dict(self.topic_status),
        ),
        **results,
    )
```

### 8.2 模块入口函数

同属 `module_a_akshare.py`，共享 5.3 节的 import 区块。

```python
def collect_akshare_data(
    symbol: str,
    name: str,
    market_cache: AKShareMarketCache | None = None,
) -> AKShareData:
    """
    模块A 对外入口函数。

    Args:
        symbol: 股票代码（纯6位数字，如 "000001"）
        name: 股票名称（如 "平安银行"）
        market_cache: 可选的全市场缓存对象；批量分析多只股票时可复用

    Returns:
        AKShareData Pydantic 对象

    Raises:
        ValueError: symbol 格式不合法
        AKShareCollectionError: 整体采集终止（所有主题失败或连续超时熔断）
    """
    # 校验入参
    if not symbol.isdigit() or len(symbol) != 6:
        raise ValueError(
            f"Invalid symbol: '{symbol}', expected 6-digit string"
        )

    logger.info(f"Starting AKShare data collection for {symbol} ({name})")
    collector = AKShareCollector(symbol, name, market_cache=market_cache)
    result = collector.collect()
    logger.info(
        f"AKShare data collection finished for {symbol}: "
        f"{result.meta.successful_topics}/12 topics, "
        f"{len(result.meta.data_errors)} errors"
    )
    return result
```

### 8.3 命令行运行脚本 `run_module_a.py`

与 `run_module_b.py` 保持一致的风格，提供独立运行入口：

```python
"""Quick runner for module A AKShare data collection — run directly to test.

Usage (from project root):
    python stock_analyzer/run_module_a.py
    python stock_analyzer/run_module_a.py 600519 贵州茅台
    python stock_analyzer/run_module_a.py 600519.SH 贵州茅台
"""

import json
import sys
from pathlib import Path

# Allow running from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from stock_analyzer.utils import normalize_symbol                # noqa: E402
from stock_analyzer.module_a_akshare import collect_akshare_data  # noqa: E402


def main() -> None:
    raw_symbol = sys.argv[1] if len(sys.argv) > 1 else "000001"
    name = sys.argv[2] if len(sys.argv) > 2 else "平安银行"

    # 自动清洗代码格式：600519.SH → 600519
    symbol = normalize_symbol(raw_symbol)

    print(f"[module A] 开始采集: {symbol} {name}\n")

    result = collect_akshare_data(symbol=symbol, name=name)

    # 输出到控制台
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))

    # 同时保存到文件
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{symbol}_akshare_data.json"
    output_path.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[module A] 结果已保存到 {output_path}")


if __name__ == "__main__":
    main()
```

**与 `run_module_b.py` 的差异：**

| 对比项 | `run_module_a.py` | `run_module_b.py` |
|--------|-------------------|-------------------|
| 命令行参数 | `symbol name`（2个） | `symbol name industry`（3个） |
| 代码清洗 | ✅ `normalize_symbol()` 自动清洗 | ❌ 直接透传 |
| 执行方式 | 同步（`def main()`） | 异步（`async def main()` + `asyncio.run()`） |
| 输出文件 | ✅ 自动保存到 `output/` | ❌ 仅打印到控制台 |
| 默认股票 | `000001 平安银行` | `600000.SH 浦发银行` |

**用法示例：**

```bash
# 默认（平安银行）
python stock_analyzer/run_module_a.py

# 指定纯代码
python stock_analyzer/run_module_a.py 600519 贵州茅台

# 带交易所后缀（自动清洗）
python stock_analyzer/run_module_a.py 600519.SH 贵州茅台

# 深圳股票
python stock_analyzer/run_module_a.py 000001.SZ 平安银行
```

---

## 九、AKShare 注意事项

### 9.1 已知问题与应对策略

| 注意事项 | 说明 | 应对策略 |
|---------|------|---------|
| **频率限制** | AKShare 底层是爬虫，数据源网站会封 IP | 串行调用 + 3秒间隔（`AKSHARE_CALL_INTERVAL`） |
| **接口不稳定** | 接口经常因数据源网站改版而失效 | `safe_call()` 捕获异常，不中断流程 |
| **全市场返回** | 部分函数返回全市场数据（5000+ 行） | 按代码/行业过滤后使用 |
| **批量重复拉全量** | 多股票分析时会重复请求同一份全市场数据 | 使用 `AKShareMarketCache` 按 key+TTL 复用 |
| **中文列名** | 绝大多数函数返回中文列名 | 用中文字符串索引，列名变化时需更新 |
| **日期格式** | 大多数 `"YYYYMMDD"`，少数 `"YYYY-MM-DD"` | 在解析层统一处理 |
| **串行调用** | 不要并行调用多个 AKShare 函数 | 使用同步代码，不用 `asyncio` |
| **代码格式不一致** | 不同函数要求不同的代码格式 | 统一使用 `format_symbol()` 转换 |
| **参数名不一致** | `symbol` / `stock` / 无参数均有 | 在各采集方法中明确传参 |

### 9.2 列名防御性编程

由于 AKShare 可能在版本更新时修改列名（中文/英文都可能变化），需要在两个层面做防御：

**层面1：单行字段提取 — 使用 `row.get()`**

```python
# ✅ 推荐：使用 get() 防御列名变化
value = row.get("主力净流入-净额")

# ❌ 不推荐：直接索引可能 KeyError
value = row["主力净流入-净额"]
```

**层面2：全市场数据过滤 — 使用 `_safe_filter()`**

从全市场 DataFrame 中按列过滤目标股票时，必须先检查列是否存在：

```python
# ✅ 推荐：使用 _safe_filter()，列不存在时返回空 DataFrame + 记录错误
row = self._safe_filter(df, "代码", self.symbol, "realtime_quote")

# ❌ 不推荐：列名变化会直接抛 KeyError，中断整个采集流程
row = df[df["代码"] == self.symbol]
```

**层面3：兜底保护 — `_safe_collect()` 包装器**

即使 `_safe_filter()` 遗漏了某个位置，`collect()` 主流程中的 `_safe_collect()` 也会
捕获解析阶段的一切非预期异常，确保"单主题失败不中断"的容错承诺始终成立：

```python
# collect() 中的调用方式
quote = self._safe_collect("realtime_quote", self._collect_realtime_quote)
#        ↑ 即使 _collect_realtime_quote() 内部抛出任何异常，
#          也会被捕获、记录到 errors，返回 None，不影响后续主题
```

**🔒 硬性规则：**
- **字段提取**：`row` 级访问一律使用 `row.get("列名")` 或 `row.get("列名", 默认值)`；`DataFrame` 级列访问前需先校验列存在（如 `item/value`）。
- **列过滤**：一律使用 `self._safe_filter(df, "列名", value, topic)`
- **兜底**：`collect()` 中一律通过 `self._safe_collect(topic, collect_func)` 调用

### 9.3 软超时的线程堆积边界与防护

软超时机制（`safe_call()` 中 `future.result(timeout=...)` + `shutdown(wait=False)`）在超时后会留下后台线程继续执行 HTTP 请求。连续超时时这些线程会短时堆积。

**堆积数量上界：**

| 条件 | 值 |
|------|-----|
| 每次超时产生遗留线程 | 1 个 |
| 连续超时熔断阈值 | `AKSHARE_MAX_CONSECUTIVE_TIMEOUTS`（默认 3） |
| 最大堆积线程数 | **3 个**（触发熔断后停止创建新线程） |
| 遗留线程存活时间 | 取决于底层 HTTP socket 超时（通常 < 60s） |

**四层防护：**

1. **串行调用**：全流程串行，同一时刻只有 1 个 `safe_call()` 在执行，不会并发创建 executor；
2. **调用间隔限速**：`AKSHARE_CALL_INTERVAL`（默认 3s）使得超时线程有更多时间自然结束；
3. **连续超时熔断**：`_consecutive_timeouts` 计数器在连续 N 次超时后抛出 `AKShareCollectionError`，中止采集。任何一次成功调用都会重置计数器为 0；
4. **生产环境监控**：建议在调度层（主流程或外部监控）定期检查 `threading.active_count()`，线程数异常时告警。

**为何不复用共享单线程 executor：**

- 在软超时模型下，超时任务不会被强制终止。若复用单线程 executor，卡住任务会长期占用唯一 worker，后续任务只能排队，导致“一个慢请求拖死全局”；
- 当前设计选择“每次调用独立 executor”，牺牲少量创建/销毁开销，换取调用级隔离与更好的故障恢复能力；
- 鉴于模块A单轮调用规模较小（约 12~15 次），该开销在可接受范围内。

**熔断后的行为：**

```python
# safe_call() 中触发熔断时：
if self._consecutive_timeouts >= AKSHARE_MAX_CONSECUTIVE_TIMEOUTS:
    raise AKShareCollectionError(
        self.symbol, self.errors + [breaker_msg]
    )
    # ↑ 签名与 AKShareCollectionError(symbol, errors) 保持一致，
    #   breaker_msg 作为最后一条错误记录追加到 errors 列表中。
    #   此异常穿透 _safe_collect()，传播到 collect() 主流程并终止本轮采集。
    #   当前实现：不返回 partial result。
    #   如需优雅降级返回部分数据，需新增 partial_result 输出机制。
```

> **设计决策**：非超时类异常（如网络 ConnectionError、AKShare 业务异常）**不**累加连续超时计数，因为这些错误通常是偶发的，不代表网络持续不可用。只有连续的 `FutureTimeoutError` 才表明网络可能整体阻塞，需要熔断保护。

### 9.4 与模块 C 的数据共享

模块A和模块C都使用 AKShare，但**不共享调用**：
- **模块A**：采集基本面/资金面数据（12个主题）
- **模块C**：采集月K线数据（`ak.stock_zh_a_hist(period="monthly")`）

两者独立调用，互不影响。在主流程编排中，模块A 先执行完毕后再执行模块C（见概要设计 7.1 节），确保 AKShare 调用间隔。

---

## 十、性能与耗时估算

### 10.1 单次调用耗时基线

| 调用类型 | 平均耗时 | 说明 |
|---------|---------|------|
| 单股票查询 | 1-3 秒 | `stock_individual_info_em` 等 |
| 全市场查询 | 3-8 秒 | `stock_zh_a_spot_em` 等 |
| 调用间隔 | 3 秒 | `AKSHARE_CALL_INTERVAL`（可配置） |
| 软超时上限 | 30 秒 | `AKSHARE_CALL_TIMEOUT`（可配置） |

### 10.2 API 调用次数分析

12 个主题中，固定调用与可变调用拆分如下：

| 主题 | 调用次数 | 说明 |
|------|---------|------|
| ①-⑥、⑧-⑩、⑫（10 个主题） | 各 1 次（共 10 次） | 单次调用即可获取该主题数据 |
| ⑦ 板块资金流向 | 2 次 | 行业板块 + 概念板块 |
| ⑪ 业绩预告 | 1-4 次 | 循环最近 4 个季度末，首次命中即停 |
| 固定总计（不含⑪额外尝试） | 12 次 | 10 + 2 |

```
实际 API 调用次数 = 12（固定）+ earnings_forecast 额外尝试次数（0-3 次）
                  = 12 ~ 15 次
```

### 10.3 分场景耗时估算

**通用公式：**

```
总耗时 ≈ N × avg_call_time + (N - 1) × interval + timeout_count × timeout
```

其中：
- `N` = 实际 API 调用次数
- `avg_call_time` = 平均单次调用耗时（1-8 秒，取决于单股/全市场查询）
- `interval` = `AKSHARE_CALL_INTERVAL`（默认 3 秒）
- `timeout_count` = 触发软超时的调用次数
- `timeout` = `AKSHARE_CALL_TIMEOUT`（默认 30 秒）

**三档估算：**

| 场景 | API 次数 | 超时次数 | 估算耗时 | 说明 |
|------|---------|---------|---------|------|
| **乐观** | 12 次（业绩预告一次命中） | 0 | **~60-70 秒** | 全部正常响应，单股查询 ~2s，全市场 ~5s |
| **常规** | 14 次（业绩预告尝试 3 个季度） | 0 | **~75-90 秒** | 多数情况，前几个季度空返回 |
| **最坏** | 15 次（业绩预告遍历 4 个季度）+ 超时 | 2 | **~130-160 秒** | 部分调用触发 30s 超时 |
| **熔断** | ≤15 次（连续 3 次超时触发熔断） | 3 | **~90-120 秒** | 熔断中止后剩余主题不再执行 |

**推导示例（常规场景，14 次调用）：**

```
API 调用耗时：5 × 5s（全市场）+ 9 × 2s（单股）= 43s
调用间隔等待：13 × 3s = 39s
数据解析：< 1s
总计 ≈ 43 + 39 + 1 ≈ 83s
```

### 10.4 优化策略

1. **不可并行**：AKShare 底层爬虫不适合并行，保持串行
2. **可适当缩短间隔**：如果运行环境不易被封 IP（如服务器），可将 `AKSHARE_CALL_INTERVAL` 调至 2 秒
3. **缓存全市场数据**：采用 `AKShareMarketCache`（见 5.3 / 12.3）对 `stock_zh_a_spot_em`、板块资金流向、北向、质押、业绩预告（按日期）做批量复用
4. **超时值调优**：如果网络稳定，可将 `AKSHARE_CALL_TIMEOUT` 从 30s 缩短到 15s，减少最坏耗时
5. **熔断阈值调优**：`AKSHARE_MAX_CONSECUTIVE_TIMEOUTS` 默认 3，网络极不稳定时可适当提高，但需权衡线程堆积上限

---

## 十一、测试策略

### 11.1 测试层次

| 层次 | 测试内容 | 文件 |
|------|---------|------|
| **工具函数** | `format_symbol()`, `get_market()` | `tests/test_utils.py` |
| **解析逻辑** | `_parse_company_info()`, `_safe_float()`, `_calc_percentile()` 等 | `tests/test_module_a_parsers.py` |
| **API 可用性** | 12 个 AKShare API 是否正常返回 | `tests/test_akshare_api.py`（已有） |
| **集成测试** | `collect_akshare_data()` 端到端 | `tests/test_module_a_integration.py` |
| **Pydantic 模型** | 模型校验合法/非法输入 | `tests/test_module_a_models.py` |

### 11.2 单元测试要点

```python
# test_utils.py 示例

def test_format_symbol_bare():
    assert format_symbol("000001", "bare") == "000001"

def test_format_symbol_lower_sz():
    assert format_symbol("000001", "lower") == "sz000001"

def test_format_symbol_lower_sh():
    assert format_symbol("600519", "lower") == "sh600519"

def test_format_symbol_upper():
    assert format_symbol("000001", "upper") == "SZ000001"

def test_format_symbol_invalid_code():
    with pytest.raises(ValueError):
        format_symbol("12345", "bare")  # 不是6位

def test_get_market_sh():
    assert get_market("600519") == "sh"

def test_get_market_sz():
    assert get_market("000001") == "sz"
    assert get_market("300750") == "sz"

def test_normalize_symbol_bare():
    assert normalize_symbol("600519") == "600519"

def test_normalize_symbol_with_suffix():
    assert normalize_symbol("600519.SH") == "600519"
    assert normalize_symbol("000001.SZ") == "000001"
    assert normalize_symbol("600519.sh") == "600519"

def test_normalize_symbol_with_prefix():
    assert normalize_symbol("SH600519") == "600519"
    assert normalize_symbol("sz000001") == "000001"

def test_normalize_symbol_invalid():
    with pytest.raises(ValueError):
        normalize_symbol("贵州茅台")
    with pytest.raises(ValueError):
        normalize_symbol("12345")
```

```python
# test_module_a_parsers.py 示例

def test_collect_company_info_returns_none_when_safe_call_none(mocker):
    collector = AKShareCollector("000001", "平安银行")
    mocker.patch.object(collector, "safe_call", return_value=None)
    assert collector._collect_company_info() is None

def test_collect_company_info_calls_parse_when_df_available(mocker):
    collector = AKShareCollector("000001", "平安银行")
    fake_df = pd.DataFrame({"item": ["行业"], "value": ["银行"]})
    mocker.patch.object(collector, "safe_call", return_value=fake_df)
    parse_mock = mocker.patch.object(
        collector, "_parse_company_info", return_value={"industry": "银行"}
    )

    result = collector._collect_company_info()
    parse_mock.assert_called_once_with(fake_df)
    assert result == {"industry": "银行"}

def test_safe_float_normal():
    assert AKShareCollector._safe_float(3.14) == 3.14

def test_safe_float_none():
    assert AKShareCollector._safe_float(None) is None

def test_safe_float_nan():
    assert AKShareCollector._safe_float(float("nan")) is None

def test_safe_int_normal():
    assert AKShareCollector._safe_int("3456789") == 3456789

def test_safe_int_float_string():
    assert AKShareCollector._safe_int("3456789.0") == 3456789

def test_safe_int_none():
    assert AKShareCollector._safe_int(None) is None

def test_safe_int_nan():
    assert AKShareCollector._safe_int(float("nan")) is None

def test_parse_number_yi():
    assert AKShareCollector._parse_number("2156.80亿") == 2156.80

def test_parse_number_wan_to_yi():
    # "万"换算到"亿"：19406 × 0.0001 = 1.9406
    assert AKShareCollector._parse_number("19406万") == 1.9406

def test_parse_number_no_unit():
    # 无单位假定已是目标单位
    assert AKShareCollector._parse_number("3.5") == 3.5

def test_parse_number_target_wan():
    # target_unit="万"：亿换算到万
    assert AKShareCollector._parse_number("2.5亿", target_unit="万") == 25000.0

def test_parse_number_dash():
    assert AKShareCollector._parse_number("-") is None

def test_calc_percentile():
    series = pd.Series(range(100))
    assert AKShareCollector._calc_percentile(series, 50) == 50.0

def test_calc_percentile_with_numeric_strings():
    # 字符串数值应先被数值化，再参与分位数计算
    series = pd.Series([str(i) for i in range(1, 21)] + [None, "bad"])
    assert AKShareCollector._calc_percentile(series, "10") == 45.0

def test_collect_sector_flow_prefers_exact_match_over_contains(mocker):
    collector = AKShareCollector("600519", "贵州茅台")
    df_industry = pd.DataFrame([
        {"名称": "白酒Ⅱ", "排名": 1, "今日主力净流入-净额": 999.0},
        {"名称": "白酒", "排名": 2, "今日主力净流入-净额": 123.0},
    ])
    df_concept = pd.DataFrame([
        {"名称": "概念A", "排名": 2, "今日主力净流入-净额": 20.0},
        {"名称": "概念B", "排名": 1, "今日主力净流入-净额": 10.0},
    ])

    def fake_market_call(cache_key, topic, func, *args, **kwargs):
        if topic == "sector_flow_industry":
            return df_industry
        if topic == "sector_flow_concept":
            return df_concept
        return None

    mocker.patch.object(
        collector, "safe_call_market_cached", side_effect=fake_market_call
    )

    result = collector._collect_sector_flow("白酒")
    assert result["industry_name"] == "白酒"
    assert result["industry_rank"] == 2
    assert result["industry_net_inflow_today"] == 123.0

def test_collect_sector_flow_hot_concepts_top5_sorted_before_head(mocker):
    collector = AKShareCollector("600519", "贵州茅台")
    # 输入顺序故意打乱，验证会先按“排名”排序再取 Top5
    df_concept = pd.DataFrame([
        {"名称": "概念5", "排名": 5, "今日主力净流入-净额": 50.0},
        {"名称": "概念2", "排名": 2, "今日主力净流入-净额": 20.0},
        {"名称": "概念1", "排名": 1, "今日主力净流入-净额": 10.0},
        {"名称": "概念4", "排名": 4, "今日主力净流入-净额": 40.0},
        {"名称": "概念3", "排名": 3, "今日主力净流入-净额": 30.0},
        {"名称": "概念6", "排名": 6, "今日主力净流入-净额": 60.0},
    ])

    def fake_market_call(cache_key, topic, func, *args, **kwargs):
        if topic == "sector_flow_industry":
            return None
        if topic == "sector_flow_concept":
            return df_concept
        return None

    mocker.patch.object(
        collector, "safe_call_market_cached", side_effect=fake_market_call
    )

    result = collector._collect_sector_flow("")
    top5_names = [x["name"] for x in result["hot_concepts_top5"]]
    assert top5_names == ["概念1", "概念2", "概念3", "概念4", "概念5"]

def test_collect_sector_flow_logs_when_industry_not_matched(mocker):
    collector = AKShareCollector("600519", "贵州茅台")
    df_industry = pd.DataFrame([
        {"名称": "白酒Ⅱ", "排名": 1, "今日主力净流入-净额": 999.0},
    ])
    df_concept = pd.DataFrame([
        {"名称": "概念A", "排名": 1, "今日主力净流入-净额": 10.0},
    ])

    def fake_market_call(cache_key, topic, func, *args, **kwargs):
        if topic == "sector_flow_industry":
            return df_industry
        if topic == "sector_flow_concept":
            return df_concept
        return None

    mocker.patch.object(
        collector, "safe_call_market_cached", side_effect=fake_market_call
    )

    result = collector._collect_sector_flow("有色金属")
    assert result["industry_name"] == "有色金属"
    assert result["industry_rank"] is None
    assert result["industry_net_inflow_today"] is None
    assert any(
        "sector_flow_industry: 行业 '有色金属' 在板块数据中精确和模糊匹配均未命中" in e
        for e in collector.errors
    )

def test_collect_sector_flow_returns_none_when_both_sources_fail(mocker):
    collector = AKShareCollector("600519", "贵州茅台")

    mocker.patch.object(
        collector, "safe_call_market_cached", return_value=None
    )

    # 行业与概念两路全失败时应返回 None，
    # 由 _safe_collect() 统一标记 STATUS_FAILED
    assert collector._collect_sector_flow("白酒") is None

def test_judge_relative_valuation_negative_pe():
    # 亏损场景（PE<=0）应直接降级为“无法判断”
    assert AKShareCollector._judge_relative_valuation(-10.0, 30.0) == "数据不足，无法判断"
    assert AKShareCollector._judge_relative_valuation(20.0, -5.0) == "数据不足，无法判断"

def test_judge_pledge_risk():
    assert AKShareCollector._judge_pledge_risk(5.0) == "低"
    assert AKShareCollector._judge_pledge_risk(25.0) == "中"
    assert AKShareCollector._judge_pledge_risk(45.0) == "高"
    assert AKShareCollector._judge_pledge_risk(60.0) == "极高"

def test_get_recent_quarter_ends_early_year():
    """年初场景：2026-02 应包含 20250930 而不跳到 20250630。"""
    from datetime import date
    result = AKShareCollector._get_recent_quarter_ends(
        lookback=4, today=date(2026, 2, 7)
    )
    assert result == ["20251231", "20250930", "20250630", "20250331"]

def test_get_recent_quarter_ends_mid_year():
    """年中场景：2026-08 应从 20260630 开始。"""
    from datetime import date
    result = AKShareCollector._get_recent_quarter_ends(
        lookback=4, today=date(2026, 8, 15)
    )
    assert result == ["20260630", "20260331", "20251231", "20250930"]

def test_get_recent_quarter_ends_quarter_boundary():
    """恰好在季度末当天：20260331 应包含在结果中。"""
    from datetime import date
    result = AKShareCollector._get_recent_quarter_ends(
        lookback=4, today=date(2026, 3, 31)
    )
    assert result == ["20260331", "20251231", "20250930", "20250630"]
```

### 11.3 集成测试

```python
# test_module_a_integration.py 示例

def test_collect_akshare_data_basic():
    """基本功能测试：能采集到至少部分数据。"""
    result = collect_akshare_data("000001", "平安银行")

    assert result.meta.symbol == "000001"
    assert result.meta.name == "平安银行"
    assert result.meta.successful_topics > 0

    # 至少公司基本信息应该能采到
    if result.company_info is not None:
        assert result.company_info.industry != ""

def test_collect_akshare_data_invalid_symbol():
    """无效代码应该抛出 ValueError。"""
    with pytest.raises(ValueError):
        collect_akshare_data("12345", "测试")
```

---

## 十二、使用示例

### 12.1 基本使用

```python
from stock_analyzer.module_a_akshare import collect_akshare_data

# 采集数据
result = collect_akshare_data("000001", "平安银行")

# ⚠️ 各主题字段均可能为 None（采集失败时），访问前必须判空
print(f"采集成功主题数：{result.meta.successful_topics}/12")
print(f"采集错误：{result.meta.data_errors}")

if result.company_info is not None:
    print(f"行业：{result.company_info.industry}")

if result.realtime_quote is not None:
    print(f"当前价格：{result.realtime_quote.price}")

if result.valuation_history is not None:
    print(f"PE分位数：{result.valuation_history.pe_percentile}%")
```

### 12.2 输出为 JSON 文件

```python
import json

result = collect_akshare_data("000001", "平安银行")

# 方式1（推荐）：保留中文
json_str = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)

# 方式2：使用 Pydantic（中文会转义为 \uXXXX）
# json_str = result.model_dump_json(indent=2)

# 保存到文件
output_path = f"output/{result.meta.symbol}_akshare_data.json"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(json_str)
```

### 12.3 与主编排集成

```python
# main.py 中的使用方式（见概要设计 7.1 节）
from stock_analyzer.module_a_akshare import collect_akshare_data

async def analyze_stock(symbol: str, name: str):
    # 模块A：AKShare 数据采集（纯代码，同步执行）
    akshare_data = collect_akshare_data(symbol, name)

    # 从模块A获取行业信息，供模块B使用
    industry = ""
    if akshare_data.company_info:
        industry = akshare_data.company_info.industry

    # 模块B：网络搜索（需要行业信息）
    web_result = await run_web_research(symbol, name, industry)

    # 模块D：首席分析师
    # ...（传入 akshare_data.model_dump() 即可）
```

```python
# 批量分析场景：共享全市场缓存，复用 5000+ 行查询结果
from stock_analyzer.module_a_akshare import AKShareMarketCache, collect_akshare_data

def analyze_batch(stocks: list[tuple[str, str]]):
    shared_cache = AKShareMarketCache()  # TTL 由 AKSHARE_MARKET_CACHE_TTL_SEC 控制
    results = []
    for symbol, name in stocks:
        data = collect_akshare_data(symbol, name, market_cache=shared_cache)
        results.append(data)
    return results
```

---

## 十三、与项目其他模块的关系

### 13.1 共享文件

| 文件 | 模块A 使用方式 | 模块B 使用方式 |
|------|--------------|--------------|
| `config.py` | 读取 `AKSHARE_*` 配置 | 读取 `TAVILY_*`、`MODEL_*` 配置 |
| `logger.py` | `from stock_analyzer.logger import logger` | 相同 |
| `exceptions.py` | 定义 `AKShare*Error` 异常 | 定义 `Tavily*Error` 等异常 |

### 13.2 模块A 新增文件

| 文件 | 用途 |
|------|------|
| `module_a_models.py` | 模块A 的 Pydantic 数据模型 |
| `module_a_akshare.py` | 模块A 主逻辑（AKShareCollector + 入口函数） |
| `utils.py` | 工具函数（`format_symbol`, `get_market`, `normalize_symbol`） |
| `run_module_a.py` | 命令行运行脚本（独立测试用） |

### 13.3 不新增文件的内容

| 内容 | 放置位置 | 说明 |
|------|---------|------|
| 模块A 配置项 | `config.py`（追加） | 与模块B配置统一管理 |
| 模块A 异常类 | `exceptions.py`（追加） | 与模块B异常统一管理 |

---

## 十四、关键设计决策总结

| 决策 | 选择 | 理由 |
|------|------|------|
| 编程范式 | 纯同步代码 | AKShare 底层是爬虫，不适合异步并发 |
| 调用策略 | 串行 + 间隔 3秒 | 避免触发数据源 IP 封禁 |
| 异常处理 | 单主题失败不中断 | 容错优先，部分数据也有分析价值 |
| 数据模型 | 所有字段可选(`None`) | 部分主题可能采集失败 |
| 代码格式 | 统一工具函数转换 | AKShare 不同函数要求不同格式 |
| 数值解析 | `_safe_float()` 防御性解析 | AKShare 返回值类型不可靠 |
| 列名引用 | `dict.get()` 防御 | AKShare 中文列名可能变化 |
| 分位数计算 | 本模块内完成 | 纯数值计算，不需要 AI |
| 风险判断 | 简单规则引擎 | 质押比例、估值分位等有明确阈值 |
| 与模块C关系 | 独立调用 AKShare | 各取所需，互不影响 |

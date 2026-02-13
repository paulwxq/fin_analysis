# A股智能投研系统 — 工作流编排详细设计

> 背景文档：`stock_analyzer/docs/stock-analysis-design-v3.1.md`（概要设计 V3）

---

## 一、目标与范围

### 1.1 目标

将已完成的四个模块（A/B/C/D）串接为一个完整的分析流水线：

- **输入**：6位股票代码（支持 `600519` / `600519.SH` / `SH600519` 等格式）
- **输出**：`FinalReport` Pydantic模型（序列化和落盘由 CLI 层负责）

### 1.2 编排方案

使用 Python 标准库 `asyncio.gather` 实现模块A/B/C并行，模块D串行等待。具体分为五步：

| 步骤 | 方式 | 说明 |
|------|------|------|
| Step 1：股票信息查询 | 串行 | AKShare单点查询，获取 name 和 industry |
| Step 2：A/B/C并行 | `asyncio.gather` | 三模块并发，全部完成后收集结果 |
| Step 3：熔断检查 | 串行 | 统一检查三个结果，任一失败则中止 |
| Step 4：保存中间结果 | 串行（可选） | 将A/B/C结果持久化到 `output/` 目录 |
| Step 5：模块D | 串行 | 等待A/B/C全部成功后执行首席分析 |

---

## 二、整体流程

```
用户输入: raw_symbol (如 "600519" / "600519.SH")
          │
          ▼
  normalize_symbol(raw_symbol)  →  symbol = "600519"
          │
          ▼
┌─────────────────────────────────────────┐
│  Step 1: 股票信息查询（串行）            │
│  await asyncio.to_thread(               │
│      lookup_stock_info, symbol)         │
│  → (name: str, industry: str)           │
│  失败 → StockInfoLookupError → 终止      │
└──────────────────┬──────────────────────┘
                   │ name="贵州茅台", industry="白酒"
                   ▼
┌──────────────────────────────────────────────────────────┐
│  Step 2: 并行执行 A/B/C                                  │
│  asyncio.gather(..., return_exceptions=True)             │
│                                                          │
│  _run_module_a(symbol, name)                             │
│    └─ asyncio.to_thread(collect_akshare_data, ...)       │
│    └─ → AKShareData                                      │
│                                                          │
│  run_web_research(symbol, name, industry)                │
│    └─ 原生 async（含多轮 Tavily 搜索）                   │
│    └─ → WebResearchResult                                │
│                                                          │
│  run_technical_analysis(symbol, name)                    │
│    └─ 原生 async（AKShare 月K线 + pandas-ta + Agent）    │
│    └─ → TechnicalAnalysisResult                          │
│                                                          │
│  三个任务并发运行，全部完成后统一收集结果（含异常对象）   │
└──────────────────────────┬───────────────────────────────┘
                           │ (akshare_result, web_result, tech_result)
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Step 3: 熔断检查                                        │
│  _check_circuit_breaker(A, B, C)                         │
│                                                          │
│  任一失败 → logger.error 逐条记录                        │
│          → raise WorkflowCircuitBreakerError → 终止      │
│  全部成功 → 继续                                         │
└──────────────────────────┬───────────────────────────────┘
                           ▼
                  Step 4: 保存中间结果（WORKFLOW_SAVE_INTERMEDIATE=true）
                  _save_intermediate_results(symbol, A, B, C)
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Step 5: 串行执行模块D                                   │
│  await run_chief_analysis(symbol, name, A, B, C)         │
│  → FinalReport                                           │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
                  返回 FinalReport
                  （序列化和落盘由 run_workflow.py CLI 负责）
```

---

## 三、Step 1：股票信息查询

### 3.1 目的

工作流入口只接受股票代码，但模块B需要 `industry` 参数，模块A/B/C/D都需要 `name` 参数。必须在并行执行前先完成查询。

### 3.2 函数设计

**位置**：`stock_analyzer/workflow.py`

```python
import akshare as ak

_EMPTY_PLACEHOLDERS: frozenset[str] = frozenset({"-", "None", "nan", "N/A", "--"})


def lookup_stock_info(symbol: str) -> tuple[str, str]:
    """
    根据6位股票代码查询股票名称和行业。

    使用 AKShare ak.stock_individual_info_em(symbol=symbol) 查询。
    返回的 DataFrame 格式：两列 (item, value)，每行一个指标。

    Args:
        symbol: 6位纯数字股票代码

    Returns:
        (name, industry) 元组
        - name: 股票简称，如 "贵州茅台"
        - industry: 所属行业，如 "白酒"；若字段缺失返回空字符串

    Raises:
        StockInfoLookupError: AKShare调用失败，或返回数据中无法解析出 name
    """
    try:
        df = ak.stock_individual_info_em(symbol=symbol)
    except Exception as e:
        raise StockInfoLookupError(
            f"AKShare lookup failed for symbol {symbol}: {type(e).__name__}: {e}"
        ) from e

    if df is None or df.empty:
        raise StockInfoLookupError(
            f"AKShare returned empty data for symbol {symbol}"
        )

    def _get(field: str) -> str:
        rows = df[df["item"] == field]["value"]
        return str(rows.iloc[0]).strip() if not rows.empty else ""

    try:
        name = _get("股票简称")
        industry = _get("行业")
    except Exception as e:
        raise StockInfoLookupError(
            f"Failed to parse AKShare response for symbol {symbol}: "
            f"{type(e).__name__}: {e}"
        ) from e

    # 过滤 AKShare 可能返回的占位符，避免"空名股票"进入后续 Prompt
    if name in _EMPTY_PLACEHOLDERS:
        name = ""
    if industry in _EMPTY_PLACEHOLDERS:
        industry = ""

    if not name:
        raise StockInfoLookupError(
            f"Cannot resolve stock name for symbol {symbol} "
            "(stock may not exist or AKShare data incomplete)"
        )

    return name, industry
```

### 3.3 调用方式

`lookup_stock_info` 是同步阻塞函数，在 async 工作流中用 `asyncio.to_thread` 调用：

```python
name, industry = await asyncio.to_thread(lookup_stock_info, symbol)
```

### 3.4 失败处理

抛出 `StockInfoLookupError` → 工作流立即终止，不进入并行阶段。

---

## 四、Step 2：并行执行

### 4.1 模块A的线程包装

`collect_akshare_data()` 是同步阻塞函数（内部含大量 `time.sleep(AKSHARE_CALL_INTERVAL)` 调用，总耗时约30–120秒）。直接放入 `asyncio.gather` 会阻塞事件循环，导致模块B和C的异步I/O无法并发。

用 `asyncio.to_thread` 将其投入线程池：

```python
async def _run_module_a(symbol: str, name: str) -> AKShareData:
    """Wrap synchronous collect_akshare_data in a thread pool."""
    return await asyncio.to_thread(collect_akshare_data, symbol, name)
```

> `asyncio.to_thread` 是 Python 3.9+ 官方推荐方式，等价于 `loop.run_in_executor(None, func, *args)`。本项目要求 Python 3.12，完全支持。
>
> **批量扩展注意**：`asyncio.to_thread` 使用默认 `ThreadPoolExecutor`（大小 `min(32, os.cpu_count() + 4)`）。当前"单次分析一只股票"场景下无任何问题。若未来需要在同一进程内并发分析多只股票，模块A的高耗时线程（30–120秒）可能耗尽默认线程池。届时建议在 `config.py` 中创建专用 `ThreadPoolExecutor`，改用 `loop.run_in_executor(custom_executor, ...)` 替代 `asyncio.to_thread`。

### 4.2 gather 调用

```python
timeout = WORKFLOW_PARALLEL_TIMEOUT if WORKFLOW_PARALLEL_TIMEOUT > 0 else None
try:
    akshare_result, web_result, tech_result = await asyncio.wait_for(
        asyncio.gather(
            _run_module_a(symbol, name),
            run_web_research(symbol=symbol, name=name, industry=industry),
            run_technical_analysis(symbol=symbol, name=name),
            return_exceptions=True,
        ),
        timeout=timeout,
    )
except asyncio.TimeoutError as e:
    logger.warning(
        f"[Workflow] Parallel phase timed out after {WORKFLOW_PARALLEL_TIMEOUT}s. "
        "Async tasks (modules B/C) have been cancelled. "
        "The synchronous thread running module A cannot be forcibly stopped and "
        "may continue running in the background until its current AKShare call "
        "completes — residual module A log entries may appear after this error."
    )
    raise WorkflowCircuitBreakerError(
        f"Parallel phase timed out after {WORKFLOW_PARALLEL_TIMEOUT}s"
    ) from e
```

`return_exceptions=True`：某个任务抛出异常时，其余任务继续运行至完成，异常以结果值形式返回，不立即传播。这确保三个模块全部执行后再统一进行熔断判断，充分利用已完成的工作。

> **线程取消限制**：`asyncio.wait_for` 超时后，模块B/C（原生 async）会收到 `CancelledError` 正常退出，但模块A（`asyncio.to_thread` 包装）的底层线程**无法立即终止**，会继续运行直到当前 AKShare 调用自然完成或超时。这是 Python asyncio 的已知限制。模块A内部的 `AKSHARE_CALL_TIMEOUT` 会确保单次调用最终结束，不会永久泄漏。

### 4.3 执行结果类型

| 变量 | 成功时类型 | 失败时类型 |
|------|----------|----------|
| `akshare_result` | `AKShareData` | `BaseException` 子类实例 |
| `web_result` | `WebResearchResult` | `BaseException` 子类实例 |
| `tech_result` | `TechnicalAnalysisResult` | `BaseException` 子类实例 |

---

## 五、Step 3：熔断检查

### 5.1 触发条件

三个模块中任一满足以下条件时触发熔断：

| 条件 | 适用模块 | 说明 |
|------|---------|------|
| `isinstance(result, BaseException)` | A/B/C | 模块执行时抛出异常 |
| `result is None` | A/B/C | 模块返回 None |

**说明**：模块A在所有12个主题全部失败时会直接抛出 `AKShareCollectionError`，已由第一条异常检查覆盖。部分主题失败（返回有效 `AKShareData`）不触发熔断，但当成功主题数低于 `WORKFLOW_AKSHARE_MIN_TOPICS_WARN`（默认6）时，记录 `logger.warning` 提示数据质量受限，工作流继续执行。模块C内部存在多条 fallback 路径（当前实现为6处：数据获取/规范化失败、历史数据不足、指标计算失败、特征提取意外异常、Agent调用失败、最终结果构造失败），均返回 `confidence` 为 0.2 或 0.35 的有效 `TechnicalAnalysisResult`，既非异常也非 None，**不触发熔断**；模块D的 `data_quality_report` 负责向下游标注此低置信度结果。

### 5.2 函数设计

```python
def _check_circuit_breaker(
    akshare_result: AKShareData | BaseException | None,
    web_result: WebResearchResult | BaseException | None,
    tech_result: TechnicalAnalysisResult | BaseException | None,
) -> None:
    """
    对 A/B/C 三个模块的结果进行熔断检查。

    发现任何失败或空结果时，逐条 logger.error 并抛出 WorkflowCircuitBreakerError。
    """
    failures: list[str] = []

    if isinstance(akshare_result, BaseException):
        logger.debug(
            "[Circuit breaker] module_a exception detail",
            exc_info=(type(akshare_result), akshare_result, akshare_result.__traceback__),
        )
        failures.append(f"module_a: {type(akshare_result).__name__}: {akshare_result}")
    elif akshare_result is None:
        failures.append("module_a: returned None")
    elif akshare_result.meta.successful_topics < WORKFLOW_AKSHARE_MIN_TOPICS_WARN:
        logger.warning(
            f"[Circuit breaker] module_a: only "
            f"{akshare_result.meta.successful_topics}/12 topics succeeded, "
            f"chief analysis context may be limited"
        )

    if isinstance(web_result, BaseException):
        logger.debug(
            "[Circuit breaker] module_b exception detail",
            exc_info=(type(web_result), web_result, web_result.__traceback__),
        )
        failures.append(f"module_b: {type(web_result).__name__}: {web_result}")
    elif web_result is None:
        failures.append("module_b: returned None")

    if isinstance(tech_result, BaseException):
        logger.debug(
            "[Circuit breaker] module_c exception detail",
            exc_info=(type(tech_result), tech_result, tech_result.__traceback__),
        )
        failures.append(f"module_c: {type(tech_result).__name__}: {tech_result}")
    elif tech_result is None:
        failures.append("module_c: returned None")

    if failures:
        for msg in failures:
            logger.error(f"[Circuit breaker] {msg}")
        raise WorkflowCircuitBreakerError(
            f"Workflow aborted: {len(failures)} module(s) failed: "
            + "; ".join(failures)
        )
```

---

## 六、Step 4：保存中间结果（可选）

### 6.1 目的

将A/B/C的结果持久化到 `output/` 目录，方便调试和单模块复用（例如只重跑模块D时可直接读取已有文件）。序列化格式与各模块独立运行脚本（`run_module_a/b/c.py`）一致，文件名前缀统一使用规范化后的6位纯数字代码（如 `600519`）。

### 6.2 输出文件

| 模块 | 输出文件 |
|------|---------|
| 模块A | `output/{symbol}_akshare_data.json` |
| 模块B | `output/{symbol}_web_research.json` |
| 模块C | `output/{symbol}_technical_analysis.json` |

> 模块D的最终报告（`output/{symbol}_final_report.json`）由 CLI 层（`run_workflow.py`）负责写入，不在此函数范围内。

### 6.3 函数设计

```python
def _save_intermediate_results(
    symbol: str,
    akshare_data: AKShareData,
    web_research: WebResearchResult,
    technical_analysis: TechnicalAnalysisResult,
) -> None:
    """Save A/B/C intermediate results to output/ for debugging and replay."""
    output_dir = Path(WORKFLOW_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / f"{symbol}_akshare_data.json").write_text(
        json.dumps(akshare_data.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / f"{symbol}_web_research.json").write_text(
        dump_web_research_result_json(web_research),
        encoding="utf-8",
    )
    (output_dir / f"{symbol}_technical_analysis.json").write_text(
        dump_technical_result_json(technical_analysis),
        encoding="utf-8",
    )
    logger.info(f"[Workflow] Intermediate results saved to {output_dir}/")
```

序列化函数来源：
- `dump_web_research_result_json` — `module_b_websearch.py`
- `dump_technical_result_json` — `module_c_technical.py`

JSON 内容与单独运行各模块脚本时的序列化方式完全一致（复用同一组序列化函数）。

> **文件命名差异说明**：`run_module_b.py` 直接使用用户传入的原始 symbol（未规范化，如 `600519.SH`）作为文件名前缀，而工作流始终使用规范化后的6位代码（如 `600519`）。因此，`run_module_b.py` 产出的文件名（`600519.SH_web_research.json`）与工作流产出的（`600519_web_research.json`）可能不同，不能按 workflow 固定命名自动发现，需手工传路径或重命名。模块A和模块C的 runner 内部均调用了 `normalize_symbol`，不存在此差异。

### 6.4 控制开关

由配置项 `WORKFLOW_SAVE_INTERMEDIATE` 控制，默认 `True`。熔断触发后不执行此步骤。

---

## 七、Step 5：模块D串行执行

A/B/C全部通过熔断检查后，串行调用模块D：

```python
final_report = await run_chief_analysis(
    symbol=symbol,
    name=name,
    akshare_data=akshare_result,
    web_research=web_result,
    technical_analysis=tech_result,
)
```

模块D内部已有重试逻辑（`CHIEF_OUTPUT_RETRIES`），工作流层不额外重试。模块D抛出的 `ChiefAnalysisError` 直接向上传播，由CLI入口统一处理。

---

## 八、新增异常类

在 `stock_analyzer/exceptions.py` 末尾追加：

```python
# ── 工作流编排异常 ──

class WorkflowError(Exception):
    """Base class for workflow orchestration failures."""


class StockInfoLookupError(WorkflowError):
    """Failed to look up stock name/industry from AKShare before parallel execution."""


class WorkflowCircuitBreakerError(WorkflowError):
    """
    One or more of modules A/B/C produced an exception or returned None.
    The workflow is aborted. All failure details are logged at ERROR level before raising.
    """
```

---

## 九、新增配置项

在 `stock_analyzer/config.py` 末尾追加：

```python
# ============================================================
# Workflow: orchestration config
# ============================================================

# Output directory for all module results and final report
WORKFLOW_OUTPUT_DIR: str = os.getenv("WORKFLOW_OUTPUT_DIR", "output")

# Whether to save intermediate A/B/C JSON outputs to disk during workflow run
WORKFLOW_SAVE_INTERMEDIATE: bool = (
    os.getenv("WORKFLOW_SAVE_INTERMEDIATE", "true").lower() == "true"
)

# Total timeout in seconds for the parallel A/B/C phase.
# Accepts any integer: positive = timeout in seconds; 0 or negative = no limit.
WORKFLOW_PARALLEL_TIMEOUT: int = int(os.getenv("WORKFLOW_PARALLEL_TIMEOUT", "1800"))

# Warn when module A succeeds on fewer than this many topics (out of 12)
WORKFLOW_AKSHARE_MIN_TOPICS_WARN: int = int(
    os.getenv("WORKFLOW_AKSHARE_MIN_TOPICS_WARN", "6")
)
```

---

## 十、主模块设计

### 10.1 文件位置

`stock_analyzer/workflow.py`

### 10.2 公开接口

```python
async def run_workflow(raw_symbol: str) -> FinalReport:
    """
    Full-pipeline entry point: from raw stock symbol to final analysis report.

    Args:
        raw_symbol: Stock code in any supported format:
                    "600519" / "600519.SH" / "SH600519" / "600519.sh"

    Returns:
        FinalReport Pydantic model with all analysis results.

    Raises:
        ValueError:                  raw_symbol format is invalid
        StockInfoLookupError:        cannot resolve stock name/industry
        WorkflowCircuitBreakerError: one or more of A/B/C failed completely
        ChiefAnalysisError:          module D output failed validation after retries
    """
```

### 10.3 完整实现骨架

```python
"""Workflow orchestrator: connects modules A/B/C/D into a single pipeline."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import akshare as ak

from stock_analyzer.config import (
    WORKFLOW_AKSHARE_MIN_TOPICS_WARN,
    WORKFLOW_OUTPUT_DIR,
    WORKFLOW_PARALLEL_TIMEOUT,
    WORKFLOW_SAVE_INTERMEDIATE,
)
from stock_analyzer.exceptions import StockInfoLookupError, WorkflowCircuitBreakerError
from stock_analyzer.logger import logger
from stock_analyzer.models import WebResearchResult
from stock_analyzer.module_a_akshare import collect_akshare_data
from stock_analyzer.module_a_models import AKShareData
from stock_analyzer.module_b_websearch import dump_web_research_result_json, run_web_research
from stock_analyzer.module_c_models import TechnicalAnalysisResult
from stock_analyzer.module_c_technical import dump_technical_result_json, run_technical_analysis
from stock_analyzer.module_d_chief import run_chief_analysis
from stock_analyzer.module_d_models import FinalReport
from stock_analyzer.utils import normalize_symbol

_EMPTY_PLACEHOLDERS: frozenset[str] = frozenset({"-", "None", "nan", "N/A", "--"})


def lookup_stock_info(symbol: str) -> tuple[str, str]:
    """Look up stock name and industry by 6-digit symbol via AKShare."""
    try:
        df = ak.stock_individual_info_em(symbol=symbol)
    except Exception as e:
        raise StockInfoLookupError(
            f"AKShare lookup failed for symbol {symbol}: {type(e).__name__}: {e}"
        ) from e

    if df is None or df.empty:
        raise StockInfoLookupError(
            f"AKShare returned empty data for symbol {symbol}"
        )

    def _get(field: str) -> str:
        rows = df[df["item"] == field]["value"]
        return str(rows.iloc[0]).strip() if not rows.empty else ""

    try:
        name = _get("股票简称")
        industry = _get("行业")
    except Exception as e:
        raise StockInfoLookupError(
            f"Failed to parse AKShare response for symbol {symbol}: "
            f"{type(e).__name__}: {e}"
        ) from e

    if name in _EMPTY_PLACEHOLDERS:
        name = ""
    if industry in _EMPTY_PLACEHOLDERS:
        industry = ""

    if not name:
        raise StockInfoLookupError(
            f"Cannot resolve stock name for symbol {symbol} "
            "(stock may not exist or AKShare data incomplete)"
        )
    return name, industry


async def _run_module_a(symbol: str, name: str) -> AKShareData:
    """Wrap synchronous collect_akshare_data in a thread pool."""
    return await asyncio.to_thread(collect_akshare_data, symbol, name)


def _check_circuit_breaker(
    akshare_result: AKShareData | BaseException | None,
    web_result: WebResearchResult | BaseException | None,
    tech_result: TechnicalAnalysisResult | BaseException | None,
) -> None:
    """
    对 A/B/C 三个模块的结果进行熔断检查。

    发现任何失败或空结果时，逐条 logger.error 并抛出 WorkflowCircuitBreakerError。
    """
    failures: list[str] = []

    if isinstance(akshare_result, BaseException):
        logger.debug(
            "[Circuit breaker] module_a exception detail",
            exc_info=(type(akshare_result), akshare_result, akshare_result.__traceback__),
        )
        failures.append(f"module_a: {type(akshare_result).__name__}: {akshare_result}")
    elif akshare_result is None:
        failures.append("module_a: returned None")
    elif akshare_result.meta.successful_topics < WORKFLOW_AKSHARE_MIN_TOPICS_WARN:
        logger.warning(
            f"[Circuit breaker] module_a: only "
            f"{akshare_result.meta.successful_topics}/12 topics succeeded, "
            f"chief analysis context may be limited"
        )

    if isinstance(web_result, BaseException):
        logger.debug(
            "[Circuit breaker] module_b exception detail",
            exc_info=(type(web_result), web_result, web_result.__traceback__),
        )
        failures.append(f"module_b: {type(web_result).__name__}: {web_result}")
    elif web_result is None:
        failures.append("module_b: returned None")

    if isinstance(tech_result, BaseException):
        logger.debug(
            "[Circuit breaker] module_c exception detail",
            exc_info=(type(tech_result), tech_result, tech_result.__traceback__),
        )
        failures.append(f"module_c: {type(tech_result).__name__}: {tech_result}")
    elif tech_result is None:
        failures.append("module_c: returned None")

    if failures:
        for msg in failures:
            logger.error(f"[Circuit breaker] {msg}")
        raise WorkflowCircuitBreakerError(
            f"Workflow aborted: {len(failures)} module(s) failed: "
            + "; ".join(failures)
        )


def _save_intermediate_results(
    symbol: str,
    akshare_data: AKShareData,
    web_research: WebResearchResult,
    technical_analysis: TechnicalAnalysisResult,
) -> None:
    """Save A/B/C intermediate results to output/ for debugging and replay."""
    output_dir = Path(WORKFLOW_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / f"{symbol}_akshare_data.json").write_text(
        json.dumps(akshare_data.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / f"{symbol}_web_research.json").write_text(
        dump_web_research_result_json(web_research),
        encoding="utf-8",
    )
    (output_dir / f"{symbol}_technical_analysis.json").write_text(
        dump_technical_result_json(technical_analysis),
        encoding="utf-8",
    )
    logger.info(f"[Workflow] Intermediate results saved to {output_dir}/")


async def run_workflow(raw_symbol: str) -> FinalReport:
    symbol = normalize_symbol(raw_symbol)
    logger.info(f"[Workflow] Starting analysis for {symbol}")

    # Step 1: 查询股票名称和行业（串行 pre-step）
    logger.info(f"[Workflow] Looking up stock info for {symbol}")
    try:
        name, industry = await asyncio.to_thread(lookup_stock_info, symbol)
    except StockInfoLookupError:
        logger.error(f"[Workflow] Stock info lookup failed for {symbol}")
        raise
    logger.info(f"[Workflow] Stock info resolved: name={name!r}, industry={industry!r}")

    # Step 2: 并行执行 A/B/C
    logger.info(
        f"[Workflow] Starting parallel execution of modules A/B/C for {symbol} {name}"
        f"（预计耗时 3–5 分钟，请耐心等待）"
    )
    timeout = WORKFLOW_PARALLEL_TIMEOUT if WORKFLOW_PARALLEL_TIMEOUT > 0 else None
    try:
        akshare_result, web_result, tech_result = await asyncio.wait_for(
            asyncio.gather(
                _run_module_a(symbol, name),
                run_web_research(symbol=symbol, name=name, industry=industry),
                run_technical_analysis(symbol=symbol, name=name),
                return_exceptions=True,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError as e:
        logger.warning(
            f"[Workflow] Parallel phase timed out after {WORKFLOW_PARALLEL_TIMEOUT}s. "
            "Async tasks (modules B/C) have been cancelled. "
            "The synchronous thread running module A cannot be forcibly stopped and "
            "may continue running in the background until its current AKShare call "
            "completes — residual module A log entries may appear after this error."
        )
        raise WorkflowCircuitBreakerError(
            f"Parallel phase timed out after {WORKFLOW_PARALLEL_TIMEOUT}s"
        ) from e

    # Step 3: 熔断检查
    _check_circuit_breaker(akshare_result, web_result, tech_result)

    # Step 4: 保存中间结果（可选）
    if WORKFLOW_SAVE_INTERMEDIATE:
        _save_intermediate_results(symbol, akshare_result, web_result, tech_result)

    # Step 5: 串行执行模块D
    logger.info(f"[Workflow] Starting chief analysis for {symbol} {name}")
    final_report = await run_chief_analysis(
        symbol=symbol,
        name=name,
        akshare_data=akshare_result,
        web_research=web_result,
        technical_analysis=tech_result,
    )
    logger.info(
        f"[Workflow] Analysis complete for {symbol}: "
        f"score={final_report.overall_score:.2f}, "
        f"confidence={final_report.overall_confidence}"
    )
    return final_report
```

---

## 十一、CLI入口设计

### 11.1 文件位置

`stock_analyzer/run_workflow.py`

### 11.2 调用方式

```bash
.venv/bin/python3 stock_analyzer/run_workflow.py <symbol>

# 示例
.venv/bin/python3 stock_analyzer/run_workflow.py 600519
.venv/bin/python3 stock_analyzer/run_workflow.py 600519.SH
.venv/bin/python3 stock_analyzer/run_workflow.py SH600519
```

### 11.3 退出码规范

| 情形 | stdout | stderr | exit code |
|------|--------|--------|-----------|
| 成功 | 完整JSON | 进度提示（启动信息 + 输出路径） | 0 |
| symbol格式错误 / 参数数量不对 | 无 | 错误说明 | 2 |
| 股票信息查询失败 | 无 | 错误说明 | 2 |
| 熔断触发 | 无 | 错误说明 | 1 |
| 模块D失败 | 无 | 错误说明 | 1 |
| 未预期错误 | 无 | 错误说明 + 查看日志提示 | 1 |

### 11.4 完整实现骨架

```python
"""CLI entry point for the full A/B/C/D workflow pipeline.

Usage (from project root):
    .venv/bin/python3 stock_analyzer/run_workflow.py <symbol>

    <symbol> supports: 600519 / 600519.SH / SH600519
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stock_analyzer.config import WORKFLOW_OUTPUT_DIR              # noqa: E402
from stock_analyzer.exceptions import (                            # noqa: E402
    ChiefAnalysisError,
    StockInfoLookupError,
    WorkflowCircuitBreakerError,
)
from stock_analyzer.logger import logger                           # noqa: E402
from stock_analyzer.module_d_chief import dump_final_report_json  # noqa: E402
from stock_analyzer.workflow import run_workflow                   # noqa: E402


async def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: .venv/bin/python3 stock_analyzer/run_workflow.py <symbol>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    raw_symbol = sys.argv[1].strip()

    try:
        print(f"[workflow] 开始全流程分析: {raw_symbol}\n", file=sys.stderr)
        final_report = await run_workflow(raw_symbol)

        json_str = dump_final_report_json(final_report)
        print(json_str)

        output_dir = Path(WORKFLOW_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        symbol = final_report.meta.symbol
        output_path = output_dir / f"{symbol}_final_report.json"
        output_path.write_text(json_str, encoding="utf-8")
        print(f"\n[workflow] 最终报告已保存到 {output_path}", file=sys.stderr)

    except ValueError as e:
        logger.error(f"Workflow input error: {e}")
        print(f"[workflow] 输入错误: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    except StockInfoLookupError as e:
        logger.error(f"Workflow stock info lookup failed: {e}")
        print(f"[workflow] 股票信息查询失败: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    except WorkflowCircuitBreakerError as e:
        logger.error(f"Workflow circuit breaker triggered: {e}")
        print(f"[workflow] 熔断触发，作业中止: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    except ChiefAnalysisError as e:
        logger.error(f"Workflow chief analysis failed: {e}")
        print(f"[workflow] 首席分析失败: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    except Exception as e:
        logger.exception(f"Workflow unexpected failure: {type(e).__name__}: {e}")
        print(f"[workflow] 未预期错误: {type(e).__name__}: {e}", file=sys.stderr)
        print("[workflow] 详细信息请查看 logs/stock_analyzer.log", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 十二、日志策略

| 阶段 | 级别 | 日志内容 |
|------|------|---------|
| 工作流启动 | INFO | `[Workflow] Starting analysis for {symbol}` |
| 股票信息查询开始 | INFO | `[Workflow] Looking up stock info for {symbol}` |
| 股票信息查询成功 | INFO | `[Workflow] Stock info resolved: name=..., industry=...` |
| 股票信息查询失败 | ERROR | `[Workflow] Stock info lookup failed for {symbol}` |
| 并行阶段开始 | INFO | `[Workflow] Starting parallel execution of modules A/B/C for {symbol} {name}（预计耗时 3–5 分钟，请耐心等待）` |
| 并行阶段超时 | WARNING | `[Workflow] Parallel phase timed out after Xs. ... residual module A log entries may appear after this error.` |
| 熔断：模块异常详情 | DEBUG | `[Circuit breaker] module_x exception detail`（含完整 traceback，由 `exc_info=` 传递） |
| 熔断：模块A低成功数 | WARNING | `[Circuit breaker] module_a: only X/12 topics succeeded, chief analysis context may be limited` |
| 熔断：单模块失败原因 | ERROR | `[Circuit breaker] module_x: ExceptionType: message` |
| 中间结果保存 | INFO | `[Workflow] Intermediate results saved to output/` |
| 模块D开始 | INFO | `[Workflow] Starting chief analysis for {symbol} {name}` |
| 工作流完成 | INFO | `[Workflow] Analysis complete for {symbol}: score=X.XX, confidence=高/中/低` |

各模块内部已有各自的日志，工作流层不重复记录模块内部的 INFO 日志。

---

## 十三、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `stock_analyzer/workflow.py` | **新增** | 工作流主模块：`lookup_stock_info`、`_run_module_a`、`_check_circuit_breaker`、`_save_intermediate_results`、`run_workflow` |
| `stock_analyzer/run_workflow.py` | **新增** | CLI入口，`asyncio.run(main())` |
| `stock_analyzer/exceptions.py` | **修改** | 末尾追加 `WorkflowError`、`StockInfoLookupError`、`WorkflowCircuitBreakerError` |
| `stock_analyzer/config.py` | **修改** | 末尾追加 `WORKFLOW_OUTPUT_DIR`、`WORKFLOW_SAVE_INTERMEDIATE`、`WORKFLOW_PARALLEL_TIMEOUT`、`WORKFLOW_AKSHARE_MIN_TOPICS_WARN` |

---

## 十四、关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 并行编排 | `asyncio.gather` | 三模块输入各不相同，可分别传参；支持与纯代码（模块A）混合 |
| 模块A并发化 | `asyncio.to_thread` | 模块A为同步阻塞函数（含 `time.sleep`），需放入线程池才能真正并发 |
| `return_exceptions=True` | 是 | 三模块全部跑完再统一熔断，避免因一个模块提前失败而浪费其他模块的已完成工作 |
| 熔断时机 | A/B/C全部完成后统一检查 | 见上一条 |
| 模块A全失败的熔断触发 | 由模块A内部抛出 `AKShareCollectionError` 覆盖；workflow层只做异常/None检查和低成功数 `logger.warning` | 模块A允许部分主题失败，只要有任意主题成功即返回有效 `AKShareData`，不触发熔断 |
| 股票信息查询数据源 | AKShare `stock_individual_info_em` | 与模块A使用相同接口，无需引入额外依赖 |
| 中间结果保存 | 可配置，默认开启 | 方便调试和单模块复用（如仅重跑模块D） |

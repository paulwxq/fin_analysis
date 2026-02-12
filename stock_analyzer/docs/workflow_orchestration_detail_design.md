# A股智能投研系统 — 工作流编排详细设计

> 背景文档：`stock_analyzer/docs/stock-analysis-design-v3.1.md`（概要设计 V3）

---

## 一、目标与范围

### 1.1 目标

将已完成的四个模块（A/B/C/D）串接为一个完整的分析流水线：

- **输入**：6位股票代码（支持 `600519` / `600519.SH` / `SH600519` 等格式）
- **输出**：`FinalReport` Pydantic模型 + `output/{symbol}_final_report.json`

### 1.2 编排方式说明

遵循概要设计决策：使用 `asyncio.gather` 并行编排模块 A/B/C，不使用 MAF 的 `ConcurrentBuilder`。MAF（`agent-framework==1.0.0b260130`）在本项目的作用仅是提供 `ChatAgent` 多轮对话与结构化输出能力，不参与模块级并行编排。

---

## 二、整体流程

```
用户输入: raw_symbol (如 "600519" / "600519.SH")
          │
          ▼
  normalize_symbol(raw_symbol)
          │ symbol = "600519"
          ▼
┌─────────────────────────────────┐
│  Step 1: 股票信息查询（串行）    │
│  lookup_stock_info(symbol)       │
│  → (name: str, industry: str)   │
│  [AKShare: stock_individual_info_em] │
└──────────────┬──────────────────┘
               │ name="贵州茅台", industry="白酒"
               ▼
┌──────────────────────────────────────────────────────────┐
│  Step 2: 并行数据准备（asyncio.gather, return_exceptions=True）│
│                                                          │
│  模块A: _run_module_a(symbol, name)                       │
│         [asyncio.to_thread 包装同步函数]  → AKShareData  │
│                                                          │
│  模块B: run_web_research(symbol, name, industry)         │
│         [原生 async]                → WebResearchResult  │
│                                                          │
│  模块C: run_technical_analysis(symbol, name)             │
│         [原生 async]            → TechnicalAnalysisResult│
│                                                          │
│  三个任务并发运行，全部完成后统一返回结果（或异常对象）    │
└──────────────────────────┬───────────────────────────────┘
                           │ (akshare_result, web_result, tech_result)
                           ▼
                  Step 3: 熔断检查
                  _check_circuit_breaker(...)
                  │ 任一失败/为空
                  ├──────────────────→ logger.error(每条失败原因)
                  │                    raise WorkflowCircuitBreakerError
                  │ 全部成功
                  ▼
                  Step 4: 保存中间结果（可选）
                  _save_intermediate_results(symbol, A, B, C)
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Step 5: 串行执行模块D                                    │
│  run_chief_analysis(symbol, name, A, B, C) → FinalReport │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
                  保存 output/{symbol}_final_report.json
                  返回 FinalReport
```

---

## 三、Step 1：股票信息查询（pre-step）

### 3.1 目的

工作流入口只接受股票代码，但模块 B 需要 `industry` 参数，模块 A/B/C/D 都需要 `name` 参数。必须在并行执行前先完成查询。

### 3.2 函数设计

```python
def lookup_stock_info(symbol: str) -> tuple[str, str]:
    """
    根据6位股票代码查询股票名称和行业。

    使用 AKShare ak.stock_individual_info_em(symbol=symbol) 查询。
    返回的 DataFrame 格式：两列 (item, value)，每行是一个指标。

    Args:
        symbol: 6位纯数字股票代码

    Returns:
        (name, industry) 元组
        - name: 股票简称，如 "贵州茅台"
        - industry: 所属行业，如 "白酒"；若数据中无此字段则返回空字符串

    Raises:
        StockInfoLookupError: AKShare 调用失败，或 name 为空（代码不存在）
    """
    import akshare as ak

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

    def _get_field(field_name: str) -> str:
        rows = df[df["item"] == field_name]["value"]
        return str(rows.iloc[0]).strip() if not rows.empty else ""

    name = _get_field("股票简称")
    industry = _get_field("行业")

    if not name:
        raise StockInfoLookupError(
            f"Cannot resolve stock name for symbol {symbol} "
            "(stock may not exist or AKShare data incomplete)"
        )

    return name, industry
```

### 3.3 异步调用方式

`lookup_stock_info` 是同步阻塞函数，在 `async` 工作流主函数中必须通过 `asyncio.to_thread` 调用：

```python
name, industry = await asyncio.to_thread(lookup_stock_info, symbol)
```

### 3.4 失败处理

- 抛出 `StockInfoLookupError` → 工作流立即终止，不进入并行阶段
- 日志级别：`logger.error`

---

## 四、Step 2：并行执行（asyncio.gather）

### 4.1 模块A的异步包装

**问题：** `collect_akshare_data()` 是同步阻塞函数（内部有大量 `time.sleep(AKSHARE_CALL_INTERVAL)` 调用，总耗时约 30–120 秒）。直接放入 `asyncio.gather` 会阻塞事件循环，导致模块B和C的异步I/O完全无法并发。

**解决方案：** 使用 `asyncio.to_thread` 将模块A投入线程池执行：

```python
async def _run_module_a(symbol: str, name: str) -> AKShareData:
    """Wrap synchronous collect_akshare_data in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(collect_akshare_data, symbol, name)
```

> `asyncio.to_thread` 是 Python 3.9+ 推荐方式，等价于 `loop.run_in_executor(None, func, *args)`。本项目要求 Python 3.12，完全支持。

### 4.2 gather 调用

```python
results = await asyncio.gather(
    _run_module_a(symbol, name),
    run_web_research(symbol=symbol, name=name, industry=industry),
    run_technical_analysis(symbol=symbol, name=name),
    return_exceptions=True,
)
akshare_result, web_result, tech_result = results
```

**`return_exceptions=True` 的作用：**
即使某个任务抛出异常，其余任务仍继续运行至完成，异常以结果值形式返回（而不是立刻传播）。这确保三个模块全部执行后，再统一判断是否熔断，充分利用已完成的工作。

### 4.3 执行结果类型

| 变量 | 成功时类型 | 异常时类型 |
|------|----------|----------|
| `akshare_result` | `AKShareData` | `Exception` 子类实例 |
| `web_result` | `WebResearchResult` | `Exception` 子类实例 |
| `tech_result` | `TechnicalAnalysisResult` | `Exception` 子类实例 |

---

## 五、Step 3：熔断检查

### 5.1 熔断触发条件

三个模块中任一满足以下条件时触发熔断：

| 条件 | 说明 |
|------|------|
| `isinstance(result, Exception)` | 模块执行时抛出异常（完全崩溃） |
| `result is None` | 模块返回 None |
| 模块A：`akshare_result.meta.successful_topics == 0` | 12个主题全部失败，数据完全为空 |

**注意：** 模块A设计上允许部分主题失败（`successful_topics > 0` 即视为有效结果），这是正常现象，**不触发熔断**。

### 5.2 函数设计

```python
def _check_circuit_breaker(
    akshare_result: AKShareData | BaseException,
    web_result: WebResearchResult | BaseException,
    tech_result: TechnicalAnalysisResult | BaseException,
) -> None:
    """
    对 A/B/C 三个模块的结果进行熔断检查。

    发现任何失败或空结果时，逐条记录 logger.error 并抛出 WorkflowCircuitBreakerError。
    """
    failures: list[str] = []

    if isinstance(akshare_result, BaseException):
        failures.append(
            f"module_a: {type(akshare_result).__name__}: {akshare_result}"
        )
    elif akshare_result is None:
        failures.append("module_a: returned None")
    elif akshare_result.meta.successful_topics == 0:
        failures.append("module_a: all 12 topics failed (successful_topics=0)")

    if isinstance(web_result, BaseException):
        failures.append(
            f"module_b: {type(web_result).__name__}: {web_result}"
        )
    elif web_result is None:
        failures.append("module_b: returned None")

    if isinstance(tech_result, BaseException):
        failures.append(
            f"module_c: {type(tech_result).__name__}: {tech_result}"
        )
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

## 六、Step 4：中间结果保存（可选）

### 6.1 目的

与 `run_module_a/b/c.py` 保持一致，将中间结果保存到 `output/` 目录，方便调试和单模块复用（如只重跑模块D）。

### 6.2 输出文件命名

| 模块 | 输出文件 |
|------|---------|
| 模块A | `output/{symbol}_akshare_data.json` |
| 模块B | `output/{symbol}_web_research.json` |
| 模块C | `output/{symbol}_technical_analysis.json` |
| 模块D（最终报告） | `output/{symbol}_final_report.json` |

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
    output_dir.mkdir(exist_ok=True)

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

> `dump_web_research_result_json` 来自 `module_b_websearch.py`，`dump_technical_result_json` 来自 `module_c_technical.py`，与单独运行 `run_module_b/c.py` 时的序列化方式完全一致。

### 6.4 控制开关

由配置项 `WORKFLOW_SAVE_INTERMEDIATE`（见第九节）控制，默认 `True`。熔断后不执行此步骤。

---

## 七、Step 5：模块D串行执行

在 A/B/C 全部成功并通过熔断检查后，串行调用模块D：

```python
final_report = await run_chief_analysis(
    symbol=symbol,
    name=name,
    akshare_data=akshare_result,
    web_research=web_result,
    technical_analysis=tech_result,
)
```

模块D内部已有重试逻辑（`CHIEF_OUTPUT_RETRIES`），不需要在工作流层面额外重试。模块D抛出的 `ChiefAnalysisError` 直接向上传播，由 CLI 入口捕获处理。

---

## 八、异常类设计

在 `stock_analyzer/exceptions.py` 的现有内容末尾追加：

```python
# ── 工作流编排异常 ──

class WorkflowError(Exception):
    """Base class for workflow orchestration failures."""


class StockInfoLookupError(WorkflowError):
    """Failed to look up stock name/industry from AKShare before parallel execution."""


class WorkflowCircuitBreakerError(WorkflowError):
    """
    One or more of modules A/B/C produced an exception, None, or completely empty result.
    The workflow is aborted. All failure details are logged at ERROR level before raising.
    """
```

---

## 九、配置项设计

在 `stock_analyzer/config.py` 的现有内容末尾追加：

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
        WorkflowError:               other workflow-level failures
    """
```

### 10.3 完整实现骨架

```python
"""Workflow orchestrator: connects modules A/B/C/D into a single pipeline."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from stock_analyzer.config import WORKFLOW_OUTPUT_DIR, WORKFLOW_SAVE_INTERMEDIATE
from stock_analyzer.exceptions import (
    StockInfoLookupError,
    WorkflowCircuitBreakerError,
)
from stock_analyzer.logger import logger
from stock_analyzer.models import WebResearchResult
from stock_analyzer.module_a_akshare import collect_akshare_data
from stock_analyzer.module_a_models import AKShareData
from stock_analyzer.module_b_websearch import dump_web_research_result_json, run_web_research
from stock_analyzer.module_c_models import TechnicalAnalysisResult
from stock_analyzer.module_c_technical import dump_technical_result_json, run_technical_analysis
from stock_analyzer.module_d_chief import dump_final_report_json, run_chief_analysis
from stock_analyzer.module_d_models import FinalReport
from stock_analyzer.utils import normalize_symbol


def lookup_stock_info(symbol: str) -> tuple[str, str]:
    """Look up stock name and industry by 6-digit symbol via AKShare."""
    import akshare as ak

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

    name = _get("股票简称")
    industry = _get("行业")

    if not name:
        raise StockInfoLookupError(
            f"Cannot resolve stock name for symbol {symbol}"
        )
    return name, industry


async def _run_module_a(symbol: str, name: str) -> AKShareData:
    """Wrap synchronous collect_akshare_data in a thread pool."""
    return await asyncio.to_thread(collect_akshare_data, symbol, name)


def _check_circuit_breaker(
    akshare_result: AKShareData | BaseException,
    web_result: WebResearchResult | BaseException,
    tech_result: TechnicalAnalysisResult | BaseException,
) -> None:
    failures: list[str] = []

    if isinstance(akshare_result, BaseException):
        failures.append(f"module_a: {type(akshare_result).__name__}: {akshare_result}")
    elif akshare_result is None:
        failures.append("module_a: returned None")
    elif akshare_result.meta.successful_topics == 0:
        failures.append("module_a: all 12 topics failed (successful_topics=0)")

    if isinstance(web_result, BaseException):
        failures.append(f"module_b: {type(web_result).__name__}: {web_result}")
    elif web_result is None:
        failures.append("module_b: returned None")

    if isinstance(tech_result, BaseException):
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
    output_dir = Path(WORKFLOW_OUTPUT_DIR)
    output_dir.mkdir(exist_ok=True)

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

    # Step 1: 查询股票信息（串行 pre-step）
    logger.info(f"[Workflow] Looking up stock info for {symbol}")
    try:
        name, industry = await asyncio.to_thread(lookup_stock_info, symbol)
    except StockInfoLookupError:
        logger.error(f"[Workflow] Stock info lookup failed for {symbol}")
        raise
    logger.info(f"[Workflow] Stock info resolved: name={name!r}, industry={industry!r}")

    # Step 2: 并行执行 A/B/C
    logger.info(f"[Workflow] Starting parallel execution of modules A/B/C for {symbol} {name}")
    akshare_result, web_result, tech_result = await asyncio.gather(
        _run_module_a(symbol, name),
        run_web_research(symbol=symbol, name=name, industry=industry),
        run_technical_analysis(symbol=symbol, name=name),
        return_exceptions=True,
    )

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

## 十一、CLI 入口设计

### 11.1 文件位置

`stock_analyzer/run_workflow.py`

### 11.2 调用方式

```bash
# 从项目根目录执行
.venv/bin/python3 stock_analyzer/run_workflow.py <symbol>

# 示例
.venv/bin/python3 stock_analyzer/run_workflow.py 600519
.venv/bin/python3 stock_analyzer/run_workflow.py 600519.SH
.venv/bin/python3 stock_analyzer/run_workflow.py SH600519
```

### 11.3 行为规范

| 情形 | stdout | stderr | exit code |
|------|--------|--------|-----------|
| 成功 | 完整 JSON | 无 | 0 |
| symbol格式错误 / 参数数量不对 | 无 | 错误说明 | 2 |
| 股票信息查询失败 | 无 | 错误说明 | 2 |
| 熔断触发（A/B/C 失败） | 无 | 错误说明 | 1 |
| 首席分析师失败（模块D） | 无 | 错误说明 | 1 |
| 未预期错误 | 无 | 错误说明 + 查看日志提示 | 1 |

### 11.4 完整实现骨架

```python
"""CLI entry point for the full A/B/C/D workflow pipeline.

Usage:
    .venv/bin/python3 stock_analyzer/run_workflow.py <symbol>

    <symbol> supports: 600519 / 600519.SH / SH600519
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from stock_analyzer.exceptions import (          # noqa: E402
    ChiefAnalysisError,
    StockInfoLookupError,
    WorkflowCircuitBreakerError,
)
from stock_analyzer.logger import logger          # noqa: E402
from stock_analyzer.module_d_chief import dump_final_report_json  # noqa: E402
from stock_analyzer.workflow import run_workflow  # noqa: E402
from stock_analyzer.config import WORKFLOW_OUTPUT_DIR  # noqa: E402


async def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: .venv/bin/python3 stock_analyzer/run_workflow.py <symbol>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    raw_symbol = sys.argv[1]

    try:
        print(f"[workflow] 开始全流程分析: {raw_symbol}\n")
        final_report = await run_workflow(raw_symbol)

        json_str = dump_final_report_json(final_report)
        print(json_str)

        output_dir = Path(WORKFLOW_OUTPUT_DIR)
        output_dir.mkdir(exist_ok=True)
        symbol = final_report.meta.symbol
        output_path = output_dir / f"{symbol}_final_report.json"
        output_path.write_text(json_str, encoding="utf-8")
        print(f"\n[workflow] 最终报告已保存到 {output_path}")

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
| 股票信息查询 | INFO | `[Workflow] Looking up stock info for {symbol}` |
| 股票信息解析成功 | INFO | `[Workflow] Stock info resolved: name=..., industry=...` |
| 股票信息查询失败 | ERROR | `[Workflow] Stock info lookup failed for {symbol}` |
| 并行阶段开始 | INFO | `[Workflow] Starting parallel execution of modules A/B/C for {symbol} {name}` |
| 熔断：单模块失败 | ERROR | `[Circuit breaker] module_x: ExceptionType: message` |
| 熔断触发 | ERROR | （由 `WorkflowCircuitBreakerError` 消息携带汇总信息） |
| 中间结果保存 | INFO | `[Workflow] Intermediate results saved to output/` |
| 模块D开始 | INFO | `[Workflow] Starting chief analysis for {symbol} {name}` |
| 工作流完成 | INFO | `[Workflow] Analysis complete for {symbol}: score=X.XX, confidence=高/中/低` |

各模块内部已有自己的日志输出，工作流层不重复记录模块内部的 INFO 日志。

---

## 十三、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `stock_analyzer/workflow.py` | **新增** | 工作流主模块（`run_workflow` + 辅助函数） |
| `stock_analyzer/run_workflow.py` | **新增** | CLI 入口 |
| `stock_analyzer/exceptions.py` | **修改** | 末尾追加 `WorkflowError`、`StockInfoLookupError`、`WorkflowCircuitBreakerError` |
| `stock_analyzer/config.py` | **修改** | 末尾追加 `WORKFLOW_OUTPUT_DIR`、`WORKFLOW_SAVE_INTERMEDIATE` |

---

## 十四、关键设计决策总结

| 决策 | 选择 | 理由 |
|------|------|------|
| 并行编排方式 | `asyncio.gather` | 三模块输入各不相同，MAF `ConcurrentBuilder` 不支持差异化输入 |
| 模块A并发化 | `asyncio.to_thread` | 模块A是同步阻塞函数（含 `time.sleep`），必须放入线程池才能真正并发 |
| `return_exceptions=True` | 是 | 让三模块全部跑完再统一熔断，避免因一个模块失败而浪费其他模块的工作 |
| 熔断时机 | A/B/C 全部完成后统一检查 | 见上一条 |
| 模块A部分失败的熔断阈值 | `successful_topics == 0` | 模块A允许单主题失败（设计决策），只要有任意主题成功即为有效结果 |
| 股票信息查询数据源 | AKShare `stock_individual_info_em` | 与模块A使用相同数据源（已验证可用），无需引入额外依赖 |
| 中间结果保存 | 可配置，默认开启 | 与 `run_module_a/b/c.py` 行为一致，方便调试和单模块复用 |
| MAF 使用范围 | 仅 `ChatAgent` | 工作流编排完全用 asyncio 原语；MAF 仅负责 B/C/D 三个 Agent 的多轮对话 |

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
    Check A/B/C results for failures.

    Any exception or None triggers circuit breaker with full failure details.
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
    symbol = normalize_symbol(raw_symbol)
    logger.info(f"[Workflow] Starting analysis for {symbol}")

    # Step 1: look up stock name and industry
    logger.info(f"[Workflow] Looking up stock info for {symbol}")
    try:
        name, industry = await asyncio.to_thread(lookup_stock_info, symbol)
    except StockInfoLookupError:
        logger.error(f"[Workflow] Stock info lookup failed for {symbol}")
        raise
    logger.info(f"[Workflow] Stock info resolved: name={name!r}, industry={industry!r}")

    # Step 2: parallel execution of A/B/C
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

    # Step 3: circuit breaker check
    _check_circuit_breaker(akshare_result, web_result, tech_result)

    # Step 4: save intermediate results (optional)
    if WORKFLOW_SAVE_INTERMEDIATE:
        _save_intermediate_results(symbol, akshare_result, web_result, tech_result)

    # Step 5: run module D
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

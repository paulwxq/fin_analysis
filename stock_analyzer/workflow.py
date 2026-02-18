"""Workflow orchestrator: connects modules A/B/C/D into a single pipeline."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
from pathlib import Path
from typing import TypedDict
from zoneinfo import ZoneInfo

import akshare as ak

from stock_analyzer.config import (
    WORKFLOW_AKSHARE_MIN_TOPICS_WARN,
    WORKFLOW_OUTPUT_DIR,
    WORKFLOW_PARALLEL_TIMEOUT,
    WORKFLOW_SAVE_INTERMEDIATE,
    WORKFLOW_USE_CACHE,
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
from stock_analyzer.utils import get_market, normalize_symbol

_EMPTY_PLACEHOLDERS: frozenset[str] = frozenset({"-", "None", "nan", "N/A", "--"})

# File suffixes for cached A/B/C outputs (relative to WORKFLOW_OUTPUT_DIR)
_CACHE_SUFFIXES = {
    "akshare": "_akshare_data.json",
    "web": "_web_research.json",
    "tech": "_technical_analysis.json",
}


def _try_load_cache(
    symbol: str,
) -> tuple[AKShareData, WebResearchResult, TechnicalAnalysisResult] | None:
    """Try loading cached A/B/C JSON files from output/.

    Returns the three model instances if ALL three files exist and parse
    successfully, otherwise returns None.
    """
    output_dir = Path(WORKFLOW_OUTPUT_DIR)
    paths = {k: output_dir / f"{symbol}{v}" for k, v in _CACHE_SUFFIXES.items()}

    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        logger.info(
            f"[Cache] Cache miss for {symbol}: "
            f"{len(missing)} file(s) not found: {', '.join(missing)}"
        )
        return None

    try:
        akshare_data = AKShareData.model_validate_json(
            paths["akshare"].read_text(encoding="utf-8")
        )
        web_research = WebResearchResult.model_validate_json(
            paths["web"].read_text(encoding="utf-8")
        )
        technical = TechnicalAnalysisResult.model_validate_json(
            paths["tech"].read_text(encoding="utf-8")
        )
    except Exception as e:
        logger.warning(
            f"[Cache] Cache files found for {symbol} but failed to parse: "
            f"{type(e).__name__}: {e}. Will run modules fresh."
        )
        return None

    logger.info(
        f"[Cache] Loaded cached A/B/C results for {symbol} from {output_dir}/"
    )
    return akshare_data, web_research, technical


class StockLookupInfo(TypedDict):
    symbol: str
    symbol_with_market_upper: str
    name: str
    industry: str
    date_beijing: str


def lookup_stock_info(symbol: str) -> StockLookupInfo:
    """Look up stock metadata by 6-digit symbol via AKShare with retry."""
    max_retries = 3
    last_error: Exception | None = None
    df = None

    for attempt in range(max_retries + 1):
        try:
            df = ak.stock_individual_info_em(symbol=symbol)
            if df is not None and not df.empty:
                # 成功获取数据，跳出重试循环
                break
            # 如果 df 为空，视为失败，抛出 ValueError 触发重试逻辑
            raise ValueError(f"AKShare returned empty data for symbol {symbol}")

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait_time = 2**attempt  # 1s, 2s, 4s
                logger.warning(
                    f"[Workflow] Stock info lookup failed (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}. Retrying in {wait_time}s..."
                )
                import time

                time.sleep(wait_time)
            else:
                logger.error(
                    f"[Workflow] Stock info lookup failed after {max_retries + 1} attempts."
                )

    # 循环结束后，如果 df 仍无效，则抛出最终异常
    if df is None or df.empty:
        if last_error:
            raise StockInfoLookupError(
                f"AKShare lookup failed for symbol {symbol} after retries: "
                f"{type(last_error).__name__}: {last_error}"
            ) from last_error
        else:
             raise StockInfoLookupError(
                f"AKShare returned empty data for symbol {symbol} (unexpected flow)"
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

    beijing_date = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    return StockLookupInfo(
        symbol=symbol,
        symbol_with_market_upper=f"{symbol}.{get_market(symbol).upper()}",
        name=name,
        industry=industry,
        date_beijing=beijing_date,
    )


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
            f"{akshare_result.meta.successful_topics}/15 topics succeeded, "
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
        stock_info = await asyncio.to_thread(lookup_stock_info, symbol)
    except StockInfoLookupError:
        logger.error(f"[Workflow] Stock info lookup failed for {symbol}")
        raise
    name = stock_info["name"]
    industry = stock_info["industry"]
    symbol_with_market_upper = stock_info["symbol_with_market_upper"]
    date_beijing = stock_info["date_beijing"]
    logger.info(
        "[Workflow] Stock info resolved: "
        f"name={name!r}, industry={industry!r}, "
        f"symbol_with_market_upper={symbol_with_market_upper!r}, date_beijing={date_beijing}"
    )

    # Step 2: load cached A/B/C results or run modules fresh
    cached = _try_load_cache(symbol) if WORKFLOW_USE_CACHE else None

    if cached is not None:
        akshare_result, web_result, tech_result = cached
        logger.info(
            f"[Workflow] Using cached A/B/C results for {symbol}, "
            "skipping module execution"
        )
    else:
        logger.info(
            f"[Workflow] Starting parallel execution of modules A/B/C for {symbol} {name}"
            f"（预计耗时 3–5 分钟，请耐心等待）"
        )
        timeout = WORKFLOW_PARALLEL_TIMEOUT if WORKFLOW_PARALLEL_TIMEOUT > 0 else None
        try:
            akshare_result, web_result, tech_result = await asyncio.wait_for(
                asyncio.gather(
                    _run_module_a(symbol, name),
                    run_web_research(
                        symbol=symbol,
                        name=name,
                        industry=industry,
                    ),
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

        # Circuit breaker check (only for fresh runs)
        _check_circuit_breaker(akshare_result, web_result, tech_result)

        # Save intermediate results (optional)
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

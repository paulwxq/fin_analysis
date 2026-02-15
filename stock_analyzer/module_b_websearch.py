"""Module B entrypoint: run web deep research workflow."""

import asyncio
from datetime import datetime
import json
import re

from stock_analyzer.agents import (
    create_extract_agent,
    create_query_agent,
    create_report_agent,
)
from stock_analyzer.config import (
    DEFAULT_BREADTH,
    DEFAULT_DEPTH,
    MODEL_EXTRACT_AGENT,
    MODEL_QUERY_AGENT,
    MODEL_REPORT_AGENT,
    REPORT_OUTPUT_RETRIES,
    REPORT_USE_STREAM,
    TOPIC_CONCURRENCY_LIMIT,
)
from stock_analyzer.deep_research import deep_research, generate_report
from stock_analyzer.exceptions import ReportGenerationError, WebResearchError
from stock_analyzer.llm_client import create_chat_client, create_openai_client
from stock_analyzer.logger import logger
from stock_analyzer.models import (
    ResearchResult,
    SearchConfig,
    SearchMeta,
    WebResearchResult,
)


def _count_successful_topics(results: list[object]) -> int:
    """Count topics with non-empty learnings."""
    return sum(
        1
        for result in results
        if isinstance(result, ResearchResult) and len(result.learnings) > 0
    )


def _extract_rating(text: str) -> str:
    """Extract rating keyword from free-form report text."""
    rating_keywords = ["买入", "增持", "中性", "持有", "减持", "卖出"]
    for keyword in rating_keywords:
        if keyword in text:
            return keyword
    return "中性"


def _extract_target_price(text: str) -> float | None:
    """Extract target price like `2200元` from free-form text."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*元", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_date(text: str) -> str:
    """Extract a date-like string from free-form text."""
    iso_match = re.search(r"\d{4}-\d{1,2}-\d{1,2}", text)
    if iso_match:
        return iso_match.group(0)

    cn_match = re.search(r"\d{4}年\d{1,2}月(?:\d{1,2}日)?", text)
    if cn_match:
        return cn_match.group(0)

    return "未知"


def _normalize_recent_report_item(item: object) -> object:
    """Normalize one recent report item into AnalystReport-compatible dict when possible."""
    if isinstance(item, str):
        text = item.strip()
        broker = text.split("：", 1)[0].split(":", 1)[0].strip() or "未知机构"
        return {
            "broker": broker,
            "rating": _extract_rating(text),
            "target_price": _extract_target_price(text),
            "date": _extract_date(text),
        }

    if isinstance(item, dict):
        normalized = dict(item)
        if "target_price" not in normalized and "target" in normalized:
            try:
                normalized["target_price"] = float(normalized["target"])
            except (TypeError, ValueError):
                normalized["target_price"] = None

        normalized.setdefault("rating", "中性")
        normalized.setdefault("date", "未知")
        return normalized

    return item


def _normalize_report_dict(report_dict: dict) -> dict:
    """Best-effort normalize LLM report payload before strict pydantic validation."""
    analyst = report_dict.get("analyst_opinions")
    if not isinstance(analyst, dict):
        return report_dict

    recent_reports = analyst.get("recent_reports")
    if isinstance(recent_reports, list):
        analyst["recent_reports"] = [
            _normalize_recent_report_item(item) for item in recent_reports
        ]
    elif isinstance(recent_reports, str):
        analyst["recent_reports"] = [_normalize_recent_report_item(recent_reports)]
    elif recent_reports is None:
        analyst["recent_reports"] = []

    return report_dict


async def run_web_research(
    symbol: str,
    name: str,
    industry: str,
    breadth: int = DEFAULT_BREADTH,
    depth: int = DEFAULT_DEPTH,
) -> WebResearchResult:
    """Run module B workflow and return structured WebResearchResult."""
    start_time = datetime.now()
    logger.info(f"[Module B] Starting web research for {symbol} {name} ({industry})")

    openai_client = create_openai_client()
    query_client = create_chat_client(openai_client, MODEL_QUERY_AGENT)
    extract_client = create_chat_client(openai_client, MODEL_EXTRACT_AGENT)
    report_client = create_chat_client(openai_client, MODEL_REPORT_AGENT)

    query_agent = create_query_agent(query_client)
    extract_agent = create_extract_agent(extract_client)
    report_agent = create_report_agent(report_client)

    logger.info(
        f"[Module B] LLM config: query_agent={MODEL_QUERY_AGENT}, "
        f"extract_agent={MODEL_EXTRACT_AGENT}"
    )

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
            "管理层变动、财务风险等负面信息"
        ),
        (
            f"{name} 券商研报、机构评级、目标价、"
            "分析师对该股的投资观点和评级变化"
        ),
    ]

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

    all_learnings: set[str] = set()
    all_urls: set[str] = set()

    for index, result in enumerate(results):
        if isinstance(result, ResearchResult):
            all_learnings.update(result.learnings)
            all_urls.update(result.visited_urls)
            logger.info(
                f"Topic {index + 1} completed: {len(result.learnings)} learnings, {len(result.visited_urls)} urls"
            )
        elif isinstance(result, asyncio.CancelledError):
            logger.warning(f"Topic {index + 1} was cancelled, propagating CancelledError")
            raise result
        elif isinstance(result, Exception):
            logger.error(f"Topic {index + 1} failed: {result}")

    unique_learnings = list(all_learnings)
    unique_urls = list(all_urls)
    successful_topics = _count_successful_topics(results)

    if successful_topics == 0:
        raise WebResearchError(
            f"All {len(topics)} topics failed, cannot generate report for {symbol}"
        )

    if len(unique_learnings) < 5:
        logger.warning(
            f"Only {len(unique_learnings)} learnings collected ({successful_topics}/{len(topics)} topics succeeded), "
            "report quality may be low"
        )

    logger.info(
        f"All topics done: {len(unique_learnings)} unique learnings, {len(unique_urls)} unique urls, "
        f"{successful_topics}/{len(topics)} topics succeeded"
    )

    # --- Report generation via LLM ---
    extra_body = report_agent.default_options.get("extra_body", {})
    thinking_enabled = extra_body.get("enable_thinking", False) if isinstance(extra_body, dict) else False

    logger.info(
        f"[Module B] LLM config: model={MODEL_REPORT_AGENT}, "
        f"thinking={thinking_enabled}, stream={REPORT_USE_STREAM}"
    )
    if thinking_enabled and not REPORT_USE_STREAM:
        logger.warning(
            "[Module B] enable_thinking=True but stream=False: "
            "DashScope may return server-side timeout for non-streaming thinking requests. "
            "Consider setting REPORT_USE_STREAM=true."
        )

    max_attempts = max(1, REPORT_OUTPUT_RETRIES + 1)
    is_fallback = False
    report_dict = None
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        logger.info(
            f"[Module B] Submitting {len(unique_learnings)} learnings to LLM "
            f"(attempt {attempt}/{max_attempts})... "
            f"{'（thinking 模式，预计等待较久）' if thinking_enabled else ''}"
        )
        try:
            report_dict = await generate_report(
                report_agent=report_agent,
                symbol=symbol,
                name=name,
                industry=industry,
                learnings=unique_learnings,
                stream=REPORT_USE_STREAM,
            )
            break
        except ReportGenerationError as e:
            last_error = e
            if attempt < max_attempts:
                logger.warning(
                    f"Report generation attempt {attempt}/{max_attempts} failed: {e}. Retrying..."
                )
                continue
            logger.error(f"Report generation failed after {max_attempts} attempts: {e}")

    if report_dict is None:
        is_fallback = True
        report_dict = _create_fallback_report(
            learnings=unique_learnings,
            error_message=str(last_error.cause) if last_error else "unknown",
        )

    meta = SearchMeta(
        symbol=symbol,
        name=name,
        search_time=start_time.isoformat(),
        search_config=SearchConfig(
            topics_count=len(topics),
            breadth=breadth,
            depth=depth,
            successful_topics=successful_topics,
        ),
        total_learnings=len(unique_learnings),
        total_sources_consulted=len(unique_urls),
        raw_learnings=unique_learnings if is_fallback else None,
    )

    report_dict["meta"] = meta.model_dump()

    if len(unique_learnings) < 5:
        logger.warning(
            f"Forcing search_confidence to '低' due to insufficient learnings: {len(unique_learnings)}"
        )
        report_dict["search_confidence"] = "低"

    report_dict = _normalize_report_dict(report_dict)

    try:
        final_result = WebResearchResult.model_validate(report_dict)
    except Exception as e:
        logger.error(f"Final result validation failed: {e}")
        raise WebResearchError(
            f"Failed to validate final report for {symbol}: {e}"
        ) from e

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"[Module B] completed for {symbol}, elapsed {elapsed:.1f}s")
    return final_result


def dump_web_research_result_json(result: WebResearchResult) -> str:
    """Serialize final web research result with meta first for readability."""
    output_dict = {
        "meta": result.meta.model_dump(),
        **result.model_dump(exclude={"meta"}),
    }
    return json.dumps(output_dict, ensure_ascii=False, indent=2)


def _create_fallback_report(learnings: list[str], error_message: str) -> dict:
    """Create minimal fallback report when report generation fails."""
    base_msg = f"报告生成失败，共收集到 {len(learnings)} 条信息，请查看原始数据。错误："
    description = base_msg + error_message
    if len(description) > 500:
        description = description[:497] + "..."

    return {
        "news_summary": {
            "positive": [],
            "negative": [],
            "neutral": [],
        },
        "competitive_advantage": {
            "description": description,
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

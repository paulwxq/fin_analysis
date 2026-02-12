"""Module D entrypoint: chief analyst final synthesis workflow."""

from __future__ import annotations

from datetime import datetime
import json

from stock_analyzer.agents import create_chief_agent
from stock_analyzer.config import (
    CHIEF_INPUT_MAX_CHARS_TOTAL,
    CHIEF_OUTPUT_RETRIES,
    MODEL_CHIEF_AGENT,
)
from stock_analyzer.exceptions import AgentCallError, ChiefAnalysisError, ChiefInputError
from stock_analyzer.llm_client import create_chat_client, create_openai_client
from stock_analyzer.llm_helpers import call_agent_with_model
from stock_analyzer.logger import logger
from stock_analyzer.models import WebResearchResult
from stock_analyzer.module_a_models import AKShareData
from stock_analyzer.module_c_models import TechnicalAnalysisResult
from stock_analyzer.module_d_models import FinalMeta, FinalReport, LLMChiefOutput

_NOISE_KEYS = {
    "_trace_id",
    "trace_id",
    "_request_id",
    "request_id",
    "_internal_id",
    "internal_id",
}
_LOW_CONFIDENCE_PREFIX = "（基于有限证据）"
_CONFIDENCE_DECLARATION_KEYWORD = "数据可信度声明"
_MAX_REASONING_CHARS = 180


def _strip_noise_fields(value: object) -> object:
    """Recursively remove known non-business tracing keys."""
    if isinstance(value, dict):
        return {
            key: _strip_noise_fields(item)
            for key, item in value.items()
            if key not in _NOISE_KEYS
        }
    if isinstance(value, list):
        return [_strip_noise_fields(item) for item in value]
    return value


def _build_overall_data_gaps(
    module_a_successful: int,
    module_a_total: int,
    module_b_confidence: str,
    module_b_is_fallback: bool,
    module_c_confidence: float,
    module_c_warnings: list[str],
) -> list[str]:
    gaps: list[str] = []
    if module_a_successful < module_a_total:
        gaps.append(
            f"模块A主题完整度不足：{module_a_successful}/{module_a_total}"
        )
    if module_b_is_fallback:
        gaps.append("模块B使用fallback报告，部分网络研究结构信息不足")
    if module_b_confidence == "低":
        gaps.append("模块B搜索置信度为低，舆情与外部证据可靠性受限")
    if module_c_confidence < 0.5:
        gaps.append(f"模块C置信度偏低：{module_c_confidence:.2f}")
    if module_c_warnings:
        warning_summary = "; ".join(module_c_warnings[:2])
        gaps.append(f"模块C质量告警：{warning_summary}")
    if not gaps:
        gaps.append("未发现显著结构化缺口")
    return gaps


def build_chief_context(
    akshare_data: AKShareData,
    web_research: WebResearchResult,
    technical_analysis: TechnicalAnalysisResult,
) -> dict:
    """Build full-fidelity, format-aligned context from A/B/C outputs."""
    akshare_full = _strip_noise_fields(akshare_data.model_dump())
    web_research_full = _strip_noise_fields(web_research.model_dump())
    technical_analysis_full = _strip_noise_fields(technical_analysis.model_dump())

    module_a_total = len(akshare_data.meta.topic_status) if akshare_data.meta.topic_status else 12
    module_a_successful = akshare_data.meta.successful_topics
    module_b_is_fallback = web_research.meta.raw_learnings is not None
    module_c_warnings = technical_analysis.meta.data_quality_warnings[:3]

    data_quality_report = {
        "module_a_success_ratio": f"{module_a_successful}/{module_a_total}",
        "module_b_search_confidence": web_research.search_confidence,
        "module_b_is_fallback": module_b_is_fallback,
        "module_c_confidence": technical_analysis.confidence,
        "module_c_warnings_top": module_c_warnings,
        "overall_data_gaps": _build_overall_data_gaps(
            module_a_successful=module_a_successful,
            module_a_total=module_a_total,
            module_b_confidence=web_research.search_confidence,
            module_b_is_fallback=module_b_is_fallback,
            module_c_confidence=technical_analysis.confidence,
            module_c_warnings=module_c_warnings,
        ),
    }

    return {
        "akshare_data_full": akshare_full,
        "web_research_full": web_research_full,
        "technical_analysis_full": technical_analysis_full,
        "data_quality_report": data_quality_report,
    }


def _build_chief_user_message(context: dict) -> str:
    """Assemble final user message payload for chief agent."""
    akshare_json = json.dumps(
        context["akshare_data_full"],
        ensure_ascii=False,
        indent=2,
    )
    web_json = json.dumps(
        context["web_research_full"],
        ensure_ascii=False,
        indent=2,
    )
    technical_json = json.dumps(
        context["technical_analysis_full"],
        ensure_ascii=False,
        indent=2,
    )
    quality_json = json.dumps(
        context["data_quality_report"],
        ensure_ascii=False,
        indent=2,
    )

    return (
        "请作为首席分析师，基于以下三份报告与数据质量摘要做最终综合判定：\n\n"
        "<akshare_data>\n"
        f"{akshare_json}\n"
        "</akshare_data>\n\n"
        "<web_research>\n"
        f"{web_json}\n"
        "</web_research>\n\n"
        "<technical_analysis>\n"
        f"{technical_json}\n"
        "</technical_analysis>\n\n"
        "<data_quality_report>\n"
        f"{quality_json}\n"
        "</data_quality_report>\n"
    )


def _validate_inputs(
    symbol: str,
    name: str,
    akshare_data: AKShareData,
    web_research: WebResearchResult,
    technical_analysis: TechnicalAnalysisResult,
) -> None:
    if not symbol.strip():
        raise ChiefInputError("symbol cannot be empty")
    if not name.strip():
        raise ChiefInputError("name cannot be empty")
    if not isinstance(akshare_data, AKShareData):
        raise ChiefInputError("akshare_data must be AKShareData")
    if not isinstance(web_research, WebResearchResult):
        raise ChiefInputError("web_research must be WebResearchResult")
    if not isinstance(technical_analysis, TechnicalAnalysisResult):
        raise ChiefInputError("technical_analysis must be TechnicalAnalysisResult")


def _apply_confidence_guards(output: LLMChiefOutput) -> LLMChiefOutput:
    """Normalize confidence-related wording without changing decision semantics."""
    if output.overall_confidence != "低":
        return output

    normalized_advice = []
    max_original = _MAX_REASONING_CHARS - len(_LOW_CONFIDENCE_PREFIX)
    if max_original < 0:
        max_original = 0

    for item in output.advice:
        reasoning = item.reasoning.strip()
        if reasoning.startswith(_LOW_CONFIDENCE_PREFIX):
            reasoning = reasoning[len(_LOW_CONFIDENCE_PREFIX):].strip()
        reasoning = reasoning[:max_original]
        reasoning = f"{_LOW_CONFIDENCE_PREFIX}{reasoning}"
        normalized_advice.append(item.model_copy(update={"reasoning": reasoning}))

    return output.model_copy(update={"advice": normalized_advice})


def validate_business_rules(output: LLMChiefOutput) -> None:
    """Deterministic business rule validation after pydantic parsing."""
    if _CONFIDENCE_DECLARATION_KEYWORD not in output.report:
        raise ChiefAnalysisError(
            "Business rule violation: report missing '数据可信度声明' section"
        )
    if output.veto_triggered and output.score_cap is None:
        raise ChiefAnalysisError(
            "Business rule violation: veto_triggered=true but score_cap is None"
        )
    if output.veto_triggered and len(output.veto_reason.strip()) < 10:
        raise ChiefAnalysisError(
            "Business rule violation: veto_triggered=true but veto_reason is too short"
        )
    if (not output.veto_triggered) and output.score_cap is not None:
        raise ChiefAnalysisError(
            "Business rule violation: veto_triggered=false but score_cap is not None"
        )
    if output.veto_triggered and output.overall_score > output.score_cap:
        raise ChiefAnalysisError(
            "Business rule violation: "
            f"veto_triggered=true but overall_score={output.overall_score} "
            f"> score_cap={output.score_cap}"
        )


async def run_chief_analysis(
    symbol: str,
    name: str,
    akshare_data: AKShareData,
    web_research: WebResearchResult,
    technical_analysis: TechnicalAnalysisResult,
) -> FinalReport:
    """Run chief analyst workflow and return validated FinalReport."""
    _validate_inputs(
        symbol=symbol,
        name=name,
        akshare_data=akshare_data,
        web_research=web_research,
        technical_analysis=technical_analysis,
    )

    logger.info(f"Starting chief analysis for {symbol} {name}")
    try:
        context = build_chief_context(
            akshare_data=akshare_data,
            web_research=web_research,
            technical_analysis=technical_analysis,
        )
        user_message = _build_chief_user_message(context)
    except Exception as e:
        logger.error(f"Failed to build chief prompt for {symbol}: {type(e).__name__}: {e}")
        raise ChiefAnalysisError(
            f"Failed to build chief prompt: {type(e).__name__}: {e}"
        ) from e

    if CHIEF_INPUT_MAX_CHARS_TOTAL > 0 and len(user_message) > CHIEF_INPUT_MAX_CHARS_TOTAL:
        raise ChiefInputError(
            "Chief prompt exceeds CHIEF_INPUT_MAX_CHARS_TOTAL: "
            f"{len(user_message)} > {CHIEF_INPUT_MAX_CHARS_TOTAL}"
        )

    openai_client = create_openai_client()
    chief_client = create_chat_client(openai_client, MODEL_CHIEF_AGENT)
    chief_agent = create_chief_agent(chief_client)

    max_attempts = max(1, CHIEF_OUTPUT_RETRIES + 1)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            llm_output = await call_agent_with_model(
                agent=chief_agent,
                message=user_message,
                model_cls=LLMChiefOutput,
            )
            llm_output = _apply_confidence_guards(llm_output)
            validate_business_rules(llm_output)
            meta = FinalMeta(
                symbol=symbol,
                name=name,
                analysis_time=datetime.now().isoformat(),
            )
            final_result = FinalReport(meta=meta, **llm_output.model_dump())
            logger.info(
                f"Chief analysis completed for {symbol}: "
                f"overall_score={final_result.overall_score:.2f}, "
                f"confidence={final_result.overall_confidence}"
            )
            return final_result
        except (AgentCallError, ChiefAnalysisError) as e:
            last_error = e
            if attempt >= max_attempts:
                break
            logger.warning(
                f"Chief analysis attempt {attempt}/{max_attempts} failed: {e}. Retrying..."
            )

    raise ChiefAnalysisError(
        f"Chief analysis failed after {max_attempts} attempts: {last_error}"
    ) from last_error


def dump_final_report_json(result: FinalReport) -> str:
    """Serialize final report with meta first for readability."""
    output_dict = {
        "meta": result.meta.model_dump(),
        **result.model_dump(exclude={"meta"}),
    }
    return json.dumps(output_dict, ensure_ascii=False, indent=2)

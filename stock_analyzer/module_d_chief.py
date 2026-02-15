"""Module D entrypoint: chief analyst final synthesis workflow."""

from __future__ import annotations

from datetime import datetime
import json

from stock_analyzer.agents import create_chief_agent
from stock_analyzer.config import (
    CHIEF_INPUT_MAX_CHARS_TOTAL,
    CHIEF_OUTPUT_RETRIES,
    CHIEF_USE_STREAM,
    MODEL_CHIEF_AGENT,
)
from stock_analyzer.exceptions import AgentCallError, ChiefAnalysisError, ChiefInputError
from stock_analyzer.llm_client import create_chat_client, create_openai_client
from stock_analyzer.llm_helpers import call_agent_with_model
from stock_analyzer.logger import logger
from stock_analyzer.markdown_formatter import (
    format_akshare_markdown,
    format_technical_markdown,
    format_web_research_markdown,
)
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

    module_a_total = len(akshare_data.meta.topic_status) if akshare_data.meta.topic_status else 15
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


def _build_chief_user_message(
    akshare_data: AKShareData,
    web_research: WebResearchResult,
    technical_analysis: TechnicalAnalysisResult,
    data_quality_report: dict,
) -> str:
    """Assemble final user message payload for chief agent.

    Uses Markdown formatting for A/B/C data and JSON for the quality report.
    """
    akshare_md = format_akshare_markdown(akshare_data)
    web_md = format_web_research_markdown(web_research)
    tech_md = format_technical_markdown(technical_analysis)
    quality_json = json.dumps(
        data_quality_report,
        ensure_ascii=False,
        indent=2,
    )

    return (
        "你现在担任首席分析师的角色。你的任务是整合并分析以下 Markdown 格式的多维数据，"
        "输出一份专业的、具备深度洞察力的投资综合判定报告。\n\n"
        "数据来源说明：\n"
        "1. **结构化财务数据**（Module A）：包含公司基础信息及15个维度的财务与经营数据。"
        "请重点关注财务指标趋势、盈利一致预期、主营构成、机构持仓、估值水平及资金流向。\n"
        "2. **深度调研报告**（Module B）：基于全网搜索的舆情、竞争力、行业前景与风险分析。\n"
        "3. **技术面分析**（Module C）：基于月线级别的趋势、动量、波动与量价分析。\n"
        "4. **数据质量报告**：各模块执行质量摘要，请据此调整结论的审慎程度。\n\n"
        "请基于以下数据做最终综合判定：\n\n"
        "---\n\n"
        "# 一、结构化财务数据（Module A）\n\n"
        f"{akshare_md}\n"
        "---\n\n"
        "# 二、深度调研报告（Module B）\n\n"
        f"{web_md}\n"
        "---\n\n"
        "# 三、技术面分析（Module C）\n\n"
        f"{tech_md}\n"
        "---\n\n"
        "# 四、数据质量报告\n\n"
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

    start_time = datetime.now()
    logger.info(f"[Module D] Starting chief analysis for {symbol} {name}")

    # --- Build context and prompt ---
    logger.info(f"[Module D] Building chief analysis context for {symbol}...")
    try:
        context = build_chief_context(
            akshare_data=akshare_data,
            web_research=web_research,
            technical_analysis=technical_analysis,
        )
        user_message = _build_chief_user_message(
            akshare_data=akshare_data,
            web_research=web_research,
            technical_analysis=technical_analysis,
            data_quality_report=context["data_quality_report"],
        )
    except Exception as e:
        logger.error(f"Failed to build chief prompt for {symbol}: {type(e).__name__}: {e}")
        raise ChiefAnalysisError(
            f"Failed to build chief prompt: {type(e).__name__}: {e}"
        ) from e
    logger.info(
        f"[Module D] Context built for {symbol}: "
        f"prompt length={len(user_message)} chars"
    )

    if CHIEF_INPUT_MAX_CHARS_TOTAL > 0 and len(user_message) > CHIEF_INPUT_MAX_CHARS_TOTAL:
        raise ChiefInputError(
            "Chief prompt exceeds CHIEF_INPUT_MAX_CHARS_TOTAL: "
            f"{len(user_message)} > {CHIEF_INPUT_MAX_CHARS_TOTAL}"
        )

    logger.debug(f"[Module D] Chief prompt payload for {symbol}:\n{user_message}")

    # --- Prepare LLM agent ---
    openai_client = create_openai_client()
    chief_client = create_chat_client(openai_client, MODEL_CHIEF_AGENT)
    chief_agent = create_chief_agent(chief_client)

    extra_body = chief_agent.default_options.get("extra_body", {})
    thinking_enabled = extra_body.get("enable_thinking", False) if isinstance(extra_body, dict) else False

    logger.info(
        f"[Module D] LLM config: model={MODEL_CHIEF_AGENT}, "
        f"thinking={thinking_enabled}, stream={CHIEF_USE_STREAM}"
    )
    if thinking_enabled and not CHIEF_USE_STREAM:
        logger.warning(
            "[Module D] enable_thinking=True but stream=False: "
            "DashScope may return server-side timeout for non-streaming thinking requests. "
            "Consider setting CHIEF_USE_STREAM=true."
        )

    max_attempts = max(1, CHIEF_OUTPUT_RETRIES + 1)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        logger.info(
            f"[Module D] Submitting to LLM (attempt {attempt}/{max_attempts})... "
            f"{'（thinking 模式，预计等待较久）' if thinking_enabled else ''}"
        )
        try:
            llm_output = await call_agent_with_model(
                agent=chief_agent,
                message=user_message,
                model_cls=LLMChiefOutput,
                stream=CHIEF_USE_STREAM,
            )
            llm_output = _apply_confidence_guards(llm_output)
            validate_business_rules(llm_output)
            meta = FinalMeta(
                symbol=symbol,
                name=name,
                analysis_time=datetime.now().isoformat(),
            )
            final_result = FinalReport(meta=meta, **llm_output.model_dump())
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"[Module D] completed for {symbol}: "
                f"overall_score={final_result.overall_score:.2f}, "
                f"confidence={final_result.overall_confidence}, "
                f"elapsed {elapsed:.1f}s"
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

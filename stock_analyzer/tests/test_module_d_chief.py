"""Unit tests for module D chief analysis helpers and workflow."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

import stock_analyzer.module_d_chief as module_d
from stock_analyzer.exceptions import ChiefAnalysisError, ChiefInputError
from stock_analyzer.models import WebResearchResult
from stock_analyzer.module_a_models import AKShareData
from stock_analyzer.module_c_models import (
    KeyLevels,
    MomentumAnalysis,
    TechnicalAnalysisResult,
    TechnicalMeta,
    TrendAnalysis,
    VolatilityAnalysis,
    VolumeAnalysis,
)
from stock_analyzer.module_d_models import (
    LLMChiefOutput,
)


def _sample_akshare_data() -> AKShareData:
    return AKShareData.model_validate(
        {
            "meta": {
                "symbol": "600519",
                "name": "贵州茅台",
                "query_time": "2026-02-12T10:00:00",
                "data_errors": [],
                "successful_topics": 10,
                "topic_status": {
                    "company_info": "ok",
                    "realtime_quote": "ok",
                    "financial_indicators": "ok",
                    "valuation_history": "ok",
                    "valuation_vs_industry": "ok",
                    "fund_flow": "ok",
                    "sector_flow": "ok",
                    "northbound": "ok",
                    "shareholder_count": "failed",
                    "dividend_history": "ok",
                    "earnings_forecast": "ok",
                    "pledge_ratio": "failed",
                },
            },
            "company_info": {"industry": "白酒", "listing_date": "2001-08-27"},
            "financial_indicators": [],
        }
    )


def _sample_web_research() -> WebResearchResult:
    return WebResearchResult.model_validate(
        {
            "meta": {
                "symbol": "600519",
                "name": "贵州茅台",
                "search_time": "2026-02-12T10:05:00",
                "search_config": {
                    "topics_count": 5,
                    "breadth": 3,
                    "depth": 2,
                    "successful_topics": 4,
                },
                "total_learnings": 20,
                "total_sources_consulted": 15,
                "raw_learnings": None,
            },
            "news_summary": {"positive": [], "negative": [], "neutral": []},
            "competitive_advantage": {
                "description": "品牌力和渠道力显著，具备长期护城河。",
                "moat_type": "品牌",
                "market_position": "行业龙头",
            },
            "industry_outlook": {
                "industry": "白酒",
                "outlook": "高端需求中长期稳定",
                "key_drivers": ["消费升级"],
                "key_risks": ["宏观需求波动"],
            },
            "risk_events": {
                "regulatory": "暂无重大监管处罚",
                "litigation": "暂无重大诉讼",
                "management": "管理层稳定",
                "other": "",
            },
            "analyst_opinions": {
                "buy_count": 10,
                "hold_count": 2,
                "sell_count": 0,
                "average_target_price": 1900.0,
                "recent_reports": [],
            },
            "search_confidence": "中",
        }
    )


def _sample_technical_analysis() -> TechnicalAnalysisResult:
    return TechnicalAnalysisResult(
        meta=TechnicalMeta(
            symbol="600519",
            name="贵州茅台",
            analysis_time="2026-02-12T10:10:00",
            data_start="2019-01-31",
            data_end="2026-01-31",
            total_months=84,
            data_quality_warnings=["样本区间不足60月，长期趋势可靠性受限"],
        ),
        score=6.8,
        signal="看多",
        confidence=0.68,
        trend_analysis=TrendAnalysis(),
        momentum=MomentumAnalysis(),
        volatility=VolatilityAnalysis(),
        volume_analysis=VolumeAnalysis(),
        key_levels=KeyLevels(),
        summary="趋势中性偏多",
    )


def _valid_llm_output(**overrides: object) -> LLMChiefOutput:
    payload = {
        "dimension_scores": {
            "technical": {"score": 6.8, "brief": "趋势中性偏多"},
            "fundamental": {"score": 7.1, "brief": "盈利能力稳健"},
            "valuation": {"score": 5.4, "brief": "估值处于中高位"},
            "capital_flow": {"score": 6.0, "brief": "资金面中性"},
            "sentiment": {"score": 6.2, "brief": "情绪中性偏正"},
        },
        "overall_score": 6.4,
        "overall_confidence": "中",
        "veto_triggered": False,
        "veto_reason": "",
        "score_cap": None,
        "advice": [
            {
                "timeframe": "1个月",
                "recommendation": "持有",
                "reasoning": "短期估值压制与业绩确定性并存，建议持有观察。",
            },
            {
                "timeframe": "6个月",
                "recommendation": "买入",
                "reasoning": "中期基本面韧性较强，若回调可分批布局。",
            },
            {
                "timeframe": "1年",
                "recommendation": "买入",
                "reasoning": "长期品牌优势与现金流稳健，具备配置价值。",
            },
        ],
        "report": "这是测试用综合报告。\n\n数据可信度声明：模块A成功率10/12，模块B置信度中，模块C置信度0.68。",
        "key_catalysts": ["旺季需求改善"],
        "primary_risks": ["消费下行风险"],
    }
    payload.update(overrides)
    return LLMChiefOutput.model_validate(payload)


def test_dimension_brief_max_length_200_boundary() -> None:
    ok_brief = "甲" * 200
    payload = _valid_llm_output().model_dump()
    payload["dimension_scores"]["technical"]["brief"] = ok_brief
    parsed = LLMChiefOutput.model_validate(payload)
    assert parsed.dimension_scores.technical.brief == ok_brief

    payload["dimension_scores"]["technical"]["brief"] = "甲" * 201
    with pytest.raises(ValidationError):
        LLMChiefOutput.model_validate(payload)


def test_build_chief_context_contains_full_payload_and_quality_report() -> None:
    context = module_d.build_chief_context(
        akshare_data=_sample_akshare_data(),
        web_research=_sample_web_research(),
        technical_analysis=_sample_technical_analysis(),
    )

    assert "akshare_data_full" in context
    assert "web_research_full" in context
    assert "technical_analysis_full" in context
    assert "data_quality_report" in context
    assert context["data_quality_report"]["module_a_success_ratio"] == "10/12"
    assert context["data_quality_report"]["module_b_search_confidence"] == "中"
    assert context["data_quality_report"]["module_c_confidence"] == 0.68


def test_build_overall_data_gaps_joins_top_two_module_c_warnings() -> None:
    gaps = module_d._build_overall_data_gaps(
        module_a_successful=12,
        module_a_total=12,
        module_b_confidence="中",
        module_b_is_fallback=False,
        module_c_confidence=0.7,
        module_c_warnings=[
            "样本区间不足60月",
            "存在停牌导致序列不连续",
            "第三条告警",
        ],
    )

    warning_lines = [line for line in gaps if line.startswith("模块C质量告警：")]
    assert len(warning_lines) == 1
    assert "样本区间不足60月; 存在停牌导致序列不连续" in warning_lines[0]
    assert "第三条告警" not in warning_lines[0]


def test_validate_business_rules_rejects_veto_without_score_cap() -> None:
    output = _valid_llm_output(
        veto_triggered=True,
        veto_reason="存在持续经营重大不确定性",
        score_cap=None,
    )
    with pytest.raises(ChiefAnalysisError, match="score_cap is None"):
        module_d.validate_business_rules(output)


def test_validate_business_rules_rejects_short_veto_reason() -> None:
    output = _valid_llm_output(
        veto_triggered=True,
        veto_reason="风险",
        score_cap=3.0,
    )
    with pytest.raises(ChiefAnalysisError, match="veto_reason is too short"):
        module_d.validate_business_rules(output)


def test_validate_business_rules_rejects_score_cap_when_no_veto() -> None:
    output = _valid_llm_output(veto_triggered=False, score_cap=4.0)
    with pytest.raises(ChiefAnalysisError, match="score_cap is not None"):
        module_d.validate_business_rules(output)


def test_validate_business_rules_rejects_score_above_cap() -> None:
    output = _valid_llm_output(
        veto_triggered=True,
        veto_reason="存在重大财务造假嫌疑，需要强制限制评分",
        score_cap=3.0,
        overall_score=5.0,
    )
    with pytest.raises(ChiefAnalysisError, match="overall_score=5.0 > score_cap=3.0"):
        module_d.validate_business_rules(output)


def test_validate_business_rules_rejects_missing_confidence_declaration() -> None:
    output = _valid_llm_output(report="普通报告内容，不含关键小节。")
    with pytest.raises(
        ChiefAnalysisError,
        match="report missing '数据可信度声明' section",
    ):
        module_d.validate_business_rules(output)


def test_dump_final_report_json_meta_first() -> None:
    llm = _valid_llm_output()
    result = module_d.FinalReport(
        meta=module_d.FinalMeta(
            symbol="600519",
            name="贵州茅台",
            analysis_time="2026-02-12T11:00:00",
        ),
        **llm.model_dump(),
    )
    output = module_d.dump_final_report_json(result)

    assert output.lstrip().startswith("{\n  \"meta\":")
    parsed = json.loads(output)
    assert parsed["meta"]["symbol"] == "600519"
    assert parsed["overall_confidence"] == "中"


@pytest.mark.asyncio
async def test_run_chief_analysis_retries_then_success(monkeypatch) -> None:
    monkeypatch.setattr(module_d, "create_openai_client", lambda: object())
    monkeypatch.setattr(module_d, "create_chat_client", lambda openai_client, model_id: object())
    monkeypatch.setattr(module_d, "create_chief_agent", lambda chat_client: object())
    monkeypatch.setattr(module_d, "CHIEF_OUTPUT_RETRIES", 1)

    calls = {"count": 0}

    async def fake_call_agent_with_model(agent, message, model_cls):
        calls["count"] += 1
        if calls["count"] == 1:
            return _valid_llm_output(
                veto_triggered=True,
                veto_reason="风险",
                score_cap=3.0,
            )
        return _valid_llm_output()

    monkeypatch.setattr(module_d, "call_agent_with_model", fake_call_agent_with_model)

    result = await module_d.run_chief_analysis(
        symbol="600519",
        name="贵州茅台",
        akshare_data=_sample_akshare_data(),
        web_research=_sample_web_research(),
        technical_analysis=_sample_technical_analysis(),
    )
    assert calls["count"] == 2
    assert result.meta.symbol == "600519"
    assert result.overall_score == 6.4


@pytest.mark.asyncio
async def test_run_chief_analysis_fail_fast_when_input_too_large(monkeypatch) -> None:
    monkeypatch.setattr(module_d, "CHIEF_INPUT_MAX_CHARS_TOTAL", 10)
    with pytest.raises(ChiefInputError, match="exceeds CHIEF_INPUT_MAX_CHARS_TOTAL"):
        await module_d.run_chief_analysis(
            symbol="600519",
            name="贵州茅台",
            akshare_data=_sample_akshare_data(),
            web_research=_sample_web_research(),
            technical_analysis=_sample_technical_analysis(),
        )


@pytest.mark.asyncio
async def test_run_chief_analysis_wraps_build_context_error(monkeypatch) -> None:
    def fake_build_chief_context(**kwargs):
        raise RuntimeError("context failed")

    monkeypatch.setattr(module_d, "build_chief_context", fake_build_chief_context)

    with pytest.raises(ChiefAnalysisError, match="Failed to build chief prompt"):
        await module_d.run_chief_analysis(
            symbol="600519",
            name="贵州茅台",
            akshare_data=_sample_akshare_data(),
            web_research=_sample_web_research(),
            technical_analysis=_sample_technical_analysis(),
        )


@pytest.mark.asyncio
async def test_run_chief_analysis_wraps_user_message_build_error(monkeypatch) -> None:
    def fake_build_user_message(context: dict) -> str:
        raise ValueError("message failed")

    monkeypatch.setattr(module_d, "_build_chief_user_message", fake_build_user_message)

    with pytest.raises(ChiefAnalysisError, match="Failed to build chief prompt"):
        await module_d.run_chief_analysis(
            symbol="600519",
            name="贵州茅台",
            akshare_data=_sample_akshare_data(),
            web_research=_sample_web_research(),
            technical_analysis=_sample_technical_analysis(),
        )


@pytest.mark.asyncio
async def test_run_chief_analysis_auto_prefix_reasoning_for_low_confidence(monkeypatch) -> None:
    monkeypatch.setattr(module_d, "create_openai_client", lambda: object())
    monkeypatch.setattr(module_d, "create_chat_client", lambda openai_client, model_id: object())
    monkeypatch.setattr(module_d, "create_chief_agent", lambda chat_client: object())

    async def fake_call_agent_with_model(agent, message, model_cls):
        return _valid_llm_output(
            overall_confidence="低",
            advice=[
                {
                    "timeframe": "1个月",
                    "recommendation": "持有",
                    "reasoning": "短期证据不充分，建议谨慎观察。",
                },
                {
                    "timeframe": "6个月",
                    "recommendation": "持有",
                    "reasoning": "中期判断依赖外部信息验证。",
                },
                {
                    "timeframe": "1年",
                    "recommendation": "买入",
                    "reasoning": "长期逻辑成立但证据链仍需补强。",
                },
            ],
        )

    monkeypatch.setattr(module_d, "call_agent_with_model", fake_call_agent_with_model)

    result = await module_d.run_chief_analysis(
        symbol="600519",
        name="贵州茅台",
        akshare_data=_sample_akshare_data(),
        web_research=_sample_web_research(),
        technical_analysis=_sample_technical_analysis(),
    )

    for row in result.advice:
        assert row.reasoning.startswith("（基于有限证据）")
        assert len(row.reasoning) <= 180


def test_apply_confidence_guards_preserves_body_tail_with_prefix_budget() -> None:
    long_body = "甲" * 180
    output = _valid_llm_output(
        overall_confidence="低",
        advice=[
            {
                "timeframe": "1个月",
                "recommendation": "持有",
                "reasoning": long_body,
            },
            {
                "timeframe": "6个月",
                "recommendation": "持有",
                "reasoning": long_body,
            },
            {
                "timeframe": "1年",
                "recommendation": "持有",
                "reasoning": long_body,
            },
        ],
    )

    guarded = module_d._apply_confidence_guards(output)
    prefix = "（基于有限证据）"
    max_original = 180 - len(prefix)
    for item in guarded.advice:
        assert item.reasoning.startswith(prefix)
        assert len(item.reasoning) <= 180
        assert len(item.reasoning[len(prefix):]) == max_original


def test_apply_confidence_guards_deduplicates_existing_prefix() -> None:
    body = "证据链仍不完整，建议控制仓位。"
    output = _valid_llm_output(
        overall_confidence="低",
        advice=[
            {
                "timeframe": "1个月",
                "recommendation": "持有",
                "reasoning": f"（基于有限证据）{body}",
            },
            {
                "timeframe": "6个月",
                "recommendation": "持有",
                "reasoning": f"（基于有限证据）{body}",
            },
            {
                "timeframe": "1年",
                "recommendation": "持有",
                "reasoning": f"（基于有限证据）{body}",
            },
        ],
    )

    guarded = module_d._apply_confidence_guards(output)
    prefix = "（基于有限证据）"
    for item in guarded.advice:
        assert item.reasoning.startswith(prefix)
        assert item.reasoning.count(prefix) == 1

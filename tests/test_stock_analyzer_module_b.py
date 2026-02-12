"""Unit tests for stock_analyzer module B core helpers."""

import json

import pytest

from stock_analyzer.llm_helpers import extract_json_str
from stock_analyzer.models import AnalystReport, ResearchResult, WebResearchResult
from stock_analyzer.module_b_websearch import (
    _count_successful_topics,
    _create_fallback_report,
    _normalize_report_dict,
    dump_web_research_result_json,
)


def test_extract_json_str_comprehensive() -> None:
    """extract_json_str should handle common model-output formats."""
    result1 = extract_json_str('{"key": "value"}')
    assert result1 == '{"key": "value"}'

    result2 = extract_json_str('```json\n{"key": "value"}\n```')
    assert result2 == '{"key": "value"}'

    result3 = extract_json_str(
        'Here is the result:\n```json\n{"key": "value"}\n```'
    )
    assert result3 == '{"key": "value"}'

    result4 = extract_json_str(
        '```json\n{"a": 1}\n```\n\n```json\n{"b": 2}\n```'
    )
    assert result4 == '{"b": 2}'

    result5 = extract_json_str(
        '```\n{"a": 1}\n```\n\n```\n{"b": 2}\n```'
    )
    assert result5 == '{"b": 2}'

    result6 = extract_json_str('  {"key": "value"}  ')
    assert result6 == '{"key": "value"}'

    with pytest.raises(ValueError, match="No valid JSON found"):
        extract_json_str("This is not JSON at all")


def test_fallback_report_empty_news_is_valid() -> None:
    """Fallback report should allow empty news lists."""
    fallback_report = _create_fallback_report(
        learnings=["data1", "data2"],
        error_message="LLM output invalid JSON",
    )

    assert fallback_report["news_summary"]["positive"] == []
    assert fallback_report["news_summary"]["negative"] == []
    assert fallback_report["news_summary"]["neutral"] == []


def test_fallback_report_description_length_boundary() -> None:
    """Fallback description should respect max length and key content."""
    learnings = ["data1", "data2", "data3"]
    short_error = "Connection timeout"

    report = _create_fallback_report(learnings, short_error)
    desc = report["competitive_advantage"]["description"]

    assert len(desc) <= 500
    assert str(len(learnings)) in desc
    assert short_error in desc

    long_error = "E" * 1000
    report2 = _create_fallback_report(learnings, long_error)
    desc2 = report2["competitive_advantage"]["description"]

    assert len(desc2) == 500
    assert desc2.endswith("...")
    assert str(len(learnings)) in desc2


def test_successful_topics_excludes_empty_results() -> None:
    """Only results with non-empty learnings count as successful."""
    results: list[object] = [
        ResearchResult(learnings=["data1", "data2"], visited_urls=["url1"]),
        ResearchResult(learnings=[], visited_urls=[]),
        RuntimeError("topic failed"),
        ResearchResult(learnings=["data3"], visited_urls=["url2"]),
    ]

    assert _count_successful_topics(results) == 2


def test_analyst_report_accepts_institution_alias() -> None:
    """AnalystReport should accept `institution` from LLM output."""
    report = AnalystReport.model_validate(
        {
            "institution": "摩根士丹利",
            "rating": "增持",
            "target_price": 1800.0,
            "date": "2026-02-10",
        }
    )

    assert report.broker == "摩根士丹利"


def test_normalize_report_dict_converts_recent_report_strings() -> None:
    """String recent reports should be converted to structured dicts."""
    payload = {
        "analyst_opinions": {
            "recent_reports": [
                "华创证券：目标价2200元（2025年2月）",
                "中金公司：维持买入评级",
            ]
        }
    }

    normalized = _normalize_report_dict(payload)
    reports = normalized["analyst_opinions"]["recent_reports"]

    assert isinstance(reports, list)
    assert isinstance(reports[0], dict)
    assert reports[0]["broker"] == "华创证券"
    assert reports[0]["target_price"] == 2200.0
    assert reports[1]["broker"] == "中金公司"
    assert reports[1]["rating"] == "买入"


def test_dump_web_research_result_json_meta_first() -> None:
    """JSON dump should keep meta at top-level for readability."""
    result = WebResearchResult.model_validate(
        {
            "meta": {
                "symbol": "600519.SH",
                "name": "贵州茅台",
                "search_time": "2026-02-12T10:00:00",
                "search_config": {
                    "topics_count": 5,
                    "breadth": 3,
                    "depth": 2,
                    "successful_topics": 4,
                },
                "total_learnings": 28,
                "total_sources_consulted": 19,
                "raw_learnings": None,
            },
            "news_summary": {
                "positive": [],
                "negative": [],
                "neutral": [],
            },
            "competitive_advantage": {
                "description": "品牌和渠道优势明显",
                "moat_type": "品牌护城河",
                "market_position": "行业龙头",
            },
            "industry_outlook": {
                "industry": "白酒",
                "outlook": "中长期需求稳定",
                "key_drivers": ["高端消费"],
                "key_risks": ["宏观波动"],
            },
            "risk_events": {
                "regulatory": "暂无重大监管事件",
                "litigation": "暂无重大诉讼",
                "management": "管理层稳定",
                "other": "",
            },
            "analyst_opinions": {
                "buy_count": 8,
                "hold_count": 2,
                "sell_count": 0,
                "average_target_price": 1850.0,
                "recent_reports": [],
            },
            "search_confidence": "中",
        }
    )

    json_str = dump_web_research_result_json(result)
    assert json_str.startswith('{\n  "meta":')

    parsed = json.loads(json_str)
    assert parsed["meta"]["symbol"] == "600519.SH"
    assert parsed["search_confidence"] == "中"

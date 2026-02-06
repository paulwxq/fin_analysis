import json

import pytest

from analysis_llm import config
from analysis_llm.models import HoldRecommendation, ReviewResult
from analysis_llm.workflow import ScoringWorkflow


def _make_summary(length: int) -> str:
    return "a" * length


def test_hold_recommendation_defaults():
    summary = _make_summary(config.SUMMARY_REASON_MIN_CHARS)
    rec = HoldRecommendation(
        stock_code="603080.SH",
        stock_name="Xinjiang",
        hold_score=7.5,
        summary_reason=summary,
    )
    assert rec.data_type == "hold_recommendation"
    assert isinstance(rec.timestamp, str)
    assert "T" in rec.timestamp


def test_review_result_model():
    review = ReviewResult(stock_code="603080.SH", passed=True, reason="")
    assert review.passed is True


def test_parse_and_validate_ok():
    wf = ScoringWorkflow.__new__(ScoringWorkflow)
    payload = {
        "hold_score": 6.0,
        "summary_reason": _make_summary(config.SUMMARY_REASON_MIN_CHARS),
    }
    data = wf._parse_and_validate(json.dumps(payload))
    assert data["hold_score"] == 6.0


def test_parse_and_validate_invalid_score():
    wf = ScoringWorkflow.__new__(ScoringWorkflow)
    payload = {
        "hold_score": 12,
        "summary_reason": _make_summary(config.SUMMARY_REASON_MIN_CHARS),
    }
    with pytest.raises(ValueError):
        wf._parse_and_validate(json.dumps(payload))


def test_extract_from_outputs_last_valid():
    wf = ScoringWorkflow.__new__(ScoringWorkflow)
    bad = "{\"hold_score\": 5, \"summary_reason\": \"short\"}"
    good = json.dumps(
        {
            "hold_score": 5.5,
            "summary_reason": _make_summary(config.SUMMARY_REASON_MIN_CHARS),
        }
    )
    data = wf._extract_from_outputs([bad, good])
    assert data["hold_score"] == 5.5

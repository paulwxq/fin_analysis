import pytest
from pydantic import ValidationError
from analysis_llm.models import HoldRecommendation, ReviewResult

def test_hold_recommendation_valid():
    """测试合法的 HoldRecommendation 对象"""
    data = HoldRecommendation(
        stock_code="603080.SH",
        stock_name="新疆火炬",
        hold_score=7.5,
        summary_reason="A" * 100 # 刚好 100 字
    )
    assert data.data_type == "hold_recommendation"
    assert data.hold_score == 7.5
    assert len(data.timestamp) > 0

def test_hold_recommendation_invalid_score():
    """测试评分越界"""
    with pytest.raises(ValidationError) as exc:
        HoldRecommendation(
            stock_code="603080.SH",
            stock_name="新疆火炬",
            hold_score=11.0, # 越界
            summary_reason="A" * 100
        )
    assert "less than or equal to 10" in str(exc.value)

def test_hold_recommendation_short_reason():
    """测试理由太短"""
    with pytest.raises(ValidationError) as exc:
        HoldRecommendation(
            stock_code="603080.SH",
            stock_name="新疆火炬",
            hold_score=8.0,
            summary_reason="Too short" # < 100
        )
    assert "at least 100 characters" in str(exc.value)

def test_review_result():
    """测试 ReviewResult"""
    res = ReviewResult(
        stock_code="603080.SH",
        passed=False,
        reason="Needs more details"
    )
    assert res.passed is False
    assert res.reason == "Needs more details"

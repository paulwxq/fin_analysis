"""Unit tests for module D chief prompt constraints."""

from stock_analyzer.prompts import CHIEF_ANALYST_SYSTEM_PROMPT


def test_chief_prompt_contains_required_output_keys() -> None:
    required_keys = [
        '"dimension_scores"',
        '"overall_score"',
        '"overall_confidence"',
        '"veto_triggered"',
        '"veto_reason"',
        '"score_cap"',
        '"advice"',
        '"report"',
        '"key_catalysts"',
        '"primary_risks"',
    ]
    for key in required_keys:
        assert key in CHIEF_ANALYST_SYSTEM_PROMPT


def test_chief_prompt_contains_strict_field_constraints() -> None:
    assert "字段名必须与下方示例完全一致" in CHIEF_ANALYST_SYSTEM_PROMPT
    assert "`key_catalysts` 必须是 1-3 条字符串" in CHIEF_ANALYST_SYSTEM_PROMPT
    assert "`primary_risks` 必须是 1-3 条字符串" in CHIEF_ANALYST_SYSTEM_PROMPT
    assert "timeframe 必须覆盖并且仅覆盖：`1个月`、`6个月`、`1年`" in CHIEF_ANALYST_SYSTEM_PROMPT
    assert "`advice.recommendation` 只能是：" in CHIEF_ANALYST_SYSTEM_PROMPT
    assert "每个 `brief` 必须 <=200 字符" in CHIEF_ANALYST_SYSTEM_PROMPT
    assert "强烈买入" in CHIEF_ANALYST_SYSTEM_PROMPT
    assert "强烈卖出" in CHIEF_ANALYST_SYSTEM_PROMPT

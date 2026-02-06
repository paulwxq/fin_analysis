"""测试 ReviewAgent 审核验证的安全性"""
import json
from unittest.mock import MagicMock

import pytest


class MockEvent:
    """模拟事件对象"""
    def __init__(self, executor_id, content):
        self.executor_id = executor_id
        self.content = content


def test_approved_score_is_accepted():
    """测试：通过审核的 ScoreAgent 输出应该被接受"""
    from analysis_llm.workflow import ScoringWorkflow

    workflow = ScoringWorkflow.__new__(ScoringWorkflow)
    workflow._get_content = lambda obj: obj.content

    events = [
        MockEvent("ScoreAgent", json.dumps({
            "stock_code": "603080.SH",
            "hold_score": 7.5,
            "summary_reason": "测试理由" * 20
        })),
        MockEvent("ReviewAgent", json.dumps({
            "stock_code": "603080.SH",
            "passed": True,
            "reason": ""
        }))
    ]

    # 应该验证通过
    result = workflow._is_approved_by_reviewer(events, 0)
    assert result is True, "通过审核的输出应该被接受"


def test_rejected_score_is_rejected():
    """测试：未通过审核的 ScoreAgent 输出应该被拒绝"""
    from analysis_llm.workflow import ScoringWorkflow

    workflow = ScoringWorkflow.__new__(ScoringWorkflow)
    workflow._get_content = lambda obj: obj.content

    events = [
        MockEvent("ScoreAgent", json.dumps({
            "stock_code": "603080.SH",
            "hold_score": 9.0,
            "summary_reason": "测试理由" * 20
        })),
        MockEvent("ReviewAgent", json.dumps({
            "stock_code": "603080.SH",
            "passed": False,
            "reason": "分数过高，理由不足"
        }))
    ]

    # 应该验证失败
    result = workflow._is_approved_by_reviewer(events, 0)
    assert result is False, "未通过审核的输出应该被拒绝"


def test_missing_reviewer_is_rejected():
    """测试：缺少 ReviewAgent 审核的输出应该被拒绝"""
    from analysis_llm.workflow import ScoringWorkflow

    workflow = ScoringWorkflow.__new__(ScoringWorkflow)
    workflow._get_content = lambda obj: obj.content

    events = [
        MockEvent("ScoreAgent", json.dumps({
            "stock_code": "603080.SH",
            "hold_score": 7.5,
            "summary_reason": "测试理由" * 20
        }))
        # 没有 ReviewAgent 事件
    ]

    # 应该验证失败
    result = workflow._is_approved_by_reviewer(events, 0)
    assert result is False, "缺少审核的输出应该被拒绝"


def test_multiple_reviews_picks_first():
    """测试：有多个 ReviewAgent 时，应该使用第一个"""
    from analysis_llm.workflow import ScoringWorkflow

    workflow = ScoringWorkflow.__new__(ScoringWorkflow)
    workflow._get_content = lambda obj: obj.content

    events = [
        MockEvent("ScoreAgent", json.dumps({
            "stock_code": "603080.SH",
            "hold_score": 7.5,
            "summary_reason": "测试理由" * 20
        })),
        MockEvent("ReviewAgent", json.dumps({
            "stock_code": "603080.SH",
            "passed": False,
            "reason": "第一次审核未通过"
        })),
        MockEvent("ScoreAgent", json.dumps({
            "stock_code": "603080.SH",
            "hold_score": 6.5,
            "summary_reason": "修改后的理由" * 20
        })),
        MockEvent("ReviewAgent", json.dumps({
            "stock_code": "603080.SH",
            "passed": True,
            "reason": "第二次审核通过"
        }))
    ]

    # 第一个 ScoreAgent (idx=0) 应该被第一个 ReviewAgent (idx=1) 拒绝
    result1 = workflow._is_approved_by_reviewer(events, 0)
    assert result1 is False, "第一个 Score 应该被拒绝"

    # 第二个 ScoreAgent (idx=2) 应该被第二个 ReviewAgent (idx=3) 接受
    result2 = workflow._is_approved_by_reviewer(events, 2)
    assert result2 is True, "第二个 Score 应该被接受"


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])

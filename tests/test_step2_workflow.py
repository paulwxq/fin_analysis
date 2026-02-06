import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from analysis_llm.workflow import ScoringWorkflow
from analysis_llm.models import Step1Output, NewsData, SectorData, KLineData

# Mock Step1 数据
@pytest.fixture
def mock_step1_output():
    return Step1Output(
        timestamp="2024-01-01T00:00:00Z",
        news=NewsData(
            data_type="news",
            stock_code="603080.SH",
            stock_name="新疆火炬",
            positive_news=["Good news"],
            negative_news=[],
            news_summary="A" * 100,
            sentiment_score=0.8
        ),
        sector=SectorData(
            data_type="sector",
            stock_code="603080.SH",
            stock_name="新疆火炬",
            sector_name="Gas",
            heat_index=80.0,
            trend="上升",
            capital_flow="Inflow"
        ),
        kline=KLineData(
            data_type="kline",
            stock_code="603080.SH",
            technical_indicators={"MACD": 1.0, "RSI": 50.0, "KDJ_K": 50.0},
            support_level=10.0,
            resistance_level=20.0,
            trend_analysis="Up",
            buy_suggestion="买入"
        )
    )

@pytest.mark.asyncio
async def test_scoring_workflow_extract_result():
    """测试结果提取逻辑"""
    # 模拟 WorkflowRunResult (Duck Typing)
    mock_result = MagicMock()
    
    # 模拟 outputs 列表
    mock_score_output = {
        "hold_score": 8.5,
        "summary_reason": "A" * 100
    }
    
    # 场景 A: get_outputs 返回列表
    mock_result.get_outputs.return_value = [mock_score_output]
    
    # 初始化 Workflow (注入 Mock Client 以避开 API Key 检查)
    mock_client = AsyncMock()
    wf = ScoringWorkflow(dashscope_client=mock_client, deepseek_client=mock_client)
    
    extracted = wf._extract_result(mock_result)
    assert extracted["hold_score"] == 8.5
    
    # 场景 B: final_output
    mock_result_b = MagicMock()
    del mock_result_b.get_outputs # 移除 get_outputs 属性模拟
    mock_result_b.final_output = json.dumps(mock_score_output)
    
    extracted_b = wf._extract_result(mock_result_b)
    assert extracted_b["hold_score"] == 8.5

@pytest.mark.asyncio
async def test_scoring_workflow_run_mocked(mock_step1_output):
    """Mock 整个 run 流程"""
    mock_client = AsyncMock()
    
    with patch("analysis_llm.workflow.MagenticBuilder") as MockBuilder:
        # Mock Builder Chain
        mock_builder_instance = MockBuilder.return_value
        mock_builder_instance.with_manager.return_value = mock_builder_instance
        mock_builder_instance.participants.return_value = mock_builder_instance
        mock_builder_instance.max_iterations.return_value = mock_builder_instance
        
        # Mock Workflow
        mock_workflow = AsyncMock()
        mock_builder_instance.build.return_value = mock_workflow
        
        # Mock Run Result
        mock_result = MagicMock()
        mock_result.get_outputs.return_value = [{
            "hold_score": 9.0,
            "summary_reason": "B" * 100
        }]
        mock_workflow.run.return_value = mock_result
        
        # Run
        wf = ScoringWorkflow(dashscope_client=mock_client, deepseek_client=mock_client)
        result = await wf.run(mock_step1_output)
        
        assert result.hold_score == 9.0
        assert result.stock_code == "603080.SH"

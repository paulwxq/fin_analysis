"""Unit tests for workflow orchestration."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from stock_analyzer.workflow import run_workflow, lookup_stock_info, _check_circuit_breaker
from stock_analyzer.exceptions import (
    StockInfoLookupError,
    WorkflowCircuitBreakerError
)
from stock_analyzer.module_a_models import AKShareData, AKShareMeta
from stock_analyzer.models import WebResearchResult
from stock_analyzer.module_c_models import TechnicalAnalysisResult
from stock_analyzer.module_d_models import FinalReport

@pytest.fixture
def mock_akshare_data():
    meta = AKShareMeta(
        symbol="600519",
        name="贵州茅台",
        query_time="2026-02-13T10:00:00",
        successful_topics=10,
        topic_status={}
    )
    return AKShareData(meta=meta)

@pytest.fixture
def mock_web_result():
    return MagicMock(spec=WebResearchResult)

@pytest.fixture
def mock_tech_result():
    return MagicMock(spec=TechnicalAnalysisResult)

@pytest.fixture
def mock_final_report():
    report = MagicMock(spec=FinalReport)
    report.overall_score = 8.5
    report.overall_confidence = "高"
    report.meta = MagicMock()
    report.meta.symbol = "600519"
    return report

class TestCircuitBreaker:
    def test_all_success_no_raise(self, mock_akshare_data, mock_web_result, mock_tech_result):
        # Should not raise
        _check_circuit_breaker(mock_akshare_data, mock_web_result, mock_tech_result)

    def test_module_a_exception_raises(self, mock_web_result, mock_tech_result):
        exc = RuntimeError("A failed")
        with pytest.raises(WorkflowCircuitBreakerError, match="module_a: RuntimeError: A failed"):
            _check_circuit_breaker(exc, mock_web_result, mock_tech_result)

    def test_module_b_none_raises(self, mock_akshare_data, mock_tech_result):
        with pytest.raises(WorkflowCircuitBreakerError, match="module_b: returned None"):
            _check_circuit_breaker(mock_akshare_data, None, mock_tech_result)

    @patch("stock_analyzer.workflow.logger")
    def test_module_a_low_topics_warns_only(self, mock_logger, mock_akshare_data, mock_web_result, mock_tech_result):
        mock_akshare_data.meta.successful_topics = 3  # Lower than default 6
        _check_circuit_breaker(mock_akshare_data, mock_web_result, mock_tech_result)
        
        # Verify warning was called
        args, kwargs = mock_logger.warning.call_args
        assert "chief analysis context may be limited" in args[0]

@pytest.mark.asyncio
class TestWorkflowRun:
    @patch("stock_analyzer.workflow.lookup_stock_info")
    @patch("stock_analyzer.workflow.collect_akshare_data")
    @patch("stock_analyzer.workflow.run_web_research")
    @patch("stock_analyzer.workflow.run_technical_analysis")
    @patch("stock_analyzer.workflow.run_chief_analysis")
    @patch("stock_analyzer.workflow._save_intermediate_results")
    async def test_full_success_flow(
        self, 
        mock_save, 
        mock_chief, 
        mock_tech, 
        mock_web, 
        mock_a, 
        mock_lookup,
        mock_akshare_data,
        mock_web_result,
        mock_tech_result,
        mock_final_report
    ):
        # Setup mocks
        mock_lookup.return_value = ("贵州茅台", "白酒")
        mock_a.return_value = mock_akshare_data
        mock_web.return_value = mock_web_result
        mock_tech.return_value = mock_tech_result
        mock_chief.return_value = mock_final_report

        # Run
        result = await run_workflow("600519")

        # Verify
        assert result == mock_final_report
        mock_lookup.assert_called_once_with("600519")
        mock_a.assert_called_once()
        mock_web.assert_called_once()
        mock_tech.assert_called_once()
        mock_chief.assert_called_once()
        mock_save.assert_called_once()

    @patch("stock_analyzer.workflow.lookup_stock_info")
    async def test_lookup_failure_aborts_early(self, mock_lookup):
        mock_lookup.side_effect = StockInfoLookupError("Lookup failed")
        
        with pytest.raises(StockInfoLookupError):
            await run_workflow("600519")

    @patch("stock_analyzer.workflow.lookup_stock_info")
    @patch("stock_analyzer.workflow.collect_akshare_data")
    @patch("stock_analyzer.workflow.run_web_research")
    @patch("stock_analyzer.workflow.run_technical_analysis")
    async def test_parallel_timeout_raises(self, mock_tech, mock_web, mock_a, mock_lookup):
        mock_lookup.return_value = ("贵州茅台", "白酒")
        
        # Make one task slow
        async def slow_task(*args, **kwargs):
            await asyncio.sleep(2)
            return MagicMock()
        
        mock_web.side_effect = slow_task
        
        with patch("stock_analyzer.workflow.WORKFLOW_PARALLEL_TIMEOUT", 0.1):
            with pytest.raises(WorkflowCircuitBreakerError, match="Parallel phase timed out"):
                await run_workflow("600519")

    @patch("stock_analyzer.workflow.lookup_stock_info")
    @patch("stock_analyzer.workflow.collect_akshare_data")
    @patch("stock_analyzer.workflow.run_web_research")
    @patch("stock_analyzer.workflow.run_technical_analysis")
    async def test_partial_failure_triggers_breaker(self, mock_tech, mock_web, mock_a, mock_lookup, mock_akshare_data):
        mock_lookup.return_value = ("贵州茅台", "白酒")
        mock_a.return_value = mock_akshare_data
        mock_web.side_effect = RuntimeError("Web failed")
        mock_tech.return_value = MagicMock()

        with pytest.raises(WorkflowCircuitBreakerError, match="module_b: RuntimeError: Web failed"):
            await run_workflow("600519")

"""Unit tests for workflow orchestration."""

import asyncio
import json
import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from stock_analyzer.workflow import (
    run_workflow,
    lookup_stock_info,
    _check_circuit_breaker,
    _try_load_module_cache,
)
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


_STOCK_LOOKUP = {
    "symbol": "600519",
    "symbol_with_market_upper": "600519.SH",
    "name": "贵州茅台",
    "industry": "白酒",
    "date_beijing": "2026-02-13",
}


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


class TestLookupStockInfo:
    @patch("stock_analyzer.workflow.ak.stock_individual_info_em")
    def test_lookup_stock_info_returns_extended_fields(self, mock_info):
        mock_info.return_value = pd.DataFrame(
            {
                "item": ["股票简称", "行业"],
                "value": ["贵州茅台", "白酒"],
            }
        )

        info = lookup_stock_info("600519")

        assert info["symbol"] == "600519"
        assert info["symbol_with_market_upper"] == "600519.SH"
        assert info["name"] == "贵州茅台"
        assert info["industry"] == "白酒"
        assert len(info["date_beijing"]) == 10

    @patch("stock_analyzer.workflow.ak.stock_individual_info_em")
    def test_lookup_stock_info_placeholder_name_raises(self, mock_info):
        mock_info.return_value = pd.DataFrame(
            {
                "item": ["股票简称", "行业"],
                "value": ["-", "白酒"],
            }
        )

        with pytest.raises(StockInfoLookupError, match="Cannot resolve stock name"):
            lookup_stock_info("600519")


_NO_CACHE = {
    "WORKFLOW_MODULE_A_USE_CACHE": False,
    "WORKFLOW_MODULE_B_USE_CACHE": False,
    "WORKFLOW_MODULE_C_USE_CACHE": False,
}


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
        mock_lookup.return_value = _STOCK_LOOKUP
        mock_a.return_value = mock_akshare_data
        mock_web.return_value = mock_web_result
        mock_tech.return_value = mock_tech_result
        mock_chief.return_value = mock_final_report

        # Run
        with patch.multiple("stock_analyzer.workflow", **_NO_CACHE):
            result = await run_workflow("600519")

        # Verify
        assert result == mock_final_report
        mock_lookup.assert_called_once_with("600519")
        mock_a.assert_called_once()
        mock_web.assert_called_once_with(
            symbol="600519",
            name="贵州茅台",
            industry="白酒",
        )
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
        mock_lookup.return_value = _STOCK_LOOKUP

        # Make one task slow
        async def slow_task(*args, **kwargs):
            await asyncio.sleep(2)
            return MagicMock()

        mock_web.side_effect = slow_task

        with patch("stock_analyzer.workflow.WORKFLOW_PARALLEL_TIMEOUT", 0.1), \
             patch.multiple("stock_analyzer.workflow", **_NO_CACHE):
            with pytest.raises(WorkflowCircuitBreakerError, match="Parallel phase timed out"):
                await run_workflow("600519")

    @patch("stock_analyzer.workflow.lookup_stock_info")
    @patch("stock_analyzer.workflow.collect_akshare_data")
    @patch("stock_analyzer.workflow.run_web_research")
    @patch("stock_analyzer.workflow.run_technical_analysis")
    async def test_partial_failure_triggers_breaker(self, mock_tech, mock_web, mock_a, mock_lookup, mock_akshare_data):
        mock_lookup.return_value = _STOCK_LOOKUP
        mock_a.return_value = mock_akshare_data
        mock_web.side_effect = RuntimeError("Web failed")
        mock_tech.return_value = MagicMock()

        with patch.multiple("stock_analyzer.workflow", **_NO_CACHE):
            with pytest.raises(WorkflowCircuitBreakerError, match="module_b: RuntimeError: Web failed"):
                await run_workflow("600519")


# ---- Minimal JSON fixtures for cache tests ----

_MINIMAL_AKSHARE_JSON = json.dumps({
    "meta": {
        "symbol": "600519",
        "name": "贵州茅台",
        "query_time": "2026-01-01T00:00:00",
        "successful_topics": 10,
        "topic_status": {},
    }
})

_MINIMAL_WEB_JSON = json.dumps({
    "meta": {
        "symbol": "600519",
        "name": "贵州茅台",
        "search_time": "2026-01-01T00:00:00",
        "search_config": {
            "topics_count": 3,
            "breadth": 3,
            "depth": 2,
            "successful_topics": 3,
        },
        "total_learnings": 5,
        "total_sources_consulted": 10,
    },
    "news_summary": {"positive": [], "negative": [], "neutral": []},
    "competitive_advantage": {
        "description": "test",
        "moat_type": "brand",
        "market_position": "leader",
    },
    "industry_outlook": {
        "industry": "白酒",
        "outlook": "稳定",
        "key_drivers": ["消费升级"],
        "key_risks": ["政策风险"],
    },
    "risk_events": {"regulatory": "", "litigation": "", "management": ""},
    "analyst_opinions": {},
    "search_confidence": "中",
})

_MINIMAL_TECH_JSON = json.dumps({
    "meta": {
        "symbol": "600519",
        "name": "贵州茅台",
        "analysis_time": "2026-01-01T00:00:00",
    },
    "score": 5.0,
    "signal": "中性",
    "confidence": 0.5,
    "trend_analysis": {},
    "momentum": {},
    "volatility": {},
    "volume_analysis": {},
    "key_levels": {},
    "summary": "test summary",
})


class TestTryLoadModuleCache:
    """Tests for _try_load_module_cache."""

    def test_cache_hit_akshare(self, tmp_path):
        """Load a valid akshare cache file."""
        (tmp_path / "600519_akshare_data.json").write_text(_MINIMAL_AKSHARE_JSON, encoding="utf-8")

        with patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            result = _try_load_module_cache("600519", "akshare")

        assert isinstance(result, AKShareData)
        assert result.meta.symbol == "600519"

    def test_cache_hit_web(self, tmp_path):
        """Load a valid web research cache file."""
        (tmp_path / "600519_web_research.json").write_text(_MINIMAL_WEB_JSON, encoding="utf-8")

        with patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            result = _try_load_module_cache("600519", "web")

        assert isinstance(result, WebResearchResult)

    def test_cache_hit_tech(self, tmp_path):
        """Load a valid technical analysis cache file."""
        (tmp_path / "600519_technical_analysis.json").write_text(_MINIMAL_TECH_JSON, encoding="utf-8")

        with patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            result = _try_load_module_cache("600519", "tech")

        assert isinstance(result, TechnicalAnalysisResult)

    def test_cache_miss_no_file(self, tmp_path):
        """When cache file does not exist, returns None."""
        with patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            result = _try_load_module_cache("600519", "akshare")
        assert result is None

    def test_cache_corrupt_json_returns_none(self, tmp_path):
        """When a file has invalid JSON, returns None gracefully."""
        (tmp_path / "600519_akshare_data.json").write_text("{bad json", encoding="utf-8")

        with patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            result = _try_load_module_cache("600519", "akshare")
        assert result is None

    def test_cache_validation_error_returns_none(self, tmp_path):
        """When a file has valid JSON but fails model validation, returns None."""
        (tmp_path / "600519_akshare_data.json").write_text('{"meta": {}}', encoding="utf-8")

        with patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            result = _try_load_module_cache("600519", "akshare")
        assert result is None


@pytest.mark.asyncio
class TestWorkflowCache:
    """Tests for per-module WORKFLOW_MODULE_*_USE_CACHE in run_workflow."""

    @patch("stock_analyzer.workflow.lookup_stock_info")
    @patch("stock_analyzer.workflow.run_chief_analysis")
    @patch("stock_analyzer.workflow.collect_akshare_data")
    @patch("stock_analyzer.workflow.run_web_research")
    @patch("stock_analyzer.workflow.run_technical_analysis")
    async def test_all_cache_true_skips_all_modules(
        self, mock_tech, mock_web, mock_a, mock_chief, mock_lookup, tmp_path
    ):
        """When all USE_CACHE=True and cache exists, A/B/C modules are NOT called."""
        mock_lookup.return_value = _STOCK_LOOKUP
        mock_chief.return_value = MagicMock(
            spec=FinalReport, overall_score=8.0, overall_confidence="高"
        )

        # Write cache files
        (tmp_path / "600519_akshare_data.json").write_text(_MINIMAL_AKSHARE_JSON, encoding="utf-8")
        (tmp_path / "600519_web_research.json").write_text(_MINIMAL_WEB_JSON, encoding="utf-8")
        (tmp_path / "600519_technical_analysis.json").write_text(_MINIMAL_TECH_JSON, encoding="utf-8")

        with patch("stock_analyzer.workflow.WORKFLOW_MODULE_A_USE_CACHE", True), \
             patch("stock_analyzer.workflow.WORKFLOW_MODULE_B_USE_CACHE", True), \
             patch("stock_analyzer.workflow.WORKFLOW_MODULE_C_USE_CACHE", True), \
             patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            result = await run_workflow("600519")

        # A/B/C should NOT have been called
        mock_a.assert_not_called()
        mock_web.assert_not_called()
        mock_tech.assert_not_called()
        # D should still run
        mock_chief.assert_called_once()

    @patch("stock_analyzer.workflow.lookup_stock_info")
    @patch("stock_analyzer.workflow.run_chief_analysis")
    @patch("stock_analyzer.workflow.collect_akshare_data")
    @patch("stock_analyzer.workflow.run_web_research")
    @patch("stock_analyzer.workflow.run_technical_analysis")
    @patch("stock_analyzer.workflow._save_intermediate_results")
    async def test_all_cache_true_no_files_runs_all_modules(
        self, mock_save, mock_tech, mock_web, mock_a, mock_chief, mock_lookup, tmp_path,
        mock_akshare_data, mock_web_result, mock_tech_result,
    ):
        """When all USE_CACHE=True but no cache files, falls back to running all modules."""
        mock_lookup.return_value = _STOCK_LOOKUP
        mock_a.return_value = mock_akshare_data
        mock_web.return_value = mock_web_result
        mock_tech.return_value = mock_tech_result
        mock_chief.return_value = MagicMock(
            spec=FinalReport, overall_score=8.0, overall_confidence="高"
        )

        with patch("stock_analyzer.workflow.WORKFLOW_MODULE_A_USE_CACHE", True), \
             patch("stock_analyzer.workflow.WORKFLOW_MODULE_B_USE_CACHE", True), \
             patch("stock_analyzer.workflow.WORKFLOW_MODULE_C_USE_CACHE", True), \
             patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            await run_workflow("600519")

        # A/B/C SHOULD have been called (cache miss)
        mock_a.assert_called_once()
        mock_web.assert_called_once()
        mock_tech.assert_called_once()

    @patch("stock_analyzer.workflow.lookup_stock_info")
    @patch("stock_analyzer.workflow.run_chief_analysis")
    @patch("stock_analyzer.workflow.collect_akshare_data")
    @patch("stock_analyzer.workflow.run_web_research")
    @patch("stock_analyzer.workflow.run_technical_analysis")
    @patch("stock_analyzer.workflow._save_intermediate_results")
    async def test_all_cache_false_always_runs_modules(
        self, mock_save, mock_tech, mock_web, mock_a, mock_chief, mock_lookup, tmp_path,
        mock_akshare_data, mock_web_result, mock_tech_result,
    ):
        """When all USE_CACHE=False, modules always run even if cache files exist."""
        mock_lookup.return_value = _STOCK_LOOKUP
        mock_a.return_value = mock_akshare_data
        mock_web.return_value = mock_web_result
        mock_tech.return_value = mock_tech_result
        mock_chief.return_value = MagicMock(
            spec=FinalReport, overall_score=8.0, overall_confidence="高"
        )

        # Write cache files - should be ignored
        (tmp_path / "600519_akshare_data.json").write_text(_MINIMAL_AKSHARE_JSON, encoding="utf-8")
        (tmp_path / "600519_web_research.json").write_text(_MINIMAL_WEB_JSON, encoding="utf-8")
        (tmp_path / "600519_technical_analysis.json").write_text(_MINIMAL_TECH_JSON, encoding="utf-8")

        with patch.multiple("stock_analyzer.workflow", **_NO_CACHE), \
             patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            await run_workflow("600519")

        # A/B/C SHOULD have been called despite cache existing
        mock_a.assert_called_once()
        mock_web.assert_called_once()
        mock_tech.assert_called_once()

    @patch("stock_analyzer.workflow.lookup_stock_info")
    @patch("stock_analyzer.workflow.run_chief_analysis")
    @patch("stock_analyzer.workflow.collect_akshare_data")
    @patch("stock_analyzer.workflow.run_web_research")
    @patch("stock_analyzer.workflow.run_technical_analysis")
    @patch("stock_analyzer.workflow._save_intermediate_results")
    async def test_partial_cache_a_cached_bc_fresh(
        self, mock_save, mock_tech, mock_web, mock_a, mock_chief, mock_lookup, tmp_path,
        mock_web_result, mock_tech_result,
    ):
        """When only module A uses cache, B and C still run fresh."""
        mock_lookup.return_value = _STOCK_LOOKUP
        mock_web.return_value = mock_web_result
        mock_tech.return_value = mock_tech_result
        mock_chief.return_value = MagicMock(
            spec=FinalReport, overall_score=8.0, overall_confidence="高"
        )

        # Only write A cache
        (tmp_path / "600519_akshare_data.json").write_text(_MINIMAL_AKSHARE_JSON, encoding="utf-8")

        with patch("stock_analyzer.workflow.WORKFLOW_MODULE_A_USE_CACHE", True), \
             patch("stock_analyzer.workflow.WORKFLOW_MODULE_B_USE_CACHE", False), \
             patch("stock_analyzer.workflow.WORKFLOW_MODULE_C_USE_CACHE", False), \
             patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            result = await run_workflow("600519")

        # A should NOT be called (cached), B/C should run
        mock_a.assert_not_called()
        mock_web.assert_called_once()
        mock_tech.assert_called_once()
        mock_chief.assert_called_once()

    @patch("stock_analyzer.workflow.lookup_stock_info")
    @patch("stock_analyzer.workflow.run_chief_analysis")
    @patch("stock_analyzer.workflow.collect_akshare_data")
    @patch("stock_analyzer.workflow.run_web_research")
    @patch("stock_analyzer.workflow.run_technical_analysis")
    @patch("stock_analyzer.workflow._save_intermediate_results")
    async def test_cache_true_but_file_missing_falls_back(
        self, mock_save, mock_tech, mock_web, mock_a, mock_chief, mock_lookup, tmp_path,
        mock_akshare_data, mock_web_result, mock_tech_result,
    ):
        """When USE_CACHE=True for a module but its cache file is missing, that module runs fresh."""
        mock_lookup.return_value = _STOCK_LOOKUP
        mock_a.return_value = mock_akshare_data
        mock_web.return_value = mock_web_result
        mock_tech.return_value = mock_tech_result
        mock_chief.return_value = MagicMock(
            spec=FinalReport, overall_score=8.0, overall_confidence="高"
        )

        # Write B and C cache but NOT A
        (tmp_path / "600519_web_research.json").write_text(_MINIMAL_WEB_JSON, encoding="utf-8")
        (tmp_path / "600519_technical_analysis.json").write_text(_MINIMAL_TECH_JSON, encoding="utf-8")

        with patch("stock_analyzer.workflow.WORKFLOW_MODULE_A_USE_CACHE", True), \
             patch("stock_analyzer.workflow.WORKFLOW_MODULE_B_USE_CACHE", True), \
             patch("stock_analyzer.workflow.WORKFLOW_MODULE_C_USE_CACHE", True), \
             patch("stock_analyzer.workflow.WORKFLOW_OUTPUT_DIR", str(tmp_path)):
            result = await run_workflow("600519")

        # A should run (cache miss), B/C should be cached
        mock_a.assert_called_once()
        mock_web.assert_not_called()
        mock_tech.assert_not_called()
        mock_chief.assert_called_once()

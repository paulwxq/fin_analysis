"""Tests for workflow retry logic."""

from unittest.mock import MagicMock, patch
import pytest
import pandas as pd
from stock_analyzer.workflow import lookup_stock_info
from stock_analyzer.exceptions import StockInfoLookupError

class TestWorkflowRetry:
    
    @patch("stock_analyzer.workflow.ak.stock_individual_info_em")
    @patch("time.sleep")  # Mock sleep to speed up tests
    def test_lookup_retry_success_after_failure(self, mock_sleep, mock_ak):
        """Test that lookup succeeds after failing twice."""
        # 模拟前两次抛出异常，第三次成功返回数据
        success_df = pd.DataFrame({
            "item": ["股票简称", "行业"],
            "value": ["贵州茅台", "白酒"]
        })
        
        mock_ak.side_effect = [
            RuntimeError("Network fail 1"),
            RuntimeError("Network fail 2"),
            success_df
        ]
        
        info = lookup_stock_info("600519")
        
        # 验证结果正确
        assert info["name"] == "贵州茅台"
        # 验证调用次数：1 (初次) + 2 (重试) = 3 次调用
        assert mock_ak.call_count == 3
        # 验证 sleep 调用次数：2 次
        assert mock_sleep.call_count == 2

    @patch("stock_analyzer.workflow.ak.stock_individual_info_em")
    @patch("time.sleep")
    def test_lookup_retry_exhausted(self, mock_sleep, mock_ak):
        """Test that lookup raises exception after exhausting all retries."""
        # 模拟一直失败
        mock_ak.side_effect = RuntimeError("Persistent failure")
        
        with pytest.raises(StockInfoLookupError) as exc:
            lookup_stock_info("600519")
            
        assert "Persistent failure" in str(exc.value)
        # 验证调用次数：1 (初次) + 3 (重试) = 4 次调用
        assert mock_ak.call_count == 4
        # 验证 sleep 调用次数：3 次
        assert mock_sleep.call_count == 3

    @patch("stock_analyzer.workflow.ak.stock_individual_info_em")
    @patch("time.sleep")
    def test_lookup_retry_on_empty_data(self, mock_sleep, mock_ak):
        """Test that lookup retries even if no exception but empty data returned."""
        # 模拟前两次返回空 DataFrame，第三次成功
        success_df = pd.DataFrame({
            "item": ["股票简称", "行业"],
            "value": ["贵州茅台", "白酒"]
        })
        
        mock_ak.side_effect = [
            pd.DataFrame(),  # Empty
            None,            # None
            success_df
        ]
        
        info = lookup_stock_info("600519")
        
        assert info["name"] == "贵州茅台"
        assert mock_ak.call_count == 3

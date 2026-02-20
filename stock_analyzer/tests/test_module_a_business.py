"""Unit tests for Module A business composition collection and formatting."""

import pytest
import pandas as pd
from stock_analyzer.module_a_akshare import AKShareCollector
from stock_analyzer.module_a_models import BusinessComposition, AKShareData, AKShareMeta
from stock_analyzer.markdown_formatter import format_akshare_markdown

# --- Mock Data ---

@pytest.fixture
def mock_zygc_df():
    """Mock DataFrame with multiple report dates."""
    data = [
        # Latest period (Year 2025 Mid)
        {"报告日期": "2025-06-30", "分类类型": "按产品分类", "主营构成": "产品A", "收入比例": 0.6, "毛利率": 0.2},
        {"报告日期": "2025-06-30", "分类类型": "按地区分类", "主营构成": "地区X", "收入比例": 0.5, "毛利率": 0.1},
        
        # Previous period (Year 2024 End)
        {"报告日期": "2024-12-31", "分类类型": "按产品分类", "主营构成": "产品A", "收入比例": 0.55, "毛利率": 0.18},
        
        # Older period (Year 2024 Mid)
        {"报告日期": "2024-06-30", "分类类型": "按产品分类", "主营构成": "产品A", "收入比例": 0.5, "毛利率": 0.15},
        
        # Very old period (Should be filtered out)
        {"报告日期": "2020-12-31", "分类类型": "按产品分类", "主营构成": "产品Old", "收入比例": 0.1, "毛利率": 0.05},
    ]
    return pd.DataFrame(data)

# --- Collection Logic Tests ---

def test_collect_business_composition_filters_top3(mocker, mock_zygc_df):
    collector = AKShareCollector("600519", "贵州茅台")
    mocker.patch.object(collector, "safe_call", return_value=mock_zygc_df)
    
    # Run collection
    results = collector._collect_business_composition()
    
    assert results is not None
    # Check total count: should be 4 (2 from 2025-06, 1 from 2024-12, 1 from 2024-06)
    # The 2020 record should be filtered out
    assert len(results) == 4
    
    # Check dates present
    dates = {r["report_date"] for r in results}
    assert dates == {"2025-06-30", "2024-12-31", "2024-06-30"}
    assert "2020-12-31" not in dates

def test_collect_business_composition_fields(mocker, mock_zygc_df):
    collector = AKShareCollector("600519", "贵州茅台")
    mocker.patch.object(collector, "safe_call", return_value=mock_zygc_df)
    
    results = collector._collect_business_composition()
    first = results[0] # Should be 2025-06-30 product A
    
    assert first["report_date"] == "2025-06-30"
    assert first["type"] == "按产品分类"
    assert first["item"] == "产品A"
    assert first["revenue_ratio"] == 0.6
    assert first["gross_margin"] == 0.2

# --- Formatting Tests ---

def test_markdown_format_grouped_by_date():
    # Construct data model directly
    bc_list = [
        BusinessComposition(report_date="2025-06-30", type="按产品分类", item="A", revenue_ratio=0.6, gross_margin=0.2),
        BusinessComposition(report_date="2024-12-31", type="按产品分类", item="A", revenue_ratio=0.5, gross_margin=0.1),
    ]
    data = AKShareData(
        meta=AKShareMeta(symbol="000001", name="Test", query_time="now"),
        business_composition=bc_list
    )
    
    md = format_akshare_markdown(data)
    
    assert "**报告期：2025-06-30**" in md
    assert "**报告期：2024-12-31**" in md
    assert "---" in md  # Separator should exist
    
    # Check content order (latest first)
    pos_2025 = md.find("2025-06-30")
    pos_2024 = md.find("2024-12-31")
    assert pos_2025 < pos_2024

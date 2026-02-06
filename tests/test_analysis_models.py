import pytest
from analysis_llm.models import SectorData, NewsData, TrendEnum
from pydantic import ValidationError

def test_sector_data_mapping():
    # 测试英文趋势映射
    data = {
        "data_type": "sector",
        "stock_code": "603080.SH",
        "sector_name": "燃气",
        "heat_index": 50.0,
        "trend": "neutral",  # 应该被映射为 '震荡'
        "capital_flow": 0     # 应该被映射为 '0'
    }
    obj = SectorData.model_validate(data)
    assert obj.trend == TrendEnum.OSCILLATE
    assert obj.capital_flow == "0"

    # 测试 up 映射
    data["trend"] = "up"
    obj = SectorData.model_validate(data)
    assert obj.trend == TrendEnum.UP

def test_news_data_defaults():
    # 测试只有 stock_code 时是否报错 (当前设计要求全部必填)
    # 注意：我们之前的讨论是维持严格模式，所以这里应该报错
    data = {
        "data_type": "news",
        "stock_code": "603080.SH"
    }
    with pytest.raises(ValidationError):
        NewsData.model_validate(data)

def test_news_data_item_length():
    # 测试新闻项长度限制
    data = {
        "data_type": "news",
        "stock_code": "603080.SH",
        "positive_news": ["A" * 501], # 超过 500
        "negative_news": [],
        "news_summary": "summary",
        "sentiment_score": 0.5
    }
    with pytest.raises(ValidationError) as exc:
        NewsData.model_validate(data)
    assert "单条新闻摘要长度超过" in str(exc.value)

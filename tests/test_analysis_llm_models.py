import pytest

from analysis_llm import config
from analysis_llm.models import NewsData


def test_news_data_length_ok():
    data = NewsData(
        data_type="news",
        stock_code="TSLA",
        positive_news=["a"],
        negative_news=["b"],
        news_summary="summary",
        sentiment_score=0.1,
    )
    assert data.stock_code == "TSLA"


def test_news_data_item_too_long():
    long_item = "a" * (config.NEWS_ITEM_MAX_CHARS + 1)
    with pytest.raises(ValueError):
        NewsData(
            data_type="news",
            stock_code="TSLA",
            positive_news=[long_item],
            negative_news=["b"],
            news_summary="summary",
            sentiment_score=0.1,
        )

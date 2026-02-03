import json
import pytest

from agent_framework import ChatMessage

from analysis_llm.merger import merge_results


def _msg(payload: dict) -> ChatMessage:
    return ChatMessage(role="assistant", text=json.dumps(payload, ensure_ascii=False))


def test_merge_results_success():
    news = {
        "data_type": "news",
        "stock_code": "TSLA",
        "positive_news": ["p1"],
        "negative_news": ["n1"],
        "news_summary": "sum",
        "sentiment_score": 0.2,
    }
    sector = {
        "data_type": "sector",
        "stock_code": "TSLA",
        "sector_name": "新能源汽车",
        "heat_index": 80,
        "trend": "上升",
        "capital_flow": "流入",
    }
    kline = {
        "data_type": "kline",
        "stock_code": "TSLA",
        "technical_indicators": {"MACD": 0.1, "RSI": 55.0, "KDJ_K": 60.0},
        "support_level": 100.0,
        "resistance_level": 150.0,
        "trend_analysis": "up",
        "buy_suggestion": "持有",
    }

    output = merge_results([_msg(news), _msg(sector), _msg(kline)])
    assert output.news.stock_code == "TSLA"
    assert output.sector.trend.value == "上升"


def test_merge_results_missing():
    news = {
        "data_type": "news",
        "stock_code": "TSLA",
        "positive_news": ["p1"],
        "negative_news": ["n1"],
        "news_summary": "sum",
        "sentiment_score": 0.2,
    }
    with pytest.raises(RuntimeError):
        merge_results([_msg(news)])

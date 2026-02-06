import pytest
from agent_framework import ChatMessage, Role
from analysis_llm.merger import merge_results
from analysis_llm.models import Step1Output

def test_merge_results_success():
    # 模拟三个单元的返回结果
    results = [
        ChatMessage(role=Role.ASSISTANT, text='{"data_type": "sector", "stock_code": "603080.SH", "sector_name": "燃气", "heat_index": 50, "trend": "上升", "capital_flow": "流出"}'),
        ChatMessage(role=Role.ASSISTANT, text='{"data_type": "news", "stock_code": "603080.SH", "positive_news": ["好消息"], "negative_news": [], "news_summary": "总得来说不错", "sentiment_score": 0.6}'),
        ChatMessage(role=Role.ASSISTANT, text='{"data_type": "kline", "stock_code": "603080.SH", "technical_indicators": {"MACD": 0.1, "RSI": 50, "KDJ_K": 40}, "support_level": 20, "resistance_level": 30, "trend_analysis": "震荡", "buy_suggestion": "持有"}')
    ]
    
    output = merge_results(results)
    assert isinstance(output, Step1Output)
    assert output.news.stock_code == "603080.SH"
    assert output.sector.sector_name == "燃气"
    assert output.kline.technical_indicators.MACD == 0.1

def test_merge_results_failure():
    # 模拟缺失一个单元的情况
    results = [
        ChatMessage(role=Role.ASSISTANT, text='{"data_type": "news", "stock_code": "603080.SH", "positive_news": [], "negative_news": [], "news_summary": "...", "sentiment_score": 0}')
    ]
    
    with pytest.raises(RuntimeError) as exc:
        merge_results(results)
    assert "Step 1 合并失败" in str(exc.value)
    assert "SectorData" in str(exc.value)
    assert "KLineData" in str(exc.value)
"""Unit tests for module C technical analysis helpers and workflow."""

from __future__ import annotations

import json

import pandas as pd
import pytest

import stock_analyzer.module_c_technical as module_c
from stock_analyzer.exceptions import AgentCallError
from stock_analyzer.module_c_models import (
    KeyLevels,
    LLMTechnicalOutput,
    MomentumAnalysis,
    TechnicalAnalysisResult,
    TechnicalMeta,
    TrendAnalysis,
    VolatilityAnalysis,
    VolumeAnalysis,
)


def _make_raw_kline(months: int) -> pd.DataFrame:
    dates = pd.date_range("2020-01-31", periods=months, freq="ME")
    close = [100 + i for i in range(months)]
    return pd.DataFrame(
        {
            "date": dates,
            "open": [c - 1 for c in close],
            "high": [c + 2 for c in close],
            "low": [c - 2 for c in close],
            "close": close,
            "volume": [1000 + i * 10 for i in range(months)],
        }
    )


def _make_feature_df(months: int, with_ma60: bool = True) -> pd.DataFrame:
    df = _make_raw_kline(months).copy()
    df["SMA_5"] = df["close"].rolling(5).mean()
    df["SMA_10"] = df["close"].rolling(10).mean()
    df["SMA_20"] = df["close"].rolling(20).mean()
    df["SMA_60"] = df["close"].rolling(60).mean() if with_ma60 else pd.NA
    df["MACD_12_26_9"] = 1.0
    df["MACDh_12_26_9"] = 0.2
    df["MACDs_12_26_9"] = 0.8
    df["RSI_14"] = 55.0
    df["BBL_20_2.0"] = df["close"] * 0.95
    df["BBM_20_2.0"] = df["close"]
    df["BBU_20_2.0"] = df["close"] * 1.05
    df["STOCHk_14_3_3"] = 60.0
    df["STOCHd_14_3_3"] = 55.0
    return df


def test_fetch_monthly_kline_fallback_adjust(monkeypatch) -> None:
    called_adjusts: list[str] = []
    expected = _make_raw_kline(12)

    def fake_hist(*, symbol: str, period: str, start_date: str, adjust: str):
        called_adjusts.append(adjust)
        if len(called_adjusts) == 1:
            raise RuntimeError("first call failed")
        return expected

    monkeypatch.setattr(module_c.ak, "stock_zh_a_hist", fake_hist)

    result = module_c.fetch_monthly_kline(symbol="600519", adjust="qfq")
    assert not result.empty
    assert called_adjusts == ["qfq", ""]


def test_normalize_kline_df_sorts_and_converts() -> None:
    raw = pd.DataFrame(
        {
            "日期": ["2024-02-29", "2024-01-31"],
            "开盘": ["100", "90"],
            "最高": ["105", "95"],
            "最低": ["95", "88"],
            "收盘": ["102", "92"],
            "成交量": ["1000", "900"],
        }
    )
    out = module_c._normalize_kline_df(raw)

    assert list(out.columns)[:6] == ["date", "open", "high", "low", "close", "volume"]
    assert out["date"].iloc[0].strftime("%Y-%m-%d") == "2024-01-31"
    assert out["close"].dtype.kind in ("f", "i")


def test_build_rows_json_handles_nan_and_datetime() -> None:
    df = _make_feature_df(36, with_ma60=False)
    rows_json = module_c._build_rows_json(df, lookback_months=6)

    parsed = json.loads(rows_json)
    assert len(parsed) == 6
    assert isinstance(parsed[0]["date"], str)
    assert parsed[-1]["SMA_60"] is None


def test_judge_volume_uses_aligned_rows_when_volume_has_nan() -> None:
    df = pd.DataFrame(
        {
            "close": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 8, 9],
            "volume": [10, 10, 10, 10, 10, 10, 10, 10, 10, 100, 100, None, 300],
        }
    )

    _, relation = module_c._judge_volume(df)
    assert relation == "价跌量增，抛压释放信号"


def test_judge_rsi_uses_configured_column_name(monkeypatch) -> None:
    monkeypatch.setattr(module_c, "_COL_RSI", "RSI_20")
    df = pd.DataFrame({"RSI_20": [45.0, 66.0]})
    latest = df.iloc[-1]

    rsi_value, rsi_status = module_c._judge_rsi(df, latest)
    assert rsi_value == 66.0
    assert rsi_status == "中性"


def test_build_rows_json_uses_configured_sma_columns(monkeypatch) -> None:
    monkeypatch.setattr(module_c, "_COL_SMA_SHORT", "SMA_3")
    monkeypatch.setattr(module_c, "_COL_SMA_MID", "SMA_7")
    monkeypatch.setattr(module_c, "_COL_SMA_LONG", "SMA_15")
    monkeypatch.setattr(module_c, "_COL_SMA_TREND", "SMA_30")
    monkeypatch.setattr(module_c, "_COL_RSI", "RSI_20")

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-31", "2024-02-29"]),
            "close": [10.0, 11.0],
            "volume": [100.0, 120.0],
            "SMA_3": [9.5, 10.5],
            "SMA_7": [9.2, 10.2],
            "SMA_15": [8.8, 9.8],
            "SMA_30": [8.5, 9.5],
            "RSI_20": [55.0, 60.0],
        }
    )

    parsed = json.loads(module_c._build_rows_json(df, lookback_months=2))
    assert "SMA_3" in parsed[0]
    assert "SMA_7" in parsed[0]
    assert "SMA_15" in parsed[0]
    assert "SMA_30" in parsed[0]
    assert "RSI_20" in parsed[0]


@pytest.mark.asyncio
async def test_run_technical_analysis_hard_degrade_when_insufficient_months(monkeypatch) -> None:
    monkeypatch.setattr(module_c, "fetch_monthly_kline", lambda symbol: _make_raw_kline(12))

    result = await module_c.run_technical_analysis("600519", "贵州茅台")
    assert result.signal == "中性"
    assert result.confidence == 0.2
    assert any("样本不足：仅 12 个月" in x for x in result.meta.data_quality_warnings)


@pytest.mark.asyncio
async def test_run_technical_analysis_soft_cap_confidence_for_24_to_59(monkeypatch) -> None:
    monkeypatch.setattr(module_c, "fetch_monthly_kline", lambda symbol: _make_raw_kline(36))
    monkeypatch.setattr(module_c, "_compute_technical_indicators", lambda df: _make_feature_df(36, False))
    monkeypatch.setattr(module_c, "create_openai_client", lambda: object())
    monkeypatch.setattr(module_c, "create_chat_client", lambda client, model_id: object())
    monkeypatch.setattr(module_c, "create_technical_agent", lambda chat_client: object())

    async def fake_call_agent_with_model(agent, message, model_cls):
        return LLMTechnicalOutput(
            score=8.2,
            signal="看多",
            confidence=0.9,
            trend_analysis=TrendAnalysis(
                ma_alignment="中期多头排列（MA5>MA10>MA20）",
                price_vs_ma20="收盘价位于MA20上方约5.00%",
                trend_6m="近6个月上涨5.00%",
                trend_12m="近12个月上涨10.00%",
                trend_judgment="中期震荡偏多",
            ),
            momentum=MomentumAnalysis(
                macd_status="MACD位于零轴上方",
                rsi_value=58.0,
                rsi_status="中性偏强",
                kdj_status="中性",
            ),
            volatility=VolatilityAnalysis(
                boll_position="价格位于布林中轨与上轨之间",
                boll_width="布林带开口收窄",
            ),
            volume_analysis=VolumeAnalysis(
                recent_vs_avg="近3月量能与年内均量接近",
                volume_price_relation="量价配合中性偏正",
            ),
            key_levels=KeyLevels(
                support_1=100.0,
                support_2=95.0,
                resistance_1=120.0,
                resistance_2=130.0,
            ),
            summary="测试输出",
        )

    monkeypatch.setattr(module_c, "call_agent_with_model", fake_call_agent_with_model)

    result = await module_c.run_technical_analysis("600519", "贵州茅台")
    assert result.confidence == 0.65
    assert result.meta.total_months == 36
    assert any("样本不足60个月" in x for x in result.meta.data_quality_warnings)


@pytest.mark.asyncio
async def test_run_technical_analysis_llm_failure_fallback(monkeypatch) -> None:
    monkeypatch.setattr(module_c, "fetch_monthly_kline", lambda symbol: _make_raw_kline(36))
    monkeypatch.setattr(module_c, "_compute_technical_indicators", lambda df: _make_feature_df(36, False))
    monkeypatch.setattr(module_c, "create_openai_client", lambda: object())
    monkeypatch.setattr(module_c, "create_chat_client", lambda client, model_id: object())
    monkeypatch.setattr(module_c, "create_technical_agent", lambda chat_client: object())

    async def fake_call_agent_with_model(agent, message, model_cls):
        raise AgentCallError("technical_analyst", Exception("bad llm output"))

    monkeypatch.setattr(module_c, "call_agent_with_model", fake_call_agent_with_model)

    result = await module_c.run_technical_analysis("600519", "贵州茅台")
    assert result.signal == "中性"
    assert result.confidence == 0.35
    assert "LLM 推理失败" in result.summary


@pytest.mark.asyncio
async def test_run_technical_analysis_final_result_build_failure_fallback(monkeypatch) -> None:
    monkeypatch.setattr(module_c, "fetch_monthly_kline", lambda symbol: _make_raw_kline(36))
    monkeypatch.setattr(module_c, "_compute_technical_indicators", lambda df: _make_feature_df(36, False))
    monkeypatch.setattr(module_c, "create_openai_client", lambda: object())
    monkeypatch.setattr(module_c, "create_chat_client", lambda client, model_id: object())
    monkeypatch.setattr(module_c, "create_technical_agent", lambda chat_client: object())

    class DummyOutput:
        def model_dump(self) -> dict:
            return {"score": "bad"}

    async def fake_call_agent_with_model(agent, message, model_cls):
        return DummyOutput()

    monkeypatch.setattr(module_c, "call_agent_with_model", fake_call_agent_with_model)

    result = await module_c.run_technical_analysis("600519", "贵州茅台")
    assert result.signal == "中性"
    assert result.confidence == 0.35
    assert "最终结果构造失败" in result.summary


def test_dump_technical_result_json_meta_first() -> None:
    result = TechnicalAnalysisResult(
        meta=TechnicalMeta(
            symbol="600519",
            name="贵州茅台",
            analysis_time="2026-02-12T00:00:00",
            data_start="2020-01-31",
            data_end="2026-01-31",
            total_months=72,
            data_quality_warnings=[],
        ),
        score=6.8,
        signal="看多",
        confidence=0.7,
        trend_analysis=TrendAnalysis(),
        momentum=MomentumAnalysis(),
        volatility=VolatilityAnalysis(),
        volume_analysis=VolumeAnalysis(),
        key_levels=KeyLevels(),
        summary="ok",
    )

    output = module_c.dump_technical_result_json(result)
    assert output.lstrip().startswith("{\n  \"meta\":")
    parsed = json.loads(output)
    assert parsed["meta"]["symbol"] == "600519"

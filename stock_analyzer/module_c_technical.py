"""Module C: monthly-kline technical analysis (code + agent)."""

from __future__ import annotations

import importlib
import json
from datetime import datetime

import akshare as ak
import pandas as pd

from stock_analyzer.agents import create_technical_agent
from stock_analyzer.config import (
    MODEL_TECHNICAL_AGENT,
    TECH_ADJUST,
    TECH_AGENT_LOOKBACK_MONTHS,
    TECH_BOLL_LENGTH,
    TECH_KDJ_D,
    TECH_KDJ_K,
    TECH_KDJ_SMOOTH,
    TECH_LONG_TREND_MIN_MONTHS,
    TECH_MA_LONG,
    TECH_MA_MID,
    TECH_MA_SHORT,
    TECH_MA_TREND,
    TECH_MIN_MONTHS,
    TECH_OUTPUT_RETRIES,
    TECH_RSI_LENGTH,
    TECH_START_DATE,
)
from stock_analyzer.exceptions import (
    AgentCallError,
    TechnicalDataError,
    TechnicalIndicatorError,
)
from stock_analyzer.llm_client import create_chat_client, create_openai_client
from stock_analyzer.llm_helpers import call_agent_with_model
from stock_analyzer.logger import logger
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

# Indicator column names derived from config to avoid hardcoded drift.
_COL_SMA_SHORT = f"SMA_{TECH_MA_SHORT}"
_COL_SMA_MID = f"SMA_{TECH_MA_MID}"
_COL_SMA_LONG = f"SMA_{TECH_MA_LONG}"
_COL_SMA_TREND = f"SMA_{TECH_MA_TREND}"
_COL_RSI = f"RSI_{TECH_RSI_LENGTH}"


def fetch_monthly_kline(
    symbol: str,
    start_date: str = TECH_START_DATE,
    adjust: str = TECH_ADJUST,
) -> pd.DataFrame:
    """Fetch monthly k-line from AKShare with one fallback adjust mode."""
    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="monthly",
            start_date=start_date,
            adjust=adjust,
        )
    except Exception as e:
        logger.warning(
            f"fetch_monthly_kline failed for {symbol} with adjust='{adjust}': {type(e).__name__}: {e}"
        )
        if adjust:
            try:
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="monthly",
                    start_date=start_date,
                    adjust="",
                )
            except Exception as e2:
                raise TechnicalDataError(
                    f"AKShare monthly kline failed for {symbol}: {type(e2).__name__}: {e2}"
                ) from e2
        else:
            raise TechnicalDataError(
                f"AKShare monthly kline failed for {symbol}: {type(e).__name__}: {e}"
            ) from e

    if df is None or df.empty:
        raise TechnicalDataError(f"Empty monthly kline data for {symbol}")
    return df


def _normalize_kline_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize AKShare monthly-kline columns and dtypes."""
    df = raw_df.copy()
    rename_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "振幅": "amplitude",
        "涨跌幅": "change_pct",
        "涨跌额": "change_amount",
        "换手率": "turnover_rate",
    }
    df = df.rename(columns=rename_map)

    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise TechnicalDataError(f"Missing required kline columns: {missing}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "close"]).sort_values("date", ascending=True)
    df = df.reset_index(drop=True)
    if df.empty:
        raise TechnicalDataError("No valid rows after kline normalization")
    return df


def _find_col(df: pd.DataFrame, candidates: list[str], prefix: str | None = None) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    if prefix:
        for col in df.columns:
            if col.startswith(prefix):
                return col
    return None


def _compute_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical indicators using pandas-ta."""
    try:
        importlib.import_module("pandas_ta")
    except Exception as e:
        raise TechnicalIndicatorError(
            "pandas_ta is required for module C; please install pandas-ta>=0.3.14b0"
        ) from e

    out = df.copy()
    try:
        out.ta.sma(length=TECH_MA_SHORT, append=True)
        out.ta.sma(length=TECH_MA_MID, append=True)
        out.ta.sma(length=TECH_MA_LONG, append=True)
        out.ta.sma(length=TECH_MA_TREND, append=True)
        out.ta.macd(append=True)
        out.ta.rsi(length=TECH_RSI_LENGTH, append=True)
        out.ta.bbands(length=TECH_BOLL_LENGTH, append=True)
        out.ta.stoch(
            k=TECH_KDJ_K,
            d=TECH_KDJ_D,
            smooth_k=TECH_KDJ_SMOOTH,
            append=True,
        )
    except Exception as e:
        raise TechnicalIndicatorError(
            f"Failed to compute technical indicators: {type(e).__name__}: {e}"
        ) from e
    return out


def _to_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def _period_return_pct(close: pd.Series, months: int) -> float | None:
    clean = pd.to_numeric(close, errors="coerce")
    if len(clean) <= months:
        return None
    current = _to_float(clean.iloc[-1])
    prev = _to_float(clean.iloc[-1 - months])
    if current is None or prev is None or prev == 0:
        return None
    return round((current / prev - 1) * 100, 2)


def _format_trend(months: int, pct: float | None) -> str:
    if pct is None:
        return f"近{months}个月数据不足"
    direction = "上涨" if pct >= 0 else "下跌"
    return f"近{months}个月{direction}{abs(pct):.2f}%"


def _judge_ma_alignment(latest: pd.Series, include_ma60: bool) -> str:
    ma_short = _to_float(latest.get(_COL_SMA_SHORT))
    ma_mid = _to_float(latest.get(_COL_SMA_MID))
    ma_long = _to_float(latest.get(_COL_SMA_LONG))
    ma_trend = _to_float(latest.get(_COL_SMA_TREND)) if include_ma60 else None
    core = [ma_short, ma_mid, ma_long]
    if any(v is None for v in core):
        return "均线数据不足"

    if include_ma60 and ma_trend is not None:
        if ma_short > ma_mid > ma_long > ma_trend:
            return (
                f"多头排列（MA{TECH_MA_SHORT}>MA{TECH_MA_MID}>"
                f"MA{TECH_MA_LONG}>MA{TECH_MA_TREND}）"
            )
        if ma_short < ma_mid < ma_long < ma_trend:
            return (
                f"空头排列（MA{TECH_MA_SHORT}<MA{TECH_MA_MID}<"
                f"MA{TECH_MA_LONG}<MA{TECH_MA_TREND}）"
            )
        return "均线缠绕或分化"

    if ma_short > ma_mid > ma_long:
        return f"中期多头排列（MA{TECH_MA_SHORT}>MA{TECH_MA_MID}>MA{TECH_MA_LONG}）"
    if ma_short < ma_mid < ma_long:
        return f"中期空头排列（MA{TECH_MA_SHORT}<MA{TECH_MA_MID}<MA{TECH_MA_LONG}）"
    return "均线缠绕或分化"


def _judge_price_vs_ma20(latest: pd.Series) -> str:
    close = _to_float(latest.get("close"))
    ma_long = _to_float(latest.get(_COL_SMA_LONG))
    if close is None or ma_long is None or ma_long == 0:
        return f"价格与MA{TECH_MA_LONG}关系数据不足"
    pct = (close / ma_long - 1) * 100
    direction = "上方" if pct >= 0 else "下方"
    return f"收盘价位于MA{TECH_MA_LONG}{direction}约{abs(pct):.2f}%"


def _judge_macd(df: pd.DataFrame) -> str:
    macd_col = _find_col(df, ["MACD_12_26_9"], prefix="MACD_")
    hist_col = _find_col(df, ["MACDh_12_26_9"], prefix="MACDh_")
    signal_col = _find_col(df, ["MACDs_12_26_9"], prefix="MACDs_")
    if not macd_col or not hist_col or not signal_col:
        return "MACD数据不足"

    macd = pd.to_numeric(df[macd_col], errors="coerce").dropna()
    hist = pd.to_numeric(df[hist_col], errors="coerce").dropna()
    signal = pd.to_numeric(df[signal_col], errors="coerce").dropna()
    if len(macd) < 2 or len(hist) < 2 or len(signal) < 2:
        return "MACD数据不足"

    cross = ""
    if macd.iloc[-2] <= signal.iloc[-2] and macd.iloc[-1] > signal.iloc[-1]:
        cross = "，近期金叉"
    elif macd.iloc[-2] >= signal.iloc[-2] and macd.iloc[-1] < signal.iloc[-1]:
        cross = "，近期死叉"

    axis = "零轴上方" if macd.iloc[-1] >= 0 else "零轴下方"
    hist_trend = "放大" if abs(hist.iloc[-1]) >= abs(hist.iloc[-2]) else "收敛"
    return f"MACD位于{axis}，柱状图{hist_trend}{cross}"


def _judge_rsi(df: pd.DataFrame, latest: pd.Series) -> tuple[float | None, str]:
    rsi_col = _find_col(df, [_COL_RSI], prefix="RSI_")
    if not rsi_col:
        return None, "RSI数据不足"
    rsi = _to_float(latest.get(rsi_col))
    if rsi is None:
        return None, "RSI数据不足"
    if rsi >= 70:
        return round(rsi, 2), "偏强（接近超买）"
    if rsi <= 30:
        return round(rsi, 2), "偏弱（接近超卖）"
    return round(rsi, 2), "中性"


def _judge_kdj(df: pd.DataFrame) -> str:
    k_col = _find_col(df, ["STOCHk_14_3_3"], prefix="STOCHk_")
    d_col = _find_col(df, ["STOCHd_14_3_3"], prefix="STOCHd_")
    if not k_col or not d_col:
        return "KDJ数据不足"
    k = pd.to_numeric(df[k_col], errors="coerce").dropna()
    d = pd.to_numeric(df[d_col], errors="coerce").dropna()
    if len(k) < 2 or len(d) < 2:
        return "KDJ数据不足"

    if k.iloc[-2] <= d.iloc[-2] and k.iloc[-1] > d.iloc[-1]:
        return "K线上穿D线，短线金叉"
    if k.iloc[-2] >= d.iloc[-2] and k.iloc[-1] < d.iloc[-1]:
        return "K线下穿D线，短线死叉"
    if k.iloc[-1] > 80:
        return "K值高位运行，注意回撤风险"
    if k.iloc[-1] < 20:
        return "K值低位运行，关注反弹信号"
    return "KDJ中性震荡"


def _judge_boll(df: pd.DataFrame, latest: pd.Series) -> tuple[str, str]:
    lower_col = _find_col(df, ["BBL_20_2.0"], prefix="BBL_")
    mid_col = _find_col(df, ["BBM_20_2.0"], prefix="BBM_")
    upper_col = _find_col(df, ["BBU_20_2.0"], prefix="BBU_")
    if not lower_col or not mid_col or not upper_col:
        return "布林带数据不足", "布林带数据不足"

    close = _to_float(latest.get("close"))
    lower = _to_float(latest.get(lower_col))
    mid = _to_float(latest.get(mid_col))
    upper = _to_float(latest.get(upper_col))
    if None in (close, lower, mid, upper) or upper == lower:
        return "布林带数据不足", "布林带数据不足"

    if close >= upper:
        pos = "价格接近或突破布林上轨"
    elif close >= mid:
        pos = "价格位于布林中轨与上轨之间"
    elif close >= lower:
        pos = "价格位于布林下轨与中轨之间"
    else:
        pos = "价格接近或跌破布林下轨"

    width_series = (
        (pd.to_numeric(df[upper_col], errors="coerce") - pd.to_numeric(df[lower_col], errors="coerce"))
        / pd.to_numeric(df[mid_col], errors="coerce")
    ).dropna()
    if len(width_series) < 2:
        width = "布林带宽度数据不足"
    else:
        width = "布林带开口扩大" if width_series.iloc[-1] >= width_series.iloc[-2] else "布林带开口收窄"
    return pos, width


def _judge_volume(df: pd.DataFrame) -> tuple[str, str]:
    # Keep volume/close row alignment before comparisons and rolling averages.
    aligned = pd.DataFrame(
        {
            "volume": pd.to_numeric(df["volume"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
        }
    ).dropna()

    if len(aligned) < 12:
        return "量能数据不足", "量价关系数据不足"

    vol = aligned["volume"]
    close = aligned["close"]

    recent3 = vol.tail(3).mean()
    avg12 = vol.tail(12).mean()
    ratio = None if avg12 == 0 else recent3 / avg12

    recent_vs_avg = (
        "近3月量能显著放大"
        if ratio is not None and ratio >= 1.2
        else "近3月量能略低于年内均量"
        if ratio is not None and ratio <= 0.8
        else "近3月量能与年内均量接近"
    )
    if ratio is not None:
        recent_vs_avg += f"（约{ratio:.2f}倍）"

    price_up = close.iloc[-1] >= close.iloc[-2]
    vol_up = vol.iloc[-1] >= vol.iloc[-2]
    if price_up and vol_up:
        relation = "价涨量增，量价配合偏正"
    elif price_up and not vol_up:
        relation = "价涨量缩，短线动能需观察"
    elif (not price_up) and vol_up:
        relation = "价跌量增，抛压释放信号"
    else:
        relation = "价跌量缩，市场观望为主"
    return recent_vs_avg, relation


def _calc_key_levels(df: pd.DataFrame) -> KeyLevels:
    low_col = "low" if "low" in df.columns else "close"
    high_col = "high" if "high" in df.columns else "close"
    low = pd.to_numeric(df[low_col], errors="coerce")
    high = pd.to_numeric(df[high_col], errors="coerce")

    support_1 = _to_float(low.tail(6).min()) if len(low.dropna()) >= 6 else _to_float(low.min())
    support_2 = _to_float(low.tail(12).min()) if len(low.dropna()) >= 12 else _to_float(low.min())
    resistance_1 = _to_float(high.tail(6).max()) if len(high.dropna()) >= 6 else _to_float(high.max())
    resistance_2 = (
        _to_float(high.tail(12).max()) if len(high.dropna()) >= 12 else _to_float(high.max())
    )
    return KeyLevels(
        support_1=support_1,
        support_2=support_2,
        resistance_1=resistance_1,
        resistance_2=resistance_2,
    )


def _build_features(df: pd.DataFrame, warnings: list[str]) -> tuple[dict, list[str]]:
    """Build deterministic features from indicator DataFrame."""
    if df.empty:
        raise TechnicalIndicatorError("Indicator DataFrame is empty")

    latest = df.iloc[-1]
    total_months = len(df)
    use_ma60 = (
        total_months >= TECH_LONG_TREND_MIN_MONTHS
        and _to_float(latest.get(_COL_SMA_TREND)) is not None
    )
    if not use_ma60:
        warnings.append(
            f"样本不足{TECH_LONG_TREND_MIN_MONTHS}个月，未使用MA{TECH_MA_TREND}长周期趋势判断"
        )

    trend_6m = _period_return_pct(df["close"], 6)
    trend_12m = _period_return_pct(df["close"], 12)
    ma_alignment = _judge_ma_alignment(latest, include_ma60=use_ma60)
    price_vs_ma20 = _judge_price_vs_ma20(latest)
    macd_status = _judge_macd(df)
    rsi_value, rsi_status = _judge_rsi(df, latest)
    kdj_status = _judge_kdj(df)
    boll_position, boll_width = _judge_boll(df, latest)
    recent_vs_avg, volume_price_relation = _judge_volume(df)
    key_levels = _calc_key_levels(df)

    features = {
        "trend_6m_pct": trend_6m,
        "trend_12m_pct": trend_12m,
        "trend_6m_text": _format_trend(6, trend_6m),
        "trend_12m_text": _format_trend(12, trend_12m),
        "ma_alignment": ma_alignment,
        "price_vs_ma20": price_vs_ma20,
        "macd_status": macd_status,
        "rsi_value": rsi_value,
        "rsi_status": rsi_status,
        "kdj_status": kdj_status,
        "boll_position": boll_position,
        "boll_width": boll_width,
        "recent_vs_avg": recent_vs_avg,
        "volume_price_relation": volume_price_relation,
        "support_1": key_levels.support_1,
        "support_2": key_levels.support_2,
        "resistance_1": key_levels.resistance_1,
        "resistance_2": key_levels.resistance_2,
        "use_ma60": use_ma60,
    }
    return features, warnings


def _build_rows_json(df: pd.DataFrame, lookback_months: int) -> str:
    """Serialize recent rows for LLM input with JSON-safe NaN/datetime handling."""
    columns = [
        "date",
        "close",
        "volume",
        _COL_SMA_SHORT,
        _COL_SMA_MID,
        _COL_SMA_LONG,
        _COL_SMA_TREND,
        _COL_RSI,
    ]
    columns.extend([col for col in df.columns if col.startswith("MACD_")][:1])
    columns.extend([col for col in df.columns if col.startswith("MACDh_")][:1])
    columns.extend([col for col in df.columns if col.startswith("MACDs_")][:1])
    columns.extend([col for col in df.columns if col.startswith("BBL_")][:1])
    columns.extend([col for col in df.columns if col.startswith("BBM_")][:1])
    columns.extend([col for col in df.columns if col.startswith("BBU_")][:1])
    columns.extend([col for col in df.columns if col.startswith("STOCHk_")][:1])
    columns.extend([col for col in df.columns if col.startswith("STOCHd_")][:1])

    existing_cols = [col for col in dict.fromkeys(columns) if col in df.columns]
    rows_df = df[existing_cols].tail(lookback_months).copy()
    return rows_df.to_json(
        orient="records",
        force_ascii=False,
        date_format="iso",
    )


def _build_prompt_message(
    symbol: str,
    name: str,
    data_start: str,
    data_end: str,
    total_months: int,
    features: dict,
    rows_json: str,
    lookback_months: int,
) -> str:
    features_json = json.dumps(features, ensure_ascii=False, indent=2)
    return (
        f"请基于以下月线技术数据输出结构化分析结果（JSON）。\n\n"
        f"股票：{symbol} {name}\n"
        f"数据区间：{data_start} ~ {data_end}\n"
        f"总月数：{total_months}\n\n"
        f"【确定性特征】\n{features_json}\n\n"
        f"【最近{lookback_months}个月关键指标明细】\n{rows_json}\n"
    )


def _build_meta(
    symbol: str,
    name: str,
    data_start: str | None,
    data_end: str | None,
    total_months: int,
    warnings: list[str],
) -> TechnicalMeta:
    return TechnicalMeta(
        symbol=symbol,
        name=name,
        analysis_time=datetime.now().isoformat(),
        data_start=data_start,
        data_end=data_end,
        total_months=total_months,
        data_quality_warnings=list(dict.fromkeys(warnings)),
    )


def _build_fallback_result(
    symbol: str,
    name: str,
    warnings: list[str],
    reason: str,
    *,
    data_start: str | None = None,
    data_end: str | None = None,
    total_months: int = 0,
    confidence: float = 0.2,
) -> TechnicalAnalysisResult:
    warning_list = [*warnings, reason]
    summary = f"技术分析降级结果：{reason}"
    if len(summary) > 1500:
        summary = summary[:1497] + "..."
    meta = _build_meta(
        symbol=symbol,
        name=name,
        data_start=data_start,
        data_end=data_end,
        total_months=total_months,
        warnings=warning_list,
    )
    return TechnicalAnalysisResult(
        meta=meta,
        score=5.0,
        signal="中性",
        confidence=confidence,
        trend_analysis=TrendAnalysis(
            ma_alignment="数据不足",
            price_vs_ma20="数据不足",
            trend_6m="数据不足",
            trend_12m="数据不足",
            trend_judgment="数据不足，无法给出趋势判断",
        ),
        momentum=MomentumAnalysis(
            macd_status="数据不足",
            rsi_value=None,
            rsi_status="数据不足",
            kdj_status="数据不足",
        ),
        volatility=VolatilityAnalysis(
            boll_position="数据不足",
            boll_width="数据不足",
        ),
        volume_analysis=VolumeAnalysis(
            recent_vs_avg="数据不足",
            volume_price_relation="数据不足",
        ),
        key_levels=KeyLevels(
            support_1=None,
            support_2=None,
            resistance_1=None,
            resistance_2=None,
        ),
        summary=summary,
    )


async def run_technical_analysis(symbol: str, name: str) -> TechnicalAnalysisResult:
    """Run module C workflow and return structured technical analysis result."""
    warnings: list[str] = []
    logger.info(f"Starting technical analysis for {symbol} {name}")

    try:
        raw_df = fetch_monthly_kline(symbol=symbol)
        kline_df = _normalize_kline_df(raw_df)
    except TechnicalDataError as e:
        logger.error(f"Technical data fetch/normalize failed: {e}")
        return _build_fallback_result(
            symbol=symbol,
            name=name,
            warnings=warnings,
            reason=str(e),
            confidence=0.2,
        )

    total_months = len(kline_df)
    data_start = kline_df["date"].iloc[0].date().isoformat()
    data_end = kline_df["date"].iloc[-1].date().isoformat()

    if total_months < TECH_MIN_MONTHS:
        reason = (
            f"样本不足：仅 {total_months} 个月，小于 TECH_MIN_MONTHS={TECH_MIN_MONTHS}"
        )
        logger.warning(reason)
        return _build_fallback_result(
            symbol=symbol,
            name=name,
            warnings=warnings,
            reason=reason,
            data_start=data_start,
            data_end=data_end,
            total_months=total_months,
            confidence=0.2,
        )

    try:
        feature_df = _compute_technical_indicators(kline_df)
        features, warnings = _build_features(feature_df, warnings)
        rows_json = _build_rows_json(feature_df, TECH_AGENT_LOOKBACK_MONTHS)
    except TechnicalIndicatorError as e:
        logger.error(f"Technical indicators failed: {e}")
        return _build_fallback_result(
            symbol=symbol,
            name=name,
            warnings=warnings,
            reason=str(e),
            data_start=data_start,
            data_end=data_end,
            total_months=total_months,
            confidence=0.2,
        )
    except Exception as e:
        logger.error(f"Feature extraction failed: {type(e).__name__}: {e}")
        return _build_fallback_result(
            symbol=symbol,
            name=name,
            warnings=warnings,
            reason=f"特征提取失败: {type(e).__name__}: {e}",
            data_start=data_start,
            data_end=data_end,
            total_months=total_months,
            confidence=0.2,
        )

    message = _build_prompt_message(
        symbol=symbol,
        name=name,
        data_start=data_start,
        data_end=data_end,
        total_months=total_months,
        features=features,
        rows_json=rows_json,
        lookback_months=TECH_AGENT_LOOKBACK_MONTHS,
    )

    openai_client = create_openai_client()
    technical_client = create_chat_client(openai_client, MODEL_TECHNICAL_AGENT)
    technical_agent = create_technical_agent(technical_client)

    max_attempts = max(1, TECH_OUTPUT_RETRIES + 1)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            llm_output = await call_agent_with_model(
                agent=technical_agent,
                message=message,
                model_cls=LLMTechnicalOutput,
            )
            # If successful, we build the final result and return immediately
            meta = _build_meta(
                symbol=symbol,
                name=name,
                data_start=data_start,
                data_end=data_end,
                total_months=total_months,
                warnings=warnings,
            )
            final_result = TechnicalAnalysisResult(meta=meta, **llm_output.model_dump())

            # Soft-degrade confidence when MA60 long-trend context is unavailable.
            if total_months < TECH_LONG_TREND_MIN_MONTHS:
                final_result = final_result.model_copy(
                    update={"confidence": min(final_result.confidence, 0.65)}
                )

            logger.info(
                f"Technical analysis completed for {symbol}: score={final_result.score}, "
                f"signal={final_result.signal}, confidence={final_result.confidence:.2f}"
            )
            return final_result

        except (AgentCallError, Exception) as e:
            last_error = e
            if attempt < max_attempts:
                logger.warning(
                    f"Technical agent attempt {attempt}/{max_attempts} failed: {e}. Retrying..."
                )
                continue
            logger.error(f"Technical agent failed after {max_attempts} attempts: {e}")

    # If we reach here, all attempts failed
    return _build_fallback_result(
        symbol=symbol,
        name=name,
        warnings=warnings,
        reason=f"LLM 推理失败 (已重试 {max_attempts} 次): {last_error}",
        data_start=data_start,
        data_end=data_end,
        total_months=total_months,
        confidence=0.35,
    )


def dump_technical_result_json(result: TechnicalAnalysisResult) -> str:
    """Serialize final result with meta first for human readability."""
    output_dict = {
        "meta": result.meta.model_dump(),
        **result.model_dump(exclude={"meta"}),
    }
    return json.dumps(output_dict, ensure_ascii=False, indent=2)

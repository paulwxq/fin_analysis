"""Pydantic models for module C technical analysis."""

from typing import Literal

from pydantic import BaseModel, Field


class TechnicalMeta(BaseModel):
    """Metadata produced by code (not by LLM)."""

    symbol: str
    name: str
    analysis_time: str
    data_start: str | None = None
    data_end: str | None = None
    total_months: int = 0
    data_quality_warnings: list[str] = Field(default_factory=list)


class TrendAnalysis(BaseModel):
    ma_alignment: str = ""
    price_vs_ma20: str = ""
    trend_6m: str = ""
    trend_12m: str = ""
    trend_judgment: str = ""


class MomentumAnalysis(BaseModel):
    macd_status: str = ""
    rsi_value: float | None = None
    rsi_status: str = ""
    kdj_status: str = ""


class VolatilityAnalysis(BaseModel):
    boll_position: str = ""
    boll_width: str = ""


class VolumeAnalysis(BaseModel):
    recent_vs_avg: str = ""
    volume_price_relation: str = ""


class KeyLevels(BaseModel):
    support_1: float | None = None
    support_2: float | None = None
    resistance_1: float | None = None
    resistance_2: float | None = None


class LLMTechnicalOutput(BaseModel):
    """LLM output schema (without meta)."""

    score: float = Field(ge=0, le=10)
    signal: Literal["强烈看多", "看多", "中性", "看空", "强烈看空"]
    confidence: float = Field(ge=0, le=1)
    trend_analysis: TrendAnalysis
    momentum: MomentumAnalysis
    volatility: VolatilityAnalysis
    volume_analysis: VolumeAnalysis
    key_levels: KeyLevels
    summary: str = Field(max_length=1500)


class TechnicalAnalysisResult(LLMTechnicalOutput):
    """Final module C output with meta injected by code."""

    meta: TechnicalMeta

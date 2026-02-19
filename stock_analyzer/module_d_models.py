"""Pydantic models for module D chief analyst output."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class FinalMeta(BaseModel):
    """Metadata injected by code after LLM output is validated."""

    symbol: str
    name: str
    analysis_time: str


class DimensionBrief(BaseModel):
    score: float = Field(ge=0, le=10)
    brief: str = Field(max_length=800)


class DimensionScores(BaseModel):
    technical: DimensionBrief
    fundamental: DimensionBrief
    valuation: DimensionBrief
    capital_flow: DimensionBrief
    sentiment: DimensionBrief


class TimeframeAdvice(BaseModel):
    timeframe: Literal["1个月", "6个月", "1年"]
    recommendation: Literal["强烈买入", "买入", "持有", "卖出", "强烈卖出"]
    reasoning: str = Field(max_length=500)

    @field_validator("timeframe", mode="before")
    @classmethod
    def normalize_timeframe(cls, v: str) -> str:
        """Strip spaces so '1 个月' → '1个月' (some models insert spaces)."""
        if isinstance(v, str):
            return re.sub(r"\s+", "", v)
        return v


class LLMChiefOutput(BaseModel):
    """LLM output schema (without meta)."""

    dimension_scores: DimensionScores
    overall_score: float = Field(ge=0, le=10)
    overall_confidence: Literal["高", "中", "低"]
    veto_triggered: bool = False
    veto_reason: str = ""
    score_cap: float | None = Field(default=None, ge=0, le=10)
    advice: list[TimeframeAdvice] = Field(min_length=3, max_length=3)
    report: str = Field(max_length=2000)
    key_catalysts: list[str] = Field(min_length=1, max_length=3)
    primary_risks: list[str] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_timeframes(self) -> "LLMChiefOutput":
        expected = {"1个月", "6个月", "1年"}
        actual = {item.timeframe for item in self.advice}
        if actual != expected:
            raise ValueError(
                "advice.timeframe must include exactly these values: 1个月, 6个月, 1年"
            )
        return self


class FinalReport(LLMChiefOutput):
    """Final module D output with meta injected by code."""

    meta: FinalMeta

"""Pydantic models for Step 1 and Step 2 outputs."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, List, Literal, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import config


class TrendEnum(str, Enum):
    UP = "上升"
    DOWN = "下降"
    OSCILLATE = "震荡"


class BuySuggestionEnum(str, Enum):
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    HOLD = "持有"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"


class StrictBaseModel(BaseModel):
    """严格的基础模型，但允许忽略 LLM 输出的额外字段以提高容错性。

    核心字段的校验依然严格（必需字段、类型、约束），只是忽略非预期的额外字段，
    避免因 LLM 输出 reasoning/thoughts 等字段导致不必要的重试。
    """
    model_config = ConfigDict(extra="ignore")


class NewsData(StrictBaseModel):
    data_type: Literal["news"] = Field(..., description="数据类型标识")
    stock_code: str
    stock_name: str = Field(..., description="股票名称")
    # In Pydantic V2, max_length on List means max items.
    positive_news: Annotated[
        List[str],
        Field(..., max_length=config.NEWS_LIMIT_POS, description=f"正面新闻列表 (最多{config.NEWS_LIMIT_POS}项)"),
    ]
    negative_news: Annotated[
        List[str],
        Field(..., max_length=config.NEWS_LIMIT_NEG, description=f"负面新闻列表 (最多{config.NEWS_LIMIT_NEG}项)"),
    ]
    news_summary: str = Field(..., min_length=300, max_length=800, description="综合摘要 (需深度分析)")
    sentiment_score: float = Field(..., ge=-1.0, le=1.0, description="情绪得分 -1~1")

    @field_validator("positive_news", "negative_news")
    @classmethod
    def check_item_content_length(cls, value: List[str]) -> List[str]:
        limit = config.NEWS_ITEM_MAX_CHARS
        for news in value:
            if len(news) > limit:
                raise ValueError(f"单条新闻摘要长度超过{limit}字符")
        return value


class SectorData(StrictBaseModel):
    data_type: Literal["sector"] = Field(..., description="数据类型标识")
    stock_code: str
    stock_name: str = Field(..., description="股票名称")
    sector_name: str = Field(..., description="板块名称")
    heat_index: float = Field(..., ge=0, le=100, description="热度指数 0-100")
    trend: TrendEnum = Field(..., description="趋势方向")
    capital_flow: str = Field(..., description="资金流向描述")

    @field_validator("trend", mode="before")
    @classmethod
    def map_trend_text(cls, value: Any) -> str:
        """映射英文趋势到中文枚举值。"""
        if not isinstance(value, str):
            return value
        val_map = {
            "neutral": "震荡",
            "oscillate": "震荡",
            "up": "上升",
            "bullish": "上升",
            "down": "下降",
            "bearish": "下降"
        }
        low_val = value.lower().strip()
        return val_map.get(low_val, value)

    @field_validator("capital_flow", mode="before")
    @classmethod
    def ensure_string(cls, value: Any) -> str:
        """确保字段为字符串，防止模型输出数字。"""
        if value is None:
            return "暂无数据"
        return str(value)


class TechnicalIndicators(StrictBaseModel):
    MACD: float = Field(..., description="MACD指标值")
    RSI: float = Field(..., description="RSI指标值")
    KDJ_K: float = Field(..., description="KDJ_K指标值")


class KLineData(StrictBaseModel):
    data_type: Literal["kline"] = Field(..., description="数据类型标识")
    stock_code: str
    technical_indicators: TechnicalIndicators
    support_level: float
    resistance_level: float = Field(..., description="阻力位价格")
    trend_analysis: str = Field(..., description="趋势分析文本")
    buy_suggestion: BuySuggestionEnum = Field(..., description="买入建议枚举")


class Step1Output(StrictBaseModel):
    timestamp: str = Field(..., description="ISO 8601 格式的时间戳 (UTC)")
    news: NewsData = Field(..., description="新闻收集单元结果")
    sector: SectorData = Field(..., description="板块分析单元结果")
    kline: KLineData = Field(..., description="K线分析单元结果")


class HoldRecommendation(StrictBaseModel):
    data_type: Literal["hold_recommendation"] = "hold_recommendation"
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="生成时间 (UTC ISO 8601)"
    )
    stock_code: str = Field(..., description="股票代码")
    stock_name: str = Field(..., description="股票名称（允许空字符串，不影响后续流程）")
    hold_score: float = Field(..., ge=0, le=100, description="推荐持有评分 (0-100)")
    summary_reason: str = Field(
        ...,
        min_length=config.SUMMARY_REASON_MIN_CHARS,
        max_length=config.SUMMARY_REASON_MAX_CHARS,
        description="推荐原因摘要"
    )


class ReviewResult(StrictBaseModel):
    stock_code: str
    passed: bool = Field(..., description="是否通过质检")
    reason: str = Field(..., description="拒绝理由或通过说明")


class CheckerResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    passed: bool
    reason: str

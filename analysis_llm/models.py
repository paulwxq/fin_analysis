"""Pydantic models for Step 1 outputs."""
from __future__ import annotations

from enum import Enum
from typing import Annotated, List, Literal

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
    model_config = ConfigDict(extra="forbid")


class NewsData(StrictBaseModel):
    data_type: Literal["news"] = Field(..., description="数据类型标识")
    stock_code: str
    # In Pydantic V2, max_length on List means max items.
    positive_news: Annotated[
        List[str],
        Field(..., max_length=config.NEWS_LIMIT_POS, description=f"正面新闻列表 (最多{config.NEWS_LIMIT_POS}项)"),
    ]
    negative_news: Annotated[
        List[str],
        Field(..., max_length=config.NEWS_LIMIT_NEG, description=f"负面新闻列表 (最多{config.NEWS_LIMIT_NEG}项)"),
    ]
    news_summary: str = Field(..., description="综合摘要")
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
    sector_name: str = Field(..., description="板块名称")
    heat_index: float = Field(..., ge=0, le=100, description="热度指数 0-100")
    trend: TrendEnum = Field(..., description="趋势方向")
    capital_flow: str = Field(..., description="资金流向描述")


class TechnicalIndicators(StrictBaseModel):
    MACD: float = Field(..., description="MACD指标值")
    RSI: float = Field(..., description="RSI指标值")
    KDJ_K: float = Field(..., description="KDJ_K指标值")


class KLineData(StrictBaseModel):
    data_type: Literal["kline"] = Field(..., description="数据类型标识")
    stock_code: str
    technical_indicators: TechnicalIndicators = Field(..., description="技术指标集合")
    support_level: float = Field(..., description="支撑位价格")
    resistance_level: float = Field(..., description="阻力位价格")
    trend_analysis: str = Field(..., description="趋势分析文本")
    buy_suggestion: BuySuggestionEnum = Field(..., description="买入建议枚举")


class Step1Output(StrictBaseModel):
    timestamp: str = Field(..., description="ISO 8601 格式的时间戳 (UTC)")
    news: NewsData = Field(..., description="新闻收集单元结果")
    sector: SectorData = Field(..., description="板块分析单元结果")
    kline: KLineData = Field(..., description="K线分析单元结果")


class CheckerResult(StrictBaseModel):
    passed: bool
    reason: str

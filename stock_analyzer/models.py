"""Pydantic models for module B."""

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field


class SerpQuery(BaseModel):
    """A single LLM-generated query."""

    query: str = Field(description="Search engine query")
    research_goal: str = Field(description="Expected research goal for this query")


class SerpQueryList(BaseModel):
    """Output of generate_serp_queries."""

    queries: list[SerpQuery] = Field(description="Generated query list")


class ProcessedResult(BaseModel):
    """Output of process_serp_result."""

    learnings: list[str] = Field(
        description="Extracted information-dense learnings with entities, numbers and dates"
    )
    follow_up_questions: list[str] = Field(description="Follow-up directions")


class ResearchResult(BaseModel):
    """Final deep research result of one topic."""

    learnings: list[str] = Field(default_factory=list)
    visited_urls: list[str] = Field(default_factory=list)


class NewsItem(BaseModel):
    """A single news item."""

    title: str = Field(description="News title")
    summary: str = Field(description="News summary")
    source: str = Field(description="Media/source name")
    date: str = Field(description="Date in YYYY-MM-DD")
    importance: Literal["高", "中", "低"] = Field(description="Importance")


class NewsSummary(BaseModel):
    """News split by sentiment."""

    positive: list[NewsItem] = Field(default_factory=list)
    negative: list[NewsItem] = Field(default_factory=list)
    neutral: list[NewsItem] = Field(default_factory=list)


class CompetitiveAdvantage(BaseModel):
    """Company competitive advantage."""

    description: str = Field(max_length=500)
    moat_type: str = Field(description="Moat type")
    market_position: str = Field(description="Market position")


class IndustryOutlook(BaseModel):
    """Industry outlook section."""

    industry: str
    outlook: str
    key_drivers: list[str]
    key_risks: list[str]


class RiskEvents(BaseModel):
    """Risk event section."""

    regulatory: str
    litigation: str
    management: str
    other: str = ""


class AnalystReport(BaseModel):
    """A single broker report."""

    broker: str = Field(validation_alias=AliasChoices("broker", "institution"))
    rating: str
    target_price: float | None = None
    date: str


class AnalystOpinions(BaseModel):
    """Analyst opinions summary."""

    buy_count: int = 0
    hold_count: int = 0
    sell_count: int = 0
    average_target_price: float | None = None
    recent_reports: list[AnalystReport] = Field(default_factory=list)


class SearchConfig(BaseModel):
    """Structured search config in meta."""

    topics_count: int
    breadth: int
    depth: int
    successful_topics: int


class SearchMeta(BaseModel):
    """Search metadata."""

    symbol: str
    name: str
    search_time: str
    search_config: SearchConfig
    total_learnings: int
    total_sources_consulted: int
    raw_learnings: list[str] | None = Field(
        default=None,
        description="Only filled when fallback report is used",
    )


class WebResearchResult(BaseModel):
    """Final module B output."""

    meta: SearchMeta
    news_summary: NewsSummary
    competitive_advantage: CompetitiveAdvantage
    industry_outlook: IndustryOutlook
    risk_events: RiskEvents
    analyst_opinions: AnalystOpinions
    search_confidence: Literal["高", "中", "低"]

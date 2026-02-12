"""Custom exceptions for module B deep research."""


class TavilySearchError(Exception):
    """Tavily search call failed."""

    def __init__(self, query: str, cause: Exception, attempts: int = 1):
        self.query = query
        self.cause = cause
        self.attempts = attempts
        super().__init__(
            f"Tavily search failed for '{query}' after {attempts} attempts: {cause}"
        )


class AgentCallError(Exception):
    """Agent call failed (including JSON parse and model validation)."""

    def __init__(self, agent_name: str, cause: Exception):
        self.agent_name = agent_name
        self.cause = cause
        super().__init__(f"Agent '{agent_name}' call failed: {cause}")


class ReportGenerationError(Exception):
    """Final report generation failed."""

    def __init__(self, symbol: str, cause: Exception, learnings_count: int):
        self.symbol = symbol
        self.cause = cause
        self.learnings_count = learnings_count
        super().__init__(
            f"Failed to generate report for {symbol} with {learnings_count} learnings: {cause}"
        )


class WebResearchError(Exception):
    """Top-level web research workflow failed."""


# ============================================================
# Module A: AKShare data collection exceptions
# ============================================================


class AKShareError(Exception):
    """AKShare data collection base exception."""


class AKShareAPIError(AKShareError):
    """Single AKShare API call failed."""

    def __init__(self, topic: str, func_name: str, cause: Exception):
        self.topic = topic
        self.func_name = func_name
        self.cause = cause
        super().__init__(
            f"AKShare API failed for topic '{topic}' (func: {func_name}): {cause}"
        )


class AKShareDataEmptyError(AKShareError):
    """AKShare API returned empty data."""

    def __init__(self, topic: str, func_name: str):
        self.topic = topic
        self.func_name = func_name
        super().__init__(
            f"AKShare returned empty data for topic '{topic}' (func: {func_name})"
        )


class AKShareCollectionError(AKShareError):
    """Module A top-level collection aborted."""

    def __init__(self, symbol: str, errors: list[str]):
        self.symbol = symbol
        self.errors = errors
        super().__init__(f"AKShare collection aborted for {symbol}: {len(errors)} errors")


# ============================================================
# Module C: technical analysis exceptions
# ============================================================


class TechnicalDataError(Exception):
    """Monthly k-line data unavailable or insufficient."""


class TechnicalIndicatorError(Exception):
    """Technical indicator computation failed."""


class TechnicalAnalysisError(Exception):
    """Top-level technical analysis workflow failed."""


# ============================================================
# Module D: chief analyst exceptions
# ============================================================


class ChiefInputError(Exception):
    """Module D input is missing or invalid."""


class ChiefAnalysisError(Exception):
    """Module D chief analysis failed after retries."""

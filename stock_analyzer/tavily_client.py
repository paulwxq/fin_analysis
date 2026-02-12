"""Tavily search wrapper with timeout and retry."""

import asyncio

import httpx
from tavily import (
    AsyncTavilyClient,
    BadRequestError,
    InvalidAPIKeyError,
    MissingAPIKeyError,
    UsageLimitExceededError,
)

try:
    # tavily-python==0.7.21 does not re-export ForbiddenError at top-level.
    from tavily import ForbiddenError
except ImportError:  # pragma: no cover - version-specific import fallback
    from tavily.errors import ForbiddenError

from stock_analyzer.config import TAVILY_API_KEY, TAVILY_MAX_RESULTS, TAVILY_TIMEOUT
from stock_analyzer.exceptions import TavilySearchError
from stock_analyzer.logger import logger

RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    OSError,
    httpx.ConnectError,
    httpx.NetworkError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
)

NON_RETRYABLE_EXCEPTIONS = (
    httpx.HTTPStatusError,
    InvalidAPIKeyError,
    MissingAPIKeyError,
    BadRequestError,
    ForbiddenError,
    UsageLimitExceededError,
)

_tavily_client: AsyncTavilyClient | None = None


def get_tavily_client() -> AsyncTavilyClient:
    """Return singleton Tavily client."""
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
    return _tavily_client


async def tavily_search(
    query: str,
    max_results: int = TAVILY_MAX_RESULTS,
    max_retries: int = 1,
) -> list[dict]:
    """Search via Tavily and retry once on transient failures."""
    client = get_tavily_client()
    last_error: Exception | None = None
    q = query[:50] + ("..." if len(query) > 50 else "")

    for attempt in range(max_retries + 1):
        try:
            response = await asyncio.wait_for(
                client.search(
                    query=query,
                    max_results=max_results,
                    search_depth="advanced",
                    include_answer=False,
                    include_raw_content=False,
                ),
                timeout=TAVILY_TIMEOUT,
            )
            results = response.get("results", [])
            if attempt > 0:
                logger.info(
                    f"Tavily search '{q}' succeeded on retry {attempt}, returned {len(results)} results"
                )
            else:
                logger.info(
                    f"Tavily search '{q}' returned {len(results)} results"
                )
            return results
        except asyncio.TimeoutError as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Tavily search '{q}' timeout (attempt {attempt + 1}/{max_retries + 1}), retrying..."
                )
                await asyncio.sleep(2)
            else:
                logger.error(
                    f"Tavily search '{q}' timeout after {max_retries + 1} attempts"
                )
        except RETRYABLE_EXCEPTIONS as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Tavily search '{q}' network error: {type(e).__name__} "
                    f"(attempt {attempt + 1}/{max_retries + 1}), retrying..."
                )
                await asyncio.sleep(2)
            else:
                logger.error(
                    f"Tavily search '{q}' failed after {max_retries + 1} attempts: {e}"
                )
        except NON_RETRYABLE_EXCEPTIONS as e:
            logger.error(
                f"Tavily search '{q}' non-retryable API/config error: {type(e).__name__}: {e}"
            )
            raise TavilySearchError(query=query, attempts=attempt + 1, cause=e) from e
        except Exception as e:
            logger.error(
                f"Tavily search '{q}' unexpected error: {type(e).__name__}: {e}"
            )
            raise TavilySearchError(query=query, attempts=attempt + 1, cause=e) from e

    assert last_error is not None
    raise TavilySearchError(query=query, cause=last_error, attempts=max_retries + 1)

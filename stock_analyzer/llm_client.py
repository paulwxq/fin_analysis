"""LLM client factory helpers."""

from agent_framework.openai import OpenAIChatClient
from openai import AsyncOpenAI

from stock_analyzer.config import API_TIMEOUT, DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL


def create_openai_client() -> AsyncOpenAI:
    """Create shared AsyncOpenAI client using DashScope-compatible endpoint."""
    return AsyncOpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url=DASHSCOPE_BASE_URL,
        timeout=API_TIMEOUT,
    )


def create_chat_client(openai_client: AsyncOpenAI, model_id: str) -> OpenAIChatClient:
    """Create MAF OpenAIChatClient."""
    return OpenAIChatClient(
        model_id=model_id,
        async_client=openai_client,
    )

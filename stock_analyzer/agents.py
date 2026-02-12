"""ChatAgent factories for module B."""

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

from stock_analyzer.prompts import (
    EXTRACT_AGENT_SYSTEM_PROMPT,
    QUERY_AGENT_SYSTEM_PROMPT,
    REPORT_AGENT_SYSTEM_PROMPT,
    TECHNICAL_AGENT_SYSTEM_PROMPT,
)


def create_query_agent(chat_client: OpenAIChatClient) -> ChatAgent:
    """Create query generation agent."""
    return ChatAgent(
        chat_client=chat_client,
        name="query_generator",
        instructions=QUERY_AGENT_SYSTEM_PROMPT,
        default_options={
            "temperature": 0.5,
            "response_format": {"type": "json_object"},
        },
    )


def create_extract_agent(chat_client: OpenAIChatClient) -> ChatAgent:
    """Create knowledge extraction agent."""
    return ChatAgent(
        chat_client=chat_client,
        name="knowledge_extractor",
        instructions=EXTRACT_AGENT_SYSTEM_PROMPT,
        default_options={
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
    )


def create_report_agent(chat_client: OpenAIChatClient) -> ChatAgent:
    """Create final report generation agent."""
    return ChatAgent(
        chat_client=chat_client,
        name="report_generator",
        instructions=REPORT_AGENT_SYSTEM_PROMPT,
        default_options={
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        },
    )


def create_technical_agent(chat_client: OpenAIChatClient) -> ChatAgent:
    """Create technical analysis agent for module C."""
    return ChatAgent(
        chat_client=chat_client,
        name="technical_analyst",
        instructions=TECHNICAL_AGENT_SYSTEM_PROMPT,
        default_options={
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
    )

"""Helpers for agent invocation and structured parsing."""

from itertools import chain
import json
import re
from typing import TypeVar

from agent_framework import ChatAgent
from pydantic import BaseModel, ValidationError

from stock_analyzer.exceptions import AgentCallError
from stock_analyzer.logger import logger

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9_-]*)\s*\n(?P<body>[\s\S]*?)```",
    re.MULTILINE,
)


def extract_json_str(text: str) -> str:
    """Extract a valid JSON string from model output."""
    stripped = text.strip()

    try:
        json.loads(stripped)
        return stripped
    except Exception:
        pass

    blocks = list(_FENCE_RE.finditer(stripped))
    if not blocks:
        raise ValueError("No valid JSON found in model output")

    json_blocks: list[str] = []
    plain_blocks: list[str] = []
    for match in blocks:
        lang = (match.group("lang") or "").strip().lower()
        body = match.group("body").strip()
        if lang == "json":
            json_blocks.append(body)
        elif lang == "":
            plain_blocks.append(body)

    for candidate in chain(reversed(json_blocks), reversed(plain_blocks)):
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            continue

    raise ValueError("No valid JSON found in model output")


async def call_agent_with_model(
    agent: ChatAgent,
    message: str,
    model_cls: type[T],
) -> T:
    """Run an agent and parse result into a pydantic model."""
    thread = agent.get_new_thread()
    try:
        response = await agent.run(message, thread=thread)
        raw_text = response.text
        json_str = extract_json_str(raw_text)
        return model_cls.model_validate_json(json_str)
    except ValidationError as e:
        logger.error(
            f"Agent '{agent.name}' validation failed: {e.error_count()} errors; "
            f"first={e.errors()[0] if e.errors() else 'unknown'}"
        )
        raise AgentCallError(agent_name=agent.name, cause=e) from e
    except Exception as e:
        logger.error(f"Agent '{agent.name}' call failed: {e}")
        raise AgentCallError(agent_name=agent.name, cause=e) from e

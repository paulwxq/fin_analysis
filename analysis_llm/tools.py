"""External tools for Step 1 agents."""
from __future__ import annotations

import os
from typing import Annotated

from agent_framework import tool


@tool(name="tavily_search", description="使用 Tavily API 搜索财经新闻", approval_mode="never_require")
async def tavily_search(query: Annotated[str, "搜索关键词"], max_results: Annotated[int, "返回条数"] = 10) -> str:
    """Search market news via Tavily API and return raw JSON string."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("未配置 TAVILY_API_KEY 环境变量")

    try:
        from tavily import TavilyClient
    except Exception as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("tavily 库未安装，请先安装 tavily") from exc

    client = TavilyClient(api_key=api_key)
    response = client.search(query, search_depth="advanced", max_results=max_results)
    return str(response)

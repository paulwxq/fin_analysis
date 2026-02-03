"""External tools for Step 1 agents."""
from __future__ import annotations

import json
import os
from typing import Annotated, Any, Dict, List

import httpx
from agent_framework import tool

from . import config


async def _tavily_search(query: str, max_results: int) -> List[Dict[str, Any]]:
    """Internal implementation for Tavily search."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("未配置 TAVILY_API_KEY 环境变量")

    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise RuntimeError("tavily 库未安装，请先安装 tavily") from exc

    client = TavilyClient(api_key=api_key)
    # Tavily SDK 可能是同步的，但在 async 函数中调用虽然不报错，
    # 最好是用 asyncio.to_thread 包装，或者如果 Tavily 有 async 方法。
    # 这里维持原样，假设并发度不高或 SDK 足够快。
    response = client.search(query, search_depth="advanced", max_results=max_results)
    
    cleaned_results = []
    if "results" in response:
        for r in response["results"]:
            cleaned_results.append({
                "title": r.get("title"),
                "url": r.get("url"),
                "content": r.get("content")
            })
    return cleaned_results


async def _serper_search(query: str, max_results: int) -> List[Dict[str, Any]]:
    """Internal implementation for Serper.dev search."""
    api_key = config.SERPER_API_KEY
    if not api_key:
        raise ValueError("未配置 SERPER_API_KEY 环境变量")

    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": max_results, "hl": "zh-cn", "gl": "cn"})
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, data=payload, timeout=30.0)
        response.raise_for_status()
        data = response.json()

    cleaned_results = []
    # Serper 返回 organic 列表
    if "organic" in data:
        for r in data["organic"]:
            cleaned_results.append({
                "title": r.get("title"),
                "url": r.get("link"),
                "content": r.get("snippet")
            })
    
    # 也可以包含 top stories 或 news
    if "news" in data:
        for r in data["news"]:
             cleaned_results.append({
                "title": r.get("title"),
                "url": r.get("link"),
                "content": r.get("snippet")
            })
            
    # 截取 max_results
    return cleaned_results[:max_results]


@tool(name="web_search", description="使用搜索引擎查询财经新闻和资料", approval_mode="never_require")
async def web_search(query: Annotated[str, "搜索关键词"], max_results: Annotated[int, "返回条数"] = 10) -> str:
    """Unified web search tool supporting multiple providers."""
    provider = config.SEARCH_PROVIDER.lower()
    
    if provider == "serper":
        results = await _serper_search(query, max_results)
    else:
        # Default to Tavily
        results = await _tavily_search(query, max_results)
        
    return json.dumps(results, ensure_ascii=False)
"""External tools for Step 1 agents."""
from __future__ import annotations

import atexit
import json
import re
import logging
from typing import Annotated, Any, Dict, List, Optional

import httpx
from agent_framework import tool

from . import config

logger = logging.getLogger("analysis_llm")

# 模块级单例 HTTP 客户端，用于复用连接池
_http_client: Optional[httpx.AsyncClient] = None


def _cleanup_http_client():
    """进程退出时自动清理 HTTP 客户端（atexit 回调）。"""
    global _http_client
    if _http_client is not None:
        try:
            # atexit 回调是同步的，需要安全处理异步关闭
            import asyncio
            try:
                # 尝试在现有事件循环中关闭
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.run_until_complete(_http_client.aclose())
            except RuntimeError:
                # 如果事件循环已关闭，创建新的临时循环
                asyncio.run(_http_client.aclose())
            logger.debug("全局 HTTP 客户端已关闭")
        except Exception as e:
            # 静默失败，避免影响程序退出
            logger.debug("关闭 HTTP 客户端时出错（已忽略）: %s", e)
        finally:
            _http_client = None


def _get_http_client() -> httpx.AsyncClient:
    """获取全局 HTTP 客户端（延迟初始化，复用连接池）。"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
        logger.debug("初始化全局 HTTP 客户端（连接池：max_keepalive=10, max_connections=20）")
    return _http_client


# 注册进程退出时的清理函数
atexit.register(_cleanup_http_client)

async def _tavily_search(query: str, max_results: int) -> List[Dict[str, Any]]:
    """Internal implementation for provider search."""
    api_key = config.TAVILY_API_KEY
    if not api_key:
        raise ValueError("未配置 TAVILY_API_KEY 环境变量")

    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise RuntimeError("tavily 库未安装，请先安装 tavily") from exc

    client = TavilyClient(api_key=api_key)
    # Tavily SDK 是同步的，在 async 函数中应使用 asyncio.to_thread 运行
    # 以防止阻塞主事件循环，确保多个 Agent 能够真正并发运行
    import asyncio
    response = await asyncio.to_thread(
        client.search, 
        query, 
        search_depth="advanced", 
        max_results=max_results
    )
    
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

    client = _get_http_client()
    response = await client.post(url, headers=headers, data=payload)
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
            
    return cleaned_results[:max_results]


@tool(name="web_search", description="使用搜索引擎查询财经新闻和资料", approval_mode="never_require")
async def web_search(query: Annotated[str, "搜索关键词"], max_results: Annotated[int, "返回条数"] = 10) -> str:
    """Unified web search tool supporting multiple providers with auto-fallback."""
    provider = config.SEARCH_PROVIDER.lower()

    async def _execute_search(q: str, preferred_provider: str):
        """执行搜索，支持 provider 回退"""
        # 尝试首选 provider
        try:
            if preferred_provider == "serper":
                return await _serper_search(q, max_results)
            else:  # tavily
                return await _tavily_search(q, max_results)
        except (ValueError, RuntimeError, ImportError) as exc:
            # API key 缺失或包未安装，尝试回退到备用 provider
            logger.warning(
                "搜索服务 %s 不可用 (%s)，尝试回退到备用服务",
                preferred_provider, str(exc)
            )

            # 确定备用 provider
            fallback_provider = "serper" if preferred_provider == "tavily" else "tavily"

            try:
                if fallback_provider == "serper":
                    logger.info("回退使用 Serper 搜索")
                    return await _serper_search(q, max_results)
                else:
                    logger.info("回退使用 Tavily 搜索")
                    return await _tavily_search(q, max_results)
            except Exception as fallback_exc:
                # 两个 provider 都失败
                logger.error(
                    "所有搜索服务都不可用。主服务 %s: %s; 备用服务 %s: %s",
                    preferred_provider, str(exc),
                    fallback_provider, str(fallback_exc)
                )
                raise RuntimeError(
                    f"搜索功能不可用：{preferred_provider} 和 {fallback_provider} 都失败。"
                    "请检查环境变量 SERPER_API_KEY 或 TAVILY_API_KEY 是否配置正确。"
                ) from exc

    # 1. 第一次搜索（使用配置的 provider，支持自动回退）
    results = await _execute_search(query, provider)
    
    # 2. 如果结果为空，尝试提取股票代码进行降级搜索
    if not results:
        # 尝试提取 A股代码 (6位数字.后缀)
        match = re.search(r"(\d{6}\.(?:SH|SZ|BJ))", query, re.IGNORECASE)
        if match:
            stock_code = match.group(1).upper()
            fallback_query = f"{stock_code} 最新新闻"
            logger.debug("Search fallback triggered for %s", fallback_query)
            results = await _execute_search(fallback_query, provider)
    
    return json.dumps(results, ensure_ascii=False)
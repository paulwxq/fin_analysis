"""Core deep research recursion and report generation."""

import asyncio
import json

from agent_framework import ChatAgent

from stock_analyzer.exceptions import AgentCallError, ReportGenerationError, TavilySearchError
from stock_analyzer.llm_helpers import _run_agent_stream, call_agent_with_model, extract_json_str
from stock_analyzer.logger import logger
from stock_analyzer.models import ProcessedResult, ResearchResult, SerpQuery, SerpQueryList
from stock_analyzer.tavily_client import tavily_search


async def generate_serp_queries(
    query_agent: ChatAgent,
    query: str,
    num_queries: int,
    learnings: list[str],
) -> list[SerpQuery]:
    """Generate search queries for a topic."""
    user_message = f"请为以下研究主题生成 {num_queries} 个搜索查询。\n\n"
    user_message += f"<topic>\n{query}\n</topic>\n"

    if learnings:
        user_message += (
            "\n以下是前几轮研究中已获得的知识点，请据此生成更有针对性的查询，避免搜索已知信息：\n"
            "<learnings>\n"
        )
        for learning in learnings:
            user_message += f"- {learning}\n"
        user_message += "</learnings>\n"

    logger.debug(f"[Module B] query_agent prompt ({len(user_message)} chars):\n{user_message}")

    result = await call_agent_with_model(
        agent=query_agent,
        message=user_message,
        model_cls=SerpQueryList,
    )
    return result.queries[:num_queries]


async def process_serp_result(
    extract_agent: ChatAgent,
    query: str,
    search_results: list[dict],
) -> ProcessedResult:
    """Extract learnings and follow-up questions from search results."""
    if not search_results:
        return ProcessedResult(learnings=[], follow_up_questions=[])

    contents_parts: list[str] = []
    for row in search_results:
        content = row.get("content", "")
        if not content:
            continue
        title = row.get("title", "")
        url = row.get("url", "")
        contents_parts.append(
            f'<source title="{title}" url="{url}">\n{content}\n</source>'
        )

    if not contents_parts:
        return ProcessedResult(learnings=[], follow_up_questions=[])

    contents_text = "\n\n".join(contents_parts)
    user_message = (
        f"以下是针对查询 <query>{query}</query> 的搜索结果。\n"
        "请从中提取关键知识点和值得追问的方向。\n\n"
        f"<search_results>\n{contents_text}\n</search_results>"
    )

    logger.debug(f"[Module B] extract_agent prompt ({len(user_message)} chars):\n{user_message}")

    return await call_agent_with_model(
        agent=extract_agent,
        message=user_message,
        model_cls=ProcessedResult,
    )


async def deep_research(
    query_agent: ChatAgent,
    extract_agent: ChatAgent,
    query: str,
    breadth: int,
    depth: int,
    learnings: list[str] | None = None,
    visited_urls: list[str] | None = None,
) -> ResearchResult:
    """Run recursive deep research for one topic."""
    if learnings is None:
        learnings = []
    if visited_urls is None:
        visited_urls = []

    if depth == 0:
        return ResearchResult(learnings=learnings, visited_urls=visited_urls)

    query_preview = query[:80] + ("..." if len(query) > 80 else "")
    logger.info(
        f"deep_research: depth={depth}, breadth={breadth}, existing_learnings={len(learnings)}, query='{query_preview}'"
    )

    try:
        serp_queries = await generate_serp_queries(
            query_agent=query_agent,
            query=query,
            num_queries=breadth,
            learnings=learnings,
        )
    except AgentCallError:
        logger.warning("Failed to generate SERP queries, returning current learnings")
        return ResearchResult(learnings=learnings, visited_urls=visited_urls)

    all_learnings = list(learnings)
    all_urls = list(visited_urls)

    async def process_single_query(serp_query: SerpQuery) -> ResearchResult:
        branch_learnings = list(all_learnings)
        branch_urls = list(all_urls)

        try:
            search_results = await tavily_search(serp_query.query)
        except TavilySearchError:
            logger.warning(f"Tavily search failed for '{serp_query.query}', skipping")
            return ResearchResult(learnings=branch_learnings, visited_urls=branch_urls)

        for row in search_results:
            url = row.get("url", "")
            if url:
                branch_urls.append(url)

        try:
            processed = await process_serp_result(
                extract_agent=extract_agent,
                query=serp_query.query,
                search_results=search_results,
            )
            branch_learnings.extend(processed.learnings)
        except AgentCallError:
            logger.warning(f"Knowledge extraction failed for '{serp_query.query}'")
            processed = ProcessedResult(learnings=[], follow_up_questions=[])

        new_depth = depth - 1
        new_breadth = max(1, breadth // 2)

        if new_depth > 0 and processed.follow_up_questions:
            next_query = (
                f"Previous research goal: {serp_query.research_goal}\n"
                "Follow-up research directions:\n"
                + "\n".join(f"- {question}" for question in processed.follow_up_questions)
            )
            return await deep_research(
                query_agent=query_agent,
                extract_agent=extract_agent,
                query=next_query,
                breadth=new_breadth,
                depth=new_depth,
                learnings=branch_learnings,
                visited_urls=branch_urls,
            )

        return ResearchResult(learnings=branch_learnings, visited_urls=branch_urls)

    tasks = [process_single_query(query_item) for query_item in serp_queries]
    branch_results = await asyncio.gather(*tasks, return_exceptions=True)

    merged_learnings: set[str] = set()
    merged_urls: set[str] = set()

    for result in branch_results:
        if isinstance(result, ResearchResult):
            merged_learnings.update(result.learnings)
            merged_urls.update(result.visited_urls)
        elif isinstance(result, asyncio.CancelledError):
            logger.warning("Branch task was cancelled, propagating CancelledError")
            raise result
        elif isinstance(result, Exception):
            logger.error(f"Branch failed with exception: {result}")

    logger.info(
        f"deep_research complete: depth={depth}, total_learnings={len(merged_learnings)}, total_urls={len(merged_urls)}"
    )

    return ResearchResult(
        learnings=list(merged_learnings),
        visited_urls=list(merged_urls),
    )


async def generate_report(
    report_agent: ChatAgent,
    symbol: str,
    name: str,
    industry: str,
    learnings: list[str],
    *,
    stream: bool = False,
) -> dict:
    """Generate report dict (without meta) from all learnings."""
    user_message = (
        f"请为股票 {symbol} {name}（{industry}行业）生成结构化的网络深度搜索研究报告。\n\n"
        f"以下是通过多轮深度搜索积累的全部 {len(learnings)} 个知识点：\n\n"
        "<learnings>\n"
    )
    for index, learning in enumerate(learnings, 1):
        user_message += f"{index}. {learning}\n"
    user_message += "</learnings>\n"

    logger.debug(f"[Module B] Report prompt payload for {symbol}:\n{user_message}")

    try:
        thread = report_agent.get_new_thread()
        if stream:
            raw_text = await _run_agent_stream(report_agent, user_message, thread)
        else:
            response = await report_agent.run(user_message, thread=thread)
            raw_text = response.text
        json_str = extract_json_str(raw_text)
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Report generation failed: invalid JSON - {e}")
        raise ReportGenerationError(
            symbol=symbol,
            cause=e,
            learnings_count=len(learnings),
        ) from e
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise ReportGenerationError(
            symbol=symbol,
            cause=e,
            learnings_count=len(learnings),
        ) from e

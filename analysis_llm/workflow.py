"""Concurrent workflow execution for Step 1 using OpenAI compatible mode."""
from __future__ import annotations
import os
from agent_framework import ConcurrentBuilder
from agent_framework.openai import OpenAIChatClient
from openai import AsyncOpenAI

from . import config
from .agents import create_kline_agent, create_news_agent, create_sector_agent
from .merger import merge_results
from .utils import init_logging

logger = init_logging()


async def execute_step1(stock_code: str):
    """Run Step 1 workflow and return Step1Output."""
    if not stock_code:
        raise ValueError("stock_code is required")

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise EnvironmentError("环境变量 'DASHSCOPE_API_KEY' 未配置，请在 .env 文件中设置。")

    base_url = config.DASHSCOPE_BASE_URL

    # Create a shared AsyncOpenAI client with timeout configuration
    # Set a generous timeout (60s) to handle network latency and long generation times
    openai_client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=60.0
    )

    # Initialize chat clients using MAF native OpenAIChatClient
    # This works for both text (qwen-plus) and vision (qwen-vl-max) models
    news_client = OpenAIChatClient(
        model_id=config.MODEL_NEWS_AGENT,
        async_client=openai_client
    )
    
    sector_client = OpenAIChatClient(
        model_id=config.MODEL_SECTOR_AGENT,
        async_client=openai_client
    )
    
    kline_client = OpenAIChatClient(
        model_id=config.MODEL_KLINE_AGENT,
        async_client=openai_client
    )

    # Note: Using the same client for checkers if needed, or separate instances
    checker_client_news = OpenAIChatClient(model_id=config.MODEL_CHECKER_NEWS, async_client=openai_client)
    checker_client_sector = OpenAIChatClient(model_id=config.MODEL_CHECKER_SECTOR, async_client=openai_client)
    checker_client_kline = OpenAIChatClient(model_id=config.MODEL_CHECKER_KLINE, async_client=openai_client)

    # Create agents with the new clients
    news_agent = create_news_agent(news_client, checker_client_news)
    sector_agent = create_sector_agent(sector_client, checker_client_sector)
    kline_agent = create_kline_agent(kline_client, checker_client_kline)

    workflow = (
        ConcurrentBuilder()
        .participants([news_agent, sector_agent, kline_agent])
        .build()
    )

    logger.info("Step1 workflow started for %s using OpenAI compatible mode", stock_code)
    events = await workflow.run(stock_code)
    
    # Extract ChatMessages from workflow events
    messages = []
    logger.info("Traversing %d events...", len(events))
    for i, event in enumerate(events):
        event_type = type(event).__name__
        
        # 针对 ExecutorCompletedEvent 进行提取
        if event_type == "ExecutorCompletedEvent":
            # 检查 event.output (如果存在) 或 event.data
            # 根据日志，attrs 包含 'data'，可能结果在 data 中
            payload = getattr(event, "output", getattr(event, "data", None))
            
            logger.debug("Event %d payload type: %s", i, type(payload))
            
            # 尝试从 payload 中提取 messages
            raw_msgs = []
            if isinstance(payload, list):
                raw_msgs = payload
            elif hasattr(payload, "messages"):
                raw_msgs = payload.messages
            
            for item in raw_msgs:
                # 检查是否为 AgentExecutorResponse (根据调试日志，它有 agent_response 属性)
                if hasattr(item, "agent_response"):
                    resp = item.agent_response
                    if hasattr(resp, "messages"):
                        messages.extend(resp.messages)
                elif hasattr(item, "messages"):
                    # 备用：如果直接是 AgentResponse
                    messages.extend(item.messages)
                elif hasattr(item, "role") and hasattr(item, "text"): # 鸭子类型检查 ChatMessage
                    messages.append(item)
                elif isinstance(item, dict):
                    # 如果是字典，尝试转换为 ChatMessage
                    try:
                        from agent_framework import ChatMessage
                        messages.append(ChatMessage.from_dict(item))
                    except Exception as e:
                        logger.warning("Failed to convert dict to ChatMessage: %s", e)
                else:
                    logger.warning("Unknown item type in payload: %s, dir: %s", type(item), dir(item))

    # Debug: Print extracted messages
    logger.info("Extracted %d messages from events", len(messages))
    for i, msg in enumerate(messages):
        logger.debug("Message %d type: %s", i, type(msg))
            
    return merge_results(messages)
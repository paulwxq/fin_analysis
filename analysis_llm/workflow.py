"""Concurrent workflow execution for Step 1."""
from __future__ import annotations

from agent_framework import ConcurrentBuilder

from qwen3 import QwenChatClient, QwenVLChatClient

from . import config
from .agents import create_kline_agent, create_news_agent, create_sector_agent
from .merger import merge_results
from .utils import init_logging

logger = init_logging()


async def execute_step1(stock_code: str):
    """Run Step 1 workflow and return Step1Output."""
    if not stock_code:
        raise ValueError("stock_code is required")

    # Initialize chat clients
    news_client = QwenChatClient(model_id=config.MODEL_NEWS_AGENT)
    sector_client = QwenChatClient(model_id=config.MODEL_SECTOR_AGENT)
    kline_client = QwenVLChatClient(model_id=config.MODEL_KLINE_AGENT)

    checker_client_news = QwenChatClient(model_id=config.MODEL_CHECKER_NEWS)
    checker_client_sector = QwenChatClient(model_id=config.MODEL_CHECKER_SECTOR)
    checker_client_kline = QwenChatClient(model_id=config.MODEL_CHECKER_KLINE)

    news_agent = create_news_agent(news_client, checker_client_news)
    sector_agent = create_sector_agent(sector_client, checker_client_sector)
    kline_agent = create_kline_agent(kline_client, checker_client_kline)

    workflow = (
        ConcurrentBuilder()
        .participants([news_agent, sector_agent, kline_agent])
        .build()
    )

    logger.info("Step1 workflow started for %s", stock_code)
    messages = await workflow.run(stock_code)
    return merge_results(messages)

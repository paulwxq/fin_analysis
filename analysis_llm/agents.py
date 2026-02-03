"""Agent implementations for Step 1 pipeline."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Sequence

from agent_framework import AgentResponse, ChatAgent, ChatMessage, Content
from agent_framework._agents import AgentProtocol

from . import config
from .models import CheckerResult, KLineData, NewsData, SectorData
from .prompts import KLINE_AGENT_SYSTEM, KLINE_CHECKER_SYSTEM, NEWS_AGENT_SYSTEM, NEWS_CHECKER_SYSTEM, SECTOR_AGENT_SYSTEM, SECTOR_CHECKER_SYSTEM
from .tools import web_search
from .utils import extract_json_str, init_logging, load_image_content

logger = init_logging()


MessageBuilder = Callable[[str, str | None], str | ChatMessage | Sequence[ChatMessage]]


def _extract_stock_code(messages: str | ChatMessage | Sequence[str | ChatMessage] | None) -> str:
    if messages is None:
        raise ValueError("messages is required")
    if isinstance(messages, str):
        return messages.strip()
    if isinstance(messages, ChatMessage):
        return (messages.text or "").strip()
    # sequence
    for item in reversed(list(messages)):
        if isinstance(item, str):
            if item.strip():
                return item.strip()
        elif isinstance(item, ChatMessage):
            text = (item.text or "").strip()
            if text:
                return text
    raise ValueError("无法从 messages 中解析 stock_code")


def _build_text_prompt(stock_code: str, feedback: str | None) -> str:
    if feedback:
        return f"股票代码: {stock_code}\n请根据以下问题修正输出，仅返回修正后的JSON：{feedback}"
    return (
        f"请对股票 {stock_code} 进行深度新闻挖掘。\n"
        f"1. 务必使用搜索工具查询“{stock_code} 最近12个月业绩”、“{stock_code} 重大公告”、“{stock_code} 负面新闻”等组合关键词。\n"
        f"2. 请仔细阅读搜索结果，提取其中的营收数据、利润增长、股权变动等实质性信息。\n"
        f"3. 不要因为信息零散就放弃，请尽力拼凑出完整的事件脉络。"
    )


def _build_kline_messages(stock_code: str, feedback: str | None) -> Sequence[ChatMessage]:
    image_path = config.IMAGE_DIR / f"{stock_code}_kline.png"
    if not image_path.exists():
        raise FileNotFoundError(f"未找到K线图片: {image_path}")

    prompt = _build_text_prompt(stock_code, feedback)
    contents = [Content.from_text(prompt), load_image_content(image_path)]
    return [ChatMessage(role="user", contents=contents)]


class DataCollectionAgent(AgentProtocol):
    """Generic data collection agent with Agent->Checker->Retry loop."""

    def __init__(
        self,
        *,
        agent_id: str,
        name: str,
        description: str,
        chat_client,
        checker_client,
        instructions_template: str,
        checker_instructions_template: str,
        model_cls,
        message_builder: MessageBuilder,
        tools: Sequence[object] | None = None,
        max_retries: int = config.MAX_RETRIES,
    ) -> None:
        self.id = agent_id
        self.name = name
        self.description = description
        self._chat_client = chat_client
        self._checker_client = checker_client
        self._instructions_template = instructions_template
        self._checker_instructions_template = checker_instructions_template
        self._model_cls = model_cls
        self._message_builder = message_builder
        self._tools = list(tools) if tools else None
        self._max_retries = max_retries
        
        # 初始化一个代理 Agent 用于生成 Thread 等辅助操作
        self._proxy_agent = ChatAgent(
            chat_client=self._chat_client,
            name=f"{self.name}_proxy",
        )

    async def run(self, messages=None, *, thread=None, **kwargs) -> AgentResponse:
        stock_code = _extract_stock_code(messages)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        instructions = self._instructions_template.format(
            stock_code=stock_code,
            max_chars=config.NEWS_ITEM_MAX_CHARS,
            limit_pos=config.NEWS_LIMIT_POS,
            limit_neg=config.NEWS_LIMIT_NEG,
            current_date=now_str
        )

        agent = ChatAgent(
            chat_client=self._chat_client,
            name=self.name,
            description=self.description,
            instructions=instructions,
            tools=self._tools,
        )

        checker = ChatAgent(
            chat_client=self._checker_client,
            name=f"{self.name}Checker",
            instructions=self._checker_instructions_template,
        )

        # 确保有 Thread，否则重试反馈无效
        active_thread = thread or agent.get_new_thread()

        feedback: str | None = None
        last_error: str | None = None

        for attempt in range(1, self._max_retries + 1):
            prompt = self._message_builder(stock_code, feedback)
            logger.info("%s attempt %s/%s", self.name, attempt, self._max_retries)

            response = await agent.run(prompt, thread=active_thread)
            raw_text = response.text
            logger.debug("%s raw response: %s", self.name, raw_text)
            try:
                json_str = extract_json_str(raw_text)
                self._model_cls.model_validate_json(json_str)
            except Exception as exc:  # noqa: BLE001
                last_error = f"结构校验失败: {exc}"
                logger.warning("%s validation failed: %s", self.name, last_error)
                feedback = last_error
                continue

            # --- Checker 校验 (增强鲁棒性版本) ---
            checker_passed = False
            
            # Checker 内部微重试 (2次机会)
            for _ in range(2):
                try:
                    checker_prompt = f"期望股票代码: {stock_code}\n待校验数据: {json_str}"
                    checker_resp = await checker.run(checker_prompt)
                    checker_raw = checker_resp.text
                    logger.debug("%s Checker raw response: %s", self.name, checker_raw)

                    checker_json = extract_json_str(checker_raw)
                    checker_result = CheckerResult.model_validate_json(checker_json)
                    
                    if checker_result.passed:
                        logger.info("%s check passed.", self.name)
                        checker_passed = True
                        break
                    else:
                        # Checker 明确否决
                        last_error = f"质检未通过: {checker_result.reason}"
                        logger.warning("%s check rejected: %s", self.name, last_error)
                        feedback = last_error
                        break # 明确失败，跳出微重试，进入下一次大循环
                except Exception as exc:
                    logger.warning("%s Checker internal error (retrying): %s", self.name, exc)
                    continue
            else:
                # 如果微重试耗尽仍未得到明确结果(passed/failed)，说明 Checker 自身有问题
                # 策略：降级放行
                logger.warning("%s Checker malfunctioned after retries, bypassing check due to Pydantic success.", self.name)
                checker_passed = True

            if checker_passed:
                msg = ChatMessage(role="assistant", text=json_str)
                return AgentResponse(messages=[msg], response_id=response.response_id, usage_details=response.usage_details)
            
            # 如果 checker_passed 为 False，说明是明确被否决，继续外层循环
            continue


        raise RuntimeError(f"{self.name} 在 {self._max_retries} 次尝试后仍未通过: {last_error}")

    def run_stream(self, messages=None, *, thread=None, **kwargs):
        raise NotImplementedError("Streaming not implemented for DataCollectionAgent")

    def get_new_thread(self, **kwargs):
        """Delegate thread creation to the proxy agent."""
        return self._proxy_agent.get_new_thread(**kwargs)


def create_news_agent(chat_client, checker_client) -> DataCollectionAgent:
    return DataCollectionAgent(
        agent_id="news_agent",
        name="NewsAgent",
        description="新闻搜索与摘要生成",
        chat_client=chat_client,
        checker_client=checker_client,
        instructions_template=NEWS_AGENT_SYSTEM,
        checker_instructions_template=NEWS_CHECKER_SYSTEM,
        model_cls=NewsData,
        message_builder=lambda stock_code, feedback: _build_text_prompt(stock_code, feedback),
        tools=[web_search],
        max_retries=config.MAX_RETRIES,
    )


def create_sector_agent(chat_client, checker_client) -> DataCollectionAgent:
    return DataCollectionAgent(
        agent_id="sector_agent",
        name="SectorAgent",
        description="板块热度分析",
        chat_client=chat_client,
        checker_client=checker_client,
        instructions_template=SECTOR_AGENT_SYSTEM,
        checker_instructions_template=SECTOR_CHECKER_SYSTEM,
        model_cls=SectorData,
        message_builder=lambda stock_code, feedback: _build_text_prompt(stock_code, feedback),
        tools=[web_search],
        max_retries=config.MAX_RETRIES,
    )


def create_kline_agent(chat_client, checker_client) -> DataCollectionAgent:
    return DataCollectionAgent(
        agent_id="kline_agent",
        name="KLineAgent",
        description="K线图技术分析",
        chat_client=chat_client,
        checker_client=checker_client,
        instructions_template=KLINE_AGENT_SYSTEM,
        checker_instructions_template=KLINE_CHECKER_SYSTEM,
        model_cls=KLineData,
        message_builder=_build_kline_messages,
        tools=None,
        max_retries=config.MAX_RETRIES,
    )

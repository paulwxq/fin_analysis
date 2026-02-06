"""Workflow execution for Step 1 (concurrent) and Step 2 (magentic) using OpenAI compatible mode."""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Any

from agent_framework import (
    ChatAgent,
    ChatMessage,
    ConcurrentBuilder,
    MagenticBuilder,
    StandardMagenticManager,
)
from agent_framework.openai import OpenAIChatClient
from openai import AsyncOpenAI
from pydantic import ValidationError

from . import config
from .agents import create_kline_agent, create_news_agent, create_sector_agent
from .merger import merge_results
from .models import HoldRecommendation, Step1Output
from .prompts import MANAGER_INSTRUCTIONS, REVIEW_AGENT_SYSTEM, SCORE_AGENT_SYSTEM
from .utils import extract_json_str

logger = logging.getLogger("analysis_llm")


async def execute_step1(stock_code: str):
    """Run Step 1 workflow and return Step1Output."""
    if not stock_code:
        raise ValueError("stock_code is required")

    api_key = config.DASHSCOPE_API_KEY
    if not api_key:
        raise EnvironmentError("环境变量 'DASHSCOPE_API_KEY' 未配置，请在 .env 文件中设置。")

    base_url = config.DASHSCOPE_BASE_URL

    # Create a shared AsyncOpenAI client with timeout configuration
    openai_client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=config.API_TIMEOUT
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
    result = await workflow.run(stock_code)
    
    messages = []
    
    # 1. 优先尝试官方 API get_outputs()
    if hasattr(result, "get_outputs"):
        try:
            outputs = result.get_outputs()
            logger.info("Using WorkflowRunResult.get_outputs(), count: %d", len(outputs))
            
            # 扁平化提取 ChatMessage
            for out in outputs:
                # out 可能是一个列表 (聚合器输出) 或单个对象
                items = out if isinstance(out, list) else [out]
                
                for item in items:
                    # 复用剥洋葱逻辑
                    if hasattr(item, "agent_response"):
                        resp = item.agent_response
                        if hasattr(resp, "messages"):
                            messages.extend(resp.messages)
                    elif hasattr(item, "messages"):
                        messages.extend(item.messages)
                    elif hasattr(item, "role") and hasattr(item, "text"): # ChatMessage duck typing
                        messages.append(item)
                    elif isinstance(item, dict):
                        try:
                            messages.append(ChatMessage.from_dict(item))
                        except Exception: pass
                    
        except Exception as e:
            logger.warning("get_outputs() failed, falling back to event scanning: %s", e)

    # 2. 如果官方 API 未返回有效消息，回退到事件扫描 (Fallback)
    if not messages:
        logger.info("No messages from get_outputs(), scanning events...")
        # result 本身是可迭代的事件流 (list[WorkflowEvent])
        for event in result:
            event_type = type(event).__name__
            if event_type == "WorkflowOutputEvent":
                logger.debug("Found WorkflowOutputEvent, processing data...")
                # 聚合器通常返回一个列表
                items = event.data if isinstance(event.data, list) else [event.data]
                for item in items:
                    if hasattr(item, "agent_response"):
                        resp = item.agent_response
                        if hasattr(resp, "messages"):
                            messages.extend(resp.messages)
                    elif hasattr(item, "messages"):
                        messages.extend(item.messages)
                    elif isinstance(item, ChatMessage):
                        messages.append(item)
                    elif isinstance(item, dict):
                        try:
                            messages.append(ChatMessage.from_dict(item))
                        except Exception: pass
            
            elif event_type == "ExecutorCompletedEvent" and not messages:
                # 进一步兜底：如果没有 WorkflowOutputEvent，从 ExecutorCompletedEvent 捞
                payload = getattr(event, "output", getattr(event, "data", None))
                raw_msgs = payload if isinstance(payload, list) else [payload]
                for item in raw_msgs:
                    if hasattr(item, "agent_response"):
                        resp = item.agent_response
                        if hasattr(resp, "messages"):
                            messages.extend(resp.messages)
                    elif hasattr(item, "messages"):
                        messages.extend(item.messages)
                    elif isinstance(item, ChatMessage):
                        messages.append(item)

    # Debug: Print extracted messages
    logger.info("Extracted %d messages from workflow result", len(messages))
            
    return merge_results(messages)


class ScoringWorkflow:
    """Magentic-based scoring workflow for Step 2."""

    def __init__(
        self,
        dashscope_client: AsyncOpenAI | None = None,
        deepseek_client: AsyncOpenAI | None = None,
    ) -> None:
        logger.info("初始化 Step2 Workflow")

        if dashscope_client is None:
            if not config.DASHSCOPE_API_KEY:
                logger.error("DASHSCOPE_API_KEY 环境变量未设置")
                raise EnvironmentError("DASHSCOPE_API_KEY is required for Step2")
            self._dashscope_client = AsyncOpenAI(
                api_key=config.DASHSCOPE_API_KEY,
                base_url=config.DASHSCOPE_BASE_URL,
                timeout=config.API_TIMEOUT,
            )
        else:
            self._dashscope_client = dashscope_client

        if deepseek_client is None:
            if not config.DEEPSEEK_API_KEY:
                logger.error("DEEPSEEK_API_KEY 环境变量未设置")
                raise EnvironmentError("DEEPSEEK_API_KEY is required for Step2")
            self._deepseek_client = AsyncOpenAI(
                api_key=config.DEEPSEEK_API_KEY,
                base_url=config.DEEPSEEK_BASE_URL,
                timeout=config.API_TIMEOUT,
            )
        else:
            self._deepseek_client = deepseek_client

        self.manager_client = OpenAIChatClient(
            model_id=config.MODEL_MANAGER,
            async_client=self._dashscope_client,
        )
        self.score_client = OpenAIChatClient(
            model_id=config.MODEL_SCORE_AGENT,
            async_client=self._dashscope_client,
        )
        self.review_client = OpenAIChatClient(
            model_id=config.MODEL_REVIEW_AGENT,
            async_client=self._deepseek_client,
        )
        logger.debug("ReviewAgent Client 初始化完成 - 模型: %s", config.MODEL_REVIEW_AGENT)
        logger.info("Step2 Workflow 初始化完成")

    async def run(self, step1_output: Step1Output) -> HoldRecommendation:
        stock_code = step1_output.news.stock_code
        logger.info("开始 Step2 评分流程 - 股票: %s", stock_code)

        try:
            # 使用 ensure_ascii=False 保持中文可读性，避免 Unicode 转义
            # 这样 LLM 能更好地理解中文内容，同时减少 token 消耗
            context_str = step1_output.model_dump_json(ensure_ascii=False)
            logger.debug("Step1 输入数据大小: %d 字符", len(context_str))

            score_agent = ChatAgent(
                name="ScoreAgent",
                chat_client=self.score_client,
                instructions=SCORE_AGENT_SYSTEM.format(stock_code=stock_code),
                default_options={
                    "temperature": 0.1,  # 降低随机性，提高一致性
                    "response_format": {"type": "json_object"},
                    "extra_body": {"enable_search": True},
                },
            )

            review_agent = ChatAgent(
                name="ReviewAgent",
                chat_client=self.review_client,
                instructions=REVIEW_AGENT_SYSTEM.format(stock_code=stock_code),
                default_options={"response_format": {"type": "json_object"}},
            )

            # Manager 也需要是一个 Agent
            manager_agent = ChatAgent(
                name="Manager",
                chat_client=self.manager_client,
                instructions=MANAGER_INSTRUCTIONS,
            )

            workflow = (
                MagenticBuilder()
                .with_manager(
                    manager=StandardMagenticManager(
                        agent=manager_agent,
                        max_round_count=config.MAX_ITERATIONS,
                    )
                )
                .participants([score_agent, review_agent])
                .build()
            )

            task = (
                "请根据以下 Step1 数据生成股票投资评分报告。\n\n"
                f"数据内容：\n{context_str}\n\n"
                "流程约束（必须严格遵守）：\n"
                "1. 首先让 ScoreAgent 生成评分报告初稿（包含 hold_score 和 summary_reason）\n"
                "2. 然后必须让 ReviewAgent 审核初稿（返回 passed 和 reason 字段）\n"
                "3. 如果 ReviewAgent 返回 passed=false，必须将 reason 反馈给 ScoreAgent 进行修改\n"
                "4. 重复步骤 2-3，直到 ReviewAgent 返回 passed=true\n"
                "5. 只有在 passed=true 的情况下才能输出最终结果\n\n"
                "注意：ReviewAgent 拥有一票否决权，不得跳过审核环节。"
            )

            try:
                result = await workflow.run(task)
                logger.info("Magentic 工作流执行完成")
            except RuntimeError as exc:
                lowered = str(exc).lower()
                if "iteration" in lowered or "max" in lowered:
                    logger.error(
                        "Magentic 工作流达到最大迭代次数 (%d)",
                        config.MAX_ITERATIONS,
                    )
                    logger.debug("迭代超限详情: %s", str(exc), exc_info=True)
                    raise RuntimeError(
                        f"Step2 consensus failed for {stock_code}. "
                        f"ScoreAgent and ReviewAgent could not reach agreement within {config.MAX_ITERATIONS} iterations. "
                        "This may indicate conflicting evaluation criteria or data quality issues."
                    ) from exc
                raise

            logger.debug("提取评分结果")
            try:
                final_json = self._extract_result(result)
                logger.info("评分生成完成 - 分数: %.2f", final_json["hold_score"])
                logger.debug("评分理由摘要: %s...", final_json["summary_reason"][:100])
            except ValueError as exc:
                logger.error("未找到有效的评分结果 - %s", stock_code)
                logger.debug("结果提取失败详情: %s", str(exc), exc_info=True)
                raise RuntimeError(
                    f"Step2 failed to produce valid output for {stock_code}. "
                    "No valid ScoreAgent output found after workflow execution. "
                    "This may indicate consensus failure or workflow timeout."
                ) from exc
            except json.JSONDecodeError as exc:
                logger.error("JSON 解析失败 - %s", stock_code)
                logger.debug("JSON 错误详情: %s", str(exc), exc_info=True)
                raise

            stock_name = step1_output.news.stock_name or step1_output.sector.stock_name
            if not stock_name:
                logger.warning(
                    "stock_name 为空 - %s: Step1 的 news.stock_name 和 sector.stock_name 都为空。"
                    "这不影响评分流程，但可能影响下游系统的显示。",
                    stock_code,
                )
                stock_name = ""

            output = HoldRecommendation(
                stock_code=stock_code,
                stock_name=stock_name,
                hold_score=final_json["hold_score"],
                summary_reason=final_json["summary_reason"],
            )
            logger.info("Step2 完成 - %s: %.2f分", stock_code, output.hold_score)
            return output

        except asyncio.TimeoutError as exc:
            logger.error(
                "Step2 执行超时 - %s: API 调用超过 %s 秒",
                stock_code,
                config.API_TIMEOUT,
            )
            logger.debug("超时详情: %s", str(exc), exc_info=True)
            raise RuntimeError(
                f"Step2 generation timeout for {stock_code}. "
                f"API call exceeded {config.API_TIMEOUT} seconds. "
                "Please retry later or check network connectivity."
            ) from exc
        except ValidationError as exc:
            logger.error("Pydantic 校验失败 - %s", stock_code)
            logger.debug("校验错误详情: %s", exc.json(), exc_info=True)
            raise
        except Exception as exc:
            if "timeout" in str(exc).lower():
                logger.error("检测到超时相关错误 - %s: %s", stock_code, str(exc))
                logger.debug("超时堆栈", exc_info=True)
                raise RuntimeError(f"Timeout error in Step2 for {stock_code}") from exc
            logger.error("Step2 执行异常 - %s: %s", stock_code, str(exc))
            logger.debug("异常堆栈", exc_info=True)
            raise

    def _extract_result(self, result: Any) -> dict:
        """
        从 Magentic 工作流结果中提取评分数据（含审核验证）。

        核心原则：不管结果从哪来，都必须验证 ReviewAgent 的 passed=true。

        提取路径优先级：
        1. events - 最可靠，包含完整的审核信息（优先使用）
        2. __iter__ - 根据内容类型选择处理方式

        所有路径都必须经过 ReviewAgent 审核验证才能返回结果。

        Args:
            result: Magentic 工作流返回的结果对象

        Returns:
            dict: 审核通过的评分结果

        Raises:
            ValueError: 如果无法提取结果或审核验证失败
        """
        logger.debug("开始提取 Magentic 工作流结果")

        # 🔑 关键：首先获取 events，用于所有路径的审核验证
        events = getattr(result, "events", None)

        # 检查 events 是否存在但为空（异常情况，应明确报错）
        if events is not None and not events:
            logger.error("⚠ 事件流为空列表 (events=[])，无法提取审核信息")
            raise ValueError(
                "Events list is empty. Cannot verify ReviewAgent approval without event history."
            )

        # 路径1: 优先使用 events（最可靠，包含完整审核信息）
        if events:
            logger.debug("从事件流中提取结果，共 %d 个事件", len(events))
            return self._extract_from_events(events)

        # 路径2: __iter__（根据内容类型选择）
        if hasattr(result, "__iter__"):
            items = list(result)
            if items:
                logger.debug("从可迭代对象中提取结果，共 %d 个元素", len(items))
                first_item = items[0]
                if hasattr(first_item, "executor_id") or hasattr(first_item, "agent_name"):
                    # 看起来是 events
                    return self._extract_from_events(items)

        logger.error("无法从 result 对象提取结果，类型: %s", type(result))
        raise ValueError("Workflow result format not supported")

    def _extract_from_events(self, events: list) -> dict:
        logger.debug("倒序遍历事件流，查找 ScoreAgent 的最终输出")

        # 统计信息收集
        stats = {
            "score_agent_total": 0,        # ScoreAgent 总提交次数
            "score_agent_valid": 0,        # ScoreAgent 有效输出次数
            "review_agent_total": 0,       # ReviewAgent 总审核次数
            "review_approved": 0,          # ReviewAgent 通过次数
            "review_rejected": 0,          # ReviewAgent 拒绝次数
            "review_format_error": 0,      # ReviewAgent 格式错误次数
        }

        for idx, event in enumerate(reversed(events)):
            event_idx = len(events) - idx - 1
            logger.debug("检查事件 [%d]: %s", event_idx, type(event))

            is_score_agent = False
            if hasattr(event, "executor_id") and event.executor_id == "ScoreAgent":
                is_score_agent = True
            elif hasattr(event, "agent_name") and event.agent_name == "ScoreAgent":
                is_score_agent = True
            elif hasattr(event, "source") and "ScoreAgent" in str(event.source):
                is_score_agent = True

            if not is_score_agent:
                logger.debug("事件 [%d] 不是 ScoreAgent 的输出，跳过", event_idx)
                continue

            logger.debug("事件 [%d] 来自 ScoreAgent，尝试解析", event_idx)
            stats["score_agent_total"] += 1

            content = self._get_content(event)
            if content is None:
                logger.debug("事件 [%d] 内容为空，跳过", event_idx)
                continue

            # 调试：记录原始内容以便排查问题
            logger.debug("事件 [%d] 原始内容: %s", event_idx, str(content)[:500])

            try:
                data = self._parse_and_validate(content)
                stats["score_agent_valid"] += 1

                # 🔒 安全检查：验证此 ScoreAgent 输出是否有对应的 ReviewAgent 审核通过
                approval_result = self._is_approved_by_reviewer(events, event_idx, stats)
                if not approval_result:
                    logger.warning(
                        "事件 [%d] 的 ScoreAgent 输出未经 ReviewAgent 审核通过，跳过",
                        event_idx
                    )
                    continue

                logger.info("成功从事件 [%d] 提取结果：hold_score=%.2f", event_idx, data["hold_score"])

                # 输出统计摘要
                self._log_workflow_stats(stats)

                return data
            except Exception as exc:
                logger.warning("事件 [%d] 解析失败: %s", event_idx, exc)
                continue

        logger.error("未在事件流中找到有效的 ScoreAgent 输出")
        raise ValueError("No valid ScoreAgent output found in events")

    def _is_approved_by_reviewer(self, events: list, score_agent_idx: int, stats: dict = None) -> bool:
        """
        验证指定的 ScoreAgent 输出是否有对应的 ReviewAgent 审核通过。

        检查逻辑：
        1. 从 score_agent_idx 之后的事件中查找 ReviewAgent 的输出
        2. 找到第一个 ReviewAgent 输出后，检查其 passed 字段
        3. 如果 passed=true，返回 True；否则返回 False

        Args:
            events: 事件流列表
            score_agent_idx: ScoreAgent 事件的索引位置
            stats: 统计信息字典（可选），用于收集审核统计

        Returns:
            bool: True 表示已审核通过，False 表示未通过或未审核
        """
        logger.debug("验证事件 [%d] 的 ScoreAgent 输出是否经过审核", score_agent_idx)

        # 从 ScoreAgent 之后的事件中查找 ReviewAgent
        for idx in range(score_agent_idx + 1, len(events)):
            event = events[idx]

            # 识别 ReviewAgent 的输出
            is_review_agent = False
            if hasattr(event, "executor_id") and event.executor_id == "ReviewAgent":
                is_review_agent = True
            elif hasattr(event, "agent_name") and event.agent_name == "ReviewAgent":
                is_review_agent = True
            elif hasattr(event, "source") and "ReviewAgent" in str(event.source):
                is_review_agent = True

            if not is_review_agent:
                continue

            # 找到 ReviewAgent，提取其输出
            logger.debug("找到 ReviewAgent 事件 [%d]，检查审核结果", idx)
            if stats is not None:
                stats["review_agent_total"] += 1

            content = self._get_content(event)
            if content is None:
                logger.debug("ReviewAgent 事件 [%d] 内容为空", idx)
                if stats is not None:
                    stats["review_format_error"] += 1
                continue

            try:
                # 解析 ReviewAgent 的输出
                if isinstance(content, dict):
                    review_data = content
                elif isinstance(content, str):
                    # 使用 extract_json_str 提取 JSON，处理代码块和前后文
                    try:
                        json_str = extract_json_str(content)
                        review_data = json.loads(json_str)
                    except ValueError as extract_exc:
                        logger.warning(
                            "ReviewAgent 事件 [%d] 无法提取 JSON: %s",
                            idx, extract_exc
                        )
                        if stats is not None:
                            stats["review_format_error"] += 1
                        continue
                else:
                    logger.warning("ReviewAgent 事件 [%d] 内容格式不支持: %s", idx, type(content))
                    if stats is not None:
                        stats["review_format_error"] += 1
                    continue

                # 检查 passed 字段
                if "passed" in review_data:
                    passed_raw = review_data["passed"]

                    # 规范化为布尔值（容忍 LLM 可能输出的多种类型）
                    if isinstance(passed_raw, bool):
                        passed = passed_raw
                    elif isinstance(passed_raw, str):
                        # 容忍字符串 "true"/"false"/"1"/"0"/"yes"/"no"
                        passed = passed_raw.lower().strip() in ("true", "1", "yes")
                    elif isinstance(passed_raw, (int, float)):
                        # 容忍数字 1/0
                        passed = bool(passed_raw)
                    else:
                        logger.warning(
                            "ReviewAgent 事件 [%d] passed 字段类型异常: %s，默认为 False",
                            idx, type(passed_raw)
                        )
                        passed = False

                    logger.debug(
                        "ReviewAgent 事件 [%d] 审核结果: passed=%s (原始值: %r, 类型: %s)",
                        idx, passed, passed_raw, type(passed_raw).__name__
                    )

                    if passed:
                        if stats is not None:
                            stats["review_approved"] += 1
                        logger.info("✓ ScoreAgent [%d] 的输出已通过 ReviewAgent [%d] 审核", score_agent_idx, idx)
                        return True
                    else:
                        if stats is not None:
                            stats["review_rejected"] += 1
                        reason = review_data.get("reason", "未提供原因")
                        logger.warning(
                            "✗ ScoreAgent [%d] 的输出未通过 ReviewAgent [%d] 审核，原因: %s",
                            score_agent_idx, idx, reason
                        )
                        return False
                else:
                    logger.warning("ReviewAgent 事件 [%d] 缺少 passed 字段", idx)
                    if stats is not None:
                        stats["review_format_error"] += 1
                    continue

            except json.JSONDecodeError as exc:
                logger.warning("ReviewAgent 事件 [%d] JSON 解析失败: %s", idx, exc)
                if stats is not None:
                    stats["review_format_error"] += 1
                continue
            except Exception as exc:
                logger.warning("ReviewAgent 事件 [%d] 处理失败: %s", idx, exc)
                if stats is not None:
                    stats["review_format_error"] += 1
                continue

        # 未找到对应的 ReviewAgent 审核记录
        logger.warning("⚠ ScoreAgent [%d] 的输出未找到对应的 ReviewAgent 审核记录", score_agent_idx)
        return False

    def _log_workflow_stats(self, stats: dict) -> None:
        """输出工作流统计摘要。

        Args:
            stats: 包含统计信息的字典
        """
        logger.info("")
        logger.info("=" * 70)
        logger.info("Step2 工作流统计摘要")
        logger.info("=" * 70)
        logger.info("ScoreAgent 提交次数:        %d", stats["score_agent_total"])
        logger.info("  - 有效输出次数:           %d", stats["score_agent_valid"])
        logger.info("  - 格式错误/空内容:        %d", stats["score_agent_total"] - stats["score_agent_valid"])
        logger.info("")
        logger.info("ReviewAgent 审核次数:       %d", stats["review_agent_total"])
        logger.info("  - 通过 (passed=true):     %d ✅", stats["review_approved"])
        logger.info("  - 拒绝 (passed=false):    %d ❌", stats["review_rejected"])
        logger.info("  - 格式错误/无法解析:      %d ⚠️", stats["review_format_error"])
        logger.info("")

        # 计算重写次数（总提交次数 - 1，因为首次不算重写）
        rewrite_count = max(0, stats["score_agent_total"] - 1)
        logger.info("ScoreAgent 重写次数:        %d", rewrite_count)
        logger.info("ReviewAgent 拒绝次数:       %d", stats["review_rejected"])
        logger.info("")

        # 计算成功率
        if stats["review_agent_total"] > 0:
            success_rate = (stats["review_approved"] / stats["review_agent_total"]) * 100
            logger.info("审核通过率:                 %.1f%%", success_rate)

        logger.info("=" * 70)
        logger.info("")

    def _get_content(self, obj: Any) -> Any:
        """
        从各种对象类型中提取内容。

        对于 list/tuple 类型，使用倒序遍历以优先获取最后一条消息。
        这确保在 messages 列表中优先获取 assistant 的输出，而不是 system/user 消息。

        Args:
            obj: 待提取内容的对象

        Returns:
            提取到的内容，如果无法提取则返回 None
        """
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, str):
            return obj
        if isinstance(obj, (list, tuple)):
            # 🔄 倒序遍历：优先获取最后一条消息（通常是 assistant 输出）
            for item in reversed(obj):
                content = self._get_content(item)
                if content is not None:
                    return content
            return None
        if hasattr(obj, "agent_response"):
            return self._get_content(getattr(obj, "agent_response"))
        if hasattr(obj, "messages"):
            return self._get_content(getattr(obj, "messages"))
        if hasattr(obj, "message"):
            return self._get_content(getattr(obj, "message"))
        if hasattr(obj, "data"):
            return self._get_content(getattr(obj, "data"))
        if hasattr(obj, "content"):
            return self._get_content(getattr(obj, "content"))
        if hasattr(obj, "text"):
            return getattr(obj, "text")
        return None

    def _parse_and_validate(self, content: Any) -> dict:
        if isinstance(content, dict):
            data = content
        elif isinstance(content, str):
            raw = content.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
            data = json.loads(raw)
        else:
            raise ValueError(f"Unsupported content type: {type(content)}")

        if "hold_score" not in data:
            raise ValueError("Missing required field: hold_score")
        if "summary_reason" not in data:
            raise ValueError("Missing required field: summary_reason")

        hold_score = data["hold_score"]
        if not isinstance(hold_score, (int, float)):
            raise ValueError(f"hold_score must be numeric, got {type(hold_score)}")
        if not (0 <= hold_score <= 100):
            raise ValueError(f"hold_score must be in [0, 100], got {hold_score}")

        summary_reason = data["summary_reason"]
        if not isinstance(summary_reason, str):
            raise ValueError(f"summary_reason must be string, got {type(summary_reason)}")
        if len(summary_reason) < config.SUMMARY_REASON_MIN_CHARS:
            raise ValueError(
                f"summary_reason too short: {len(summary_reason)} chars "
                f"(min: {config.SUMMARY_REASON_MIN_CHARS})"
            )
        if len(summary_reason) > config.SUMMARY_REASON_MAX_CHARS:
            raise ValueError(
                f"summary_reason too long: {len(summary_reason)} chars "
                f"(max: {config.SUMMARY_REASON_MAX_CHARS})"
            )

        logger.debug("内容验证通过")
        return data

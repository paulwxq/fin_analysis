"""
Deep Research 自动化编排器
用于自动处理 Qwen Deep Research 的"提问-回答"流程，实现无人值守的深度研究。
"""
import logging
from typing import AsyncIterable, Optional
from agent_framework import ChatAgent, Content

logger = logging.getLogger(__name__)

class DeepResearchAutomator:
    def __init__(self, agent: ChatAgent):
        """
        初始化编排器
        :param agent: 必须是配置了 QwenDeepResearchClient 的 ChatAgent
        """
        self.agent = agent

    async def run_with_auto_clarification(
        self, 
        user_prompt: str, 
        auto_reply_template: str = None
    ) -> AsyncIterable[str]:
        """
        执行全自动深度研究：
        1. 发送初始请求
        2. 接收模型反问（静默处理）
        3. 自动提交回复
        4. 流式返回最终研究报告
        
        :param user_prompt: 用户的原始研究意图
        :param auto_reply_template: (可选) 自定义自动回复内容。如果为 None，使用默认的"全覆盖"策略。
        :return: 最终报告的流式内容生成器
        """
        
        # 1. 创建对话线程，确保上下文连贯
        thread = self.agent.get_new_thread()
        
        # --- 第一阶段：诱导模型反问 ---
        logger.info(f"AutoResearch: 发送初始请求 - {user_prompt[:50]}...")
        clarification_questions = ""
        
        # 我们需要消费完第一轮的流，以便让 thread 状态更新，同时收集问题（可选，用于日志）
        async for update in self.agent.run_stream(user_prompt, thread=thread):
            for content in update.contents:
                if content.text:
                    clarification_questions += content.text
        
        logger.info(f"AutoResearch: 收到澄清问题 ({len(clarification_questions)} chars)")
        # 可以在这里打印问题供调试，但对用户不可见
        # print(f"DEBUG [Model Questions]: {clarification_questions}")

        # --- 第二阶段：构造自动回复 ---
        # 策略：构造一个“既全面又聚焦”的回答，让模型火力全开。
        if auto_reply_template:
            final_reply = auto_reply_template
        else:
            # 默认通用回复策略
            final_reply = (
                f"请基于你的上述问题，进行最全面、最深入的综合研究。"
                f"不要局限于某一个方面，请涵盖基本面、技术面、市场情绪、宏观政策等所有关键维度。"
                f"我的核心诉求是：{user_prompt}。"
                f"请确保数据尽可能新，并提供详实的论据和引用。"
            )

        logger.info(f"AutoResearch: 自动提交回复 - {final_reply[:50]}...")

        # --- 第三阶段：执行研究并流式返回结果 ---
        async for update in self.agent.run_stream(final_reply, thread=thread):
            for content in update.contents:
                if content.text:
                    yield content.text


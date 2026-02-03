"""
联网搜索示例
演示如何启用 Qwen 的原生联网搜索能力
"""
import asyncio
import os
from dotenv import load_dotenv
from agent_framework import ChatAgent
from qwen3 import QwenChatClient, QwenChatOptions

async def main():
    load_dotenv()
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("请在 .env 文件中配置 DASHSCOPE_API_KEY")
        return
    
    client = QwenChatClient(model_id="qwen-plus")
    agent = ChatAgent(chat_client=client)

    # 1. 启用联网搜索
    options = QwenChatOptions(
        enable_search=True
    )

    # 2. 询问一个需要实时信息的问题
    query = "今天上海的天气怎么样？适合穿什么衣服？"
    print(f"用户: {query}")
    print("正在搜索并生成回答...\n")

    response = await agent.run(query, additional_chat_options=options)
    
    print(f"助手: {response.text}")

if __name__ == "__main__":
    asyncio.run(main())


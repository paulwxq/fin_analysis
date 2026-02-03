"""
基础对话示例
演示如何使用 QwenChatClient 进行简单的问答
"""
import asyncio
import os
from dotenv import load_dotenv
from agent_framework import ChatAgent
from qwen3 import QwenChatClient

async def main():
    # 1. 加载环境变量 (需要 DASHSCOPE_API_KEY)
    load_dotenv()
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("请在 .env 文件中配置 DASHSCOPE_API_KEY")
        return

    # 2. 初始化 Client
    client = QwenChatClient(model_id="qwen-plus")

    # 3. 创建 Agent
    agent = ChatAgent(chat_client=client, name="HelpfulAssistant")

    # 4. 执行对话
    query = "你好，请介绍一下 Qwen 模型。"
    print(f"用户: {query}")
    
    response = await agent.run(query)
    
    print(f"助手: {response.text}")
    print(f"\n[Stats] Token 使用: {response.usage_details}")

if __name__ == "__main__":
    asyncio.run(main())


"""
思考模式示例
演示如何启用 DeepSeek 风格的思维链 (CoT) 并流式输出
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
    
    # 1. 初始化 (使用 qwen-max 以获得更好的思考能力)
    client = QwenChatClient(model_id="qwen-max")
    agent = ChatAgent(chat_client=client)

    # 2. 配置思考模式 (注意：必须使用流式调用)
    options = QwenChatOptions(
        enable_thinking=True,
        thinking_budget=2048,  # 限制思考 Token 数量
        temperature=0.6
    )

    query = "如果 3x+1=10，那么 x 等于多少？请一步步推理。"
    print(f"用户: {query}\n")
    print("助手: ", end="", flush=True)

    # 3. 流式执行
    # Qwen 的思考内容会包裹在 <thinking> 标签中返回
    async for update in agent.run_stream(query, additional_chat_options=options):
        if update.text:
            print(update.text, end="", flush=True)
    
    print("\n\n[对话结束]")

if __name__ == "__main__":
    asyncio.run(main())


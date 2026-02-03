"""
视觉分析示例
演示如何使用 Qwen-VL 模型理解图像内容
"""
import asyncio
import os
from dotenv import load_dotenv
from agent_framework import ChatAgent, ChatMessage, Role, Content
from qwen3 import QwenVLChatClient, QwenVLChatOptions

async def main():
    load_dotenv()
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("请在 .env 文件中配置 DASHSCOPE_API_KEY")
        return
    
    # 1. 初始化视觉 Client
    client = QwenVLChatClient(model_id="qwen3-vl-plus")
    agent = ChatAgent(chat_client=client)

    # 2. 构造多模态消息
    # 使用公开的测试图片
    image_url = "https://help-static-aliyun-doc.aliyuncs.com/assets/img/zh-CN/6119365761/p558693.png"
    
    message = ChatMessage(
        role=Role.USER,
        contents=[
            Content.from_uri(uri=image_url),
            Content.from_text(text="请详细描述这张图片的内容，并提取其中的关键信息。")
        ]
    )

    print("用户: [发送了一张图片] 请详细描述这张图片...")
    print("助手正在分析...\n")

    # 3. 流式获取分析结果
    async for update in agent.run_stream([message]):
        if update.text:
            print(update.text, end="", flush=True)
            
    print("\n\n[分析结束]")

if __name__ == "__main__":
    asyncio.run(main())


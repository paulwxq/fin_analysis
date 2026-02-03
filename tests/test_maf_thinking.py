import asyncio
import os
import base64
from agent_framework import ChatMessage, Content, ChatAgent
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()

async def test_maf_thinking():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL")
    # 使用支持 thinking 的模型
    model = "qwen3-vl-plus" 

    print(f"Connecting to model: {model}...")

    # 1. Initialize Client
    client = OpenAIChatClient(
        model_id=model,
        api_key=api_key,
        base_url=base_url
    )

    # 2. Initialize Agent
    agent = ChatAgent(
        name="TestThinkingAgent",
        chat_client=client,
        instructions="你是一个助手。"
    )

    # 3. Prepare Image (Use local file if exists)
    image_path = "output/600482.SH_kline.png"
    if not os.path.exists(image_path):
         # Fallback to finding any image
        import glob
        files = glob.glob("output/*_kline.png")
        if files:
            image_path = files[0]
        else:
            print("No image found, skipping image test.")
            return

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    image_uri = f"data:image/png;base64,{image_data}"

    # 4. Prepare Message
    user_message = ChatMessage(
        role="user",
        contents=[
            Content.from_text(text="请分析这张图。请严格按照JSON格式输出，包含stock_code, score, reasoning字段。不要输出任何其他文本。"),
            Content.from_uri(uri=image_uri, media_type="image/png")
        ]
    )

    print("Sending request with extra_body options...")

    try:
        # 5. Call Agent with options
        # 尝试通过 options 传递 extra_body
        response = await agent.run(
            user_message,
            options={
                "extra_body": {
                    "enable_thinking": True,
                    "thinking_budget": 1024
                }
            }
        )

        print("\n" + "="*20 + " Response " + "="*20 + "\n")
        print(response.text)
        
        # Check raw contents to see if reasoning is separate
        print("\n" + "="*20 + " Raw Contents Inspection " + "="*20)
        for item in response.chat_message.contents:
            print(f"Type: {item.type}, Data: {str(item)[:100]}...")

        
    except Exception as e:
        print(f"\nFailed: {e}")

if __name__ == "__main__":
    asyncio.run(test_maf_thinking())

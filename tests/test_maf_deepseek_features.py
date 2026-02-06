import os
import asyncio
import logging
from dotenv import load_dotenv
from agent_framework import ChatAgent, ChatMessage
from agent_framework.openai import OpenAIChatClient
from openai import AsyncOpenAI

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_maf_deepseek")

async def test_deepseek_features():
    load_dotenv()
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL")
    
    if not api_key:
        print("Skipping test: DEEPSEEK_API_KEY not set")
        return

    logger.info("Initializing MAF OpenAIChatClient for DeepSeek...")
    
    # 注入 AsyncOpenAI 实例以控制超时
    openai_client = AsyncOpenAI(
        api_key=api_key, 
        base_url=base_url, 
        timeout=60.0
    )
    
    client = OpenAIChatClient(
        model_id="deepseek-chat", # 通常 DeepSeek V3 的模型 ID
        async_client=openai_client
    )

    agent = ChatAgent(chat_client=client, name="DeepSeekTester")

    # --- Test 1: JSON Mode Success Case ---
    print("\n--- Test 1: JSON Mode (Standard Success) ---")
    # Prompt 必须包含 "json"
    json_query = "生成一个关于华为公司的简单JSON，包含 name, hq_city 字段。"
    
    try:
        response = await agent.run(
            json_query,
            options={"response_format": {"type": "json_object"}}
        )
        print(f"Response: {response.text}")
        
        if response.text.strip().startswith("{") and "Huawei" in response.text:
            print("✅ JSON Output active and valid.")
        else:
            print("❌ JSON Output failed (format or content issue).")
            
    except Exception as e:
        print(f"❌ JSON test failed: {e}")

    # --- Test 2: JSON Mode Constraint Check (Missing keyword) ---
    print("\n--- Test 2: JSON Mode Constraint (Missing 'json' keyword) ---")
    # Prompt 不包含 "json"
    no_keyword_query = "Please output info about Huawei."
    
    try:
        await agent.run(
            no_keyword_query,
            options={"response_format": {"type": "json_object"}}
        )
        print("❓ Unexpected success: API should have returned 400 Bad Request.")
    except Exception as e:
        # 期待报错
        if "400" in str(e):
            print(f"✅ Correctly received 400 error: {e}")
        else:
            print(f"❓ Received error but not 400: {e}")

    # --- Test 3: Thinking Process Check ---
    print("\n--- Test 3: Thinking Process Check ---")
    think_query = "9.11 和 9.8 哪个大？请一步步思考。"
    
    try:
        response = await agent.run(think_query)
        print(f"Response: {response.text}")
        
        if "<think>" in response.text:
            print("💡 Thinking process (<think> tag) DETECTED.")
        else:
            print("⚪ No thinking process detected (Standard Chat).")
            
    except Exception as e:
        print(f"❌ Thinking test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_deepseek_features())

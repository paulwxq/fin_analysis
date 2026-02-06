import os
import asyncio
import logging
from dotenv import load_dotenv
from agent_framework import ChatAgent, ChatMessage, Role
from agent_framework.openai import OpenAIChatClient

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_maf_qwen")

async def test_search_and_json():
    load_dotenv()
    
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL")
    
    if not api_key:
        print("Skipping test: DASHSCOPE_API_KEY not set")
        return

    from openai import AsyncOpenAI
    openai_client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)

    logger.info("Initializing MAF OpenAIChatClient...")
    # 使用 qwen-plus 或 qwen-max，它们支持 enable_search
    client = OpenAIChatClient(
        model_id="qwen-plus",
        async_client=openai_client
    )

    agent = ChatAgent(chat_client=client, name="QwenTester")

    # --- 测试 1: 联网搜索 (enable_search) ---
    print("\n--- Test 1: Native Web Search (enable_search) ---")
    query = "杭州明天天气如何？请给出具体温度。"
    
    # 尝试通过 extra_body 传递 enable_search
    # 在 MAF 中，OpenAIChatClient 的 get_response 通常接受 **kwargs
    # 我们需要确认这些 kwargs 是否会被传给 openai.chat.completions.create
    
    try:
        # 尝试方法 1: 使用 options 字典传递参数
        # 这是 Agent Framework 的标准扩展方式
        response = await agent.run(
            query,
            options={"extra_body": {"enable_search": True}}
        )
        print(f"Response: {response.text}")
        
        # 检查是否真的联网了（如果回答了具体温度，说明联网成功）
        if "度" in response.text or "雨" in response.text or "晴" in response.text:
            print("✅ Search likely active (content contains weather info).")
        else:
            print("❓ Search might be inactive (content is generic).")
            
    except Exception as e:
        print(f"❌ Search test failed: {e}")

    # --- 测试 2: 结构化输出 (JSON Mode) ---
    print("\n--- Test 2: Structured Output (JSON Mode) ---")
    json_query = "生成一个关于苹果公司的简单JSON，包含 name, symbol, price 字段。"
    
    try:
        # OpenAI 标准参数是 response_format={"type": "json_object"}
        # MAF 的 ChatOptions 中包含 response_format，或者作为 kwargs 传递
        response = await agent.run(
            json_query,
            options={"response_format": {"type": "json_object"}}
        )
        print(f"Response: {response.text}")
        
        if response.text.strip().startswith("{"):
            print("✅ JSON Output active.")
        else:
            print("❌ JSON Output failed (not starting with {).")
            
    except Exception as e:
        print(f"❌ JSON test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_search_and_json())


import asyncio
import os
import logging
from typing import Annotated

from agent_framework import ChatAgent, tool
from agent_framework.openai import OpenAIChatClient
from openai import AsyncOpenAI

# 手动加载 .env 如果存在
def load_env_manual():
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value

load_env_manual()

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_parallel")

# 禁用底层的喧闹日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

@tool(name="get_weather", description="查询指定城市的天气")
async def get_weather(city: Annotated[str, "城市名称"]) -> str:
    return f"{city} 的天气是晴天，25度。"

async def run_test(name: str, options: dict):
    logger.info(f"=== 测试 {name} ===")
    
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    client = OpenAIChatClient(
        model_id="qwen-plus",
        async_client=AsyncOpenAI(api_key=api_key, base_url=base_url)
    )
    
    agent = ChatAgent(
        name="WeatherAgent",
        chat_client=client,
        tools=[get_weather],
        instructions="你是一个天气助手。请使用工具回答问题。"
    )
    
    prompt = "请帮我查一下北京和上海现在的天气。"
    
    try:
        response = await agent.run(prompt, options=options)
        
        tool_calls_count = 0
        for msg in response.messages:
            for content in msg.contents:
                if content.type == "function_call":
                    tool_calls_count += 1
        
        logger.info(f"结果: 返回了 {tool_calls_count} 个工具调用请求")
        if tool_calls_count > 1:
            logger.info(f"✅ {name} 成功开启并行调用！")
        else:
            logger.info(f"❌ {name} 未能开启并行调用（仅 {tool_calls_count} 个）。")
            
    except Exception as e:
        logger.error(f"💥 {name} 发生错误: {e}")

async def main():
    # 方式 A: MAF 标准映射
    await run_test("方式 A (MAF Standard)", {"allow_multiple_tool_calls": True})
    
    # 方式 B: extra_body 显式传递
    await run_test("方式 B (extra_body)", {"extra_body": {"parallel_tool_calls": True}})
    
    # 方式 C: 对比组
    await run_test("方式 C (Default/Disabled)", {"allow_multiple_tool_calls": False})

if __name__ == "__main__":
    asyncio.run(main())

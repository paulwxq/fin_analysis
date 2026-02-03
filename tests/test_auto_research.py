import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent_framework import ChatAgent
from qwen3.qwen_deep_research_client import QwenDeepResearchClient
from qwen3.auto_research import DeepResearchAutomator

load_dotenv()

async def test_fully_automated_research():
    print(">>> 初始化全自动研究助手...")
    api_key = os.getenv("DASHSCOPE_API_KEY")
    client = QwenDeepResearchClient(api_key=api_key)
    agent = ChatAgent(name="AutoResearcher", chat_client=client)
    
    # 实例化自动化编排器
    automator = DeepResearchAutomator(agent)
    
    topic = "分析 2026年 苹果公司(AAPL) 的最新产品传闻与股价潜在影响"
    print(f"\n>>> 用户指令: {topic}")
    print(">>> 正在自动执行 (无需人工干预)...")
    print("-" * 60)

    # 一行代码调用，自动处理中间环节
    async for chunk in automator.run_with_auto_clarification(topic):
        print(chunk, end="", flush=True)
    
    print("\n" + "-" * 60)
    print(">>> 研究完成！")

if __name__ == "__main__":
    asyncio.run(test_fully_automated_research())

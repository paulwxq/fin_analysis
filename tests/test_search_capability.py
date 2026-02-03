import asyncio
import os
import sys
import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent_framework import ChatAgent
from qwen3.qwen_deep_research_client import QwenDeepResearchClient

load_dotenv()

async def verify_deep_research_search_capability():
    print(">>> 正在初始化 Deep Research 客户端以验证联网搜索能力...")
    
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("Error: 未找到 DASHSCOPE_API_KEY")
        return

    # 初始化客户端
    client = QwenDeepResearchClient(api_key=api_key)
    
    # 初始化 Agent
    agent = ChatAgent(
        name="SearchTester", 
        chat_client=client,
        instructions="你是一个验证测试助手。用户的目的是验证你是否具备联网搜索能力。请务必使用搜索工具查找最新信息。"
    )

    # 构造一个必须联网才能回答的问题
    # 为了证明它真的搜了，我们问一个实时性很强的问题
    topic = "最近一周关于'DeepSeek'的最新重大新闻"
    prompt = f"请搜索并总结{topic}。我需要具体的日期、事件和来源，以验证你的联网能力。请务必列出新闻的引用来源（[1], [2]...）。"

    print(f"\n>>> [Turn 1] 发送测试请求: {prompt}")
    print(">>> (Deep Research 模型通常会先反问澄清，我们会自动处理)")

    thread = agent.get_new_thread()
    
    try:
        # Turn 1: 获取反问
        print("\n--- 等待模型反问 (Clarification) ---")
        async for update in agent.run_stream(prompt, thread=thread):
            for content in update.contents:
                if content.text:
                    print(content.text, end="", flush=True)
        print("\n")

        # Turn 2: 自动回复
        auto_reply = "请重点关注技术进展、市场反应以及与其他大模型（如OpenAI o1/DeepResearch）的对比。请提供尽可能新的信息，不需要非常长，但要有事实依据。"
        print(f"\n>>> [Turn 2] 自动回复反问: {auto_reply}")
        print(">>> 正在执行深度研究 (Deep Research)... 这可能需要几分钟，请耐心等待...")

        full_report = ""
        async for update in agent.run_stream(auto_reply, thread=thread):
            for content in update.contents:
                if content.text:
                    print(content.text, end="", flush=True)
                    full_report += content.text
        
        print("\n\n" + "="*50)
        print(">>> 验证结果分析:")
        
        # 1. 检查引用标记
        has_citations = "[" in full_report and "]" in full_report
        if has_citations:
            print("[√] 检测到引用标记 (如 [1], [2])，证明模型引用了外部资料。" )
        else:
            print("[?] 未检测到明显的引用标记，请人工检查内容。" )
            
        # 2. 检查内容长度
        if len(full_report) > 500:
            print(f"[√] 报告长度充足 ({len(full_report)} 字符)，符合深度研究特征。" )
        else:
            print(f"[!] 报告较短 ({len(full_report)} 字符)，可能未进行充分研究。" )
            
        print(">>> 请人工检查报告中是否包含最近几天的具体日期，这将是联网搜索的最有力证明。" )
        print("="*50)

    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_deep_research_search_capability())

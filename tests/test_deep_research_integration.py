import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent_framework import ChatMessage, Content, ChatAgent
# Use the new specialized client
from qwen3.qwen_deep_research_client import QwenDeepResearchClient 

load_dotenv()

async def analyze_stock_with_deep_research(stock_code: str):
    print(f"Initializing Qwen Deep Research Agent for {stock_code}...")
    
    # 1. Initialize the specialized Client
    # Default timeout is handled by the class now
    client = QwenDeepResearchClient(
        api_key=os.getenv("DASHSCOPE_API_KEY")
    )

    # 2. Initialize Agent
    agent = ChatAgent(
        name="DeepResearchAnalyst",
        chat_client=client,
        instructions="""你是一个专业的金融分析师。
请利用 Deep Research 能力对用户提供的股票代码进行深度调研。
报告应包含：
1. 基本面现状（营收、利润、核心竞争力）
2. 行业与板块热度分析
3. 3-6个月的中期走势逻辑分析
请用中文回答，逻辑清晰，引用数据。"""
    )

    # Create a new conversation thread to maintain context
    thread = agent.get_new_thread()

    # --- Turn 1: Initial Request ---
    prompt = f"请详细分析股票 {stock_code}。分析它的现状，是否属于当前热点板块，并评估未来3-6个月的上涨可能性。"
    
    print(f"\n[Turn 1] Sending request: {prompt}")
    print("--- Waiting for clarification questions ---")

    try:
        # Run Agent with run_stream (Turn 1)
        full_text_turn1 = ""
        async for update in agent.run_stream(prompt, thread=thread):
            if update.contents:
                for content in update.contents:
                    if content.text:
                        print(content.text, end="", flush=True)
                        full_text_turn1 += content.text
        
        print("\n" + "="*30 + " END OF TURN 1 " + "="*30 + "\n")

        # --- Turn 2: Answer Clarification & Get Report ---
        # Automatically answer the clarification questions to proceed
        # In a real app, you might ask the user here.
        clarification_answer = "请进行综合分析。1. 侧重基本面和市场情绪的结合。2. 重点关注行业政策和国产替代/AI等相关热门概念。3. 希望看到定性判断为主，辅以核心估值数据的分析。"
        
        print(f"\n[Turn 2] Auto-answering clarification: {clarification_answer}")
        print("--- Waiting for Deep Research Report (This may take several minutes) ---")
        
        full_text_turn2 = ""
        async for update in agent.run_stream(clarification_answer, thread=thread):
            if update.contents:
                for content in update.contents:
                    if content.text:
                        print(content.text, end="", flush=True)
                        full_text_turn2 += content.text

        print("\n" + "="*30 + " RESEARCH REPORT " + "="*30 + "\n")
        print(full_text_turn2)
        print("\n" + "="*77)

    except Exception as e:
        print(f"\nError occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    target = "002378.SZ"
    if len(sys.argv) > 1:
        target = sys.argv[1]
    asyncio.run(analyze_stock_with_deep_research(target))

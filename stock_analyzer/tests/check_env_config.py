import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from stock_analyzer.config import MODEL_CHIEF_AGENT
from stock_analyzer.llm_client import create_openai_client, create_chat_client
from stock_analyzer.agents import create_chief_agent

def check():
    print("--- 运行时环境检查 ---")
    print(f"Config 解析后的 MODEL_CHIEF_AGENT: {MODEL_CHIEF_AGENT}")
    
    openai_client = create_openai_client()
    chat_client = create_chat_client(openai_client, MODEL_CHIEF_AGENT)
    agent = create_chief_agent(chat_client)
    
    print("\n--- Chief Agent 实例配置 ---")
    # 检查 default_options
    opts = agent.default_options
    print(f"Model ID: {agent.chat_client.model_id}")
    print(f"Options: {opts}")

if __name__ == "__main__":
    check()

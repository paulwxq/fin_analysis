
import asyncio
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

# 添加项目根目录到路径
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from stock_analyzer.llm_client import create_openai_client, create_chat_client
from agent_framework import ChatAgent

async def run_probe():
    model_id = "deepseek-v3"
    print(f"=== 开始探测 {model_id} Thinking 兼容性 ===")
    
    openai_client = create_openai_client()
    chat_client = create_chat_client(openai_client, model_id)
    
    # 模拟 agent 配置
    agent = ChatAgent(
        chat_client=chat_client,
        name="prober",
        instructions="你是一个严谨的数学老师。",
        default_options={
            "temperature": 0.1,
            "extra_body": {"enable_thinking": True}
        }
    )
    
    prompt = "比较 9.11 和 9.9 的大小。要求：必须包含推理链，并以 JSON 格式输出结果，包含 'comparison' 键。"
    
    try:
        start_time = time.time()
        response = await agent.run(prompt)
        duration = time.time() - start_time
        
        print(f"\n[结果汇总]")
        print(f"1. 响应状态: 成功")
        print(f"2. 总耗时: {duration:.2f}秒")
        print(f"3. 响应文本: {response.text[:150]}...")
        
        # 检查结构化推理块
        has_reasoning_block = False
        for msg in response.messages:
            if msg.role == "assistant":
                for content in msg.contents:
                    if content.type == "reasoning":
                        has_reasoning_block = True
        
        print(f"4. 是否包含独立 Reasoning 块: {'✅ 是' if has_reasoning_block else '❌ 否'}")
        
        # 检查正文内嵌推理
        has_inline_think = "<think>" in response.text
        print(f"5. 是否包含内嵌 <think> 标签: {'✅ 是' if has_inline_think else '❌ 否'}")

    except Exception as e:
        print(f"\n[错误] 请求失败: {e}")

if __name__ == "__main__":
    asyncio.run(run_probe())

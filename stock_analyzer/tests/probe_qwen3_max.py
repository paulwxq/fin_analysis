import asyncio
import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from stock_analyzer.llm_client import create_openai_client, create_chat_client
from stock_analyzer.agents import create_chief_agent

async def probe_qwen3_max():
    print("=== 旗舰模型 qwen3-max 深度兼容性探测 ===")
    
    openai_client = create_openai_client()
    model_id = "qwen3-max" 
    chat_client = create_chat_client(openai_client, model_id)
    agent = create_chief_agent(chat_client)
    
    print("验证：Thinking + JSON Mode 是否能共存并产出结果...")
    
    prompt = "请对‘海油工程’进行多维度投资价值分析。要求：必须基于严密的逻辑链进行推理，并严格输出 JSON 格式。JSON 中必须包含 'overall_score' 和 'thinking_evidence' 键。"
    
    try:
        start_time = time.time()
        response = await agent.run(prompt)
        duration = time.time() - start_time
        
        print("\n" + "="*30)
        print(f"运行状态: 成功 (耗时 {duration:.2f} 秒)")
        print(f"输出内容预览: {response.text[:200]}...")
        
        # 检查内部消息是否包含推理块
        has_reasoning = False
        for msg in response.messages:
            if msg.role == "assistant":
                for c in msg.contents:
                    if c.type == "reasoning":
                        has_reasoning = True
                        print("\n🎯 核心证据发现：消息流中存在 reasoning 类型的内容块！")
                        # 尝试安全解析 protected_data
                        try:
                            reasoning_text = json.loads(c.to_dict().get('protected_data', '""'))
                            print(f"推理内容预览: {reasoning_text[:200]}...")
                        except:
                            print("（推理内容为加密或无法解析的原始格式）")
        
        if not has_reasoning:
            if duration > 40:
                print("\n⚠️ 虽然未发现显式推理块，但耗时异常长，可能是在后台完成了思维链。")
            else:
                print("\n❌ 结论：Thinking 参数可能被网关静默忽略了。")

    except Exception as e:
        print(f"\n❌ 运行失败: {e}")

if __name__ == "__main__":
    asyncio.run(probe_qwen3_max())

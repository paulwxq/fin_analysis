
import asyncio
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

# 加载环境变量
load_dotenv()

# 添加项目根目录到路径
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from stock_analyzer.config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL

async def test_qwen35_plus_stream():
    model_id = "qwen3.5-plus"
    client = AsyncOpenAI(api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL)
    
    print(f"=== 探测 {model_id} Stream + Thinking + JSON Mode ===")
    
    try:
        stream = await client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "你是一个助手。请分析海油工程的财务优势。必须严格输出 JSON 格式，包含 'advantage' (list) 和 'summary' (str) 键。"},
                {"role": "user", "content": "开始分析。"}
            ],
            extra_body={"enable_thinking": True},
            response_format={"type": "json_object"},
            stream=True
        )
        
        full_content = ""
        has_reasoning = False
        
        print("  - 正在接收流...")
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            
            # 检查推理内容
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                has_reasoning = True
            
            # 检查正文内容
            if delta.content:
                full_content += delta.content
        
        print("  - ✅ 流式接收完成！")
        print(f"  - 推理链 (Reasoning): {'已获取' if has_reasoning else '未返回'}")
        print(f"  - 最终 JSON: {full_content.strip()}")
        
        try:
            json.loads(full_content)
            print("  - ✅ JSON 结构校验: 成功")
        except:
            print("  - ❌ JSON 结构校验: 失败")
            
    except Exception as e:
        print(f"  - ❌ 流式请求执行失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_qwen35_plus_stream())

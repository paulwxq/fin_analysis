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

async def test_qwen35_plus_compatibility():
    model_id = "qwen3.5-plus"
    client = AsyncOpenAI(api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL)
    
    print(f"=== 开始探测 {model_id} Thinking + JSON Mode 兼容性 ===")
    
    # 测试场景：同时传递 enable_thinking 和 response_format
    try:
        print(f"\n[测试] 尝试调用 {model_id} (Thinking=True, JSON_Mode=True) ...")
        response = await client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "你是一个助手。请计算 12345 * 6789。必须严格输出 JSON 格式，包含 'answer' 键。"},
                {"role": "user", "content": "开始计算。"}
            ],
            extra_body={"enable_thinking": True},
            response_format={"type": "json_object"},
            stream=False
        )
        
        msg = response.choices[0].message
        content = msg.content
        reasoning = getattr(msg, 'reasoning_content', None)
        
        print("  - ✅ 请求成功！")
        print(f"  - 推理内容 (Reasoning): {'已获取' if reasoning else '未返回'}")
        print(f"  - 最终内容 (Content): {content.strip()}")
        
        # 验证是否为合法 JSON
        try:
            json.loads(content)
            print("  - ✅ JSON 结构校验: 成功")
        except:
            print("  - ❌ JSON 结构校验: 失败")
            
    except Exception as e:
        print(f"  - ❌ 请求执行失败。")
        print(f"  - 错误详情: {e}")

if __name__ == "__main__":
    asyncio.run(test_qwen35_plus_compatibility())

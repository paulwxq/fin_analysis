import asyncio
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

# 加载 .env
load_dotenv()

# 添加项目根目录到路径
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from stock_analyzer.llm_helpers import extract_json_str

async def test_qwen_thinking_json_modes():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL")
    model_id = "qwen-plus"
    
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    
    print(f"=== 探测 {model_id} Thinking + JSON 兼容性 ===")

    # 场景 1: Thinking + Stream + API 级别 JSON Mode
    print("\n[测试 1] Thinking + Stream + response_format={'type': 'json_object'}")
    try:
        response = await client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Output JSON only."},
                {"role": "user", "content": "9.11 和 9.9 哪个大？以 JSON 格式输出，键名为 'result'。"}
            ],
            extra_body={"enable_thinking": True},
            stream=True,
            response_format={"type": "json_object"}
        )
        print("  - 请求成功发送，正在接收流...")
        async for chunk in response:
            pass
        print("  - ✅ 结论: API 级别 JSON Mode 兼容")
    except Exception as e:
        print(f"  - ❌ 结论: 不兼容。错误信息: {e}")

    # 场景 2: Thinking + Stream + Prompt 约束 JSON
    print("\n[测试 2] Thinking + Stream + Prompt 约束 (手动提取 JSON)")
    try:
        response = await client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "你是一个助手。必须严格输出 JSON 格式，不要有 Markdown 标签。"},
                {"role": "user", "content": "计算 12345 * 6789 并给出逻辑。JSON 包含 'answer' 字段。"}
            ],
            extra_body={"enable_thinking": True},
            stream=True
        )
        
        full_text = ""
        has_reasoning = False
        async for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    has_reasoning = True
                if delta.content:
                    full_text += delta.content
        
        print(f"  - 推理链检测: {'检测到' if has_reasoning else '未发现'}")
        print(f"  - 原始输出预览: {full_text.strip()[:100]}...")
        
        try:
            json_str = extract_json_str(full_text)
            parsed = json.loads(json_str)
            print(f"  - ✅ JSON 提取解析: 成功! 结果: {parsed}")
        except Exception as parse_err:
            print(f"  - ❌ JSON 提取解析: 失败。错误: {parse_err}")

    except Exception as e:
        print(f"  - 请求执行失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_qwen_thinking_json_modes())

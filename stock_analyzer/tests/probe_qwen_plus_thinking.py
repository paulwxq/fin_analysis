"""Probe: qwen-plus + thinking + stream, prompt-only JSON constraint (no response_format)."""
import asyncio
import json
import re

from dotenv import load_dotenv
load_dotenv()

from stock_analyzer.config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL
from openai import AsyncOpenAI


async def main():
    client = AsyncOpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url=DASHSCOPE_BASE_URL,
        timeout=600,
    )

    print("=== qwen-plus + thinking + stream (no response_format, prompt-only JSON) ===\n")
    stream = await client.chat.completions.create(
        model="qwen-plus",
        stream=True,
        extra_body={"enable_thinking": True},
        messages=[
            {"role": "system", "content": "你是一个金融分析助手。你必须严格输出 JSON 格式，不要输出任何 JSON 之外的内容。"},
            {"role": "user", "content": '请对"贵州茅台"给出简短评价。输出格式：{"score": 0-10, "comment": "一句话评价"}'},
        ],
    )

    text_chunks = []
    reasoning_chunks = []

    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            reasoning_chunks.append(delta.reasoning_content)
        if delta.content:
            text_chunks.append(delta.content)

    reasoning_text = "".join(reasoning_chunks)
    final_text = "".join(text_chunks)

    print(f"Reasoning: {len(reasoning_text)} chars")
    if reasoning_text:
        print(f"  Preview: {reasoning_text[:200]}...\n")

    print(f"Final text: {len(final_text)} chars")
    print(f"  Content:\n{final_text}\n")

    # Try JSON parse
    try:
        parsed = json.loads(final_text.strip())
        print(f"JSON parse: SUCCESS\n  {parsed}")
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*\n([\s\S]*?)```", final_text)
        if match:
            parsed = json.loads(match.group(1).strip())
            print(f"JSON parse (from code block): SUCCESS\n  {parsed}")
        else:
            print("JSON parse: FAILED")


asyncio.run(main())

import asyncio
import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("DASHSCOPE_API_KEY")
base_url = os.getenv("DASHSCOPE_BASE_URL")

async def test_model_json(model_name):
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    results = {
        "model": model_name,
        "json_object_support": False,
        "json_output_quality": "unknown",
        "error_with_format": None,
        "content_without_format": None
    }
    
    print(f"\n[Probe] Testing model: {model_name}")
    
    # Attempt 1: With response_format={"type": "json_object"}
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Please output your response in JSON format. The JSON should have keys 'greeting' and 'status'."},
                {"role": "user", "content": "Give me a simple greeting in JSON."}
            ],
            response_format={"type": "json_object"}
        )
        results["json_object_support"] = True
        print(f"  - Attempt 1 (json_object): SUCCESS")
    except Exception as e:
        results["error_with_format"] = str(e)
        print(f"  - Attempt 1 (json_object): FAILED")

    # Attempt 2: Without response_format, but asking for JSON in prompt
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. YOU MUST ONLY OUTPUT JSON. DO NOT USE MARKDOWN BACKTICKS (```json). JUST THE RAW JSON STRING. The JSON should have keys 'greeting' and 'status'."},
                {"role": "user", "content": "Give me a simple greeting in JSON."}
            ]
        )
        content = response.choices[0].message.content.strip()
        results["content_without_format"] = content
        
        # Try to parse it
        try:
            json.loads(content)
            results["json_output_quality"] = "Valid Raw JSON"
            print(f"  - Attempt 2 (Prompt-only): SUCCESS (Valid JSON)")
        except json.JSONDecodeError:
            # Check if it has markdown backticks
            if "```json" in content or "```" in content:
                # Try to extract from backticks
                try:
                    inner = content.split("```")[1]
                    if inner.startswith("json"):
                        inner = inner[4:]
                    json.loads(inner.strip())
                    results["json_output_quality"] = "Valid JSON within Markdown"
                    print(f"  - Attempt 2 (Prompt-only): SUCCESS (Valid JSON within Markdown)")
                except:
                    results["json_output_quality"] = "Invalid JSON"
                    print(f"  - Attempt 2 (Prompt-only): FAILED (Malformed JSON)")
            else:
                results["json_output_quality"] = "Invalid JSON"
                print(f"  - Attempt 2 (Prompt-only): FAILED (Malformed JSON)")
    except Exception as e:
        print(f"  - Attempt 2 (Prompt-only): CRITICAL FAILURE ({e})")

    return results

async def main():
    models = ["glm-4.7", "kimi-k2.5", "MiniMax-M2.1", "deepseek-v3.2"]
    final_results = []
    for m in models:
        res = await test_model_json(m)
        final_results.append(res)
    
    print("\n" + "="*50)
    print("FINAL PROBE RESULTS")
    print("="*50)
    for res in final_results:
        print(f"Model: {res['model']}")
        print(f"  Supports response_format='json_object': {'YES' if res['json_object_support'] else 'NO'}")
        if not res['json_object_support']:
            err_msg = str(res['error_with_format'])[:80]
            print(f"  Reason: {err_msg}...")
        print(f"  Natural JSON Output Quality: {res['json_output_quality']}")
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(main())

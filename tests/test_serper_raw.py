import os
import json
import httpx
import asyncio
from dotenv import load_dotenv

async def test_serper():
    load_dotenv()
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("Error: SERPER_API_KEY not found in .env")
        return

    url = "https://google.serper.dev/search"
    # 搜索 603080.SH 的新闻
    payload = json.dumps({
        "q": "603080.SH 新闻 2025",
        "num": 10,
        "hl": "zh-cn",
        "gl": "cn"
    })
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }

    print(f"Testing Serper API with query: 603080.SH 新闻 2025")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, data=payload, timeout=10.0)
            print(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print("--- Search Results (Organic) ---")
                organic = data.get("organic", [])
                for i, result in enumerate(organic):
                    print(f"{i+1}. {result.get('title')}")
                    print(f"   Link: {result.get('link')}")
                    print(f"   Snippet: {result.get('snippet')}\n")
                
                if not organic:
                    print("No organic results found.")
                    print(f"Full response: {data}")
            else:
                print(f"Error Response: {response.text}")
        except Exception as e:
            print(f"Request failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_serper())

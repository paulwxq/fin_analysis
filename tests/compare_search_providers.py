import asyncio
import os
import json
import httpx
from tavily import TavilyClient

# 手动加载 .env
def load_env_manual():
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    parts = line.strip().split("=", 1)
                    if len(parts) == 2:
                        os.environ[parts[0]] = parts[1]

load_env_manual()

async def fetch_serper(query: str, max_results: int = 3):
    api_key = os.getenv("SERPER_API_KEY")
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": max_results, "hl": "zh-cn", "gl": "cn"})
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, data=payload)
        return response.json()

async def fetch_tavily(query: str, max_results: int = 3):
    api_key = os.getenv("TAVILY_API_KEY")
    client = TavilyClient(api_key=api_key)
    # 使用 advanced 模式
    return client.search(query, search_depth="advanced", max_results=max_results, include_raw_content=True)

async def main():
    query = "英伟达最新财报深度分析 2025 Q3 业绩表现"
    print(f"Query: {query}")
    print("=" * 50)

    # 1. 测试 SERPER
    print("\n[SERPER.dev (Google Search API)]")
    serper_res = await fetch_serper(query)
    organic = serper_res.get("organic", [])
    if organic:
        first = organic[0]
        snippet = first.get("snippet", "")
        print(f"Title: {first.get('title')}")
        print(f"URL: {first.get('link')}")
        print(f"Content Length (Snippet): {len(snippet)}")
        print(f"Snippet Preview: {snippet[:150]}...")
        print(f"Raw Content available? {'raw_content' in first}")
    else:
        print("No results from Serper.")

    # 2. 测试 TAVILY
    print("\n" + "-" * 50)
    print("[TAVILY (AI Research Optimized)]")
    tavily_res = await fetch_tavily(query)
    results = tavily_res.get("results", [])
    if results:
        first = results[0]
        content = first.get("content", "")
        raw_content = first.get("raw_content", "")
        print(f"Title: {first.get('title')}")
        print(f"URL: {first.get('url')}")
        print(f"Content Length (Standard): {len(content)}")
        print(f"Raw Content Length: {len(str(raw_content))}")
        print(f"Content Preview: {content[:150]}...")
        if raw_content:
             print(f"Raw Content (first 150 chars): {str(raw_content)[:150]}...")
    else:
        print("No results from Tavily.")

    print("\n" + "=" * 50)
    print("Conclusion:")
    print("1. SERPER 返回的是 Google 搜索结果的 'Snippet'，通常只有 100-200 字符。")
    print("2. TAVILY 的 'content' 通常是网页抓取后的清洗文本，长度通常显著大于 Serper。")
    print("3. TAVILY 的 'raw_content' 提供了网页的完整文本，适合大模型深度阅读。")

if __name__ == "__main__":
    asyncio.run(main())
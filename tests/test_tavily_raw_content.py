import asyncio
import os
import json
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

async def test_tavily_params():
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        print("Error: TAVILY_API_KEY not found in environment")
        return

    client = TavilyClient(api_key=api_key)
    query = "NVIDIA latest financial results"

    print("\n--- Testing with include_raw_content=False (Default) ---")
    resp_default = client.search(query, search_depth="advanced", max_results=1)
    
    results = resp_default.get("results", [])
    if not results:
        print("No results found.")
    for i, res in enumerate(results):
        keys = list(res.keys())
        print(f"Result {i} keys: {keys}")
        if "raw_content" in res:
            print("  [!] Found raw_content unexpectedly!")
        else:
            print("  [OK] No raw_content found.")

    print("\n--- Testing with include_raw_content=True ---")
    resp_raw = client.search(query, search_depth="advanced", max_results=1, include_raw_content=True)
    
    results_raw = resp_raw.get("results", [])
    if not results_raw:
        print("No results found.")
    for i, res in enumerate(results_raw):
        keys = list(res.keys())
        print(f"Result {i} keys: {keys}")
        if "raw_content" in res:
            content_len = len(str(res["raw_content"]))
            print(f"  [SUCCESS] Found raw_content! Length: {content_len}")
        else:
            print("  [FAIL] raw_content NOT found even with include_raw_content=True")

if __name__ == "__main__":
    asyncio.run(test_tavily_params())
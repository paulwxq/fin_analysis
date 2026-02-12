"""Quick runner for module B web research — run directly to test.

Usage (from project root):
    .venv/bin/python3 stock_analyzer/run_module_b.py
    .venv/bin/python3 stock_analyzer/run_module_b.py 600519.SH 贵州茅台 白酒
"""

import asyncio
import json
import sys
from pathlib import Path

# Allow running from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from stock_analyzer.module_b_websearch import run_web_research  # noqa: E402


async def main() -> None:
    # Default stock; override via CLI: symbol name industry
    symbol = sys.argv[1] if len(sys.argv) > 1 else "600000.SH"
    name = sys.argv[2] if len(sys.argv) > 2 else "浦发银行"
    industry = sys.argv[3] if len(sys.argv) > 3 else "金融"

    print(f"[module B] 开始研究: {symbol} {name} ({industry})\n")

    result = await run_web_research(symbol=symbol, name=name, industry=industry)

    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

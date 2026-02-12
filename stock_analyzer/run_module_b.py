"""Quick runner for module B web research — run directly to test.

Usage (from project root):
    .venv/bin/python3 stock_analyzer/run_module_b.py
    .venv/bin/python3 stock_analyzer/run_module_b.py 600519.SH 贵州茅台 白酒
"""

import asyncio
import sys
from pathlib import Path

# Allow running from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from stock_analyzer.module_b_websearch import (  # noqa: E402
    dump_web_research_result_json,
    run_web_research,
)


async def main() -> None:
    if len(sys.argv) != 4:
        print(
            "Usage: .venv/bin/python3 stock_analyzer/run_module_b.py "
            "<symbol> <name> <industry>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    symbol = sys.argv[1]
    name = sys.argv[2]
    industry = sys.argv[3]

    print(f"[module B] 开始研究: {symbol} {name} ({industry})\n")

    result = await run_web_research(symbol=symbol, name=name, industry=industry)
    json_str = dump_web_research_result_json(result)
    print(json_str)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{symbol}_web_research.json"
    output_path.write_text(json_str, encoding="utf-8")
    print(f"\n[module B] 结果已保存到 {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

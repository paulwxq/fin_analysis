"""Quick runner for module C technical analysis.

Usage (from project root):
    .venv/bin/python3 stock_analyzer/run_module_c.py 600519 贵州茅台
    .venv/bin/python3 stock_analyzer/run_module_c.py 600519.SH 贵州茅台
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running from any working directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

from stock_analyzer.module_c_technical import (  # noqa: E402
    dump_technical_result_json,
    run_technical_analysis,
)
from stock_analyzer.utils import normalize_symbol  # noqa: E402


async def main() -> None:
    if len(sys.argv) != 3:
        print(
            "Usage: .venv/bin/python3 stock_analyzer/run_module_c.py "
            "<symbol> <name>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    raw_symbol = sys.argv[1]
    name = sys.argv[2]
    symbol = normalize_symbol(raw_symbol)

    print(f"[module C] 开始技术分析: {symbol} {name}\n")

    result = await run_technical_analysis(symbol=symbol, name=name)
    json_str = dump_technical_result_json(result)
    print(json_str)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{symbol}_technical_analysis.json"
    output_path.write_text(json_str, encoding="utf-8")
    print(f"\n[module C] 结果已保存到 {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

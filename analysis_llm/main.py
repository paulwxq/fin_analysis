"""CLI entry for Step 1 analysis workflow."""
from __future__ import annotations

import asyncio
import sys

from .workflow import execute_step1
from .utils import init_logging


async def _main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m analysis_llm.main <STOCK_CODE>")
        raise SystemExit(1)

    stock_code = sys.argv[1]
    result = await execute_step1(stock_code)
    print(result.model_dump_json(ensure_ascii=False, indent=2))


if __name__ == "__main__":
    init_logging()
    asyncio.run(_main())

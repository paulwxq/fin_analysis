"""CLI entry point for the full A/B/C/D workflow pipeline.

Usage (from project root):
    .venv/bin/python3 stock_analyzer/run_workflow.py <symbol>

    <symbol> supports: 600519 / 600519.SH / SH600519
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stock_analyzer.config import WORKFLOW_OUTPUT_DIR              # noqa: E402
from stock_analyzer.exceptions import (                            # noqa: E402
    ChiefAnalysisError,
    StockInfoLookupError,
    WorkflowCircuitBreakerError,
)
from stock_analyzer.logger import logger                           # noqa: E402
from stock_analyzer.module_d_chief import dump_final_report_json  # noqa: E402
from stock_analyzer.workflow import run_workflow                   # noqa: E402


async def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: .venv/bin/python3 stock_analyzer/run_workflow.py <symbol>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    raw_symbol = sys.argv[1].strip()

    try:
        print(f"[workflow] 开始全流程分析: {raw_symbol}\n", file=sys.stderr)
        final_report = await run_workflow(raw_symbol)

        json_str = dump_final_report_json(final_report)
        print(json_str)

        output_dir = Path(WORKFLOW_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        symbol = final_report.meta.symbol
        output_path = output_dir / f"{symbol}_final_report.json"
        output_path.write_text(json_str, encoding="utf-8")
        print(f"\n[workflow] 最终报告已保存到 {output_path}", file=sys.stderr)

    except ValueError as e:
        logger.error(f"Workflow input error: {e}")
        print(f"[workflow] 输入错误: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    except StockInfoLookupError as e:
        logger.error(f"Workflow stock info lookup failed: {e}")
        print(f"[workflow] 股票信息查询失败: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    except WorkflowCircuitBreakerError as e:
        logger.error(f"Workflow circuit breaker triggered: {e}")
        print(f"[workflow] 熔断触发，作业中止: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    except ChiefAnalysisError as e:
        logger.error(f"Workflow chief analysis failed: {e}")
        print(f"[workflow] 首席分析失败: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    except Exception as e:
        logger.exception(f"Workflow unexpected failure: {type(e).__name__}: {e}")
        print(f"[workflow] 未预期错误: {type(e).__name__}: {e}", file=sys.stderr)
        print("[workflow] 详细信息请查看 logs/stock_analyzer.log", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    asyncio.run(main())

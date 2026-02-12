"""Quick runner for module A AKShare data collection.

Usage (from project root):
    .venv/bin/python3 stock_analyzer/run_module_a.py 600519 贵州茅台
    .venv/bin/python3 stock_analyzer/run_module_a.py 600519.SH 贵州茅台
"""

import json
import sys
from pathlib import Path

# Allow running from any working directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

from stock_analyzer.exceptions import AKShareError  # noqa: E402
from stock_analyzer.logger import logger  # noqa: E402
from stock_analyzer.module_a_akshare import collect_akshare_data  # noqa: E402
from stock_analyzer.utils import normalize_symbol  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "Usage: .venv/bin/python3 stock_analyzer/run_module_a.py "
            "<symbol> <name>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    raw_symbol = sys.argv[1]
    name = sys.argv[2]

    try:
        symbol = normalize_symbol(raw_symbol)
        if not name.strip():
            raise ValueError("name cannot be empty")

        print(f"[module A] 开始采集: {symbol} {name}\n")

        result = collect_akshare_data(symbol=symbol, name=name)

        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))

        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"{symbol}_akshare_data.json"
        output_path.write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n[module A] 结果已保存到 {output_path}")
    except ValueError as e:
        logger.error(f"Module A input error: {e}")
        print(f"[module A] 输入错误: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    except AKShareError as e:
        logger.error(f"Module A failed: {e}")
        print(f"[module A] 运行失败: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    except Exception as e:
        logger.exception(f"Module A unexpected failure: {type(e).__name__}: {e}")
        print(f"[module A] 未预期错误: {type(e).__name__}: {e}", file=sys.stderr)
        print(
            "[module A] 详细信息请查看 logs/stock_analyzer.log",
            file=sys.stderr,
        )
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()

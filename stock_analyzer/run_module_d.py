"""Quick runner for module D chief analysis.

Usage (from project root):
    .venv/bin/python3 stock_analyzer/run_module_d.py \
      <symbol> <name> <akshare_json_path> <web_json_path> <technical_json_path>
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

# Allow running from any working directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import ValidationError  # noqa: E402

from stock_analyzer.exceptions import ChiefAnalysisError, ChiefInputError  # noqa: E402
from stock_analyzer.logger import logger  # noqa: E402
from stock_analyzer.models import WebResearchResult  # noqa: E402
from stock_analyzer.module_a_models import AKShareData  # noqa: E402
from stock_analyzer.module_c_models import TechnicalAnalysisResult  # noqa: E402
from stock_analyzer.module_d_chief import (  # noqa: E402
    dump_final_report_json,
    run_chief_analysis,
)
from stock_analyzer.utils import normalize_symbol  # noqa: E402


def _load_json(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Input JSON not found: {path}")
    return path.read_text(encoding="utf-8")


async def main() -> None:
    if len(sys.argv) != 6:
        print(
            "Usage: .venv/bin/python3 stock_analyzer/run_module_d.py "
            "<symbol> <name> <akshare_json_path> <web_json_path> <technical_json_path>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    raw_symbol = sys.argv[1]
    name = sys.argv[2]
    akshare_json_path = Path(sys.argv[3])
    web_json_path = Path(sys.argv[4])
    technical_json_path = Path(sys.argv[5])

    try:
        symbol = normalize_symbol(raw_symbol)
        print(f"[module D] 开始综合分析: {symbol} {name}\n")

        akshare_data = AKShareData.model_validate_json(_load_json(akshare_json_path))
        web_research = WebResearchResult.model_validate_json(_load_json(web_json_path))
        technical_analysis = TechnicalAnalysisResult.model_validate_json(
            _load_json(technical_json_path)
        )

        final_report = await run_chief_analysis(
            symbol=symbol,
            name=name,
            akshare_data=akshare_data,
            web_research=web_research,
            technical_analysis=technical_analysis,
        )
        json_str = dump_final_report_json(final_report)
        print(json_str)

        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"{symbol}_final_report.json"
        output_path.write_text(json_str, encoding="utf-8")
        print(f"\n[module D] 结果已保存到 {output_path}")
    except (FileNotFoundError, ValidationError, ValueError) as e:
        logger.error(f"Module D input error: {type(e).__name__}: {e}")
        print(f"[module D] 输入错误: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    except ChiefInputError as e:
        logger.error(f"Module D input validation failed: {e}")
        print(f"[module D] 输入校验失败: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    except ChiefAnalysisError as e:
        logger.error(f"Module D chief analysis failed: {e}")
        print(f"[module D] 综合分析失败: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    except Exception as e:
        logger.exception(f"Module D unexpected failure: {type(e).__name__}: {e}")
        print(f"[module D] 未预期错误: {type(e).__name__}: {e}", file=sys.stderr)
        print(
            "[module D] 详细信息请查看 logs/stock_analyzer.log",
            file=sys.stderr,
        )
        raise SystemExit(1) from e


if __name__ == "__main__":
    asyncio.run(main())

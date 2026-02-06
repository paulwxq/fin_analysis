import argparse
import asyncio
import json
import sys
from pathlib import Path

from .models import Step1Output
from .workflow import ScoringWorkflow, execute_step1


async def _main():
    parser = argparse.ArgumentParser(description="Stock Analysis LLM Pipeline")
    parser.add_argument("stock_code", nargs="?", help="Stock code (e.g., 603080.SH)")
    parser.add_argument("--step", type=int, choices=[1, 2], help="Execute only specific step")
    parser.add_argument("--input", type=Path, help="Input JSON file for Step 2 (required if --step 2 is used alone)")
    
    args = parser.parse_args()

    # 场景 1: 只运行 Step 2 (需要 input 文件)
    if args.step == 2:
        if not args.input or not args.input.exists():
            print("Error: --input file is required for Step 2 standalone execution.")
            sys.exit(1)
        
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        step1_output = Step1Output.model_validate(data)
        scoring_wf = ScoringWorkflow()
        final_recommendation = await scoring_wf.run(step1_output)
        print(final_recommendation.model_dump_json(indent=2))
        return

    # 场景 2: 运行 Step 1 (如果是全流程，这也是第一步)
    if not args.stock_code:
        print("Error: stock_code is required for Step 1 or full pipeline.")
        sys.exit(1)

    step1_output = await execute_step1(args.stock_code)

    # 如果只要求跑 Step 1，打印结果并退出
    if args.step == 1:
        print(step1_output.model_dump_json(indent=2))
        return

    # 场景 3: 全流程 (默认) -> 继续运行 Step 2
    # 将 Step 1 的内存对象直接传给 Step 2
    scoring_wf = ScoringWorkflow()
    final_recommendation = await scoring_wf.run(step1_output)
    print(final_recommendation.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(_main())

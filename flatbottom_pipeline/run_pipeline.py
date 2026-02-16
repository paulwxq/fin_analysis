"""
flatbottom_pipeline 统一编排入口

薄编排层：按阶段顺序执行 preflight 检查 + 子模块调用。
各子模块保持独立的 argparse 参数体系，本入口不封装子模块参数。

用法：
  python -m flatbottom_pipeline.run_pipeline --step select
  python -m flatbottom_pipeline.run_pipeline --step plot
  python -m flatbottom_pipeline.run_pipeline --step refine
  python -m flatbottom_pipeline.run_pipeline --step all
  python -m flatbottom_pipeline.run_pipeline --preflight-only
"""
import argparse
import glob
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_pipeline")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

def _get_db_connection():
    """获取数据库连接（复用 load_data 公共模块）"""
    from load_data.db import get_db_connection
    return get_db_connection()


def check_db_connection() -> bool:
    """检查数据库可连接"""
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        logger.info("[preflight] 数据库连接正常")
        return True
    except Exception as e:
        logger.error(f"[preflight] 数据库连接失败: {e}")
        logger.error("  → 请检查 .env 中的 DB_HOST / DB_PORT / DB_USER / DB_PASS / DB_NAME")
        return False


def check_monthly_kline() -> bool:
    """检查 stock_monthly_kline 视图存在且非空"""
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                # 存在性检查
                cur.execute("SELECT to_regclass('public.stock_monthly_kline')")
                result = cur.fetchone()
                if result is None or result[0] is None:
                    logger.error("[preflight] stock_monthly_kline 视图不存在")
                    logger.error("  → 请先运行: python -m load_data.aggregate")
                    return False
                # 非空性检查
                cur.execute("SELECT 1 FROM stock_monthly_kline LIMIT 1")
                if cur.fetchone() is None:
                    logger.error("[preflight] stock_monthly_kline 视图为空（无数据）")
                    logger.error("  → 请先运行: python -m load_data.aggregate --force-backfill")
                    return False
        logger.info("[preflight] stock_monthly_kline 视图就绪")
        return True
    except Exception as e:
        logger.error(f"[preflight] stock_monthly_kline 检查失败: {e}")
        return False


def check_preselect_table() -> bool:
    """检查 stock_flatbottom_preselect 表有数据"""
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM stock_flatbottom_preselect LIMIT 1")
                if cur.fetchone() is None:
                    logger.error("[preflight] stock_flatbottom_preselect 表为空")
                    logger.error("  → 请先运行: python -m flatbottom_pipeline.run_pipeline --step select")
                    return False
        logger.info("[preflight] stock_flatbottom_preselect 表有数据")
        return True
    except Exception as e:
        logger.error(f"[preflight] stock_flatbottom_preselect 检查失败: {e}")
        logger.error("  → 请先运行: python -m flatbottom_pipeline.run_pipeline --step select")
        return False


def check_kline_images() -> bool:
    """检查 output/ 目录下存在 K 线图文件"""
    output_dir = PROJECT_ROOT / "output"
    images = glob.glob(str(output_dir / "*_kline.png"))
    if not images:
        logger.error(f"[preflight] {output_dir} 下未找到 *_kline.png 文件")
        logger.error("  → 请先运行: python -m flatbottom_pipeline.run_pipeline --step plot")
        return False
    logger.info(f"[preflight] 找到 {len(images)} 个 K 线图文件")
    return True


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------

def _run_module(module_path: str, stop_on_error: bool) -> bool:
    """通过 subprocess 调用子模块"""
    cmd = [sys.executable, "-m", module_path]
    logger.info(f"执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        logger.error(f"阶段失败 (exit code {result.returncode}): {module_path}")
        if stop_on_error:
            logger.error("--stop-on-error 已启用，终止流水线")
            return False
    return True


STAGES = {
    "select": {
        "module": "flatbottom_pipeline.selection.find_flatbottom",
        "preflight": [check_db_connection, check_monthly_kline],
        "description": "规则筛选（平底锅形态识别）",
    },
    "plot": {
        "module": "flatbottom_pipeline.visualization.plot_kline",
        "preflight": [check_db_connection, check_preselect_table],
        "description": "K 线图生成",
    },
    "refine": {
        "module": "flatbottom_pipeline.refinement_llm.main",
        "preflight": [check_kline_images],
        "description": "LLM 视觉评分（细化打分）",
    },
}

STAGE_ORDER = ["select", "plot", "refine"]


def run_preflight(stage_name: str) -> bool:
    """执行指定阶段的前置条件检查"""
    stage = STAGES[stage_name]
    for check_fn in stage["preflight"]:
        if not check_fn():
            return False
    return True


def run_preflight_all() -> bool:
    """一次性检查所有阶段的前置条件（用于 --preflight-only 环境诊断）"""
    logger.info("=" * 60)
    logger.info("Preflight Check（全量环境诊断）")
    logger.info("=" * 60)
    all_ok = True
    for stage_name in STAGE_ORDER:
        logger.info(f"\n--- {stage_name}: {STAGES[stage_name]['description']} ---")
        if not run_preflight(stage_name):
            all_ok = False
    logger.info("=" * 60)
    if all_ok:
        logger.info("所有前置条件满足，可以运行 --step all")
    else:
        logger.warning("部分前置条件不满足，请根据上方提示修复")
    return all_ok


def run_stage(stage_name: str, skip_preflight: bool, stop_on_error: bool) -> bool:
    """执行单个阶段（preflight + run）"""
    stage = STAGES[stage_name]
    logger.info(f"\n{'='*60}")
    logger.info(f"阶段: {stage_name} — {stage['description']}")
    logger.info(f"{'='*60}")

    if not skip_preflight:
        if not run_preflight(stage_name):
            return False

    return _run_module(stage["module"], stop_on_error)


def main():
    parser = argparse.ArgumentParser(
        description="flatbottom_pipeline 统一编排入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python -m flatbottom_pipeline.run_pipeline --step all
  python -m flatbottom_pipeline.run_pipeline --step select
  python -m flatbottom_pipeline.run_pipeline --preflight-only
        """,
    )
    parser.add_argument(
        "--step",
        choices=["select", "plot", "refine", "all"],
        default="all",
        help="选择执行阶段（默认: all）",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="仅执行前置条件检查，不运行任何阶段",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="跳过前置条件检查（高级用户）",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        default=True,
        help="某阶段失败时终止流水线（默认: True）",
    )
    parser.add_argument(
        "--no-stop-on-error",
        action="store_false",
        dest="stop_on_error",
        help="某阶段失败时继续执行后续阶段",
    )

    args = parser.parse_args()

    # --preflight-only 模式
    if args.preflight_only:
        ok = run_preflight_all()
        sys.exit(0 if ok else 1)

    # 确定要执行的阶段列表
    if args.step == "all":
        stages_to_run = STAGE_ORDER
    else:
        stages_to_run = [args.step]

    # 逐阶段执行 preflight → run
    for stage_name in stages_to_run:
        ok = run_stage(stage_name, args.skip_preflight, args.stop_on_error)
        if not ok and args.stop_on_error:
            sys.exit(1)

    logger.info("\n流水线执行完成")


if __name__ == "__main__":
    main()

import argparse
import os
import sys
import logging
import pandas as pd
import mplfinance as mpf
import psycopg
from datetime import datetime
from load_data.db import get_db_connection
from load_data.stock_code import classify_cn_stock

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def _dedupe_preserve_order(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result

def load_codes_from_table(limit: int | None = None):
    """
    Load stock codes from a preselect table (ordered by score desc).
    """
    sql = "SELECT code FROM public.stock_flatbottom_preselect ORDER BY score DESC"
    params = None
    if limit is not None and limit > 0:
        sql += " LIMIT %s"
        params = (limit,)
    sql += ";"
    try:
        conn = get_db_connection()
        df = pd.read_sql(sql, conn, params=params)
        conn.close()
    except Exception as e:
        logger.error(f"Failed to load codes from table 'public.stock_flatbottom_preselect': {e}")
        return []

    return df['code'].dropna().astype(str).tolist()

def process_stock(raw_code, args):
    """
    处理单只股票的核心逻辑：标准化 -> 查询 -> 绘图 -> 保存
    返回: True (成功) / False (失败)
    """
    # 1. 代码标准化
    try:
        code_info = classify_cn_stock(raw_code)
        std_code = code_info.ts_code
    except ValueError as e:
        logger.error(f"Skipping invalid code '{raw_code}': {e}")
        return False

    # 2. 数据查询
    sql = """
    SELECT month as "Date", open as "Open", high as "High", 
           low as "Low", close as "Close", volume / 10000.0 as "Volume" 
    FROM stock_monthly_kline
    WHERE code = %s AND month >= %s AND month <= %s
    ORDER BY month ASC;
    """
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'Asia/Shanghai';")
        
        # 使用原生连接读取，可能会有 Pandas UserWarning，已知且无害
        df = pd.read_sql(sql, conn, params=(std_code, args.start, args.end))
        conn.close()
    except Exception as e:
        logger.error(f"[{std_code}] Database error: {e}")
        return False

    if df.empty:
        logger.warning(f"[{std_code}] No data found in range {args.start}~{args.end}.")
        return False
        
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    
    # 防御性检查
    if not (df['High'] >= df[['Open', 'Close']].max(axis=1)).all():
        logger.warning(f"[{std_code}] Caution: Inconsistent price data detected (High < Open/Close).")

    # 3. 动态标题时间 (使用数据中的真实起止时间)
    actual_start = df.index.min().strftime('%Y-%m-%d')
    actual_end = df.index.max().strftime('%Y-%m-%d')

    # 4. 渲染与保存逻辑
    # 判断是否为批量模式 (有文件输入，或者同时处理文件和单个代码)
    is_batch = args.file is not None
    
    # 批量模式强制使用默认命名，防止 --out 导致覆盖
    default_name = f"output/{std_code}_kline.png"
    
    if is_batch:
        out_path = default_name
    else:
        # 单股模式：优先使用 --out，其次默认，如果是 show 模式则为 None
        out_path = None if args.show else (args.out or default_name)
    
    if out_path:
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)

    try:
        mpf.plot(
            df,
            type='candle',
            mav=(5, 10, 20, 30),
            volume=True,
            ylabel='Price (CNY)',
            ylabel_lower='Volume (10k Shares)',
            title=f"{std_code} Monthly ({actual_start} ~ {actual_end})",
            style='yahoo',
            savefig=out_path,
            closefig=not args.show  # show模式下不关闭，否则关闭以释放内存
        )
        if out_path:
            logger.info(f"[{std_code}] Saved to {out_path}")
        return True
    except Exception as e:
        logger.error(f"[{std_code}] Plotting failed: {e}")
        return False

def main():
    # 参数解析调整：code 变为可选位置参数，增加 -f 可选参数
    parser = argparse.ArgumentParser(description='Plot monthly K-line chart (Batch Support)')
    parser.add_argument('code', nargs='?', help='Stock code (optional if -f is used)')
    parser.add_argument('-f', '--file', help='Batch file path (one code per line)')
    parser.add_argument(
        '--from-preselect-table',
        action='store_true',
        help='Load codes from public.stock_flatbottom_preselect'
    )
    parser.add_argument(
        '--preselect-limit',
        type=int,
        default=-1,
        help='Limit number of codes loaded from preselect table (-1 means no limit)'
    )
    
    parser.add_argument('--start', default='2000-01-01', help='YYYY-MM-DD')
    parser.add_argument('--end', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--out', help='Output path (only effective in single stock mode)')
    parser.add_argument('--show', action='store_true', help='Show window (disabled in batch mode)')
    args = parser.parse_args()

    # GUI 环境检测
    has_gui = os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
    if args.show and not has_gui:
        logger.warning("No GUI detected. Falling back to Save Mode.")
        args.show = False

    # 1. 构建任务列表
    codes = []

    # 来源 A: 预选表
    if args.from_preselect_table:
        try:
            limit = None if args.preselect_limit is None or args.preselect_limit < 0 else args.preselect_limit
            table_codes = load_codes_from_table(limit=limit)
            codes.extend(table_codes)
            logger.info(f"Loaded {len(table_codes)} codes from table public.stock_flatbottom_preselect.")
        except Exception as e:
            logger.error(f"Failed to load codes from table: {e}")
            sys.exit(1)
    
    # 来源 B: 文件
    if args.file:
        try:
            if not os.path.exists(args.file):
                logger.error(f"File not found: {args.file}")
                sys.exit(1)
                
            with open(args.file, 'r', encoding='utf-8') as f:
                # 过滤空行和注释行
                file_codes = [line.strip() for line in f 
                              if line.strip() and not line.strip().startswith('#')]
                codes.extend(file_codes)
                logger.info(f"Loaded {len(file_codes)} codes from file.")
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            sys.exit(1)
            
    # 来源 C: 命令行参数
    if args.code:
        codes.append(args.code)

    # 去重
    codes = _dedupe_preserve_order(codes)

    # 校验
    if not codes:
        logger.error("No stock codes provided. Please provide a 'code' argument, use '-f', or set --from-preselect-table.")
        parser.print_help()
        sys.exit(1)

    # 2. 批量模式强制关闭弹窗
    if len(codes) > 1 and args.show:
        logger.warning("Batch processing detected. Disabling --show mode to prevent window storm.")
        args.show = False

    # 3. 循环处理
    logger.info(f"Starting batch task for {len(codes)} stocks...")
    success_count = 0
    
    for i, code in enumerate(codes):
        if process_stock(code, args):
            success_count += 1

    logger.info("="*30)
    logger.info(f"Batch task finished. Success: {success_count}/{len(codes)}")

if __name__ == "__main__":
    main()

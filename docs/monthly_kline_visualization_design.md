# 月K线绘图工具设计文档 (v13 - Batch Mode Support)

本文档设计了一个专业的 K 线绘图脚本 (`visualization/plot_kline.py`)，支持单只股票查询、通过文件批量生成图表，或从预选表批量读取股票代码生成图表。

## 1. 设计目标

*   **结果可视化**: 将复杂的成交数据转化为专业的金融 K 线图。
*   **批量处理**: 支持通过文件导入股票列表，一次性生成大量图表。
*   **智能环境适配**: 自动检测 GUI 环境，批量模式下自动强制保存。
*   **高鲁棒性**: 单个任务失败不影响整体批处理进度。

## 2. 技术栈与依赖

### 2.1 依赖管理 (uv)

```bash
uv add pandas "mplfinance>=0.12.7"
```

### 2.2 模块复用

*   `load_data.config`: 数据库配置。
*   `load_data.db`: 数据库连接。
*   `load_data.stock_code`: A 股标准化规则库。

## 3. 模块设计

### 3.1 文件结构

```text
/opt/fin_analysis/
├── output/             <-- (脚本自动创建)
├── visualization/
│   ├── __init__.py     
│   └── plot_kline.py   
```

### 3.2 参数交互逻辑 (CLI)

| 参数 | 必选 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `code` | 否 | - | 单个股票代码 (当未指定 `-f` 时必填) |
| `-f`, `--file` | 否 | - | 包含股票代码的文件路径 (每行一个代码) |
| `--from-preselect-table` | 否 | `False` | 从 public.stock_flatbottom_preselect 读取股票代码（按 score DESC） |
| `--preselect-limit` | 否 | `-1` | 预选表读取数量上限（-1 表示不限制） |
| `--start` | 否 | `2000-01-01` | 开始日期 (YYYY-MM-DD) |
| `--end` | 否 | `NOW()` | 结束日期 (YYYY-MM-DD) |
| `--out` | 否 | `output/{std_code}_kline.png` | 保存路径 (仅在单股模式下生效) |
| `--show` | 否 | `False` | 弹窗显示 (批量模式下强制禁用) |

### 3.3 核心逻辑流程

1.  **任务收集**:
    *   若有 `--from-preselect-table`: 读取 public.stock_flatbottom_preselect 的 code 列（按 score DESC，可选 `--preselect-limit`）。
    *   若有 `-f`: 读取文件，将每行非空代码加入任务列表。
    *   若有 `code`: 将该代码加入列表。
    *   去重后若为空: 报错退出。
2.  **模式强制**: 若任务数 > 1，强制 `show=False`，防止弹窗风暴。
3.  **循环执行**:
    *   遍历任务列表。
    *   对每个代码执行：标准化 -> 查询 -> 绘图 -> 保存。
    *   **异常隔离**: 单个股票报错（如代码错误、无数据）仅打印 Error，不中断循环。

## 4. 核心逻辑实现参考

### 4.1 主函数重构

```python
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
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def process_stock(raw_code, args):
    """处理单只股票的查询与绘图逻辑"""
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
        
        df = pd.read_sql(sql, conn, params=(std_code, args.start, args.end))
        conn.close()
    except Exception as e:
        logger.error(f"[{std_code}] Database error: {e}")
        return False

    if df.empty:
        logger.warning(f"[{std_code}] No data found.")
        return False
        
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    
    # 3. 动态标题时间
    actual_start = df.index.min().strftime('%Y-%m-%d')
    actual_end = df.index.max().strftime('%Y-%m-%d')

    # 4. 渲染与保存
    # 批量模式下忽略 --out 参数，强制使用默认命名，防止文件覆盖
    is_batch = args.file is not None or (args.code and args.file)
    default_name = f"output/{std_code}_kline.png"
    
    if is_batch:
        out_path = default_name
    else:
        out_path = None if args.show else (args.out or default_name)
    
    if out_path:
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)

    try:
        mpf.plot(
            df,
            type='candle',
            mav=(5, 10, 20),
            volume=True,
            ylabel='Price (CNY)',
            ylabel_lower='Volume (10k Shares)',
            title=f"{std_code} Monthly ({actual_start} ~ {actual_end})",
            style='yahoo',
            savefig=out_path,
            closefig=not args.show
        )
        if out_path:
            logger.info(f"[{std_code}] Saved to {out_path}")
        return True
    except Exception as e:
        logger.error(f"[{std_code}] Plotting failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Plot monthly K-line chart (Batch Support)')
    parser.add_argument('code', nargs='?', help='Stock code (optional if -f is used)')
    parser.add_argument('-f', '--file', help='Batch file path (one code per line)')
    parser.add_argument('--from-preselect-table',
                        help='Load codes from a preselect table (e.g., stock_flatbottom_preselect)')
    parser.add_argument('--start', default='2000-01-01', help='YYYY-MM-DD')
    parser.add_argument('--end', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--out', help='Output path (only for single stock mode)')
    parser.add_argument('--show', action='store_true', help='Show window (disabled in batch mode)')
    args = parser.parse_args()

    # GUI 检测
    has_gui = os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
    if args.show and not has_gui:
        logger.warning("No GUI detected. Falling back to Save Mode.")
        args.show = False

    # 构建任务列表
    codes = []
    if args.from_preselect_table:
        try:
            table_codes = load_codes_from_table(args.from_preselect_table)
            codes.extend(table_codes)
        except Exception as e:
            logger.error(f"Failed to load codes from table: {e}")
            sys.exit(1)
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                codes.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            sys.exit(1)
            
    if args.code:
        codes.append(args.code)

    # 去重
    codes = _dedupe_preserve_order(codes)

    if not codes:
        logger.error("No stock codes provided. Use 'code', '-f', or --from-preselect-table.")
        sys.exit(1)

    # 批量模式强制关闭弹窗
    if len(codes) > 1 and args.show:
        logger.warning("Batch mode detected. Disabling --show.")
        args.show = False

    # 循环处理
    success_count = 0
    for code in codes:
        if process_stock(code, args):
            success_count += 1

    logger.info("="*30)
    logger.info(f"Batch task finished. Success: {success_count}/{len(codes)}")

if __name__ == "__main__":
    main()
```

## 5. 使用示例

```bash
# 1. 单只股票 (兼容旧用法)
python -m flatbottom_pipeline.visualization.plot_kline 600000

# 2. 批量处理 (文件在 visualization 目录下)
python -m flatbottom_pipeline.visualization.plot_kline -f visualization/my_stocks.txt

# 3. 混合使用 (文件 + 命令行追加)
python -m flatbottom_pipeline.visualization.plot_kline 000001 -f list.txt

# 4. 从预选表读取 (按 score DESC)
python -m flatbottom_pipeline.visualization.plot_kline --from-preselect-table
```

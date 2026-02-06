import akshare as ak
import pandas as pd
from datetime import datetime

def test_monthly_kline():
    # 获取当前日期作为结束日期，格式 YYYYMMDD
    current_date = datetime.now().strftime("%Y%m%d")

    # 设定开始日期为 2000年1月1日
    start_date = "20000101"

    # 目标股票代码 (新疆火炬)
    # 注意：ak.stock_zh_a_hist 接口通常直接使用数字代码
    symbol = "603080"

    print(f">>> 正在获取 {symbol} 从 {start_date} 至今的月K线数据 (前复权)...")

    try:
        # period="monthly" 表示获取月K线
        # adjust="qfq" 表示使用前复权
        df = ak.stock_zh_a_hist(
            symbol=symbol, 
            period="monthly", 
            start_date=start_date, 
            end_date=current_date, 
            adjust="qfq"
        )
        
        if df.empty:
            print("结果为空，请检查股票代码或日期范围。")
            return

        print(f"成功获取数据！共 {len(df)} 条月度记录。")
        
        # 设置 Pandas 显示选项以展示所有行
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        
        print("\n--- 完整月K线数据清单 ---")
        print(df) 
        
        # 恢复默认设置（可选）
        pd.reset_option('display.max_rows')

    except Exception as e:
        print(f"获取数据失败: {e}")

if __name__ == "__main__":
    test_monthly_kline()
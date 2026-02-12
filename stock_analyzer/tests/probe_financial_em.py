"""
探测 stock_financial_analysis_indicator_em 的返回结构。
直接运行：.venv/bin/python3 stock_analyzer/tests/probe_financial_em.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import akshare as ak
import pandas as pd

symbol = "600519.SH"
print(f"调用 stock_financial_analysis_indicator_em(symbol='{symbol}', indicator='按报告期')")
df = ak.stock_financial_analysis_indicator_em(symbol=symbol, indicator="按报告期")

print(f"\n行数：{len(df)}，列数：{len(df.columns)}")
print("\n全部列名：")
for i, col in enumerate(df.columns):
    print(f"  [{i:02d}] {col}")

print("\n最新两行数据（转置方便阅读）：")
pd.set_option("display.max_rows", 200)
pd.set_option("display.max_colwidth", 40)
print(df.head(2).T.to_string())

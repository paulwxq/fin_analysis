"""
Probe multiple AKShare APIs for Module A expansion candidates.
Run: .venv/bin/python3 stock_analyzer/tests/probe_new_akshare_apis.py
"""
import sys
from pathlib import Path
import pandas as pd
import akshare as ak

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def probe_api(name, func, **kwargs):
    print(f"\n[Candidate: {name}]")
    print(f"Calling {func.__name__} with {kwargs}")
    try:
        df = func(**kwargs)
        if df is None or df.empty:
            print("Result: Empty or None")
            return False
        
        print(f"Success! Rows: {len(df)}, Columns: {len(df.columns)}")
        print(f"Columns: {list(df.columns)}")
        print("Sample data:")
        print(df.head(2).to_string(index=False))
        return True
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    symbol = "600519"
    upper_symbol = "SH600519"
    
    print(f"Probing candidates for {symbol} / {upper_symbol}...")

    # --- 1. 一致预期 (Consensus Expectations) ---
    print("\n--- 1. Consensus Expectations Candidates ---")
    probe_api("Profit Forecast EM", ak.stock_profit_forecast_em, symbol=symbol)
    probe_api("Profit Forecast THS", ak.stock_profit_forecast_ths, symbol=symbol)

    # --- 2. 机构持仓 (Institutional Holdings) ---
    print("\n--- 2. Institutional Holdings Candidates ---")
    # Trying detail with a recent quarter
    probe_api("Institute Hold Detail Sina", ak.stock_institute_hold_detail, stock=symbol, quarter="20243")
    # Check if there's any EM one under a different name
    # Maybe stock_individual_info_em already has some? No.

    # --- 3. 主营结构 (Main Business Structure) ---
    print("\n--- 3. Main Business Structure Candidates ---")
    probe_api("Main Business Composition EM", ak.stock_zygc_em, symbol=upper_symbol)
    probe_api("Main Business Intro THS", ak.stock_zyjs_ths, symbol=symbol)

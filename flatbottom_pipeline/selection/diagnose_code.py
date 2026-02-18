"""
Diagnose why a single stock code is filtered out.

Usage:
  .venv/bin/python -m flatbottom_pipeline.selection.diagnose_code --code 600583 --preset balanced
"""
import argparse
from typing import Optional

import numpy as np
from scipy import stats

from data_infra.db import get_db_connection
from data_infra.stock_code import classify_cn_stock
from flatbottom_pipeline.selection.config import get_config, validate_config


def _calculate_trend(prices: np.ndarray) -> tuple[float, float]:
    """Same trend calculation as selection/find_flatbottom.py."""
    if len(prices) < 12:
        return (0.0, 0.0)
    if abs(prices[0]) < 1e-10:
        return (0.0, 0.0)
    x = np.arange(len(prices))
    y = (prices - prices[0]) / abs(prices[0])
    slope, _, r_value, _, _ = stats.linregress(x, y)
    return (slope, r_value ** 2)


def diagnose(code: str, preset: str) -> None:
    cfg = get_config(preset)
    validate_config(cfg)

    std_code = classify_cn_stock(code).ts_code
    print(f"Code: {code} -> {std_code}")

    conn = get_db_connection()
    cur = conn.cursor()

    history_lookback = cfg['HISTORY_LOOKBACK']
    recent_lookback = cfg['RECENT_LOOKBACK']
    min_positive_low = cfg['MIN_POSITIVE_LOW']

    sql = f"""
    WITH StockMetrics AS (
        SELECT
            code,
            month,
            close,
            high,
            low,
            MAX(high) OVER (
                PARTITION BY code
                ORDER BY month
                ROWS BETWEEN {history_lookback - 1} PRECEDING AND CURRENT ROW
            ) AS history_high,
            MIN(low) OVER (
                PARTITION BY code
                ORDER BY month
                ROWS BETWEEN {history_lookback - 1} PRECEDING AND CURRENT ROW
            ) AS history_low,
            MAX(high) OVER (
                PARTITION BY code
                ORDER BY month
                ROWS BETWEEN {recent_lookback - 1} PRECEDING AND CURRENT ROW
            ) AS recent_high,
            MIN(low) OVER (
                PARTITION BY code
                ORDER BY month
                ROWS BETWEEN {recent_lookback - 1} PRECEDING AND CURRENT ROW
            ) AS recent_low,
            STDDEV(close) OVER (
                PARTITION BY code
                ORDER BY month
                ROWS BETWEEN {recent_lookback - 1} PRECEDING AND CURRENT ROW
            ) AS recent_stddev,
            STDDEV(close) OVER (
                PARTITION BY code
                ORDER BY month
                ROWS BETWEEN {history_lookback - 1} PRECEDING AND {recent_lookback} PRECEDING
            ) AS historical_stddev,
            COUNT(*) OVER (
                PARTITION BY code
                ORDER BY month
                ROWS BETWEEN {history_lookback - 1} PRECEDING AND CURRENT ROW
            ) AS data_points
        FROM stock_monthly_kline
        WHERE code = %s
    ), Derived AS (
        SELECT
            code,
            month,
            close AS current_price,
            history_high,
            history_low,
            recent_high,
            recent_low,
            CASE
                WHEN history_high > 0 AND history_low > {min_positive_low}
                THEN history_high / history_low
                WHEN history_high IS NOT NULL AND history_low IS NOT NULL
                     AND GREATEST(ABS(history_high), ABS(history_low)) > 0
                THEN (history_high - history_low) / GREATEST(ABS(history_high), ABS(history_low))
                ELSE NULL
            END AS glory_ratio,
            CASE
                WHEN history_high > 0 AND history_low > {min_positive_low}
                THEN 'ratio'
                WHEN history_high IS NOT NULL AND history_low IS NOT NULL
                THEN 'amplitude'
                ELSE NULL
            END AS glory_type,
            CASE
                WHEN history_high IS NOT NULL AND ABS(history_high) > 0
                THEN (close - history_high) / ABS(history_high)
                ELSE NULL
            END AS drawdown_pct,
            CASE
                WHEN recent_high IS NOT NULL AND recent_low IS NOT NULL
                     AND GREATEST(ABS(recent_high), ABS(recent_low)) > 0
                THEN (recent_high - recent_low) / GREATEST(ABS(recent_high), ABS(recent_low))
                ELSE NULL
            END AS box_range_pct,
            CASE
                WHEN historical_stddev > 0 THEN recent_stddev / historical_stddev
                WHEN historical_stddev IS NULL THEN NULL
                ELSE 999
            END AS volatility_ratio,
            CASE
                WHEN (recent_high - recent_low) > 0
                THEN (close - recent_low) / (recent_high - recent_low)
                ELSE 0.5
            END AS price_position,
            data_points
        FROM StockMetrics
    )
    SELECT *
    FROM Derived
    ORDER BY month DESC
    LIMIT 1;
    """

    cur.execute(sql, (std_code,))
    row = cur.fetchone()
    if not row:
        print("No data found for code.")
        conn.close()
        return

    columns = [desc[0] for desc in cur.description]
    metrics = dict(zip(columns, row))

    print("\nLatest metrics:")
    for k in columns:
        print(f"  {k}: {metrics[k]}")

    fails = []
    glory_type = metrics['glory_type']
    glory_ratio = metrics['glory_ratio']
    if glory_type == 'ratio':
        if glory_ratio is None or glory_ratio < cfg['MIN_GLORY_RATIO']:
            fails.append('glory_ratio (ratio)')
    elif glory_type == 'amplitude':
        if glory_ratio is None or glory_ratio < cfg['MIN_GLORY_AMPLITUDE']:
            fails.append('glory_ratio (amplitude)')
    else:
        fails.append('glory_type null')

    if metrics['history_high'] is None or metrics['history_high'] <= cfg['MIN_HIGH_PRICE']:
        fails.append('min_high_price')
    if metrics['drawdown_pct'] is None or metrics['drawdown_pct'] >= cfg['MIN_DRAWDOWN']:
        fails.append('min_drawdown')
    if metrics['box_range_pct'] is None or metrics['box_range_pct'] >= cfg['MAX_BOX_RANGE']:
        fails.append('max_box_range')
    if metrics['volatility_ratio'] is None or metrics['volatility_ratio'] >= cfg['MAX_VOLATILITY_RATIO']:
        fails.append('max_volatility_ratio')
    if metrics['price_position'] is None or not (cfg['PRICE_POSITION_MIN'] <= metrics['price_position'] <= cfg['PRICE_POSITION_MAX']):
        fails.append('price_position_range')
    if metrics['current_price'] is None or abs(metrics['current_price']) < cfg['MIN_PRICE']:
        fails.append('min_price')
    if metrics['data_points'] is None or metrics['data_points'] < cfg['MIN_DATA_MONTHS']:
        fails.append('min_data_months')

    print("\nSQL filter failures:")
    if not fails:
        print("  None (passes SQL rough screening)")
    else:
        for f in fails:
            print(f"  - {f}")

    # Trend check (Python stage)
    cur.execute(
        """
        SELECT close
        FROM stock_monthly_kline
        WHERE code = %s
        ORDER BY month ASC
        """,
        (std_code,),
    )
    prices = [r[0] for r in cur.fetchall()]
    prices = prices[-cfg['RECENT_LOOKBACK']:]
    prices = np.array(prices, dtype=float)

    if len(prices) < max(12, cfg['RECENT_LOOKBACK'] // 2):
        print("\nPython trend check: insufficient recent months")
    else:
        slope, r2 = _calculate_trend(prices)
        slope_ok = cfg['SLOPE_MIN'] <= slope <= cfg['SLOPE_MAX']
        r2_ok = r2 >= cfg['MIN_R_SQUARED']
        print("\nPython trend check:")
        print(f"  slope={slope:.6f} (ok={slope_ok})")
        print(f"  R2={r2:.6f} (ok={r2_ok})")

    conn.close()


def _load_codes_from_file(path: str) -> list[str]:
    codes: list[str] = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            code = line.strip()
            if not code or code.startswith('#'):
                continue
            codes.append(code)
    # Deduplicate while preserving order
    seen = set()
    return [code for code in codes if not (code in seen or seen.add(code))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose why a stock is filtered")
    parser.add_argument('--code', help='Stock code (e.g., 600583)')
    parser.add_argument('-f', '--file', help='Path to a txt file with stock codes (one per line)')
    parser.add_argument('--preset', default='balanced', help='Preset (balanced/conservative/aggressive)')
    args = parser.parse_args()

    if not args.code and not args.file:
        parser.error("Either --code or -f/--file must be provided.")

    if args.code:
        diagnose(args.code, args.preset)
        return

    codes = _load_codes_from_file(args.file)
    if not codes:
        print("No valid codes found in file.")
        return

    for raw in codes:
        print("\n" + "=" * 60)
        try:
            diagnose(raw, args.preset)
        except Exception as e:
            print(f"Failed to diagnose {raw}: {e}")


if __name__ == '__main__':
    main()

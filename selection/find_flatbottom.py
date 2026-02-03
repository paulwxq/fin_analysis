"""
Flatbottom stock screening module.

This module implements a high-performance stock screening system for identifying
"flatbottom" (平底锅) pattern stocks using a 4-stage pipeline:
1. SQL rough screening (database layer)
2. Batch price fetching (solves N+1 problem)
3. Python fine screening (trend analysis)
4. Result persistence (TRUNCATE + INSERT + CSV export)
"""
import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import numpy as np
from scipy import stats

from load_data.db import get_db_connection
from load_data.stock_code import classify_cn_stock
from selection.config import get_config, validate_config, print_config, DEFAULT_PRESET
from selection.logger import logger


class FlatbottomScreener:
    """Flatbottom pattern stock screener."""

    def __init__(self, preset: Optional[str] = None, code_filter: Optional[list] = None):
        """
        Initialize screener with configuration preset.

        Args:
            preset: Configuration preset name ('conservative' | 'balanced' | 'aggressive')
            code_filter: Optional list of stock codes to restrict screening
        """
        self.config = get_config(preset)
        validate_config(self.config)
        self.preset = preset or DEFAULT_PRESET
        self.code_filter = code_filter or []
        logger.info(f"Screener initialized with preset: {self.preset}")

    def run(self) -> pd.DataFrame:
        """
        Execute full screening pipeline.

        Returns:
            DataFrame with screening results

        Pipeline stages:
            1. SQL rough screening (~5s)
            2. Batch price fetching (~0.5s)
            3. Python fine screening (~2s)
            4. Result persistence (~1s)
        """
        logger.info("=" * 60)
        logger.info("Starting flatbottom stock screening")
        logger.info("=" * 60)

        # Stage 1: SQL rough screening
        logger.info("Stage 1: SQL rough screening...")
        candidates = self._execute_sql_screening()

        # If using a code filter file, log which codes did not pass SQL screening
        if self.code_filter:
            candidate_codes = set(candidates['code'].tolist()) if not candidates.empty else set()
            for code in self.code_filter:
                if code not in candidate_codes:
                    logger.debug(f"{code}: Filtered out in SQL screening stage")

        if candidates.empty:
            logger.warning("SQL screening returned no candidates. Stopping.")
            return pd.DataFrame()

        logger.info(f"✓ SQL screening complete: {len(candidates)} candidates found")

        # Stage 2: Batch price fetching
        logger.info("Stage 2: Fetching price data in batch...")
        codes = candidates['code'].tolist()
        prices_df = self._get_prices_batch(codes, self.config['RECENT_LOOKBACK'])

        if prices_df.empty:
            logger.warning("Failed to fetch price data. Stopping.")
            return pd.DataFrame()

        logger.info(f"✓ Price data fetched: {len(prices_df)} records")

        # Stage 3: Python fine screening
        logger.info("Stage 3: Python fine screening (trend analysis)...")
        results = self._refine_candidates(candidates, prices_df)

        if results.empty:
            logger.warning("Fine screening returned no results.")
            return pd.DataFrame()

        logger.info(f"✓ Fine screening complete: {len(results)} stocks passed")

        logger.info("=" * 60)
        logger.info(f"Screening complete: Found {len(results)} stocks")
        logger.info("=" * 60)

        return results

    def _execute_sql_screening(self) -> pd.DataFrame:
        """
        Stage 1: Execute SQL query with parameter injection.

        Returns:
            DataFrame with SQL screening results
        """
        sql_query = self._build_sql_query()
        count_query = self._build_sql_query(
            final_query="SELECT COUNT(*) AS total FROM ScoredCandidates"
        )

        conn = None
        try:
            conn = get_db_connection()
            count_df = pd.read_sql(count_query, conn)
            total_passed = int(count_df.iloc[0, 0]) if not count_df.empty else 0
            logger.info(
                f"SQL rough screening passed {total_passed} stocks before truncation "
                f"(SQL_LIMIT={self.config['SQL_LIMIT']})"
            )
            df = pd.read_sql(sql_query, conn)
            return df
        except Exception as e:
            logger.error(f"SQL screening failed: {e}")
            raise
        finally:
            if conn is not None:
                conn.close()

    def _build_sql_query(self, final_query: Optional[str] = None) -> str:
        """Build SQL query with parameter injection."""
        cfg = self.config

        # Read SQL template
        sql_template_path = Path(__file__).parent / 'sql' / 'flatbottom_screen.sql'
        with open(sql_template_path, 'r', encoding='utf-8') as f:
            sql_template = f.read()

        if final_query is None:
            final_query = """
SELECT
    code,
    name,
    ROUND(current_price::numeric, 2) AS current_price,
    ROUND(history_high::numeric, 2) AS history_high,
    ROUND(glory_ratio::numeric, 2) AS glory_ratio,
    glory_type,
    ROUND(drawdown_pct::numeric * 100, 1) AS drawdown_pct,
    ROUND(box_range_pct::numeric * 100, 1) AS box_range_pct,
    ROUND(volatility_ratio::numeric, 3) AS volatility_ratio,
    ROUND(price_position::numeric, 3) AS price_position,
    ROUND(composite_score::numeric, 1) AS score,
    data_points
FROM ScoredCandidates
ORDER BY composite_score DESC
LIMIT {sql_limit}
            """.strip()
            if cfg['SQL_LIMIT'] == -1:
                final_query = final_query.replace("LIMIT {sql_limit}", "")
            final_query = final_query.format(sql_limit=cfg['SQL_LIMIT'])
        else:
            # Allow callers to use {sql_limit} placeholder if needed
            if cfg['SQL_LIMIT'] == -1:
                final_query = final_query.replace("LIMIT {sql_limit}", "")
            if '{sql_limit}' in final_query:
                final_query = final_query.format(sql_limit=cfg['SQL_LIMIT'])

        # Parameter injection
        code_filter_clause = ''
        if self.code_filter:
            escaped_codes = [code.replace("'", "''") for code in self.code_filter]
            code_list_sql = ", ".join(f"'{code}'" for code in escaped_codes)
            code_filter_clause = f"AND code = ANY(ARRAY[{code_list_sql}])"

        return sql_template.format(
            history_lookback_minus_1=cfg['HISTORY_LOOKBACK'] - 1,
            recent_lookback_minus_1=cfg['RECENT_LOOKBACK'] - 1,
            recent_lookback=cfg['RECENT_LOOKBACK'],
            min_drawdown=cfg['MIN_DRAWDOWN'],
            min_drawdown_abs=abs(cfg['MIN_DRAWDOWN']),
            max_box_range=cfg['MAX_BOX_RANGE'],
            max_volatility_ratio=cfg['MAX_VOLATILITY_RATIO'],
            min_glory_ratio=cfg['MIN_GLORY_RATIO'],
            min_glory_amplitude=cfg['MIN_GLORY_AMPLITUDE'],
            min_positive_low=cfg['MIN_POSITIVE_LOW'],
            max_drawdown_abs=cfg['MAX_DRAWDOWN_ABS'],
            min_high_price=cfg['MIN_HIGH_PRICE'],
            min_price=cfg['MIN_PRICE'],
            min_data_months=cfg['MIN_DATA_MONTHS'],
            price_position_min=cfg['PRICE_POSITION_MIN'],
            price_position_max=cfg['PRICE_POSITION_MAX'],
            sql_limit=cfg['SQL_LIMIT'],
            code_filter_clause=code_filter_clause,
            final_query=final_query
        )

    def _get_prices_batch(self, codes: list, months: int) -> pd.DataFrame:
        """
        Stage 2: Batch fetch prices (solve N+1 problem).

        Args:
            codes: List of stock codes
            months: Number of months to fetch

        Returns:
            DataFrame with columns: code, month, close
        """
        if not codes:
            return pd.DataFrame()

        conn = None
        try:
            conn = get_db_connection()

            # Use PostgreSQL ANY() syntax for single query
            df = pd.read_sql("""
                SELECT code, month, close
                FROM stock_monthly_kline
                WHERE code = ANY(%s)
                ORDER BY code, month ASC
            """, conn, params=(codes,))

            # Filter to recent months (keep last N months per stock)
            df = df.groupby('code').tail(months).reset_index(drop=True)

            return df
        except Exception as e:
            logger.error(f"Batch price fetching failed: {e}")
            raise
        finally:
            if conn is not None:
                conn.close()

    def _refine_candidates(self, candidates: pd.DataFrame, prices_df: pd.DataFrame) -> pd.DataFrame:
        """
        Stage 3: Python refinement with trend analysis.

        Args:
            candidates: SQL screening results
            prices_df: Batch price data

        Returns:
            Refined DataFrame with slope and r_squared fields
        """
        # Optional: Filter ST stocks
        if self.config['EXCLUDE_ST']:
            candidates = self._filter_st_stocks(candidates)
            if candidates.empty:
                logger.warning("No candidates after ST filtering")
                return pd.DataFrame()
            logger.info(f"After ST filtering: {len(candidates)} stocks")

        # Optional: Filter blacklist
        if self.config['EXCLUDE_BLACKLIST']:
            candidates = self._filter_blacklist(candidates)
            if candidates.empty:
                logger.warning("No candidates after blacklist filtering")
                return pd.DataFrame()
            logger.info(f"After blacklist filtering: {len(candidates)} stocks")

        # Data completeness check
        # Use half of RECENT_LOOKBACK as minimum (at least 12 months for meaningful regression)
        min_months = max(12, self.config['RECENT_LOOKBACK'] // 2)
        data_counts = prices_df.groupby('code').size()
        insufficient_codes = data_counts[data_counts < min_months].index.tolist()

        if insufficient_codes:
            logger.warning(f"{len(insufficient_codes)} stocks lack sufficient data (< {min_months} months), removing")
            candidates = candidates[~candidates['code'].isin(insufficient_codes)]

        if candidates.empty:
            logger.warning("No candidates after data completeness check")
            return pd.DataFrame()

        # Trend analysis
        results = []
        failed_count = 0
        for _, row in candidates.iterrows():
            code = row['code']

            # Get price series for this stock
            stock_prices = prices_df[prices_df['code'] == code]['close'].values

            if len(stock_prices) < min_months:
                logger.debug(f"{code}: Not enough recent months ({len(stock_prices)} < {min_months}), skipping")
                continue

            # Convert to float array (handles Decimal from PostgreSQL NUMERIC type)
            try:
                stock_prices = stock_prices.astype(float)
            except (ValueError, TypeError) as e:
                logger.debug(f"{code}: Failed to convert prices to float: {e}")
                failed_count += 1
                continue

            # Drop NaN/inf to avoid silent linregress failures
            finite_mask = np.isfinite(stock_prices)
            if not finite_mask.all():
                invalid_count = (~finite_mask).sum()
                logger.debug(f"{code}: Found {invalid_count} non-finite prices (NaN/inf), skipping")
                failed_count += 1
                continue

            # Calculate trend
            try:
                slope, r_squared = self._calculate_trend(stock_prices)
            except Exception as e:
                logger.debug(f"{code}: Trend calculation failed: {e}")
                failed_count += 1
                continue

            # Validate trend
            if not self._validate_trend(slope, r_squared):
                slope_ok = self.config['SLOPE_MIN'] <= slope <= self.config['SLOPE_MAX']
                fit_ok = r_squared >= self.config['MIN_R_SQUARED']
                if not slope_ok and not fit_ok:
                    reason = "slope_out_of_range_and_r2_too_low"
                elif not slope_ok:
                    reason = "slope_out_of_range"
                else:
                    reason = "r2_too_low"
                logger.debug(
                    f"{code}: Trend validation failed ({reason}), "
                    f"slope={slope:.4f}, R²={r_squared:.3f}"
                )
                continue

            # Pass validation
            results.append({
                **row.to_dict(),
                'slope': round(slope, 6),
                'r_squared': round(r_squared, 4)
            })

        # Report failures if any
        if failed_count > 0:
            logger.warning(f"{failed_count} stocks failed trend calculation (type conversion or scipy errors)")

        # Convert to DataFrame
        if not results:
            logger.warning("No stocks passed trend validation")
            return pd.DataFrame()

        result_df = pd.DataFrame(results)

        # Sort by score
        result_df = result_df.sort_values('score', ascending=False)

        # Log pre-truncate count, then apply limit (if any)
        total_passed = len(result_df)
        logger.info(
            f"Fine screening passed {total_passed} stocks before truncation "
            f"(FINAL_LIMIT={self.config['FINAL_LIMIT']})"
        )
        if self.config['FINAL_LIMIT'] != -1:
            result_df = result_df.head(self.config['FINAL_LIMIT'])

        return result_df

    def _calculate_trend(self, prices: np.ndarray) -> Tuple[float, float]:
        """
        Calculate linear regression slope and R².

        Args:
            prices: Price series (should be float array, not Decimal/object)

        Returns:
            (slope, r_squared)

        Notes:
            - Input must be float array (caller should convert Decimal to float)
            - Uses percentage change normalization: (prices - prices[0]) / abs(prices[0])
            - This preserves relative change semantics (slope = % change per month)
            - Avoids trend reversal in negative price scenarios (uses abs())
            - Avoids division by zero when prices[0] == 0 (returns 0)
            - Requires at least 12 months of data for meaningful regression
        """
        # Minimum data points for meaningful linear regression
        min_data_points = 12
        if len(prices) < min_data_points:
            return (0.0, 0.0)

        # Check for zero initial price
        if abs(prices[0]) < 1e-10:
            logger.debug(f"Initial price is zero, skipping trend calculation")
            return (0.0, 0.0)

        x = np.arange(len(prices))
        # Use percentage change normalization (relative to absolute value of first price)
        # This preserves slope semantics while avoiding negative price reversal
        y = (prices - prices[0]) / abs(prices[0])

        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        return (slope, r_value ** 2)

    def _validate_trend(self, slope: float, r_squared: float) -> bool:
        """
        Validate trend against flatbottom criteria.

        Args:
            slope: Trend slope
            r_squared: R² goodness-of-fit

        Returns:
            True if trend is valid
        """
        cfg = self.config

        # Condition 1: Slope in reasonable range
        slope_ok = cfg['SLOPE_MIN'] <= slope <= cfg['SLOPE_MAX']

        # Condition 2: Sufficient fit quality
        fit_ok = r_squared >= cfg['MIN_R_SQUARED']

        return slope_ok and fit_ok

    def _filter_st_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter out ST stocks (optional).

        ST (Special Treatment) stocks are identified by specific markers in their names
        according to Chinese stock market regulations. This method filters stocks based
        on name pattern matching, not from a separate ST stock table.

        Args:
            df: Candidate DataFrame with 'name' column

        Returns:
            Filtered DataFrame

        Notes:
            - No separate ST table is needed (ST status is marked in stock names)
            - Uses comprehensive ST marker list to avoid false positives
            - ST markers: ST, *ST, S*ST, SST, 退市, PT, 终止上市
        """
        if 'name' not in df.columns:
            logger.warning("'name' column not found, skipping ST filtering")
            return df

        # Comprehensive ST marker list (Chinese stock market regulations)
        st_markers = ['ST', '*ST', 'S*ST', 'SST', '退市', 'PT', '终止上市']

        def is_st_stock(name: str) -> bool:
            """Check if stock name contains ST markers (excluding false positives)."""
            if pd.isna(name):
                return False
            # Use word boundary checking to avoid false positives like "BEST", "FASTEST"
            # ST markers in Chinese stocks appear at the beginning or as standalone markers
            name_upper = str(name).upper()
            for marker in st_markers:
                # Check if marker is at the beginning or is a complete word
                if name_upper.startswith(marker) or f' {marker}' in name_upper:
                    return True
                # Chinese markers rely on original name
                if marker in ['退市', '终止上市'] and marker in name:
                    return True
                # PT should be case-insensitive
                if marker == 'PT' and 'PT' in name_upper:
                    return True
            return False

        # Apply ST filtering
        st_mask = df['name'].apply(is_st_stock)
        st_count = st_mask.sum()

        if st_count > 0:
            logger.info(f"Filtering {st_count} ST stocks (markers: {', '.join(st_markers)})")
            return df[~st_mask].reset_index(drop=True)

        return df

    def _filter_blacklist(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter out blacklist stocks (optional).

        Args:
            df: Candidate DataFrame with 'code' column

        Returns:
            Filtered DataFrame
        """
        conn = None
        try:
            conn = get_db_connection()
            blacklist_df = pd.read_sql("""
                SELECT code
                FROM stock_blacklist
                WHERE is_active = true
            """, conn)

            if blacklist_df is None or blacklist_df.empty:
                logger.debug("Blacklist table is empty")
                return df

            blacklist_codes = set(blacklist_df['code'].tolist())
            mask = df['code'].isin(blacklist_codes)
            blacklist_count = mask.sum()

            if blacklist_count > 0:
                logger.info(f"Filtering {blacklist_count} blacklist stocks")
                return df[~mask].reset_index(drop=True)

            return df

        except Exception as e:
            logger.warning(f"Blacklist filtering failed: {e}. Continuing without blacklist filter.")
            return df
        finally:
            if conn is not None:
                conn.close()

    def _ensure_tables_exist(self) -> None:
        """Ensure required tables exist (idempotent)."""
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            self._ensure_table_exists(cursor)
            self._ensure_blacklist_table_exists(cursor)
            conn.commit()
        except Exception as e:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"Failed to ensure tables exist: {e}")
            raise
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()

    def _ensure_blacklist_table_exists(self, cursor) -> None:
        """Ensure blacklist table exists (idempotent)."""
        ddl_path = Path(__file__).parent / 'sql' / 'stock_blacklist.sql'
        with open(ddl_path, 'r', encoding='utf-8') as f:
            ddl = f.read().strip()
        if ddl:
            cursor.execute(ddl)

    def _ensure_table_exists(self, cursor) -> None:
        """
        Ensure result table exists (idempotent).

        Args:
            cursor: Database cursor
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_flatbottom_preselect (
                code VARCHAR(20) PRIMARY KEY,
                name VARCHAR(100),
                current_price NUMERIC(10, 2),
                history_high NUMERIC(10, 2),
                glory_ratio NUMERIC(10, 2),
                glory_type VARCHAR(20),
                drawdown_pct NUMERIC(10, 2),
                box_range_pct NUMERIC(10, 2),
                volatility_ratio NUMERIC(10, 4),
                price_position NUMERIC(10, 4),
                slope NUMERIC(10, 6),
                r_squared NUMERIC(10, 4),
                score NUMERIC(10, 2),
                screening_preset VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_flatbottom_preselect_score
            ON stock_flatbottom_preselect(score DESC);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_flatbottom_preselect_updated_at
            ON stock_flatbottom_preselect(updated_at);
        """)

    def save_to_db(self, results: pd.DataFrame) -> int:
        """
        Stage 4a: TRUNCATE + INSERT results to database.

        Args:
            results: Screening results

        Returns:
            Number of records inserted/updated
        """
        if results.empty:
            logger.warning("Results are empty, skipping database write")
            return 0

        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            self._ensure_table_exists(cursor)
            # Always clear the output table before insert
            cursor.execute("TRUNCATE stock_flatbottom_preselect;")
            # INSERT SQL
            insert_sql = """
                INSERT INTO stock_flatbottom_preselect (
                    code, name, current_price, history_high, glory_ratio, glory_type,
                    drawdown_pct, box_range_pct, volatility_ratio, price_position,
                    slope, r_squared, score, screening_preset, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    NOW(), NOW()
                )
            """

            # Build data tuples
            data_tuples = []
            for _, row in results.iterrows():
                data_tuples.append((
                    row.get('code', None),
                    row.get('name', None),
                    row.get('current_price', None),
                    row.get('history_high', None),
                    row.get('glory_ratio', None),
                    row.get('glory_type', None),
                    row.get('drawdown_pct', None),
                    row.get('box_range_pct', None),
                    row.get('volatility_ratio', None),
                    row.get('price_position', None),
                    row.get('slope', None),
                    row.get('r_squared', None),
                    row.get('score', None),
                    self.preset,
                ))

            # Batch INSERT
            cursor.executemany(insert_sql, data_tuples)
            conn.commit()

            inserted_count = len(data_tuples)
            logger.info(f"✓ Successfully wrote {inserted_count} records to database")

            return inserted_count

        except Exception as e:
            # Only rollback if connection was established
            if conn is not None:
                try:
                    conn.rollback()
                except Exception as rollback_error:
                    logger.warning(f"Rollback failed: {rollback_error}")

            logger.error(f"Database write failed: {e}")
            raise

        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()

    def export_csv(self, results: pd.DataFrame) -> Optional[str]:
        """
        Stage 4b: Export timestamped CSV.

        Args:
            results: Screening results

        Returns:
            CSV file path (or None if failed)
        """
        if results.empty:
            logger.warning("Results are empty, skipping CSV export")
            return None

        try:
            # Generate timestamped filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"stock_flatbottom_preselect_{timestamp}.csv"
            output_dir = 'output'
            output_path = os.path.join(output_dir, filename)

            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # Export CSV (utf-8-sig for Excel compatibility)
            results.to_csv(output_path, index=False, encoding='utf-8-sig')
            logger.info(f"✓ CSV file saved: {output_path}")

            return output_path

        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            return None


def main():
    """Main entry point for command-line execution."""
    parser = argparse.ArgumentParser(
        description='Flatbottom stock screener - identifies "平底锅" pattern stocks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Use balanced preset
  python -m selection.find_flatbottom --preset balanced

  # Override specific parameters
  python -m selection.find_flatbottom --preset balanced --min-drawdown -0.50 --exclude-st

  # Show current configuration
  python -m selection.find_flatbottom --show-config
        '''
    )
    parser.add_argument(
        '--preset',
        choices=['conservative', 'balanced', 'aggressive'],
        default=None,
        help=f'Screening preset (default: {DEFAULT_PRESET})'
    )
    parser.add_argument(
        '--show-config',
        action='store_true',
        help='Print configuration and exit'
    )
    parser.add_argument(
        '-f', '--filter-file',
        help='Path to a txt file with stock codes (one per line)'
    )

    # SQL layer parameters
    parser.add_argument('--history-lookback', type=int, metavar='MONTHS',
                       help='Historical lookback months (e.g., 120)')
    parser.add_argument('--recent-lookback', type=int, metavar='MONTHS',
                       help='Recent lookback months (e.g., 24)')
    parser.add_argument('--min-drawdown', type=float, metavar='PCT',
                       help='Minimum drawdown percentage (negative, e.g., -0.40). '
                            'Positive values will be converted to negative.')
    parser.add_argument('--max-drawdown-abs', type=float, metavar='PCT',
                       help='Maximum absolute drawdown (e.g., 0.90)')
    parser.add_argument('--max-box-range', type=float, metavar='PCT',
                       help='Maximum box range percentage (e.g., 0.50)')
    parser.add_argument('--max-volatility-ratio', type=float, metavar='RATIO',
                       help='Maximum volatility ratio (e.g., 0.60)')
    parser.add_argument('--min-glory-ratio', type=float, metavar='RATIO',
                       help='Minimum glory ratio for positive prices (e.g., 3.0)')
    parser.add_argument('--min-glory-amplitude', type=float, metavar='PCT',
                       help='Minimum glory amplitude for negative prices (e.g., 0.60)')
    parser.add_argument('--min-positive-low', type=float, metavar='PRICE',
                       help='Positive price threshold (e.g., 0.01)')
    parser.add_argument('--min-high-price', type=float, metavar='PRICE',
                       help='Minimum historical high price (e.g., 3.0)')
    parser.add_argument('--min-price', type=float, metavar='PRICE',
                       help='Minimum absolute stock price (e.g., 3.0)')
    parser.add_argument('--min-data-months', type=int, metavar='MONTHS',
                       help='Minimum data months required (e.g., 60)')
    parser.add_argument('--price-position-min', type=float, metavar='RATIO',
                       help='Minimum price position in box (e.g., 0.05)')
    parser.add_argument('--price-position-max', type=float, metavar='RATIO',
                       help='Maximum price position in box (e.g., 0.80)')
    parser.add_argument('--sql-limit', type=int, metavar='N',
                       help='SQL candidate limit (e.g., 200)')

    # Python layer parameters
    parser.add_argument('--slope-min', type=float, metavar='SLOPE',
                       help='Minimum trend slope (e.g., -0.01)')
    parser.add_argument('--slope-max', type=float, metavar='SLOPE',
                       help='Maximum trend slope (e.g., 0.02)')
    parser.add_argument('--min-r-squared', type=float, metavar='R2',
                       help='Minimum R-squared fit (e.g., 0.30)')
    parser.add_argument('--exclude-st', action='store_true',
                       help='Exclude ST stocks')
    parser.add_argument('--exclude-blacklist', action='store_true',
                       help='Exclude blacklist stocks')
    parser.add_argument('--final-limit', type=int, metavar='N',
                       help='Final output limit after refinement (e.g., 100)')

    args = parser.parse_args()

    code_filter = []
    if args.filter_file:
        try:
            with open(args.filter_file, 'r', encoding='utf-8') as f:
                for line in f:
                    code = line.strip()
                    if not code or code.startswith('#'):
                        continue
                    try:
                        code_filter.append(classify_cn_stock(code).ts_code)
                    except ValueError as e:
                        logger.warning(f"Skipping invalid code '{code}': {e}")
        except Exception as e:
            logger.error(f"Failed to read filter file: {e}")
            print(f"\n❌ Failed to read filter file: {e}")
            return
        # Deduplicate while preserving order
        seen = set()
        code_filter = [code for code in code_filter if not (code in seen or seen.add(code))]
        if not code_filter:
            logger.error("Filter file is empty or contains no valid codes")
            print("\n❌ Filter file is empty or contains no valid codes")
            return

    # Build configuration overrides from command-line arguments
    overrides = {}
    if args.history_lookback is not None:
        overrides['HISTORY_LOOKBACK'] = args.history_lookback
    if args.recent_lookback is not None:
        overrides['RECENT_LOOKBACK'] = args.recent_lookback
    if args.min_drawdown is not None:
        overrides['MIN_DRAWDOWN'] = -abs(args.min_drawdown)
    if args.max_drawdown_abs is not None:
        overrides['MAX_DRAWDOWN_ABS'] = args.max_drawdown_abs
    if args.max_box_range is not None:
        overrides['MAX_BOX_RANGE'] = args.max_box_range
    if args.max_volatility_ratio is not None:
        overrides['MAX_VOLATILITY_RATIO'] = args.max_volatility_ratio
    if args.min_glory_ratio is not None:
        overrides['MIN_GLORY_RATIO'] = args.min_glory_ratio
    if args.min_glory_amplitude is not None:
        overrides['MIN_GLORY_AMPLITUDE'] = args.min_glory_amplitude
    if args.min_positive_low is not None:
        overrides['MIN_POSITIVE_LOW'] = args.min_positive_low
    if args.min_high_price is not None:
        overrides['MIN_HIGH_PRICE'] = args.min_high_price
    if args.min_price is not None:
        overrides['MIN_PRICE'] = args.min_price
    if args.min_data_months is not None:
        overrides['MIN_DATA_MONTHS'] = args.min_data_months
    if args.price_position_min is not None:
        overrides['PRICE_POSITION_MIN'] = args.price_position_min
    if args.price_position_max is not None:
        overrides['PRICE_POSITION_MAX'] = args.price_position_max
    if args.sql_limit is not None:
        overrides['SQL_LIMIT'] = args.sql_limit
    if args.slope_min is not None:
        overrides['SLOPE_MIN'] = args.slope_min
    if args.slope_max is not None:
        overrides['SLOPE_MAX'] = args.slope_max
    if args.min_r_squared is not None:
        overrides['MIN_R_SQUARED'] = args.min_r_squared
    if args.exclude_st:
        overrides['EXCLUDE_ST'] = True
    if args.exclude_blacklist:
        overrides['EXCLUDE_BLACKLIST'] = True
    if args.final_limit is not None:
        overrides['FINAL_LIMIT'] = args.final_limit

    # Resolve preset (CLI > DEFAULT_PRESET)
    preset = args.preset or DEFAULT_PRESET

    # Get configuration with overrides (auto-validates)
    from selection.config import get_config
    try:
        config = get_config(preset, **overrides)
        validate_config(config)
    except AssertionError as e:
        logger.error(f"Invalid configuration: {e}")
        print(f"\n❌ Configuration Error: {e}")
        print("\nPlease check your command-line parameters.")
        print("Use --show-config to see the current configuration.")
        return

    # Initialize screener with validated config
    screener = FlatbottomScreener(preset=preset, code_filter=code_filter)
    screener.config = config  # Apply validated config
    screener.preset = preset

    # Ensure required tables exist (idempotent)
    screener._ensure_tables_exist()

    # Show config if requested
    if args.show_config:
        print_config(screener.config)
        if overrides:
            print("\nCommand-line overrides:")
            for key, value in overrides.items():
                print(f"  {key}: {value}")
        return

    # Run screening
    results = screener.run()

    if results.empty:
        logger.warning("No results to save")
        return

    # Save results
    screener.save_to_db(results)
    screener.export_csv(results)

    # Print summary
    print("\n" + "=" * 60)
    print("SCREENING SUMMARY")
    print("=" * 60)
    print(f"Preset:          {preset}")
    print(f"Stocks found:    {len(results)}")
    print(f"Top 10 scores:   {results['score'].head(10).tolist()}")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    main()

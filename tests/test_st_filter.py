#!/usr/bin/env python3
"""Test ST stock filtering to verify pattern matching accuracy."""

import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from selection.find_flatbottom import FlatbottomScreener

def test_st_filtering():
    """Test ST filtering with various stock names."""

    # Create test data with various stock names
    test_stocks = pd.DataFrame({
        'code': [
            '600365.SH', '000860.SZ', '688057.SH', '600959.SH',  # Should KEEP
            '600001.SH', '600002.SH', '600003.SH', '600004.SH',  # Should FILTER (ST stocks)
            '600005.SH', '600006.SH'  # Should KEEP (false positive test)
        ],
        'name': [
            '通葡股份',      # Should KEEP (non-ST)
            '顺鑫农业',      # Should KEEP (non-ST)
            '金达莱',        # Should KEEP (non-ST)
            '江苏有线',      # Should KEEP (non-ST)
            'ST通葡',        # Should FILTER (ST stock)
            '*ST海润',       # Should FILTER (*ST stock)
            'S*ST前锋',      # Should FILTER (S*ST stock)
            'SST天一',       # Should FILTER (SST stock)
            'BEST股份',      # Should KEEP (contains "ST" but not ST stock)
            'FASTEST科技'    # Should KEEP (contains "ST" but not ST stock)
        ],
        'score': [66.8, 65.5, 53.4, 66.8, 50.0, 45.0, 40.0, 38.0, 55.0, 52.0]
    })

    print("=" * 80)
    print("ST STOCK FILTERING TEST")
    print("=" * 80)
    print(f"\nOriginal test data ({len(test_stocks)} stocks):")
    print(test_stocks[['code', 'name', 'score']].to_string(index=False))

    # Create screener instance
    screener = FlatbottomScreener(preset='balanced')

    # Apply ST filtering
    filtered = screener._filter_st_stocks(test_stocks.copy())

    print(f"\n\nAfter ST filtering ({len(filtered)} stocks remaining):")
    print(filtered[['code', 'name', 'score']].to_string(index=False))

    # Verify results
    print("\n" + "=" * 80)
    print("VERIFICATION RESULTS")
    print("=" * 80)

    expected_filtered_out = ['ST通葡', '*ST海润', 'S*ST前锋', 'SST天一']
    expected_kept = ['通葡股份', '顺鑫农业', '金达莱', '江苏有线', 'BEST股份', 'FASTEST科技']

    actually_kept = filtered['name'].tolist()
    actually_filtered = test_stocks[~test_stocks['name'].isin(actually_kept)]['name'].tolist()

    print(f"\nExpected to filter: {expected_filtered_out}")
    print(f"Actually filtered:  {actually_filtered}")
    print(f"✓ Match: {set(expected_filtered_out) == set(actually_filtered)}")

    print(f"\nExpected to keep:   {expected_kept}")
    print(f"Actually kept:      {actually_kept}")
    print(f"✓ Match: {set(expected_kept) == set(actually_kept)}")

    # Final verdict
    print("\n" + "=" * 80)
    if (set(expected_filtered_out) == set(actually_filtered) and
        set(expected_kept) == set(actually_kept)):
        print("✅ ST FILTERING TEST PASSED")
        print("\nKey points verified:")
        print("  1. Correctly filters ST stocks (ST, *ST, S*ST, SST)")
        print("  2. Correctly keeps non-ST stocks")
        print("  3. Avoids false positives (BEST股份, FASTEST科技)")
        print("=" * 80)
        return True
    else:
        print("❌ ST FILTERING TEST FAILED")
        print("=" * 80)
        return False

if __name__ == '__main__':
    success = test_st_filtering()
    sys.exit(0 if success else 1)

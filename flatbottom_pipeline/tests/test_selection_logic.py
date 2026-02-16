"""Tests for flatbottom_pipeline.selection.find_flatbottom core logic."""
import numpy as np
import pandas as pd
import pytest

from flatbottom_pipeline.selection.find_flatbottom import FlatbottomScreener


# ---------------------------------------------------------------------------
# Helper: create screener with a known config (no DB needed)
# ---------------------------------------------------------------------------

def _make_screener(**overrides):
    """Create a FlatbottomScreener with balanced preset + optional overrides."""
    s = FlatbottomScreener(preset="balanced")
    s.config.update(overrides)
    return s


# ===========================================================================
# _calculate_trend
# ===========================================================================

class TestCalculateTrend:
    """Tests for FlatbottomScreener._calculate_trend."""

    def test_normal_increasing(self):
        """Linearly increasing prices → positive slope, high R²."""
        s = _make_screener()
        prices = np.linspace(10.0, 20.0, num=24)  # 24 months, 10→20
        slope, r2 = s._calculate_trend(prices)
        assert slope > 0, f"Expected positive slope, got {slope}"
        assert r2 > 0.99, f"Expected R²≈1, got {r2}"

    def test_normal_decreasing(self):
        """Linearly decreasing prices → negative slope, high R²."""
        s = _make_screener()
        prices = np.linspace(20.0, 10.0, num=24)
        slope, r2 = s._calculate_trend(prices)
        assert slope < 0, f"Expected negative slope, got {slope}"
        assert r2 > 0.99

    def test_flat(self):
        """Constant prices → slope≈0, R² is NaN (no variation to explain)."""
        s = _make_screener()
        prices = np.full(24, 15.0)
        slope, r2 = s._calculate_trend(prices)
        assert abs(slope) < 1e-10, f"Expected slope≈0, got {slope}"
        # R² is undefined for constant y; scipy linregress returns NaN
        assert np.isnan(r2) or r2 < 0.01

    def test_insufficient_data(self):
        """< 12 data points → (0, 0)."""
        s = _make_screener()
        prices = np.array([10.0, 11.0, 12.0])  # only 3 points
        slope, r2 = s._calculate_trend(prices)
        assert slope == 0.0
        assert r2 == 0.0

    def test_zero_initial_price(self):
        """First price = 0 → (0, 0) to avoid division by zero."""
        s = _make_screener()
        prices = np.concatenate([[0.0], np.linspace(1, 10, 23)])
        slope, r2 = s._calculate_trend(prices)
        assert slope == 0.0
        assert r2 == 0.0


# ===========================================================================
# _validate_trend
# ===========================================================================

class TestValidateTrend:
    """Tests for FlatbottomScreener._validate_trend."""

    def test_pass(self):
        """Slope and R² both in range → True."""
        s = _make_screener(SLOPE_MIN=-0.02, SLOPE_MAX=0.03, MIN_R_SQUARED=0.25)
        assert s._validate_trend(slope=0.01, r_squared=0.5) is True

    def test_slope_below_min(self):
        """Slope below SLOPE_MIN → False."""
        s = _make_screener(SLOPE_MIN=-0.02, SLOPE_MAX=0.03, MIN_R_SQUARED=0.25)
        assert s._validate_trend(slope=-0.05, r_squared=0.5) is False

    def test_slope_above_max(self):
        """Slope above SLOPE_MAX → False."""
        s = _make_screener(SLOPE_MIN=-0.02, SLOPE_MAX=0.03, MIN_R_SQUARED=0.25)
        assert s._validate_trend(slope=0.05, r_squared=0.5) is False

    def test_r2_too_low(self):
        """R² below threshold → False."""
        s = _make_screener(SLOPE_MIN=-0.02, SLOPE_MAX=0.03, MIN_R_SQUARED=0.25)
        assert s._validate_trend(slope=0.01, r_squared=0.10) is False

    def test_boundary_slope_min(self):
        """Slope exactly at SLOPE_MIN → True (inclusive boundary)."""
        s = _make_screener(SLOPE_MIN=-0.02, SLOPE_MAX=0.03, MIN_R_SQUARED=0.25)
        assert s._validate_trend(slope=-0.02, r_squared=0.30) is True

    def test_boundary_r2_exactly_at_threshold(self):
        """R² exactly at MIN_R_SQUARED → True (>= check)."""
        s = _make_screener(SLOPE_MIN=-0.02, SLOPE_MAX=0.03, MIN_R_SQUARED=0.25)
        assert s._validate_trend(slope=0.0, r_squared=0.25) is True


# ===========================================================================
# _filter_st_stocks
# ===========================================================================

class TestFilterStStocks:
    """Tests for FlatbottomScreener._filter_st_stocks."""

    def _make_df(self, names):
        return pd.DataFrame({"code": range(len(names)), "name": names})

    def test_no_st_stocks(self):
        """Normal names should all pass."""
        s = _make_screener()
        df = self._make_df(["浦发银行", "贵州茅台", "比亚迪"])
        result = s._filter_st_stocks(df)
        assert len(result) == 3

    def test_st_filtered(self):
        """ST prefix names should be removed."""
        s = _make_screener()
        df = self._make_df(["ST金泰", "浦发银行", "*ST长生"])
        result = s._filter_st_stocks(df)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "浦发银行"

    def test_delisted(self):
        """退市/PT/终止上市 markers should be removed."""
        s = _make_screener()
        df = self._make_df(["退市博元", "PT水仙", "终止上市测试", "正常股票"])
        result = s._filter_st_stocks(df)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "正常股票"

    def test_sst_variant(self):
        """SST and S*ST variants should be removed."""
        s = _make_screener()
        df = self._make_df(["SST华新", "S*ST集琦", "正常"])
        result = s._filter_st_stocks(df)
        assert len(result) == 1

    def test_missing_name_column(self):
        """DataFrame without 'name' column → return as-is."""
        s = _make_screener()
        df = pd.DataFrame({"code": [1, 2, 3]})
        result = s._filter_st_stocks(df)
        assert len(result) == 3

    def test_nan_name(self):
        """NaN name should not be flagged as ST."""
        s = _make_screener()
        df = self._make_df([None, "浦发银行"])
        result = s._filter_st_stocks(df)
        assert len(result) == 2

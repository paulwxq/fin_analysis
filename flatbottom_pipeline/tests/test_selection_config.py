"""Tests for flatbottom_pipeline.selection.config (presets & validation)."""
import pytest

from flatbottom_pipeline.selection.config import (
    PRESETS,
    get_config,
    validate_config,
)


# ===========================================================================
# Preset loading
# ===========================================================================

class TestPresetLoading:
    """Verify all three presets load and pass validation."""

    @pytest.mark.parametrize("preset", ["conservative", "balanced", "aggressive"])
    def test_preset_loads(self, preset):
        cfg = get_config(preset)
        assert isinstance(cfg, dict)
        # Must contain both SQL and Python layer keys
        assert "SLOPE_MIN" in cfg
        assert "MIN_DRAWDOWN" in cfg

    def test_default_preset_loads(self):
        """get_config() without argument uses DEFAULT_PRESET."""
        cfg = get_config()
        assert isinstance(cfg, dict)

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="未知预设"):
            get_config("nonexistent")


# ===========================================================================
# Override mechanism
# ===========================================================================

class TestOverride:
    def test_override_merges(self):
        """Override params should replace preset values."""
        cfg = get_config("balanced", MIN_DRAWDOWN=-0.60)
        assert cfg["MIN_DRAWDOWN"] == -0.60

    def test_override_does_not_leak(self):
        """Override in one call should not affect subsequent calls."""
        _ = get_config("balanced", MIN_DRAWDOWN=-0.60)
        cfg2 = get_config("balanced")
        assert cfg2["MIN_DRAWDOWN"] == PRESETS["balanced"]["MIN_DRAWDOWN"]


# ===========================================================================
# validate_config edge cases
# ===========================================================================

class TestValidateConfig:
    """Each test creates an invalid config and verifies AssertionError."""

    def _base_config(self):
        return get_config("balanced")

    def test_drawdown_positive_fails(self):
        cfg = self._base_config()
        cfg["MIN_DRAWDOWN"] = 0.30  # should be negative
        with pytest.raises(AssertionError, match="MIN_DRAWDOWN 必须为负数"):
            validate_config(cfg)

    def test_slope_inverted_fails(self):
        cfg = self._base_config()
        cfg["SLOPE_MIN"] = 0.05
        cfg["SLOPE_MAX"] = -0.01  # min > max
        with pytest.raises(AssertionError, match="SLOPE_MIN 必须小于 SLOPE_MAX"):
            validate_config(cfg)

    def test_r_squared_above_one_fails(self):
        cfg = self._base_config()
        cfg["MIN_R_SQUARED"] = 1.5
        with pytest.raises(AssertionError, match="MIN_R_SQUARED"):
            validate_config(cfg)

    def test_r_squared_zero_fails(self):
        cfg = self._base_config()
        cfg["MIN_R_SQUARED"] = 0.0
        with pytest.raises(AssertionError, match="MIN_R_SQUARED"):
            validate_config(cfg)

    def test_glory_ratio_below_one_fails(self):
        cfg = self._base_config()
        cfg["MIN_GLORY_RATIO"] = 0.5
        with pytest.raises(AssertionError, match="MIN_GLORY_RATIO 必须 > 1.0"):
            validate_config(cfg)

    def test_recent_ge_history_fails(self):
        cfg = self._base_config()
        cfg["RECENT_LOOKBACK"] = cfg["HISTORY_LOOKBACK"] + 1
        with pytest.raises(AssertionError, match="RECENT_LOOKBACK 必须小于 HISTORY_LOOKBACK"):
            validate_config(cfg)

    def test_valid_config_passes(self):
        """A valid config should not raise."""
        cfg = self._base_config()
        validate_config(cfg)  # should not raise

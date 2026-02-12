"""Unit tests for stock_analyzer.utils."""

import pytest

from stock_analyzer.utils import format_symbol, get_market, normalize_symbol


def test_format_symbol_bare() -> None:
    assert format_symbol("000001", "bare") == "000001"


def test_format_symbol_lower_sz() -> None:
    assert format_symbol("000001", "lower") == "sz000001"


def test_format_symbol_lower_sh() -> None:
    assert format_symbol("600519", "lower") == "sh600519"


def test_format_symbol_upper() -> None:
    assert format_symbol("000001", "upper") == "SZ000001"


def test_format_symbol_invalid_code() -> None:
    with pytest.raises(ValueError):
        format_symbol("12345", "bare")


def test_get_market_sh() -> None:
    assert get_market("600519") == "sh"


def test_get_market_sz() -> None:
    assert get_market("000001") == "sz"
    assert get_market("300750") == "sz"


def test_normalize_symbol_bare() -> None:
    assert normalize_symbol("600519") == "600519"


def test_normalize_symbol_with_suffix() -> None:
    assert normalize_symbol("600519.SH") == "600519"
    assert normalize_symbol("000001.SZ") == "000001"
    assert normalize_symbol("600519.sh") == "600519"


def test_normalize_symbol_with_prefix() -> None:
    assert normalize_symbol("SH600519") == "600519"
    assert normalize_symbol("sz000001") == "000001"


def test_normalize_symbol_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_symbol("贵州茅台")
    with pytest.raises(ValueError):
        normalize_symbol("12345")

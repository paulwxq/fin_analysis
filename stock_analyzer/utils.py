"""Utility helpers shared by stock_analyzer modules."""

from __future__ import annotations

import re


# Match common symbol formats:
# 600519.SH / 600519.sh / SH600519 / sh600519 / 600519
_SYMBOL_RE = re.compile(
    r"^(?:(?P<prefix>[A-Za-z]{2})(?P<code1>\d{6}))$"
    r"|^(?:(?P<code2>\d{6})(?:[.\-](?P<suffix>[A-Za-z]{2,4}))?)$"
)


def get_market(code: str) -> str:
    """Return exchange market code for a 6-digit A-share symbol."""
    if not code.isdigit() or len(code) != 6:
        raise ValueError(f"Invalid stock code: '{code}', expected 6-digit string")
    return "sh" if code.startswith("6") else "sz"


def format_symbol(code: str, style: str) -> str:
    """Convert a 6-digit symbol into AKShare-specific symbol style."""
    if not code.isdigit() or len(code) != 6:
        raise ValueError(f"Invalid stock code: '{code}', expected 6-digit string")

    market = get_market(code)

    if style == "bare":
        return code
    if style == "lower":
        return f"{market}{code}"
    if style == "upper":
        return f"{market.upper()}{code}"
    raise ValueError(f"Unknown style: '{style}', expected 'bare'/'lower'/'upper'")


def normalize_symbol(raw: str) -> str:
    """Extract normalized 6-digit symbol from common CLI symbol forms."""
    value = raw.strip()
    match = _SYMBOL_RE.match(value)
    if match:
        code = match.group("code1") or match.group("code2")
        if code and len(code) == 6:
            return code

    raise ValueError(
        f"Cannot normalize symbol: '{value}'. "
        "Expected formats: 600519 / 600519.SH / SH600519"
    )

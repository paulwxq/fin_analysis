from dataclasses import dataclass
import re
from typing import Optional, Literal

Exchange = Literal["SH", "SZ", "BJ"]
Board = Literal["STAR", "SH_MAIN", "SZ_MAIN", "SME", "CHINEXT", "BSE"]

@dataclass(frozen=True)
class CodeInfo:
    raw: str          # 输入原值
    code6: str        # 6位纯数字
    exchange: Exchange
    board: Board
    ts_code: str      # 600000.SH / 300001.SZ / 830001.BJ

_CODE_RE = re.compile(r"^\d{6}$")

def normalize_to_6_digits(code: str) -> str:
    """去空格，保留纯数字；支持输入 '600000.SH' / '600000' / ' 600000 '."""
    if code is None:
        raise ValueError("code is None")

    s = str(code).strip().upper()

    # 兼容 600000.SH / 600000.SZ / 600000.BJ
    if "." in s:
        left, _ = s.split(".", 1)
        s = left.strip()

    if not _CODE_RE.match(s):
        raise ValueError(f"Invalid code (expect 6 digits): {code}")

    return s

def classify_cn_stock(code: str) -> CodeInfo:
    """
    识别A股代码归属：识别交易所、板块，并生成标准代码。
    """
    c = normalize_to_6_digits(code)

    # SH
    if c.startswith("6"):
        if c.startswith("688"):
            exchange: Exchange = "SH"
            board: Board = "STAR"
        elif c.startswith(("600", "601", "603", "605")):
            exchange = "SH"
            board = "SH_MAIN"
        else:
            # 保守兜底：6xxxxx 仍视为 SH
            exchange = "SH"
            board = "SH_MAIN"
        ts = f"{c}.SH"
        return CodeInfo(raw=str(code), code6=c, exchange=exchange, board=board, ts_code=ts)

    # SZ
    if c.startswith(("0", "1", "2", "3")):
        exchange = "SZ"
        if c.startswith(("000", "001")):
            board = "SZ_MAIN"
        elif c.startswith("002"):
            board = "SME"       # 中小板（已并入主板，但代码仍保留）
        elif c.startswith("300"):
            board = "CHINEXT"   # 创业板
        else:
            # 兜底：0/1/2/3 开头但不在常见段，按 SZ_MAIN
            board = "SZ_MAIN"
        ts = f"{c}.SZ"
        return CodeInfo(raw=str(code), code6=c, exchange=exchange, board=board, ts_code=ts)

    # BJ
    if c.startswith(("8", "4")):
        exchange = "BJ"
        board = "BSE"
        ts = f"{c}.BJ"
        return CodeInfo(raw=str(code), code6=c, exchange=exchange, board=board, ts_code=ts)

    raise ValueError(f"Unrecognized A-share code prefix: {code}")

if __name__ == "__main__":
    # 简单的冒烟测试
    tests = ["600000", "688001", "000001", "002415", "300750", "830001", "600000.SH", "430090"]
    for t in tests:
        print(f"Input: {t:10} -> {classify_cn_stock(t)}")

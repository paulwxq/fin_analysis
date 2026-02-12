"""
验证 stock_financial_analysis_indicator_em 的可用性及字段映射。
改造思路：以 EM 接口为主路径，重命名关键列后复用现有解析逻辑。

字段映射（已通过 probe_financial_em.py 实测确认）：
    REPORT_DATE           → 报告期（转为 YYYY-MM-DD 字符串）
    EPSJB                 → 每股收益 eps（基本每股收益）
    BPS                   → 每股净资产 net_asset_per_share
    ROEJQ                 → ROE (加权平均净资产收益率%)
    XSMLL                 → 毛利率 gross_margin (销售毛利率%)
    XSJLL                 → 净利率 net_margin (销售净利率%)
    TOTALOPERATEREVETZ    → 营收同比增长率 revenue_growth (%)
    PARENTNETPROFITTZ     → 净利润同比增长率 profit_growth (%)
    ZCFZL                 → 资产负债率 debt_ratio (%)
    LD                    → 流动比率 current_ratio
"""

import pandas as pd
import pytest

import stock_analyzer.module_a_akshare as module_a
from stock_analyzer.module_a_akshare import AKShareCollector

# ---------------------------------------------------------------------------
# 字段映射常量（改造后的生产代码也将使用这套映射）
# ---------------------------------------------------------------------------
EM_FIELD_MAP = {
    "REPORT_DATE": "报告期",
    "EPSJB": "摊薄每股收益(元)",
    "BPS": "每股净资产_调整后(元)",
    "ROEJQ": "净资产收益率_摊薄(%)",
    "XSMLL": "销售毛利率(%)",
    "XSJLL": "销售净利率(%)",
    "TOTALOPERATEREVETZ": "营业总收入同比增长率(%)",
    "PARENTNETPROFITTZ": "归属母公司股东的净利润同比增长率(%)",
    "ZCFZL": "资产负债率(%)",
    "LD": "流动比率",
}


def _make_em_df() -> pd.DataFrame:
    """模拟 stock_financial_analysis_indicator_em 的真实返回（最近2期）。
    字段值来自 probe_financial_em.py 的实测结果。
    """
    return pd.DataFrame([
        {
            "SECUCODE": "600519.SH",
            "SECURITY_CODE": "600519",
            "REPORT_DATE": pd.Timestamp("2025-09-30"),
            "REPORT_TYPE": "三季报",
            "EPSJB": 51.53,
            "EPSXS": 51.53,
            "BPS": 205.283142,
            "ROEJQ": 24.64,
            "XSMLL": 91.293383,
            "XSJLL": 52.080089,
            "TOTALOPERATEREVETZ": 6.320002,
            "PARENTNETPROFITTZ": 6.245845,
            "ZCFZL": 12.808753,
            "LD": 6.619319,
        },
        {
            "SECUCODE": "600519.SH",
            "SECURITY_CODE": "600519",
            "REPORT_DATE": pd.Timestamp("2025-06-30"),
            "REPORT_TYPE": "中报",
            "EPSJB": 36.18,
            "EPSXS": 36.18,
            "BPS": 189.975286,
            "ROEJQ": 17.89,
            "XSMLL": 91.299309,
            "XSJLL": 52.564068,
            "TOTALOPERATEREVETZ": 9.158168,
            "PARENTNETPROFITTZ": 8.891467,
            "ZCFZL": 14.754852,
            "LD": 5.72974,
        },
    ])


# ---------------------------------------------------------------------------
# 测试 stock_financial_analysis_indicator_em 接口本身
# ---------------------------------------------------------------------------

def test_em_func_exists_in_akshare():
    """确认 stock_financial_analysis_indicator_em 在 AKShare 1.18.22 中存在。"""
    import akshare as ak
    assert hasattr(ak, "stock_financial_analysis_indicator_em")


def test_em_func_accepts_dot_format_symbol():
    """确认接口接受 '600519.SH' 格式的 symbol 参数。"""
    import inspect
    import akshare as ak
    sig = inspect.signature(ak.stock_financial_analysis_indicator_em)
    assert "symbol" in sig.parameters


def test_em_field_map_keys_exist_in_real_data():
    """
    验证字段映射的 key 都在 EM 接口返回的列中存在。
    如果此 test 失败说明 AKShare 改列名了，需更新 EM_FIELD_MAP。
    """
    df = _make_em_df()
    for em_col in EM_FIELD_MAP:
        assert em_col in df.columns, f"列 '{em_col}' 不在 EM 返回中"


# ---------------------------------------------------------------------------
# 测试列名重命名后的解析逻辑
# ---------------------------------------------------------------------------

def _apply_em_rename(df: pd.DataFrame) -> pd.DataFrame:
    """将 EM 列名重命名为 _collect_financial_indicators 期望的中文列名。"""
    df = df.copy()
    df["报告期"] = pd.to_datetime(df["REPORT_DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    rename_cols = {k: v for k, v in EM_FIELD_MAP.items() if k != "REPORT_DATE" and k in df.columns}
    df = df.rename(columns=rename_cols)
    return df


def test_rename_produces_expected_chinese_columns():
    df = _apply_em_rename(_make_em_df())
    for cn_col in EM_FIELD_MAP.values():
        assert cn_col in df.columns, f"重命名后缺少列 '{cn_col}'"


def test_report_date_formatted_as_date_string():
    df = _apply_em_rename(_make_em_df())
    assert df["报告期"].iloc[0] == "2025-09-30"
    assert df["报告期"].iloc[1] == "2025-06-30"


def test_em_parse_gives_correct_values(mocker):
    """修复后 _collect_financial_indicators 使用 EM 数据，字段值正确。"""
    collector = AKShareCollector("600519", "贵州茅台")

    em_renamed = _apply_em_rename(_make_em_df())
    mocker.patch.object(
        collector, "safe_call",
        return_value=em_renamed,
    )

    result = collector._collect_financial_indicators()

    assert result is not None
    assert len(result) >= 1
    r0 = result[0]
    assert r0["report_date"] == "2025-09-30"
    assert r0["eps"] == pytest.approx(51.53)
    assert r0["net_asset_per_share"] == pytest.approx(205.283142)
    assert r0["roe"] == pytest.approx(24.64)
    assert r0["gross_margin"] == pytest.approx(91.293383)
    assert r0["net_margin"] == pytest.approx(52.080089)
    assert r0["revenue_growth"] == pytest.approx(6.320002)
    assert r0["profit_growth"] == pytest.approx(6.245845)
    assert r0["debt_ratio"] == pytest.approx(12.808753)
    assert r0["current_ratio"] == pytest.approx(6.619319)


def test_em_parse_returns_multiple_periods(mocker):
    """EM 返回多期数据时，按报告期降序截取前 N 期。"""
    from stock_analyzer.config import AKSHARE_FINANCIAL_PERIODS
    collector = AKShareCollector("600519", "贵州茅台")

    em_renamed = _apply_em_rename(_make_em_df())
    mocker.patch.object(collector, "safe_call", return_value=em_renamed)

    result = collector._collect_financial_indicators()

    assert result is not None
    assert len(result) <= AKSHARE_FINANCIAL_PERIODS
    # 降序排列：三季报在前，中报在后
    assert result[0]["report_date"] == "2025-09-30"
    assert result[1]["report_date"] == "2025-06-30"


def test_em_parse_topic_status_ok(mocker):
    """EM 数据返回正常时 topic_status 应为 ok。"""
    collector = AKShareCollector("600519", "贵州茅台")
    em_renamed = _apply_em_rename(_make_em_df())
    mocker.patch.object(collector, "safe_call", return_value=em_renamed)

    result = collector._safe_collect(
        "financial_indicators",
        collector._collect_financial_indicators,
    )

    assert result is not None
    assert collector.topic_status["financial_indicators"] == AKShareCollector.STATUS_OK

"""
验证 module_a_akshare.py 三处列名修复后的行为。

修复对应关系：
  northbound            持股数量/持股市值/持股数量变化-增减比例
                     →  今日持股-股数/今日持股-市值/今日增持估计-市值增幅

  valuation_vs_industry 个股PE/行业PE(平均)/行业PE(中位数)/个股PB/行业PB(平均)
                     →  按代码定位目标股行，用 市盈率-TTM/市净率-MRQ，
                         其余行计算均值/中位数

  valuation_baidu PS/DV 移除不支持的 市销率(TTM)/股息率(TTM)，
                     → ps_ttm/dv_ttm 置 None，不再抛 TypeError
"""

import pandas as pd
import pytest

import stock_analyzer.module_a_akshare as module_a
from stock_analyzer.module_a_akshare import AKShareCollector


# ---------------------------------------------------------------------------
# 复用 diagnosis 里的 helper（也可以直接定义 fixture）
# ---------------------------------------------------------------------------

def _make_northbound_df(symbol: str = "600519") -> pd.DataFrame:
    return pd.DataFrame([
        {
            "序号": 1, "代码": symbol, "名称": "贵州茅台",
            "今日收盘价": 1500.0, "今日涨跌幅": 1.2,
            "今日持股-股数": 12345678.0, "今日持股-市值": 18518517000.0,
            "今日持股-占流通股比": 0.98, "今日持股-占总股本比": 0.98,
            "今日增持估计-股数": 50000.0, "今日增持估计-市值": 75000000.0,
            "今日增持估计-市值增幅": 0.41,
            "今日增持估计-占流通股比": 0.004, "今日增持估计-占总股本比": 0.004,
            "所属板块": "白酒", "日期": "2026-02-11",
        },
    ])


def _make_valuation_vs_industry_df(symbol: str = "600519") -> pd.DataFrame:
    return pd.DataFrame([
        {  # Row 0: 行业汇总行
            "排名": "5/28", "代码": "", "简称": "行业均值",
            "PEG": None, "市盈率-TTM": None, "市净率-MRQ": None,
        },
        {  # Row 1: 同行甲
            "排名": "1", "代码": "000858", "简称": "五粮液",
            "PEG": 1.2, "市盈率-TTM": 22.0, "市净率-MRQ": 3.8,
        },
        {  # Row 2: 目标股（被 swap 到这里）
            "排名": "5", "代码": symbol, "简称": "贵州茅台",
            "PEG": 2.1, "市盈率-TTM": 32.0, "市净率-MRQ": 10.5,
        },
        {  # Row 3: 同行乙
            "排名": "2", "代码": "600809", "简称": "山西汾酒",
            "PEG": 1.5, "市盈率-TTM": 25.0, "市净率-MRQ": 5.2,
        },
    ])


# ===========================================================================
# Fix #1: northbound 列名修复
# ===========================================================================

class TestNorthboundFix:
    def test_shares_held_reads_correct_column(self, mocker):
        """修复后：今日持股-股数 能被正确读取。"""
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call_market_cached",
            return_value=_make_northbound_df("600519"),
        )

        result = collector._collect_northbound()

        assert result is not None
        assert result["held"] is True
        assert result["shares_held"] == pytest.approx(12345678.0)

    def test_market_value_reads_correct_column(self, mocker):
        """修复后：今日持股-市值 能被正确读取。"""
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call_market_cached",
            return_value=_make_northbound_df("600519"),
        )

        result = collector._collect_northbound()

        assert result["market_value"] == pytest.approx(18518517000.0)

    def test_change_pct_reads_correct_column(self, mocker):
        """修复后：今日增持估计-市值增幅 能被正确读取。"""
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call_market_cached",
            return_value=_make_northbound_df("600519"),
        )

        result = collector._collect_northbound()

        assert result["change_pct"] == pytest.approx(0.41)

    def test_not_held_returns_none_values(self, mocker):
        """未持有时，数值仍全为 None。"""
        collector = AKShareCollector("000001", "平安银行")
        mocker.patch.object(
            collector, "safe_call_market_cached",
            return_value=_make_northbound_df("600519"),
        )

        result = collector._collect_northbound()

        assert result["held"] is False
        assert result["shares_held"] is None


# ===========================================================================
# Fix #2: valuation_vs_industry 列名修复
# ===========================================================================

class TestValuationVsIndustryFix:
    def test_stock_pe_reads_from_market_pe_ttm(self, mocker):
        """修复后：stock_pe 从 市盈率-TTM 列读取，且定位到目标股行。"""
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call",
            return_value=_make_valuation_vs_industry_df("600519"),
        )

        result = collector._collect_valuation_vs_industry()

        assert result is not None
        assert result["stock_pe"] == pytest.approx(32.0)

    def test_stock_pb_reads_from_market_pb_mrq(self, mocker):
        """修复后：stock_pb 从 市净率-MRQ 列读取。"""
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call",
            return_value=_make_valuation_vs_industry_df("600519"),
        )

        result = collector._collect_valuation_vs_industry()

        assert result["stock_pb"] == pytest.approx(10.5)

    def test_industry_avg_pe_computed_from_peers(self, mocker):
        """修复后：行业均值 PE 从同行（排除目标股和汇总行）计算。"""
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call",
            return_value=_make_valuation_vs_industry_df("600519"),
        )

        result = collector._collect_valuation_vs_industry()

        # 同行：五粮液(22.0) + 山西汾酒(25.0) → 均值 23.5
        assert result["industry_avg_pe"] == pytest.approx(23.5)

    def test_industry_median_pe_computed_from_peers(self, mocker):
        """中位数 PE。"""
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call",
            return_value=_make_valuation_vs_industry_df("600519"),
        )

        result = collector._collect_valuation_vs_industry()

        assert result["industry_median_pe"] == pytest.approx(23.5)

    def test_industry_avg_pb_computed_from_peers(self, mocker):
        """行业均值 PB。"""
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call",
            return_value=_make_valuation_vs_industry_df("600519"),
        )

        result = collector._collect_valuation_vs_industry()

        # 五粮液(3.8) + 山西汾酒(5.2) → 均值 4.5
        assert result["industry_avg_pb"] == pytest.approx(4.5)

    def test_relative_valuation_reflects_real_comparison(self, mocker):
        """修复后：relative_valuation 能用真实数据得到有意义的判断。"""
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call",
            return_value=_make_valuation_vs_industry_df("600519"),
        )

        result = collector._collect_valuation_vs_industry()

        # 32.0 / 23.5 ≈ 1.36 → "明显高于行业平均"
        assert result["relative_valuation"] == "明显高于行业平均"

    def test_symbol_not_in_df_returns_none_values(self, mocker):
        """目标股不在表中时，PE/PB 为 None，不崩溃。"""
        collector = AKShareCollector("688008", "澜起科技")
        mocker.patch.object(
            collector, "safe_call",
            return_value=_make_valuation_vs_industry_df("600519"),  # 只有茅台
        )

        result = collector._collect_valuation_vs_industry()

        assert result is not None
        assert result["stock_pe"] is None
        assert result["stock_pb"] is None


# ===========================================================================
# Fix #3: valuation_baidu 不再请求不支持的 PS/DV 指标
# ===========================================================================

class TestValuationBaiduFix:
    def test_build_valuation_history_from_baidu_no_longer_requests_ps_dv(self, mocker):
        """
        修复后 _build_valuation_history_from_baidu 只请求 pe_ttm/pb，
        不再请求 市销率(TTM)/股息率(TTM)。
        """
        collector = AKShareCollector("600519", "贵州茅台")

        requested_indicators: list[str] = []

        def fake_baidu(symbol, indicator, period):
            requested_indicators.append(indicator)
            return pd.DataFrame({
                "date": pd.to_datetime(["2025-01-02", "2026-01-02"]),
                "value": [28.0, 32.0],
            })

        mocker.patch.object(module_a.ak, "stock_zh_valuation_baidu", fake_baidu)

        collector._build_valuation_history_from_baidu()

        assert "市销率(TTM)" not in requested_indicators
        assert "股息率(TTM)" not in requested_indicators
        assert "市盈率(TTM)" in requested_indicators
        assert "市净率" in requested_indicators

    def test_ps_dv_are_none_after_fix(self, mocker):
        """
        修复后 _collect_valuation_history：ps_ttm/dv_ttm 为 None，
        但 pe_ttm/pb 正常有值，不影响 topic_status = ok。
        """
        collector = AKShareCollector("600519", "贵州茅台")

        pe_df = pd.DataFrame({
            "date": pd.to_datetime([f"2025-{m:02d}-01" for m in range(1, 13)]
                                   + ["2026-01-02"]),
            "value": [28.0 + i * 0.3 for i in range(13)],
        })
        pb_df = pd.DataFrame({
            "date": pd.to_datetime([f"2025-{m:02d}-01" for m in range(1, 13)]
                                   + ["2026-01-02"]),
            "value": [9.0 + i * 0.1 for i in range(13)],
        })

        def fake_baidu(symbol, indicator, period):
            if indicator == "市盈率(TTM)":
                return pe_df
            if indicator == "市净率":
                return pb_df
            raise TypeError("'NoneType' object is not subscriptable")

        mocker.patch.object(module_a.ak, "stock_zh_valuation_baidu", fake_baidu)
        # 让代码走回退路径（stock_a_lg_indicator 不存在已在运行时为 False，
        # 但这里直接 patch _build_valuation_history_from_baidu 的上层入口）
        # 直接验证 _build_valuation_history_from_baidu 的结果
        merged = collector._build_valuation_history_from_baidu()

        assert merged is not None
        assert "pe_ttm" in merged.columns
        assert "pb" in merged.columns
        assert "ps_ttm" not in merged.columns
        assert "dv_ttm" not in merged.columns

        # 再模拟 _collect_valuation_history 读取 latest 行
        latest = merged.sort_values("trade_date").iloc[-1]
        ps = AKShareCollector._safe_float(latest.get("ps_ttm"))
        dv = AKShareCollector._safe_float(latest.get("dv_ttm"))
        assert ps is None
        assert dv is None

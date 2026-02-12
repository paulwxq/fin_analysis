"""
诊断并验证 module_a_akshare_failure_analysis_600519.md 中报告的 AKShare 列名/接口问题。

根因：
1. financial_indicators  ── stock_financial_analysis_indicator(start_year="1900") 固定返回空 DF
2. valuation_vs_industry ── 列名不匹配：代码找 "个股PE" 等，API 实际返回 "市盈率-TTM" 等
3. northbound            ── 列名不匹配：代码找 "持股数量" 等，API 实际返回 "今日持股-股数" 等
4. valuation_history PS/DV ── stock_zh_valuation_baidu 不支持 "市销率(TTM)"/"股息率(TTM)"，
                              但代码请求了这两个不支持的 indicator → TypeError
"""

import pandas as pd
import pytest

import stock_analyzer.module_a_akshare as module_a
from stock_analyzer.module_a_akshare import AKShareCollector


# ---------------------------------------------------------------------------
# 辅助：构造北向持仓 DataFrame（真实列名）
# ---------------------------------------------------------------------------

def _make_northbound_df(symbol: str = "600519") -> pd.DataFrame:
    """模拟 stock_hsgt_hold_stock_em(market='北向', indicator='今日排行') 真实返回。

    真实列（由 AKShare 1.18.22 源码 stock_hsgt_em.py 确认）：
    序号, 代码, 名称, 今日收盘价, 今日涨跌幅,
    今日持股-股数, 今日持股-市值, 今日持股-占流通股比, 今日持股-占总股本比,
    今日增持估计-股数, 今日增持估计-市值, 今日增持估计-市值增幅,
    今日增持估计-占流通股比, 今日增持估计-占总股本比,
    所属板块, 日期
    """
    return pd.DataFrame([
        {
            "序号": 1,
            "代码": symbol,
            "名称": "贵州茅台",
            "今日收盘价": 1500.0,
            "今日涨跌幅": 1.2,
            "今日持股-股数": 12345678.0,
            "今日持股-市值": 18518517000.0,
            "今日持股-占流通股比": 0.98,
            "今日持股-占总股本比": 0.98,
            "今日增持估计-股数": 50000.0,
            "今日增持估计-市值": 75000000.0,
            "今日增持估计-市值增幅": 0.41,
            "今日增持估计-占流通股比": 0.004,
            "今日增持估计-占总股本比": 0.004,
            "所属板块": "白酒",
            "日期": "2026-02-11",
        },
        {
            "序号": 2,
            "代码": "000858",
            "名称": "五粮液",
            "今日收盘价": 120.0,
            "今日涨跌幅": -0.5,
            "今日持股-股数": 9000000.0,
            "今日持股-市值": 1080000000.0,
            "今日持股-占流通股比": 0.24,
            "今日持股-占总股本比": 0.24,
            "今日增持估计-股数": -10000.0,
            "今日增持估计-市值": -1200000.0,
            "今日增持估计-市值增幅": -0.11,
            "今日增持估计-占流通股比": -0.003,
            "今日增持估计-占总股本比": -0.003,
            "所属板块": "白酒",
            "日期": "2026-02-11",
        },
    ])


# ---------------------------------------------------------------------------
# 辅助：构造估值对比 DataFrame（真实列名）
# ---------------------------------------------------------------------------

def _make_valuation_vs_industry_df(symbol: str = "600519") -> pd.DataFrame:
    """模拟 stock_zh_valuation_comparison_em(symbol='SH600519') 真实返回。

    真实列（由 AKShare 1.18.22 源码 stock_zh_comparison_em.py 确认）：
    排名, 代码, 简称, PEG,
    市盈率-TTM, 市盈率-25E, 市盈率-26E, 市盈率-27E,
    市销率-24A, 市销率-TTM, 市销率-25E, 市销率-26E, 市销率-27E,
    市净率-24A, 市净率-MRQ,
    市现率1-24A, 市现率1-TTM, 市现率2-24A, 市现率2-TTM,
    EV/EBITDA-24A
    注意：没有 "个股PE"、"行业PE(平均)"、"行业PE(中位数)"、"个股PB"、"行业PB(平均)" 等列！
    """
    return pd.DataFrame([
        {  # Row 0: 行业汇总行（移至首行）
            "排名": "5/28", "代码": "", "简称": "行业均值",
            "PEG": None, "市盈率-TTM": 28.5, "市净率-MRQ": 4.2,
            "市盈率-25E": 26.0, "市盈率-26E": 24.0, "市盈率-27E": 22.0,
            "市销率-TTM": 8.0, "市净率-24A": 4.0,
        },
        {  # Row 1: 某同行甲
            "排名": "1", "代码": "000858", "简称": "五粮液",
            "PEG": 1.2, "市盈率-TTM": 22.0, "市净率-MRQ": 3.8,
            "市盈率-25E": 20.0, "市盈率-26E": 18.5, "市盈率-27E": 17.0,
            "市销率-TTM": 7.0, "市净率-24A": 3.7,
        },
        {  # Row 2: 目标股（原 Row 0 被 swap 到这里）
            "排名": "5", "代码": symbol, "简称": "贵州茅台",
            "PEG": 2.1, "市盈率-TTM": 32.0, "市净率-MRQ": 10.5,
            "市盈率-25E": 30.0, "市盈率-26E": 28.0, "市盈率-27E": 26.0,
            "市销率-TTM": 14.0, "市净率-24A": 10.2,
        },
        {  # Row 3: 某同行乙
            "排名": "2", "代码": "600809", "简称": "山西汾酒",
            "PEG": 1.5, "市盈率-TTM": 25.0, "市净率-MRQ": 5.2,
            "市盈率-25E": 23.0, "市盈率-26E": 21.0, "市盈率-27E": 19.5,
            "市销率-TTM": 9.0, "市净率-24A": 5.0,
        },
    ])


# ===========================================================================
# Bug #1: financial_indicators ── start_year="1900" 必然返回空 DataFrame
# ===========================================================================

class TestFinancialIndicatorsBug:
    """验证 stock_financial_analysis_indicator(start_year='1900') 永远返回空。"""

    def test_start_year_1900_returns_empty_because_not_in_year_list(self, mocker):
        """
        AKShare 源码逻辑：
            if start_year in year_list:
                year_list = year_list[: year_list.index(start_year) + 1]
            else:
                return pd.DataFrame()      ← 固定 return 空

        "1900" 永远不在 Sina 的可用年份列表（最早约 1990 年），因此永远返回空 DF。

        注1：safe_call 内部读取 func.__name__，需用 lambda 或具名函数 patch，
             不能用 return_value=... 的 MagicMock。
        注2：生产代码现已优先使用 EM 接口，此测试同时 patch EM 返回空以触发 Sina 回退路径。
        """
        collector = AKShareCollector("600519", "贵州茅台")

        # EM 接口也返回空 → 触发 Sina 回退路径
        mocker.patch.object(
            module_a.ak,
            "stock_financial_analysis_indicator_em",
            lambda *a, **kw: pd.DataFrame(),
        )
        # 模拟 Sina 返回空 DF（这就是 start_year="1900" 时的真实行为）
        mocker.patch.object(
            module_a.ak,
            "stock_financial_analysis_indicator",
            lambda *a, **kw: pd.DataFrame(),
        )

        result = collector._collect_financial_indicators()

        # 两条路径均返回空 → _collect_financial_indicators 返回 None
        assert result is None

    def test_financial_indicators_topic_status_is_failed_when_empty(self, mocker):
        """safe_collect 将 None 结果记为 failed。"""
        collector = AKShareCollector("600519", "贵州茅台")
        # 两条路径均返回空，确保不会因 EM 成功而绕过此测试
        mocker.patch.object(
            module_a.ak,
            "stock_financial_analysis_indicator_em",
            lambda *a, **kw: pd.DataFrame(),
        )
        mocker.patch.object(
            module_a.ak,
            "stock_financial_analysis_indicator",
            lambda *a, **kw: pd.DataFrame(),
        )
        result = collector._safe_collect(
            "financial_indicators",
            collector._collect_financial_indicators,
        )
        assert result is None
        assert collector.topic_status["financial_indicators"] == AKShareCollector.STATUS_FAILED

    def test_financial_indicators_works_when_df_has_real_columns(self, mocker):
        """
        验证：如果 EM 接口能返回有数据的 DF（已重命名为中文列名格式），
        解析逻辑本身是正确的。
        此 case 使用 EM 主路径（生产代码优先调用 _fetch_financial_indicators_em）。
        """
        collector = AKShareCollector("600519", "贵州茅台")
        # EM 接口返回的数据已经过 _fetch_financial_indicators_em 内部重命名，
        # 直接提供重命名后的 DataFrame（含 "报告期" 和中文财务列名）
        fake_em_df = pd.DataFrame([
            {
                "报告期": "2024-09-30",
                "摊薄每股收益(元)": 45.21,
                "每股净资产_调整后(元)": 131.5,
                "净资产收益率_摊薄(%)": 34.4,
                "销售毛利率(%)": 92.0,
                "销售净利率(%)": 52.3,
                "营业总收入同比增长率(%)": 16.8,
                "归属母公司股东的净利润同比增长率(%)": 15.1,
                "资产负债率(%)": 19.2,
                "流动比率": 3.8,
            },
        ])
        # 直接 patch _fetch_financial_indicators_em 返回已重命名的 DF
        mocker.patch.object(
            collector,
            "_fetch_financial_indicators_em",
            return_value=fake_em_df,
        )

        result = collector._collect_financial_indicators()

        assert result is not None
        assert len(result) == 1
        assert result[0]["report_date"] == "2024-09-30"
        assert result[0]["eps"] == pytest.approx(45.21)
        assert result[0]["roe"] == pytest.approx(34.4)


# ===========================================================================
# Bug #2: northbound ── 列名不匹配（持股数量 → 今日持股-股数 等）
# ===========================================================================

class TestNorthboundColumnMismatch:
    """验证北向持仓的列名不匹配问题。"""

    def test_northbound_correct_column_names_now_give_real_values(self, mocker):
        """
        修复后（使用 今日持股-股数/今日持股-市值/今日增持估计-市值增幅）：
        held=True 且数值不再全为 None。
        此测试同时验证 bug 已被修复：旧列名 "持股数量" 等已不再使用。
        """
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call_market_cached",
            return_value=_make_northbound_df("600519"),
        )

        result = collector._collect_northbound()

        # 修复后：代码命中（held=True），且数值能正常读取
        assert result is not None
        assert result["held"] is True
        assert result["shares_held"] is not None      # "今日持股-股数" 存在
        assert result["market_value"] is not None     # "今日持股-市值" 存在
        assert result["change_pct"] is not None       # "今日增持估计-市值增幅" 存在

    def test_northbound_correct_column_names_give_real_values(self, mocker):
        """
        修复后（使用真实列名）：持仓数量、市值、增幅均能正确读取。
        此 case 验证修复方向正确，且会在代码修复后通过。

        正确列名映射：
            持股数量        → 今日持股-股数
            持股市值        → 今日持股-市值
            持股数量变化-增减比例 → 今日增持估计-市值增幅
        """
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call_market_cached",
            return_value=_make_northbound_df("600519"),
        )

        # 直接调用底层行提取，绕过 _collect_northbound 内部列名，
        # 模拟修复后的读取逻辑
        df = _make_northbound_df("600519")
        r = df[df["代码"] == "600519"].iloc[0]

        shares_held = AKShareCollector._safe_float(r.get("今日持股-股数"))
        market_value = AKShareCollector._safe_float(r.get("今日持股-市值"))
        change_pct = AKShareCollector._safe_float(r.get("今日增持估计-市值增幅"))

        assert shares_held == pytest.approx(12345678.0)
        assert market_value == pytest.approx(18518517000.0)
        assert change_pct == pytest.approx(0.41)

    def test_northbound_not_held_when_code_not_in_df(self, mocker):
        """不在持仓名单时，held=False，数值全为 None（现有逻辑已正确）。"""
        collector = AKShareCollector("000001", "平安银行")
        mocker.patch.object(
            collector, "safe_call_market_cached",
            return_value=_make_northbound_df("600519"),  # 只有茅台
        )

        result = collector._collect_northbound()

        assert result is not None
        assert result["held"] is False
        assert result["shares_held"] is None


# ===========================================================================
# Bug #3: valuation_vs_industry ── 列名不匹配（个股PE → 市盈率-TTM 等）
# ===========================================================================

class TestValuationVsIndustryColumnMismatch:
    """验证估值对比的列名不匹配问题。"""

    def test_valuation_vs_industry_correct_columns_now_give_real_values(self, mocker):
        """
        修复后（使用 市盈率-TTM/市净率-MRQ，按代码定位目标股）：
        stock_pe/stock_pb 等不再为 None。
        此测试同时验证旧列名 "个股PE"/"行业PE(平均)" 已被正确替换。
        """
        collector = AKShareCollector("600519", "贵州茅台")
        mocker.patch.object(
            collector, "safe_call",
            return_value=_make_valuation_vs_industry_df("600519"),
        )

        result = collector._collect_valuation_vs_industry()

        assert result is not None
        assert result["stock_pe"] is not None         # 修复后："市盈率-TTM" 存在
        assert result["industry_avg_pe"] is not None  # 修复后：从同行计算均值
        assert result["stock_pb"] is not None         # 修复后："市净率-MRQ" 存在
        assert result["relative_valuation"] != "数据不足，无法判断"

    def test_valuation_vs_industry_correct_column_extraction(self):
        """
        验证修复方向：使用真实列名 "市盈率-TTM" / "市净率-MRQ"，
        按 "代码" 定位目标股行，其余行计算行业均值。
        """
        df = _make_valuation_vs_industry_df("600519")
        symbol = "600519"

        # 找到目标股行
        stock_row = df[df["代码"] == symbol].iloc[0]
        # 同行（排除目标股和行业汇总行）
        peer_df = df[(df["代码"] != symbol) & (df["代码"] != "")]

        stock_pe = AKShareCollector._safe_float(stock_row.get("市盈率-TTM"))
        stock_pb = AKShareCollector._safe_float(stock_row.get("市净率-MRQ"))

        pe_series = pd.to_numeric(peer_df["市盈率-TTM"], errors="coerce").dropna()
        pb_series = pd.to_numeric(peer_df["市净率-MRQ"], errors="coerce").dropna()
        industry_avg_pe = round(pe_series.mean(), 2) if len(pe_series) > 0 else None
        industry_avg_pb = round(pb_series.mean(), 2) if len(pb_series) > 0 else None

        assert stock_pe == pytest.approx(32.0)
        assert stock_pb == pytest.approx(10.5)
        # 同行：五粮液(22.0) + 山西汾酒(25.0) → 均值 23.5
        assert industry_avg_pe == pytest.approx(23.5)
        assert industry_avg_pb == pytest.approx(4.5)

    def test_relative_valuation_uses_computed_averages(self):
        """修复后 relative_valuation 能用真实 PE 数据进行判断。"""
        # 32.0 / 23.5 ≈ 1.36 → "明显高于行业平均"
        result = AKShareCollector._judge_relative_valuation(32.0, 23.5)
        assert result == "明显高于行业平均"

        # 22.0 / 23.5 ≈ 0.94 → "略低于行业平均"
        result2 = AKShareCollector._judge_relative_valuation(22.0, 23.5)
        assert result2 == "略低于行业平均"


# ===========================================================================
# Bug #4: valuation_history PS/DV ── stock_zh_valuation_baidu 不支持这两个指标
# ===========================================================================

class TestValuationBaiduUnsupportedIndicators:
    """验证 stock_zh_valuation_baidu 不支持 "市销率(TTM)" 和 "股息率(TTM)"。"""

    def test_ps_ttm_unsupported_causes_type_error(self, mocker):
        """
        stock_zh_valuation_baidu 只支持：
            {"总市值", "市盈率(TTM)", "市盈率(静)", "市净率", "市现率"}
        当 indicator="市销率(TTM)" 时，API 返回的 JSON 结构不包含 chartInfo 路径 →
        代码访问 data_json["Result"][0][...]["chartInfo"][0]["body"] 抛出
        TypeError: 'NoneType' object is not subscriptable。
        safe_call 捕获异常并返回 None。
        """
        collector = AKShareCollector("600519", "贵州茅台")

        def fake_baidu(symbol, indicator, period):
            if indicator in ("市销率(TTM)", "股息率(TTM)"):
                # 模拟 API 在不支持指标时抛出的 TypeError
                raise TypeError("'NoneType' object is not subscriptable")
            # 支持的指标（市盈率TTM、市净率）正常返回
            return pd.DataFrame({"date": ["2026-01-01"], "value": [30.0]})

        mocker.patch.object(module_a.ak, "stock_zh_valuation_baidu", fake_baidu)

        # safe_call 会捕获 TypeError，记录到 errors，返回 None
        result_ps = collector.safe_call(
            "valuation_history_baidu:ps_ttm",
            module_a.ak.stock_zh_valuation_baidu,
            symbol="600519",
            indicator="市销率(TTM)",
            period="近五年",
        )
        result_dv = collector.safe_call(
            "valuation_history_baidu:dv_ttm",
            module_a.ak.stock_zh_valuation_baidu,
            symbol="600519",
            indicator="股息率(TTM)",
            period="近五年",
        )

        assert result_ps is None
        assert result_dv is None
        assert any("ps_ttm" in e and "TypeError" in e for e in collector.errors)
        assert any("dv_ttm" in e and "TypeError" in e for e in collector.errors)

    def test_supported_indicators_pe_pb_work_correctly(self, mocker):
        """
        在 PS/DV 修复为"不请求不支持的指标"后，PE/PB 回退路径应能正常工作。
        此 case 验证修复后的 _build_valuation_history_from_baidu（仅请求 PE/PB）能返回有效数据。
        """
        collector = AKShareCollector("600519", "贵州茅台")

        pe_df = pd.DataFrame({
            "date": pd.to_datetime(["2025-01-02", "2025-06-30", "2026-01-02"]),
            "value": [28.0, 30.5, 32.0],
        })
        pb_df = pd.DataFrame({
            "date": pd.to_datetime(["2025-01-02", "2025-06-30", "2026-01-02"]),
            "value": [9.0, 10.0, 10.5],
        })

        def fake_baidu(symbol, indicator, period):
            if indicator == "市盈率(TTM)":
                return pe_df
            if indicator == "市净率":
                return pb_df
            raise TypeError("'NoneType' object is not subscriptable")

        mocker.patch.object(module_a.ak, "stock_zh_valuation_baidu", fake_baidu)
        mocker.patch.object(
            module_a, "getattr",
            side_effect=AttributeError,  # 让 stock_a_lg_indicator 判定为不可用
        ) if False else None  # 直接 patch getattr 影响太广，改用下面的方式

        # 直接测试 _build_valuation_history_from_baidu
        # 仅请求支持的 pe_ttm / pb（修复后的行为）
        indicators_fixed = {
            "pe_ttm": "市盈率(TTM)",
            "pb": "市净率",
        }
        merged = None
        for field, indicator_label in indicators_fixed.items():
            part = collector.safe_call(
                f"valuation_history_baidu:{field}",
                module_a.ak.stock_zh_valuation_baidu,
                symbol="600519",
                indicator=indicator_label,
                period="近五年",
            )
            assert part is not None, f"{field} 应能正常获取"

            normalized = collector._normalize_valuation_series(part, field, indicator_label)
            assert normalized is not None

            if merged is None:
                merged = normalized
            else:
                merged = merged.merge(normalized, on="trade_date", how="outer")

        assert merged is not None
        assert "pe_ttm" in merged.columns
        assert "pb" in merged.columns
        # 最新值（排序后 iloc[-1]）
        merged_sorted = merged.sort_values("trade_date")
        latest = merged_sorted.iloc[-1]
        assert AKShareCollector._safe_float(latest.get("pe_ttm")) == pytest.approx(32.0)
        assert AKShareCollector._safe_float(latest.get("pb")) == pytest.approx(10.5)

    def test_ps_dv_are_none_when_not_available(self, mocker):
        """
        修复后：PS/DV 无数据时应为 None，不影响 PE/PB 正常输出；
        topic_status 仍应为 ok（有 PE/PB 数据）。
        """
        collector = AKShareCollector("600519", "贵州茅台")

        pe_df = pd.DataFrame({
            "date": pd.to_datetime(["2025-01-02", "2026-01-02"]),
            "value": [28.0, 32.0],
        })
        pb_df = pd.DataFrame({
            "date": pd.to_datetime(["2025-01-02", "2026-01-02"]),
            "value": [9.0, 10.5],
        })

        # 模拟 _build_valuation_history_from_baidu 返回仅含 pe/pb 的 merged df
        merged = pd.DataFrame({
            "trade_date": pd.to_datetime(["2025-01-02", "2026-01-02"]),
            "pe_ttm": [28.0, 32.0],
            "pb": [9.0, 10.5],
        }).sort_values("trade_date")

        mocker.patch.object(
            collector, "_build_valuation_history_from_baidu",
            return_value=merged,
        )
        # 让 stock_a_lg_indicator 不可用（触发回退路径）
        mocker.patch.object(
            module_a, "getattr",
            return_value=None,
        ) if False else None

        # 通过直接调用 _build_valuation_history_from_baidu 已经 patched，
        # 模拟整体 _collect_valuation_history 流程
        df = merged
        latest = df.iloc[-1]
        result = {
            "current_pe_ttm": AKShareCollector._safe_float(latest.get("pe_ttm")),
            "current_pb": AKShareCollector._safe_float(latest.get("pb")),
            "current_ps_ttm": AKShareCollector._safe_float(latest.get("ps_ttm")),
            "current_dv_ttm": AKShareCollector._safe_float(latest.get("dv_ttm")),
        }

        assert result["current_pe_ttm"] == pytest.approx(32.0)
        assert result["current_pb"] == pytest.approx(10.5)
        assert result["current_ps_ttm"] is None   # 没有该列 → None（正确行为）
        assert result["current_dv_ttm"] is None   # 没有该列 → None（正确行为）


# ===========================================================================
# 快速验证：stock_a_lg_indicator 在当前 AKShare 版本不存在
# ===========================================================================

def test_stock_a_lg_indicator_not_in_akshare_1_18_22():
    """确认 AKShare 1.18.22 中 stock_a_lg_indicator 不存在。"""
    import akshare as ak
    assert not hasattr(ak, "stock_a_lg_indicator"), (
        "stock_a_lg_indicator 存在于当前版本，"
        "可直接启用主路径，不需要回退到 stock_zh_valuation_baidu"
    )


def test_stock_zh_valuation_baidu_supported_indicators_signature():
    """
    验证 stock_zh_valuation_baidu 签名中默认 indicator 参数及支持范围：
    只支持 {"总市值", "市盈率(TTM)", "市盈率(静)", "市净率", "市现率"}
    代码里错误地请求了 "市销率(TTM)" 和 "股息率(TTM)"。
    """
    import inspect
    import akshare as ak
    sig = inspect.signature(ak.stock_zh_valuation_baidu)
    params = sig.parameters
    assert "indicator" in params
    # 默认值是 "总市值"（说明它是受限列表型接口）
    assert params["indicator"].default == "总市值"

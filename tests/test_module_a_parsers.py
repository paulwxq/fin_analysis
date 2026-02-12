"""Unit tests for module A parser and helper logic."""

from datetime import date

import pandas as pd

import stock_analyzer.module_a_akshare as module_a_akshare
from stock_analyzer.module_a_akshare import AKShareCollector


def _patch_sector_api_symbols(mocker) -> None:
    """Patch sector API symbols to avoid akshare version differences in unit tests."""
    mocker.patch.object(
        module_a_akshare.ak,
        "stock_board_industry_fund_flow_rank_em",
        lambda *args, **kwargs: None,
        create=True,
    )
    mocker.patch.object(
        module_a_akshare.ak,
        "stock_board_concept_fund_flow_rank_em",
        lambda *args, **kwargs: None,
        create=True,
    )


def test_collect_company_info_returns_none_when_safe_call_none(mocker) -> None:
    collector = AKShareCollector("000001", "平安银行")
    mocker.patch.object(collector, "safe_call", return_value=None)
    assert collector._collect_company_info() is None


def test_collect_company_info_calls_parse_when_df_available(mocker) -> None:
    collector = AKShareCollector("000001", "平安银行")
    fake_df = pd.DataFrame({"item": ["行业"], "value": ["银行"]})
    mocker.patch.object(collector, "safe_call", return_value=fake_df)
    parse_mock = mocker.patch.object(
        collector, "_parse_company_info", return_value={"industry": "银行"}
    )

    result = collector._collect_company_info()
    parse_mock.assert_called_once_with(fake_df)
    assert result == {"industry": "银行"}


def test_safe_call_retries_three_times_on_timeout_then_succeeds(mocker) -> None:
    collector = AKShareCollector("000001", "平安银行")
    mocker.patch.object(module_a_akshare, "AKSHARE_TIMEOUT_RETRIES", 3)
    mocker.patch.object(collector, "_wait_interval", return_value=None)
    execute_mock = mocker.patch.object(
        collector,
        "_execute_with_timeout",
        side_effect=[
            module_a_akshare.FutureTimeoutError(),
            module_a_akshare.FutureTimeoutError(),
            module_a_akshare.FutureTimeoutError(),
            pd.DataFrame([{"x": 1}]),
        ],
    )

    result = collector.safe_call("topic_x", lambda: None)
    assert result is not None
    assert len(result) == 1
    assert execute_mock.call_count == 4
    assert collector.errors == []


def test_safe_call_retry_exhausted_records_error(mocker) -> None:
    collector = AKShareCollector("000001", "平安银行")
    mocker.patch.object(module_a_akshare, "AKSHARE_TIMEOUT_RETRIES", 3)
    mocker.patch.object(collector, "_wait_interval", return_value=None)
    execute_mock = mocker.patch.object(
        collector,
        "_execute_with_timeout",
        side_effect=module_a_akshare.FutureTimeoutError(),
    )

    result = collector.safe_call("topic_x", lambda: None)
    assert result is None
    assert execute_mock.call_count == 4
    assert any("topic_x: 调用超时" in msg for msg in collector.errors)


def test_safe_call_retries_on_requests_style_timeout_exception(mocker) -> None:
    class ReadTimeout(Exception):
        pass

    collector = AKShareCollector("000001", "平安银行")
    mocker.patch.object(module_a_akshare, "AKSHARE_TIMEOUT_RETRIES", 3)
    mocker.patch.object(collector, "_wait_interval", return_value=None)
    execute_mock = mocker.patch.object(
        collector,
        "_execute_with_timeout",
        side_effect=[
            ReadTimeout("read timed out"),
            ReadTimeout("read timed out"),
            ReadTimeout("read timed out"),
            pd.DataFrame([{"x": 1}]),
        ],
    )

    result = collector.safe_call("topic_x", lambda: None)
    assert result is not None
    assert len(result) == 1
    assert execute_mock.call_count == 4


def test_safe_call_retries_on_connection_error_then_succeeds(mocker) -> None:
    collector = AKShareCollector("000001", "平安银行")
    mocker.patch.object(module_a_akshare, "AKSHARE_TIMEOUT_RETRIES", 3)
    mocker.patch.object(collector, "_wait_interval", return_value=None)
    execute_mock = mocker.patch.object(
        collector,
        "_execute_with_timeout",
        side_effect=[
            ConnectionError(
                "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
            ),
            pd.DataFrame([{"x": 1}]),
        ],
    )

    result = collector.safe_call("topic_conn", lambda: None)
    assert result is not None
    assert len(result) == 1
    assert execute_mock.call_count == 2
    assert collector.errors == []


def test_safe_call_connection_error_retry_exhausted_records_error(mocker) -> None:
    collector = AKShareCollector("000001", "平安银行")
    mocker.patch.object(module_a_akshare, "AKSHARE_TIMEOUT_RETRIES", 2)
    mocker.patch.object(collector, "_wait_interval", return_value=None)
    execute_mock = mocker.patch.object(
        collector,
        "_execute_with_timeout",
        side_effect=ConnectionError(
            "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
        ),
    )

    result = collector.safe_call("topic_conn", lambda: None)
    assert result is None
    assert execute_mock.call_count == 3
    assert any("topic_conn: ConnectionError" in msg for msg in collector.errors)


def test_safe_float_normal() -> None:
    assert AKShareCollector._safe_float(3.14) == 3.14


def test_safe_float_none() -> None:
    assert AKShareCollector._safe_float(None) is None


def test_safe_float_nan() -> None:
    assert AKShareCollector._safe_float(float("nan")) is None


def test_safe_float_nan_string() -> None:
    assert AKShareCollector._safe_float("nan") is None


def test_safe_float_dash_string() -> None:
    assert AKShareCollector._safe_float("-") is None


def test_safe_float_none_string() -> None:
    assert AKShareCollector._safe_float("None") is None


def test_safe_str_nan_like_values() -> None:
    assert AKShareCollector._safe_str("nan") == ""
    assert AKShareCollector._safe_str("NaT") == ""
    assert AKShareCollector._safe_str("None") == ""
    assert AKShareCollector._safe_str("  ") == ""


def test_safe_optional_str_nan_like_values() -> None:
    assert AKShareCollector._safe_optional_str("nan") is None
    assert AKShareCollector._safe_optional_str(float("nan")) is None
    assert AKShareCollector._safe_optional_str("文本") == "文本"


def test_safe_int_normal() -> None:
    assert AKShareCollector._safe_int("3456789") == 3456789


def test_safe_int_float_string() -> None:
    assert AKShareCollector._safe_int("3456789.0") == 3456789


def test_safe_int_none() -> None:
    assert AKShareCollector._safe_int(None) is None


def test_safe_int_nan() -> None:
    assert AKShareCollector._safe_int(float("nan")) is None


def test_parse_number_yi() -> None:
    assert AKShareCollector._parse_number("2156.80亿") == 2156.80


def test_parse_number_wan_to_yi() -> None:
    assert AKShareCollector._parse_number("19406万") == 1.9406


def test_parse_number_no_unit() -> None:
    assert AKShareCollector._parse_number("3.5") == 3.5


def test_parse_number_target_wan() -> None:
    assert AKShareCollector._parse_number("2.5亿", target_unit="万") == 25000.0


def test_parse_number_dash() -> None:
    assert AKShareCollector._parse_number("-") is None


def test_calc_percentile() -> None:
    series = pd.Series(range(100))
    assert AKShareCollector._calc_percentile(series, 50) == 50.0


def test_calc_percentile_with_numeric_strings() -> None:
    series = pd.Series([str(i) for i in range(1, 21)] + [None, "bad"])
    assert AKShareCollector._calc_percentile(series, "10") == 45.0


def test_collect_sector_flow_prefers_exact_match_over_contains(mocker) -> None:
    _patch_sector_api_symbols(mocker)
    collector = AKShareCollector("600519", "贵州茅台")
    df_industry = pd.DataFrame(
        [
            {"名称": "白酒Ⅱ", "排名": 1, "今日主力净流入-净额": 999.0},
            {"名称": "白酒", "排名": 2, "今日主力净流入-净额": 123.0},
        ]
    )
    df_concept = pd.DataFrame(
        [
            {"名称": "概念A", "排名": 2, "今日主力净流入-净额": 20.0},
            {"名称": "概念B", "排名": 1, "今日主力净流入-净额": 10.0},
        ]
    )

    def fake_market_call(cache_key, topic, func, *args, **kwargs):
        if topic == "sector_flow_industry":
            return df_industry
        if topic == "sector_flow_concept":
            return df_concept
        return None

    mocker.patch.object(collector, "safe_call_market_cached", side_effect=fake_market_call)

    result = collector._collect_sector_flow("白酒")
    assert result is not None
    assert result["industry_name"] == "白酒"
    assert result["industry_rank"] == 2
    assert result["industry_net_inflow_today"] == 123.0


def test_collect_sector_flow_hot_concepts_top5_sorted_before_head(mocker) -> None:
    _patch_sector_api_symbols(mocker)
    collector = AKShareCollector("600519", "贵州茅台")
    df_concept = pd.DataFrame(
        [
            {"名称": "概念5", "排名": 5, "今日主力净流入-净额": 50.0},
            {"名称": "概念2", "排名": 2, "今日主力净流入-净额": 20.0},
            {"名称": "概念1", "排名": 1, "今日主力净流入-净额": 10.0},
            {"名称": "概念4", "排名": 4, "今日主力净流入-净额": 40.0},
            {"名称": "概念3", "排名": 3, "今日主力净流入-净额": 30.0},
            {"名称": "概念6", "排名": 6, "今日主力净流入-净额": 60.0},
        ]
    )

    def fake_market_call(cache_key, topic, func, *args, **kwargs):
        if topic == "sector_flow_industry":
            return None
        if topic == "sector_flow_concept":
            return df_concept
        return None

    mocker.patch.object(collector, "safe_call_market_cached", side_effect=fake_market_call)

    result = collector._collect_sector_flow("")
    assert result is not None
    top5_names = [x["name"] for x in result["hot_concepts_top5"]]
    assert top5_names == ["概念1", "概念2", "概念3", "概念4", "概念5"]


def test_collect_sector_flow_logs_when_industry_not_matched(mocker) -> None:
    _patch_sector_api_symbols(mocker)
    collector = AKShareCollector("600519", "贵州茅台")
    df_industry = pd.DataFrame([
        {"名称": "白酒Ⅱ", "排名": 1, "今日主力净流入-净额": 999.0},
    ])
    df_concept = pd.DataFrame([
        {"名称": "概念A", "排名": 1, "今日主力净流入-净额": 10.0},
    ])

    def fake_market_call(cache_key, topic, func, *args, **kwargs):
        if topic == "sector_flow_industry":
            return df_industry
        if topic == "sector_flow_concept":
            return df_concept
        return None

    mocker.patch.object(collector, "safe_call_market_cached", side_effect=fake_market_call)

    result = collector._collect_sector_flow("有色金属")
    assert result is not None
    assert result["industry_name"] == "有色金属"
    assert result["industry_rank"] is None
    assert result["industry_net_inflow_today"] is None
    assert any(
        "sector_flow_industry: 行业 '有色金属' 在板块数据中精确和模糊匹配均未命中" in e
        for e in collector.errors
    )


def test_safe_call_sector_fund_flow_fallback_to_stock_sector_api(mocker) -> None:
    collector = AKShareCollector("600519", "贵州茅台")
    mocker.patch.object(
        module_a_akshare.ak,
        "stock_board_industry_fund_flow_rank_em",
        None,
        create=True,
    )
    fallback_func = lambda *args, **kwargs: None
    mocker.patch.object(
        module_a_akshare.ak, "stock_sector_fund_flow_rank", fallback_func, create=True
    )

    call_mock = mocker.patch.object(
        collector,
        "safe_call_market_cached",
        return_value=pd.DataFrame([{"名称": "白酒", "序号": 1, "今日主力净流入-净额": 1.0}]),
    )

    collector._safe_call_sector_fund_flow(
        topic="sector_flow_industry",
        legacy_func_name="stock_board_industry_fund_flow_rank_em",
        legacy_cache_key="legacy_key",
        sector_type="行业资金流",
        fallback_cache_key="fallback_key",
    )
    call_mock.assert_called_once_with(
        "fallback_key",
        "sector_flow_industry",
        fallback_func,
        indicator="今日",
        sector_type="行业资金流",
    )


def test_collect_sector_flow_returns_none_when_both_sources_fail(mocker) -> None:
    _patch_sector_api_symbols(mocker)
    collector = AKShareCollector("600519", "贵州茅台")
    mocker.patch.object(collector, "safe_call_market_cached", return_value=None)
    assert collector._collect_sector_flow("白酒") is None


def test_collect_dividend_history_with_detail_schema(mocker) -> None:
    collector = AKShareCollector("600519", "贵州茅台")
    mocker.patch.object(module_a_akshare.ak, "stock_history_dividend_detail", lambda **_: None, create=True)
    mocker.patch.object(
        collector,
        "safe_call",
        return_value=pd.DataFrame(
            [
                {"公告日期": "2024-06-01", "派息": "30.876", "除权除息日": "2024-06-20"},
                {"公告日期": "2023-06-01", "派息": "25.911"},
            ]
        ),
    )

    result = collector._collect_dividend_history()
    assert result is not None
    assert result[0]["year"] == "2024"
    assert result[0]["dividend_per_share"] == 30.876
    assert result[0]["ex_date"] == "2024-06-20"
    assert result[1]["year"] == "2023"
    assert result[1]["ex_date"] == "2023-06-01"


def test_collect_earnings_forecast_nan_fields_become_none(mocker) -> None:
    mocker.patch.object(
        module_a_akshare.ak,
        "stock_yjyg_em",
        lambda *args, **kwargs: None,
        create=True,
    )
    collector = AKShareCollector("600519", "贵州茅台")
    mocker.patch.object(collector, "_get_recent_quarter_ends", return_value=["20251231"])
    mocker.patch.object(
        collector,
        "safe_call_market_cached",
        return_value=pd.DataFrame(
            [
                {
                    "股票代码": "600519",
                    "业绩变动类型": float("nan"),
                    "预测内容": "nan",
                }
            ]
        ),
    )

    result = collector._collect_earnings_forecast()
    assert result is not None
    assert result["available"] is True
    assert result["forecast_type"] is None
    assert result["forecast_range"] is None


def test_judge_relative_valuation_negative_pe() -> None:
    assert AKShareCollector._judge_relative_valuation(-10.0, 30.0) == "数据不足，无法判断"
    assert AKShareCollector._judge_relative_valuation(20.0, -5.0) == "数据不足，无法判断"


def test_judge_pledge_risk() -> None:
    assert AKShareCollector._judge_pledge_risk(5.0) == "低"
    assert AKShareCollector._judge_pledge_risk(25.0) == "中"
    assert AKShareCollector._judge_pledge_risk(45.0) == "高"
    assert AKShareCollector._judge_pledge_risk(60.0) == "极高"


def test_get_recent_quarter_ends_early_year() -> None:
    result = AKShareCollector._get_recent_quarter_ends(
        lookback=4, today=date(2026, 2, 7)
    )
    assert result == ["20251231", "20250930", "20250630", "20250331"]


def test_get_recent_quarter_ends_mid_year() -> None:
    result = AKShareCollector._get_recent_quarter_ends(
        lookback=4, today=date(2026, 8, 15)
    )
    assert result == ["20260630", "20260331", "20251231", "20250930"]


def test_get_recent_quarter_ends_quarter_boundary() -> None:
    result = AKShareCollector._get_recent_quarter_ends(
        lookback=4, today=date(2026, 3, 31)
    )
    assert result == ["20260331", "20251231", "20250930", "20250630"]

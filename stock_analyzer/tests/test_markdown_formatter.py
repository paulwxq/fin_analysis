"""Unit tests for markdown_formatter module."""

import pytest

from stock_analyzer.markdown_formatter import (
    _fmt_amount_wan,
    _fmt_int,
    _fmt_pct,
    _fmt_ratio,
    _fmt_val,
    _to_table,
    format_akshare_markdown,
    format_technical_markdown,
    format_web_research_markdown,
)
from stock_analyzer.models import (
    AnalystOpinions,
    AnalystReport,
    CompetitiveAdvantage,
    IndustryOutlook,
    NewsItem,
    NewsSummary,
    RiskEvents,
    SearchConfig,
    SearchMeta,
    WebResearchResult,
)
from stock_analyzer.module_a_models import (
    AKShareData,
    AKShareMeta,
    BusinessComposition,
    CompanyInfo,
    ConsensusForecast,
    DividendRecord,
    EarningsForecast,
    FinancialIndicator,
    FundFlow,
    FundFlowDay,
    FundFlowSummary,
    InstitutionalHolding,
    Northbound,
    PledgeRatio,
    RealtimeQuote,
    SectorFlow,
    ShareholderCount,
    ValuationHistory,
    ValuationVsIndustry,
)
from stock_analyzer.module_c_models import (
    KeyLevels,
    MomentumAnalysis,
    TechnicalAnalysisResult,
    TechnicalMeta,
    TrendAnalysis,
    VolatilityAnalysis,
    VolumeAnalysis,
)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def minimal_akshare_meta():
    return AKShareMeta(
        symbol="600519",
        name="贵州茅台",
        query_time="2026-02-13T10:00:00",
        successful_topics=15,
        topic_status={},
    )


@pytest.fixture
def full_akshare_data(minimal_akshare_meta):
    return AKShareData(
        meta=minimal_akshare_meta,
        company_info=CompanyInfo(
            industry="白酒",
            listing_date="20010827",
            total_market_cap=20000.0,
            circulating_market_cap=20000.0,
            total_shares=12.56,
            circulating_shares=12.56,
        ),
        realtime_quote=RealtimeQuote(
            price=1590.0,
            change_pct=1.23,
            volume=50000.0,
            turnover=7950000.0,
            pe_ttm=30.5,
            pb=10.2,
            turnover_rate=0.5,
            volume_ratio=1.1,
            change_60d_pct=5.0,
            change_ytd_pct=8.0,
        ),
        financial_indicators=[
            FinancialIndicator(
                report_date="2025-09-30",
                eps=30.5,
                net_asset_per_share=150.0,
                roe=25.0,
                gross_margin=91.5,
                net_margin=50.0,
                revenue_growth=10.5,
                profit_growth=12.0,
                debt_ratio=20.0,
                current_ratio=3.5,
            ),
            FinancialIndicator(
                report_date="2025-06-30",
                eps=20.0,
                net_asset_per_share=145.0,
                roe=18.0,
                gross_margin=90.0,
                net_margin=48.0,
                revenue_growth=8.0,
                profit_growth=10.0,
                debt_ratio=21.0,
                current_ratio=3.2,
            ),
        ],
        valuation_history=ValuationHistory(
            current_pe_ttm=30.5,
            current_pb=10.2,
            pe_percentile=60.0,
            pb_percentile=75.0,
            current_ps_ttm=15.0,
            current_dv_ttm=1.5,
            history_summary="PE中等分位",
        ),
        valuation_vs_industry=ValuationVsIndustry(
            stock_pe=30.5,
            industry_avg_pe=25.0,
            industry_median_pe=22.0,
            stock_pb=10.2,
            industry_avg_pb=8.0,
            relative_valuation="略高于行业平均",
        ),
        fund_flow=FundFlow(
            recent_days=[
                FundFlowDay(
                    date="2026-02-13",
                    main_net_inflow=5000000.0,
                    main_net_inflow_pct=2.5,
                ),
            ],
            summary=FundFlowSummary(
                main_net_inflow_5d_total=10000000.0,
                main_net_inflow_10d_total=20000000.0,
                trend="净流入",
            ),
        ),
        sector_flow=SectorFlow(
            industry_name="白酒",
            industry_rank=5,
            industry_net_inflow_today=100000000.0,
        ),
        northbound=Northbound(
            held=True,
            shares_held=10000.0,
            market_value=150000.0,
            change_pct=0.5,
            note="测试备注",
        ),
        shareholder_count=[
            ShareholderCount(date="2025-09-30", count=80000, change_pct=-5.0),
        ],
        dividend_history=[
            DividendRecord(year="2024", dividend_per_share=20.0, ex_date="2024-06-20"),
        ],
        earnings_forecast=EarningsForecast(
            available=True,
            latest_period="2025-06-30",
            forecast_type="略增",
            forecast_range="净利润增长10%-20%",
        ),
        pledge_ratio=PledgeRatio(ratio_pct=0.0, risk_level="低"),
        consensus_forecast=[
            ConsensusForecast(year="2025", inst_count=10, net_profit_avg=80.0, industry_avg=50.0),
        ],
        institutional_holdings=[
            InstitutionalHolding(type="基金", name="某基金", ratio=1.5),
        ],
        business_composition=[
            BusinessComposition(type="按产品分类", item="白酒", revenue_ratio=0.95, gross_margin=0.92),
            BusinessComposition(type="按地区分类", item="境内", revenue_ratio=0.85, gross_margin=0.91),
            BusinessComposition(type="", item="白酒行业", revenue_ratio=0.99, gross_margin=0.90),
        ],
    )


@pytest.fixture
def minimal_web_research():
    return WebResearchResult(
        meta=SearchMeta(
            symbol="600519",
            name="贵州茅台",
            search_time="2026-02-13T10:00:00",
            search_config=SearchConfig(
                topics_count=5, breadth=3, depth=2, successful_topics=5
            ),
            total_learnings=50,
            total_sources_consulted=30,
        ),
        news_summary=NewsSummary(
            positive=[
                NewsItem(
                    title="营收创新高",
                    summary="贵州茅台2024年营收创历史新高",
                    source="公司公告",
                    date="2025-04-30",
                    importance="高",
                ),
            ],
            negative=[
                NewsItem(
                    title="提价不及预期",
                    summary="部分产品提价幅度低于市场预期",
                    source="券商研报",
                    date="2025-03-15",
                    importance="中",
                ),
            ],
            neutral=[],
        ),
        competitive_advantage=CompetitiveAdvantage(
            description="品牌壁垒极强",
            moat_type="品牌护城河",
            market_position="白酒行业龙头",
        ),
        industry_outlook=IndustryOutlook(
            industry="白酒",
            outlook="行业整体稳健",
            key_drivers=["消费升级", "品牌集中"],
            key_risks=["政策限制", "消费降级"],
        ),
        risk_events=RiskEvents(
            regulatory="无重大风险",
            litigation="无",
            management="稳定",
        ),
        analyst_opinions=AnalystOpinions(
            buy_count=15,
            hold_count=3,
            sell_count=0,
            average_target_price=1800.0,
            recent_reports=[
                AnalystReport(
                    broker="中信证券",
                    rating="买入",
                    target_price=1850.0,
                    date="2025-03-01",
                ),
            ],
        ),
        search_confidence="高",
    )


@pytest.fixture
def minimal_technical():
    return TechnicalAnalysisResult(
        meta=TechnicalMeta(
            symbol="600519",
            name="贵州茅台",
            analysis_time="2026-02-13T10:00:00",
            data_start="2001-09-30",
            data_end="2026-02-13",
            total_months=293,
        ),
        score=8.0,
        signal="看多",
        confidence=0.85,
        trend_analysis=TrendAnalysis(
            ma_alignment="多头排列",
            price_vs_ma20="上方15%",
            trend_6m="上涨20%",
            trend_12m="上涨35%",
            trend_judgment="中长期上升趋势",
        ),
        momentum=MomentumAnalysis(
            macd_status="零轴上方",
            rsi_value=65.0,
            rsi_status="中性偏强",
            kdj_status="金叉",
        ),
        volatility=VolatilityAnalysis(
            boll_position="中轨上方",
            boll_width="收敛",
        ),
        volume_analysis=VolumeAnalysis(
            recent_vs_avg="略高于均值",
            volume_price_relation="量价配合",
        ),
        key_levels=KeyLevels(
            support_1=1500.0,
            support_2=1400.0,
            resistance_1=1700.0,
            resistance_2=1800.0,
        ),
        summary="技术面积极向好",
    )


# ── Utility function tests ───────────────────────────────────


class TestFmtPct:
    def test_normal(self):
        assert _fmt_pct(14.377) == "14.38%"

    def test_negative(self):
        assert _fmt_pct(-5.123) == "-5.12%"

    def test_zero(self):
        assert _fmt_pct(0.0) == "0.00%"

    def test_none(self):
        assert _fmt_pct(None) == "—"


class TestFmtRatio:
    def test_normal(self):
        assert _fmt_ratio(0.75388) == "75.39%"

    def test_small(self):
        assert _fmt_ratio(0.003801) == "0.38%"

    def test_none(self):
        assert _fmt_ratio(None) == "—"

    def test_one(self):
        assert _fmt_ratio(1.0) == "100.00%"


class TestFmtVal:
    def test_float(self):
        assert _fmt_val(6.103824) == "6.10"

    def test_none(self):
        assert _fmt_val(None) == "—"

    def test_string(self):
        assert _fmt_val("text") == "text"

    def test_custom_decimals(self):
        assert _fmt_val(1.5678, 3) == "1.568"


class TestFmtInt:
    def test_normal(self):
        assert _fmt_int(78886) == "78,886"

    def test_none(self):
        assert _fmt_int(None) == "—"


class TestFmtAmountWan:
    def test_normal(self):
        assert _fmt_amount_wan(3714368.0) == "371.44"

    def test_none(self):
        assert _fmt_amount_wan(None) == "—"

    def test_negative(self):
        assert _fmt_amount_wan(-81708722.0) == "-8170.87"


class TestToTable:
    def test_normal(self):
        result = _to_table(["A", "B"], [["1", "2"], ["3", "4"]])
        lines = result.split("\n")
        assert len(lines) == 4
        assert "| A | B |" in lines[0]
        assert "| --- | --- |" in lines[1]
        assert "| 1 | 2 |" in lines[2]

    def test_empty_rows(self):
        assert _to_table(["A"], []) == ""


# ── Module A formatter tests ─────────────────────────────────


class TestFormatAkshareMarkdown:
    def test_full_data_contains_sections(self, full_akshare_data):
        result = format_akshare_markdown(full_akshare_data)
        assert "### 公司概况" in result
        assert "### 实时行情" in result
        assert "### 财务指标" in result
        assert "### 估值历史" in result
        assert "### 估值-行业对比" in result
        assert "### 个股资金流向" in result
        assert "### 板块资金流向" in result
        assert "### 北向资金" in result
        assert "### 股东户数变动" in result
        assert "### 分红历史" in result
        assert "### 业绩预告" in result
        assert "### 股权质押" in result
        assert "### 一致预期" in result
        assert "### 机构持仓" in result
        assert "### 主营结构" in result

    def test_company_info_values(self, full_akshare_data):
        result = format_akshare_markdown(full_akshare_data)
        assert "白酒" in result
        assert "20010827" in result
        assert "20000.00" in result

    def test_financial_indicators_table(self, full_akshare_data):
        result = format_akshare_markdown(full_akshare_data)
        assert "2025-09-30" in result
        assert "2025-06-30" in result
        assert "25.00%" in result  # ROE
        assert "91.50%" in result  # gross_margin

    def test_null_realtime_quote(self, minimal_akshare_meta):
        data = AKShareData(meta=minimal_akshare_meta, realtime_quote=None)
        result = format_akshare_markdown(data)
        assert "（数据缺失）" in result

    def test_earnings_forecast_unavailable(self, minimal_akshare_meta):
        data = AKShareData(
            meta=minimal_akshare_meta,
            earnings_forecast=EarningsForecast(available=False),
        )
        result = format_akshare_markdown(data)
        assert "暂无业绩预告数据" in result

    def test_earnings_forecast_available(self, full_akshare_data):
        result = format_akshare_markdown(full_akshare_data)
        assert "略增" in result
        assert "净利润增长10%-20%" in result

    def test_northbound_not_held(self, minimal_akshare_meta):
        data = AKShareData(
            meta=minimal_akshare_meta,
            northbound=Northbound(held=False),
        )
        result = format_akshare_markdown(data)
        assert "是否持有：否" in result

    def test_business_composition_grouped(self, full_akshare_data):
        result = format_akshare_markdown(full_akshare_data)
        assert "按产品分类" in result
        assert "按地区分类" in result
        assert "行业汇总" in result
        assert "95.00%" in result  # revenue_ratio 0.95 → 95.00%
        assert "92.00%" in result  # gross_margin 0.92 → 92.00%

    def test_empty_institutional_holdings(self, minimal_akshare_meta):
        data = AKShareData(
            meta=minimal_akshare_meta,
            institutional_holdings=[],
        )
        result = format_akshare_markdown(data)
        assert "无机构持仓数据" in result

    def test_all_none_fields(self, minimal_akshare_meta):
        """All optional fields None should not crash."""
        data = AKShareData(meta=minimal_akshare_meta)
        result = format_akshare_markdown(data)
        assert isinstance(result, str)
        assert "数据缺失" in result


# ── Module B formatter tests ─────────────────────────────────


class TestFormatWebResearchMarkdown:
    def test_contains_sections(self, minimal_web_research):
        result = format_web_research_markdown(minimal_web_research)
        assert "### 舆情汇总" in result
        assert "### 核心竞争力" in result
        assert "### 行业展望" in result
        assert "### 风险事件" in result
        assert "### 分析师观点" in result
        assert "搜索置信度：高" in result

    def test_news_markers(self, minimal_web_research):
        result = format_web_research_markdown(minimal_web_research)
        assert "[+]" in result
        assert "[-]" in result
        assert "正面新闻" in result
        assert "负面新闻" in result

    def test_news_content(self, minimal_web_research):
        result = format_web_research_markdown(minimal_web_research)
        assert "营收创新高" in result
        assert "提价不及预期" in result

    def test_analyst_table(self, minimal_web_research):
        result = format_web_research_markdown(minimal_web_research)
        assert "中信证券" in result
        assert "1850.00" in result

    def test_competitive_advantage(self, minimal_web_research):
        result = format_web_research_markdown(minimal_web_research)
        assert "品牌护城河" in result
        assert "白酒行业龙头" in result

    def test_industry_drivers_and_risks(self, minimal_web_research):
        result = format_web_research_markdown(minimal_web_research)
        assert "消费升级" in result
        assert "政策限制" in result


# ── Module C formatter tests ─────────────────────────────────


class TestFormatTechnicalMarkdown:
    def test_contains_sections(self, minimal_technical):
        result = format_technical_markdown(minimal_technical)
        assert "### 技术面总览" in result
        assert "### 趋势分析" in result
        assert "### 动量分析" in result
        assert "### 波动性分析" in result
        assert "### 量价分析" in result
        assert "### 关键价位" in result
        assert "### 技术总结" in result

    def test_overview_panel(self, minimal_technical):
        result = format_technical_markdown(minimal_technical)
        assert "8.00/10" in result
        assert "看多" in result
        assert "0.85" in result

    def test_key_levels_bold(self, minimal_technical):
        result = format_technical_markdown(minimal_technical)
        assert "**1500.00**" in result
        assert "**1700.00**" in result

    def test_rsi_value(self, minimal_technical):
        result = format_technical_markdown(minimal_technical)
        assert "65.00" in result

    def test_trend_judgment(self, minimal_technical):
        result = format_technical_markdown(minimal_technical)
        assert "中长期上升趋势" in result

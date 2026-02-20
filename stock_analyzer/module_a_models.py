"""Pydantic models for module A (AKShare data collection)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AKShareMeta(BaseModel):
    """Collection metadata."""

    symbol: str = Field(description="股票代码（纯6位数字）")
    name: str = Field(description="股票名称")
    query_time: str = Field(description="采集时间 ISO 格式")
    data_errors: list[str] = Field(default_factory=list, description="采集过程中遇到的错误列表")
    successful_topics: int = Field(
        default=0, description="成功采集的主题数（ok + no_data，总共15个）"
    )
    topic_status: dict[str, str] = Field(
        default_factory=dict,
        description="每个主题的采集状态。ok=有数据, no_data=成功但无业务数据, failed=失败",
    )


class CompanyInfo(BaseModel):
    """主题①：公司基本信息。"""

    industry: str = Field(default="", description="所属行业")
    listing_date: str = Field(default="", description="上市日期")
    total_market_cap: float | None = Field(default=None, description="总市值（亿元）")
    circulating_market_cap: float | None = Field(default=None, description="流通市值（亿元）")
    total_shares: float | None = Field(default=None, description="总股本（亿股）")
    circulating_shares: float | None = Field(default=None, description="流通股（亿股）")


class RealtimeQuote(BaseModel):
    """主题②：实时行情快照。"""

    price: float | None = Field(default=None, description="最新价")
    change_pct: float | None = Field(default=None, description="涨跌幅(%)")
    volume: float | None = Field(default=None, description="成交量")
    turnover: float | None = Field(default=None, description="成交额")
    pe_ttm: float | None = Field(default=None, description="动态市盈率")
    pb: float | None = Field(default=None, description="市净率")
    turnover_rate: float | None = Field(default=None, description="换手率(%)")
    volume_ratio: float | None = Field(default=None, description="量比")
    change_60d_pct: float | None = Field(default=None, description="60日涨跌幅(%)")
    change_ytd_pct: float | None = Field(default=None, description="年初至今涨跌幅(%)")


class FinancialIndicator(BaseModel):
    """主题③：单期财务分析指标。"""

    report_date: str = Field(description="报告期")
    eps: float | None = Field(default=None, description="每股收益(元)")
    net_asset_per_share: float | None = Field(default=None, description="每股净资产(元)")
    roe: float | None = Field(default=None, description="ROE(%)")
    gross_margin: float | None = Field(default=None, description="毛利率(%)")
    net_margin: float | None = Field(default=None, description="净利率(%)")
    revenue_growth: float | None = Field(default=None, description="营收同比增长率(%)")
    profit_growth: float | None = Field(default=None, description="净利润同比增长率(%)")
    debt_ratio: float | None = Field(default=None, description="资产负债率(%)")
    current_ratio: float | None = Field(default=None, description="流动比率")


class ValuationHistory(BaseModel):
    """主题④：估值历史数据与分位数。"""

    current_pe_ttm: float | None = Field(default=None, description="当前PE(TTM)")
    current_pb: float | None = Field(default=None, description="当前PB")
    pe_percentile: float | None = Field(default=None, description="PE历史分位数(0-100)")
    pb_percentile: float | None = Field(default=None, description="PB历史分位数(0-100)")
    current_ps_ttm: float | None = Field(default=None, description="当前PS(TTM)")
    current_dv_ttm: float | None = Field(default=None, description="当前股息率(TTM,%)")
    history_summary: str = Field(default="", description="估值分位描述")


class ValuationVsIndustry(BaseModel):
    """主题⑤：行业估值对比。"""

    stock_pe: float | None = Field(default=None, description="个股PE")
    industry_avg_pe: float | None = Field(default=None, description="行业平均PE")
    industry_median_pe: float | None = Field(default=None, description="行业中位数PE")
    stock_pb: float | None = Field(default=None, description="个股PB")
    industry_avg_pb: float | None = Field(default=None, description="行业平均PB")
    relative_valuation: str = Field(default="", description="相对估值判断")


class FundFlowDay(BaseModel):
    """单日资金流向。"""

    date: str = Field(description="日期")
    main_net_inflow: float | None = Field(default=None, description="主力净流入(万元)")
    main_net_inflow_pct: float | None = Field(default=None, description="主力净流入占比(%)")


class FundFlowSummary(BaseModel):
    """资金流向汇总。"""

    main_net_inflow_5d_total: float | None = Field(
        default=None, description="近5日主力净流入合计(万元，不足5日则为None)"
    )
    main_net_inflow_10d_total: float | None = Field(
        default=None, description="近10日主力净流入合计(万元，不足10日则为None)"
    )
    trend: str = Field(default="", description="资金流向趋势描述")


class FundFlow(BaseModel):
    """主题⑥：个股资金流向。"""

    recent_days: list[FundFlowDay] = Field(default_factory=list)
    summary: FundFlowSummary = Field(default_factory=FundFlowSummary)


class HotConcept(BaseModel):
    """热门概念板块。"""

    name: str
    net_inflow: float | None = None


class SectorFlow(BaseModel):
    """主题⑦：板块资金流向。"""

    industry_name: str = Field(default="", description="所属行业名称")
    industry_rank: int | None = Field(default=None, description="行业板块资金流向排名")
    industry_net_inflow_today: float | None = Field(
        default=None, description="行业板块今日主力净流入"
    )
    hot_concepts_top5: list[HotConcept] = Field(default_factory=list)


class Northbound(BaseModel):
    """主题⑧：北向资金持仓。"""

    held: bool = Field(default=False, description="是否在北向持仓名单中")
    shares_held: float | None = Field(default=None, description="持股数量")
    market_value: float | None = Field(default=None, description="持股市值")
    change_pct: float | None = Field(default=None, description="持股数量增减比例(%)")
    note: str = Field(default="", description="备注（如披露规则变化提醒）")


class ShareholderCount(BaseModel):
    """单期股东户数。"""

    date: str = Field(description="统计截止日")
    count: int | None = Field(default=None, description="股东户数（整数）")
    change_pct: float | None = Field(default=None, description="增减比例(%)")


class DividendRecord(BaseModel):
    """单年分红记录。"""

    year: str = Field(description="年度")
    dividend_per_share: float | None = Field(default=None, description="累计股息(元/股)")
    ex_date: str = Field(default="", description="除权除息日")


class EarningsForecast(BaseModel):
    """主题⑪：业绩预告。"""

    latest_period: str | None = Field(default=None, description="最新预告报告期")
    forecast_type: str | None = Field(default=None, description="业绩变动类型")
    forecast_range: str | None = Field(default=None, description="预测内容")
    available: bool = Field(default=False, description="是否有业绩预告")


class PledgeRatio(BaseModel):
    """主题⑫：股权质押。"""

    ratio_pct: float | None = Field(default=None, description="质押比例(%)")
    pledged_shares: float | None = Field(default=None, description="质押股数")
    risk_level: Literal["低", "中", "高", "极高"] = Field(
        default="低", description="质押风险等级"
    )


class ConsensusForecast(BaseModel):
    """主题⑬：一致预期。"""

    year: str = Field(description="预测年度")
    inst_count: int | None = Field(default=None, description="预测机构数")
    net_profit_avg: float | None = Field(default=None, description="归母净利润均值（亿元）")
    industry_avg: float | None = Field(default=None, description="行业平均（亿元）")


class InstitutionalHolding(BaseModel):
    """主题⑭：机构持仓详情。"""

    type: str = Field(description="持股机构类型")
    name: str = Field(description="持股机构简称")
    ratio: float | None = Field(default=None, description="持股比例(%)")


class BusinessComposition(BaseModel):
    """主题⑮：主营结构。"""

    report_date: str = Field(description="报告期")
    type: str = Field(description="分类类型（按产品/按地区/按行业）")
    item: str = Field(description="主营构成项目")
    revenue_ratio: float | None = Field(default=None, description="收入比例(%)")
    gross_margin: float | None = Field(default=None, description="毛利率(%)")


class AKShareData(BaseModel):
    """模块A 最终输出。"""

    meta: AKShareMeta
    company_info: CompanyInfo | None = None
    realtime_quote: RealtimeQuote | None = None
    financial_indicators: list[FinancialIndicator] | None = None
    valuation_history: ValuationHistory | None = None
    valuation_vs_industry: ValuationVsIndustry | None = None
    fund_flow: FundFlow | None = None
    sector_flow: SectorFlow | None = None
    northbound: Northbound | None = None
    shareholder_count: list[ShareholderCount] | None = None
    dividend_history: list[DividendRecord] | None = None
    earnings_forecast: EarningsForecast | None = None
    pledge_ratio: PledgeRatio | None = None
    consensus_forecast: list[ConsensusForecast] | None = None
    institutional_holdings: list[InstitutionalHolding] | None = None
    business_composition: list[BusinessComposition] | None = None

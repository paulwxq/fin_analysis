"""Markdown formatters for Module A/B/C data serialization.

Converts Pydantic model outputs into compact, human-readable Markdown
for injection into Module D (chief analyst) prompts.
"""

from __future__ import annotations

from stock_analyzer.models import WebResearchResult
from stock_analyzer.module_a_models import AKShareData
from stock_analyzer.module_c_models import TechnicalAnalysisResult
from stock_analyzer.module_d_models import FinalReport

_NULL = "—"


# ── Utility functions ─────────────────────────────────────────


def _fmt_pct(value: float | None) -> str:
    """Format a percentage field: 14.377 → '14.38%', None → '—'."""
    if value is None:
        return _NULL
    return f"{value:.2f}%"


def _fmt_ratio(value: float | None) -> str:
    """Format a 0-1 ratio to percentage: 0.75388 → '75.39%', None → '—'."""
    if value is None:
        return _NULL
    return f"{value * 100:.2f}%"


def _fmt_val(value: object, decimals: int = 2) -> str:
    """Generic null-safe formatter: None → '—', float → rounded string."""
    if value is None:
        return _NULL
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def _fmt_int(value: int | None) -> str:
    """Format integer with comma separator: 78886 → '78,886', None → '—'."""
    if value is None:
        return _NULL
    return f"{value:,}"


def _fmt_amount_wan(value: float | None) -> str:
    """Format raw amount to 万元: 3714368.0 → '371.44', None → '—'."""
    if value is None:
        return _NULL
    return f"{value / 10000:.2f}"


def _to_table(headers: list[str], rows: list[list[str]]) -> str:
    """Generate a Markdown table string."""
    if not rows:
        return ""
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join("---" for _ in headers) + " |"
    data_lines = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, sep_line, *data_lines])


# ── Module A formatter ────────────────────────────────────────


def _format_company_info(data: AKShareData) -> str:
    ci = data.company_info
    if ci is None:
        return "### 公司概况\n（数据缺失）\n"
    lines = [
        "### 公司概况",
        f"- 行业：{ci.industry or _NULL}",
        f"- 上市日期：{ci.listing_date or _NULL}",
        f"- 总市值：{_fmt_val(ci.total_market_cap)} 亿元 | "
        f"流通市值：{_fmt_val(ci.circulating_market_cap)} 亿元",
        f"- 总股本：{_fmt_val(ci.total_shares)} 亿股 | "
        f"流通股：{_fmt_val(ci.circulating_shares)} 亿股",
    ]
    return "\n".join(lines) + "\n"


def _format_realtime_quote(data: AKShareData) -> str:
    rq = data.realtime_quote
    if rq is None:
        return "### 实时行情\n（数据缺失）\n"
    lines = [
        "### 实时行情",
        f"- 最新价：{_fmt_val(rq.price)} | "
        f"涨跌幅：{_fmt_pct(rq.change_pct)} | "
        f"换手率：{_fmt_pct(rq.turnover_rate)}",
        f"- 成交量：{_fmt_val(rq.volume)} | "
        f"成交额：{_fmt_val(rq.turnover)} | "
        f"量比：{_fmt_val(rq.volume_ratio)}",
        f"- PE(TTM)：{_fmt_val(rq.pe_ttm)} | PB：{_fmt_val(rq.pb)}",
        f"- 60日涨跌幅：{_fmt_pct(rq.change_60d_pct)} | "
        f"年初至今：{_fmt_pct(rq.change_ytd_pct)}",
    ]
    return "\n".join(lines) + "\n"


def _format_financial_indicators(data: AKShareData) -> str:
    fi = data.financial_indicators
    if not fi:
        return "### 财务指标\n（数据缺失）\n"

    periods = [item.report_date for item in fi]
    headers = ["指标", *periods]

    def _row(label: str, extractor, fmt_fn=_fmt_pct):
        return [label, *[fmt_fn(extractor(item)) for item in fi]]

    rows = [
        _row("EPS(元)", lambda x: x.eps, _fmt_val),
        _row("每股净资产(元)", lambda x: x.net_asset_per_share, _fmt_val),
        _row("ROE(%)", lambda x: x.roe),
        _row("毛利率(%)", lambda x: x.gross_margin),
        _row("净利率(%)", lambda x: x.net_margin),
        _row("营收增长(%)", lambda x: x.revenue_growth),
        _row("利润增长(%)", lambda x: x.profit_growth),
        _row("资产负债率(%)", lambda x: x.debt_ratio),
        _row("流动比率", lambda x: x.current_ratio, _fmt_val),
    ]
    return f"### 财务指标（近{len(fi)}期）\n\n{_to_table(headers, rows)}\n"


def _format_valuation_history(data: AKShareData) -> str:
    vh = data.valuation_history
    if vh is None:
        return "### 估值历史\n（数据缺失）\n"
    lines = [
        "### 估值历史",
        f"- PE(TTM)：{_fmt_val(vh.current_pe_ttm)} | "
        f"PB：{_fmt_val(vh.current_pb)}",
        f"- PE历史分位：{_fmt_pct(vh.pe_percentile)} | "
        f"PB历史分位：{_fmt_pct(vh.pb_percentile)}",
        f"- PS(TTM)：{_fmt_val(vh.current_ps_ttm)} | "
        f"股息率(TTM)：{_fmt_pct(vh.current_dv_ttm)}",
    ]
    if vh.history_summary:
        lines.append(f"- 分位解读：{vh.history_summary}")
    return "\n".join(lines) + "\n"


def _format_valuation_vs_industry(data: AKShareData) -> str:
    vi = data.valuation_vs_industry
    if vi is None:
        return "### 估值-行业对比\n（数据缺失）\n"
    headers = ["指标", "个股", "行业均值", "行业中位数"]
    rows = [
        ["PE", _fmt_val(vi.stock_pe), _fmt_val(vi.industry_avg_pe),
         _fmt_val(vi.industry_median_pe)],
        ["PB", _fmt_val(vi.stock_pb), _fmt_val(vi.industry_avg_pb), _NULL],
    ]
    table = _to_table(headers, rows)
    verdict = f"\n相对估值判断：{vi.relative_valuation}" if vi.relative_valuation else ""
    return f"### 估值-行业对比\n\n{table}{verdict}\n"


def _format_fund_flow(data: AKShareData) -> str:
    ff = data.fund_flow
    if ff is None:
        return "### 个股资金流向\n（数据缺失）\n"

    parts = ["### 个股资金流向\n"]
    if ff.recent_days:
        headers = ["日期", "主力净流入(万元)", "占比(%)"]
        rows = [
            [d.date, _fmt_amount_wan(d.main_net_inflow),
             _fmt_pct(d.main_net_inflow_pct)]
            for d in ff.recent_days
        ]
        parts.append(_to_table(headers, rows))
        parts.append("")

    s = ff.summary
    parts.append(
        f"- 近5日主力净流入合计：{_fmt_amount_wan(s.main_net_inflow_5d_total)} 万元"
    )
    parts.append(
        f"- 近10日主力净流入合计：{_fmt_amount_wan(s.main_net_inflow_10d_total)} 万元"
    )
    if s.trend:
        parts.append(f"- 趋势：{s.trend}")
    return "\n".join(parts) + "\n"


def _format_sector_flow(data: AKShareData) -> str:
    sf = data.sector_flow
    if sf is None:
        return "### 板块资金流向\n（数据缺失）\n"
    lines = [
        "### 板块资金流向",
        f"- 所属行业：{sf.industry_name or _NULL} | "
        f"行业排名：{_fmt_val(sf.industry_rank, 0) if sf.industry_rank is not None else _NULL}",
        f"- 行业今日主力净流入：{_fmt_amount_wan(sf.industry_net_inflow_today)} 万元",
    ]
    if sf.hot_concepts_top5:
        lines.append("")
        headers = ["概念", "主力净流入(万元)"]
        rows = [
            [c.name, _fmt_amount_wan(c.net_inflow)]
            for c in sf.hot_concepts_top5
        ]
        lines.append(_to_table(headers, rows))
    return "\n".join(lines) + "\n"


def _format_northbound(data: AKShareData) -> str:
    nb = data.northbound
    if nb is None:
        return "### 北向资金\n（数据缺失）\n"
    if not nb.held:
        return "### 北向资金\n- 是否持有：否\n"
    lines = [
        "### 北向资金",
        f"- 是否持有：是",
        f"- 持股数量：{_fmt_val(nb.shares_held)} 万股 | "
        f"持股市值：{_fmt_val(nb.market_value)} 万元",
        f"- 增减比例：{_fmt_pct(nb.change_pct)}",
    ]
    if nb.note:
        lines.append(f"- 备注：{nb.note}")
    return "\n".join(lines) + "\n"


def _format_shareholder_count(data: AKShareData) -> str:
    sc = data.shareholder_count
    if not sc:
        return "### 股东户数变动\n（数据缺失）\n"
    headers = ["截止日", "股东户数", "增减(%)"]
    rows = [
        [item.date, _fmt_int(item.count), _fmt_pct(item.change_pct)]
        for item in sc
    ]
    return f"### 股东户数变动\n\n{_to_table(headers, rows)}\n"


def _format_dividend_history(data: AKShareData) -> str:
    dh = data.dividend_history
    if not dh:
        return "### 分红历史\n（数据缺失）\n"
    headers = ["年度", "累计股息(元/股)", "除权除息日"]
    rows = [
        [item.year, _fmt_val(item.dividend_per_share), item.ex_date or _NULL]
        for item in dh
    ]
    return f"### 分红历史\n\n{_to_table(headers, rows)}\n"


def _format_earnings_forecast(data: AKShareData) -> str:
    ef = data.earnings_forecast
    if ef is None or not ef.available:
        return "### 业绩预告\n（暂无业绩预告数据）\n"
    lines = [
        "### 业绩预告",
        f"- 报告期：{ef.latest_period or _NULL} | "
        f"变动类型：{ef.forecast_type or _NULL}",
        f"- 预告内容：{ef.forecast_range or _NULL}",
    ]
    return "\n".join(lines) + "\n"


def _format_pledge_ratio(data: AKShareData) -> str:
    pr = data.pledge_ratio
    if pr is None:
        return "### 股权质押\n（数据缺失）\n"
    return (
        f"### 股权质押\n"
        f"- 质押比例：{_fmt_pct(pr.ratio_pct)} | "
        f"风险等级：{pr.risk_level}\n"
    )


def _format_consensus_forecast(data: AKShareData) -> str:
    cf = data.consensus_forecast
    if not cf:
        return "### 一致预期\n（数据缺失）\n"
    headers = ["年度", "机构数", "归母净利润均值(亿元)", "行业平均(亿元)"]
    rows = [
        [item.year, _fmt_int(item.inst_count),
         _fmt_val(item.net_profit_avg), _fmt_val(item.industry_avg)]
        for item in cf
    ]
    return f"### 一致预期\n\n{_to_table(headers, rows)}\n"


def _format_institutional_holdings(data: AKShareData) -> str:
    ih = data.institutional_holdings
    if not ih:
        return "### 机构持仓\n（无机构持仓数据）\n"
    headers = ["类型", "机构", "持股比例(%)"]
    rows = [
        [item.type, item.name, _fmt_pct(item.ratio)]
        for item in ih
    ]
    return f"### 机构持仓\n\n{_to_table(headers, rows)}\n"


def _format_business_composition(data: AKShareData) -> str:
    bc = data.business_composition
    if not bc:
        return "### 主营结构\n（数据缺失）\n"

    # Group by report_date
    grouped: dict[str, list] = {}
    for item in bc:
        grouped.setdefault(item.report_date, []).append(item)

    # Sort dates descending
    sorted_dates = sorted(grouped.keys(), reverse=True)

    parts = ["### 主营结构\n"]

    for date in sorted_dates:
        items = grouped[date]
        parts.append(f"**报告期：{date}**\n")

        # Split by type
        by_product = [r for r in items if r.type == "按产品分类"]
        by_region = [r for r in items if r.type == "按地区分类"]
        by_summary = [r for r in items if r.type == ""]

        if by_product:
            headers = ["项目", "收入占比", "毛利率"]
            rows = [
                [item.item, _fmt_ratio(item.revenue_ratio),
                 _fmt_ratio(item.gross_margin)]
                for item in by_product
            ]
            parts.append(f"按产品分类：")
            parts.append(_to_table(headers, rows))
            parts.append("")

        if by_region:
            headers = ["地区", "收入占比", "毛利率"]
            rows = [
                [item.item, _fmt_ratio(item.revenue_ratio),
                 _fmt_ratio(item.gross_margin)]
                for item in by_region
            ]
            parts.append(f"按地区分类：")
            parts.append(_to_table(headers, rows))
            parts.append("")
        
        # Add a separator between periods if it's not the last one
        if date != sorted_dates[-1]:
            parts.append("---\n")

    return "\n".join(parts) + "\n"


def format_akshare_markdown(data: AKShareData) -> str:
    """Convert Module A AKShareData to Markdown string."""
    sections = [
        _format_company_info(data),
        _format_realtime_quote(data),
        _format_financial_indicators(data),
        _format_valuation_history(data),
        _format_valuation_vs_industry(data),
        _format_fund_flow(data),
        _format_sector_flow(data),
        _format_northbound(data),
        _format_shareholder_count(data),
        _format_dividend_history(data),
        _format_earnings_forecast(data),
        _format_pledge_ratio(data),
        _format_consensus_forecast(data),
        _format_institutional_holdings(data),
        _format_business_composition(data),
    ]
    return "\n".join(sections)


# ── Module B formatter ────────────────────────────────────────


def _format_news_summary(data: WebResearchResult) -> str:
    ns = data.news_summary
    parts = ["### 舆情汇总\n"]

    def _news_list(items, marker: str, label: str) -> list[str]:
        if not items:
            return []
        lines = [f"**{label}：**"]
        for n in items:
            lines.append(
                f"- {marker}[{n.importance}] {n.title} — {n.summary}"
                f"（来源：{n.source}，{n.date}）"
            )
        return lines

    for section in [
        _news_list(ns.positive, "[+]", "正面新闻"),
        _news_list(ns.negative, "[-]", "负面新闻"),
        _news_list(ns.neutral, "[~]", "中性新闻"),
    ]:
        if section:
            parts.extend(section)
            parts.append("")

    return "\n".join(parts)


def _format_competitive_advantage(data: WebResearchResult) -> str:
    ca = data.competitive_advantage
    lines = [
        "### 核心竞争力",
        f"- 描述：{ca.description}",
        f"- 护城河类型：{ca.moat_type}",
        f"- 市场地位：{ca.market_position}",
    ]
    return "\n".join(lines) + "\n"


def _format_industry_outlook(data: WebResearchResult) -> str:
    io = data.industry_outlook
    lines = [
        f"### 行业展望（{io.industry}）",
        f"展望：{io.outlook}",
        "",
        "关键驱动力：",
    ]
    for i, d in enumerate(io.key_drivers, 1):
        lines.append(f"{i}. {d}")
    lines.append("")
    lines.append("关键风险：")
    for i, r in enumerate(io.key_risks, 1):
        lines.append(f"{i}. {r}")
    return "\n".join(lines) + "\n"


def _format_risk_events(data: WebResearchResult) -> str:
    re_ = data.risk_events
    lines = [
        "### 风险事件",
        f"- 监管风险：{re_.regulatory}",
        f"- 诉讼风险：{re_.litigation}",
        f"- 管理层风险：{re_.management}",
    ]
    if re_.other:
        lines.append(f"- 其他风险：{re_.other}")
    return "\n".join(lines) + "\n"


def _format_analyst_opinions(data: WebResearchResult) -> str:
    ao = data.analyst_opinions
    lines = [
        "### 分析师观点",
        f"- 评级分布：买入 {ao.buy_count} | 持有 {ao.hold_count} | 卖出 {ao.sell_count}",
        f"- 平均目标价：{_fmt_val(ao.average_target_price)} 元",
    ]
    if ao.recent_reports:
        headers = ["券商", "评级", "目标价(元)", "日期"]
        rows = [
            [r.broker, r.rating, _fmt_val(r.target_price), r.date]
            for r in ao.recent_reports
        ]
        lines.append("")
        lines.append(_to_table(headers, rows))
    return "\n".join(lines) + "\n"


def format_web_research_markdown(data: WebResearchResult) -> str:
    """Convert Module B WebResearchResult to Markdown string."""
    sections = [
        _format_news_summary(data),
        _format_competitive_advantage(data),
        _format_industry_outlook(data),
        _format_risk_events(data),
        _format_analyst_opinions(data),
        f"搜索置信度：{data.search_confidence}\n",
    ]
    return "\n".join(sections)


# ── Module C formatter ────────────────────────────────────────


def format_technical_markdown(data: TechnicalAnalysisResult) -> str:
    """Convert Module C TechnicalAnalysisResult to Markdown string."""
    parts: list[str] = []

    # Overview panel
    parts.append("### 技术面总览")
    parts.append(
        f"- 评分：{_fmt_val(data.score)}/10 | "
        f"信号：{data.signal} | "
        f"置信度：{_fmt_val(data.confidence)}"
    )
    parts.append("")

    # Trend analysis
    ta = data.trend_analysis
    parts.append("### 趋势分析")
    parts.append(f"- 均线排列：{ta.ma_alignment}")
    parts.append(f"- 价格 vs MA20：{ta.price_vs_ma20}")
    parts.append(f"- 近6月涨幅：{ta.trend_6m} | 近12月涨幅：{ta.trend_12m}")
    if ta.trend_judgment:
        parts.append(f"- 趋势判断：{ta.trend_judgment}")
    parts.append("")

    # Momentum
    m = data.momentum
    parts.append("### 动量分析")
    parts.append(f"- MACD：{m.macd_status}")
    rsi_label = _fmt_val(m.rsi_value) if m.rsi_value is not None else _NULL
    parts.append(f"- RSI：{rsi_label} — {m.rsi_status}")
    parts.append(f"- KDJ：{m.kdj_status}")
    parts.append("")

    # Volatility
    v = data.volatility
    parts.append("### 波动性分析")
    parts.append(f"- 布林位置：{v.boll_position}")
    parts.append(f"- 布林带宽：{v.boll_width}")
    parts.append("")

    # Volume
    vol = data.volume_analysis
    parts.append("### 量价分析")
    parts.append(f"- 量能对比：{vol.recent_vs_avg}")
    parts.append(f"- 量价关系：{vol.volume_price_relation}")
    parts.append("")

    # Key levels
    kl = data.key_levels
    parts.append("### 关键价位\n")
    headers = ["类型", "第一位", "第二位"]
    rows = [
        ["支撑", f"**{_fmt_val(kl.support_1)}**", f"**{_fmt_val(kl.support_2)}**"],
        ["阻力", f"**{_fmt_val(kl.resistance_1)}**", f"**{_fmt_val(kl.resistance_2)}**"],
    ]
    parts.append(_to_table(headers, rows))
    parts.append("")

    # Summary
    parts.append("### 技术总结")
    parts.append(data.summary)
    parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Final Report (Module D) → Markdown
# ---------------------------------------------------------------------------

_DIMENSION_LABELS = {
    "technical": "技术面",
    "fundamental": "基本面",
    "valuation": "估值",
    "capital_flow": "资金流向",
    "sentiment": "市场情绪",
}


def render_final_report_markdown(report: FinalReport) -> str:
    """Render a FinalReport to a human-readable Markdown string."""
    m = report.meta
    parts: list[str] = []

    # Title
    parts.append(f"# {m.name}（{m.symbol}）投资分析报告\n")
    parts.append(f"> 分析时间：{m.analysis_time}\n")

    # Overall score (first section)
    parts.append("## 综合评估\n")
    parts.append(
        f"- 综合评分：**{report.overall_score}**/10\n"
        f"- 置信度：**{report.overall_confidence}**"
    )
    if report.veto_triggered:
        cap = f"（评分上限：{report.score_cap}）" if report.score_cap is not None else ""
        parts.append(f"- 一票否决触发：{report.veto_reason}{cap}")
    parts.append("")

    # Dimension scores
    parts.append("## 维度评分\n")
    dim_headers = ["维度", "评分", "简评"]
    dim_rows: list[list[str]] = []
    ds = report.dimension_scores
    for field, label in _DIMENSION_LABELS.items():
        dim = getattr(ds, field)
        dim_rows.append([label, str(dim.score), dim.brief])
    parts.append(_to_table(dim_headers, dim_rows))
    parts.append("")

    # Advice
    parts.append("## 投资建议\n")
    adv_headers = ["时间框架", "建议", "理由"]
    adv_rows = [[a.timeframe, a.recommendation, a.reasoning] for a in report.advice]
    parts.append(_to_table(adv_headers, adv_rows))
    parts.append("")

    # Report body
    parts.append("## 分析报告\n")
    parts.append(report.report)
    parts.append("")

    # Catalysts
    parts.append("## 关键催化剂\n")
    for c in report.key_catalysts:
        parts.append(f"- {c}")
    parts.append("")

    # Risks
    parts.append("## 主要风险\n")
    for r in report.primary_risks:
        parts.append(f"- {r}")
    parts.append("")

    # Disclaimer
    parts.append("---")
    parts.append("*免责声明：本报告由 AI 自动生成，仅供参考，不构成投资建议。*")
    parts.append("")

    return "\n".join(parts)

# Module A 目标数据清单（按详细设计）

本文用于明确：按照 `module_a_akshare_detail_design.md`，模块A最终**应该采集并输出哪些信息**。  
可直接作为测试 checklist 使用。

---

## 1. 顶层输出结构（AKShareData）

输出对象包含 `meta` + 12 个主题字段：

1. `meta`
2. `company_info`
3. `realtime_quote`
4. `financial_indicators`
5. `valuation_history`
6. `valuation_vs_industry`
7. `fund_flow`
8. `sector_flow`
9. `northbound`
10. `shareholder_count`
11. `dividend_history`
12. `earnings_forecast`
13. `pledge_ratio`

---

## 2. 元信息（meta）应包含内容

路径：`meta.*`

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` | `str` | 纯6位股票代码 |
| `name` | `str` | 股票名称 |
| `query_time` | `str` | 采集时间（ISO格式） |
| `data_errors` | `list[str]` | 采集过程错误列表 |
| `successful_topics` | `int` | 成功主题数（`ok + no_data`） |
| `topic_status` | `dict[str, str]` | 每主题状态：`ok/no_data/failed` |

---

## 3. 12 个主题应采集字段

## 3.1 主题① 公司基本信息 `company_info`

| 字段 | 类型 | 说明 |
|---|---|---|
| `industry` | `str` | 所属行业 |
| `listing_date` | `str` | 上市日期（YYYYMMDD格式） |
| `total_market_cap` | `float \| None` | 总市值（亿元，由原始元值 ÷ 1e8 得到） |
| `circulating_market_cap` | `float \| None` | 流通市值（亿元，由原始元值 ÷ 1e8 得到） |
| `total_shares` | `float \| None` | 总股本（亿股，由原始股数 ÷ 1e8 得到） |
| `circulating_shares` | `float \| None` | 流通股（亿股，由原始股数 ÷ 1e8 得到） |

## 3.2 主题② 实时行情 `realtime_quote`

| 字段 | 类型 | 说明 |
|---|---|---|
| `price` | `float \| None` | 最新价 |
| `change_pct` | `float \| None` | 涨跌幅(%) |
| `volume` | `float \| None` | 成交量 |
| `turnover` | `float \| None` | 成交额 |
| `pe_ttm` | `float \| None` | 动态市盈率 |
| `pb` | `float \| None` | 市净率 |
| `turnover_rate` | `float \| None` | 换手率(%) |
| `volume_ratio` | `float \| None` | 量比 |
| `change_60d_pct` | `float \| None` | 60日涨跌幅(%) |
| `change_ytd_pct` | `float \| None` | 年初至今涨跌幅(%) |

## 3.3 主题③ 财务分析指标 `financial_indicators`

类型：`list[FinancialIndicator]`，默认取最近 `AKSHARE_FINANCIAL_PERIODS` 期（默认 8）

单期字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `report_date` | `str` | 报告期 |
| `eps` | `float \| None` | 每股收益(元) |
| `net_asset_per_share` | `float \| None` | 每股净资产(元) |
| `roe` | `float \| None` | ROE(%) |
| `gross_margin` | `float \| None` | 毛利率(%) |
| `net_margin` | `float \| None` | 净利率(%) |
| `revenue_growth` | `float \| None` | 营收同比增长率(%) |
| `profit_growth` | `float \| None` | 净利润同比增长率(%) |
| `debt_ratio` | `float \| None` | 资产负债率(%) |
| `current_ratio` | `float \| None` | 流动比率 |

## 3.4 主题④ 估值历史 `valuation_history`

| 字段 | 类型 | 说明 |
|---|---|---|
| `current_pe_ttm` | `float \| None` | 当前PE(TTM) |
| `current_pb` | `float \| None` | 当前PB |
| `pe_percentile` | `float \| None` | PE历史分位(0-100) |
| `pb_percentile` | `float \| None` | PB历史分位(0-100) |
| `current_ps_ttm` | `float \| None` | 当前PS(TTM) |
| `current_dv_ttm` | `float \| None` | 当前股息率(TTM, %) |
| `history_summary` | `str` | 分位描述文本 |

## 3.5 主题⑤ 行业估值对比 `valuation_vs_industry`

| 字段 | 类型 | 说明 |
|---|---|---|
| `stock_pe` | `float \| None` | 个股PE |
| `industry_avg_pe` | `float \| None` | 行业平均PE |
| `industry_median_pe` | `float \| None` | 行业中位数PE |
| `stock_pb` | `float \| None` | 个股PB |
| `industry_avg_pb` | `float \| None` | 行业平均PB |
| `relative_valuation` | `str` | 相对估值判断 |

## 3.6 主题⑥ 个股资金流 `fund_flow`

结构：
- `recent_days`: `list[FundFlowDay]`，默认最近 `AKSHARE_FUND_FLOW_DAYS` 天（默认 5）
- `summary`: `FundFlowSummary`

`recent_days` 单日字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `date` | `str` | 日期 |
| `main_net_inflow` | `float \| None` | 主力净流入(万元) |
| `main_net_inflow_pct` | `float \| None` | 主力净流入占比(%) |

`summary` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `main_net_inflow_5d_total` | `float \| None` | 近5日主力净流入合计 |
| `main_net_inflow_10d_total` | `float \| None` | 近10日主力净流入合计 |
| `trend` | `str` | 趋势描述 |

## 3.7 主题⑦ 板块资金流 `sector_flow`

| 字段 | 类型 | 说明 |
|---|---|---|
| `industry_name` | `str` | 行业名称 |
| `industry_rank` | `int \| None` | 行业资金流排名 |
| `industry_net_inflow_today` | `float \| None` | 行业今日主力净流入 |
| `hot_concepts_top5` | `list[HotConcept]` | 热门概念Top5 |

`hot_concepts_top5` 单项字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | `str` | 概念名 |
| `net_inflow` | `float \| None` | 净流入 |

## 3.8 主题⑧ 北向资金持仓 `northbound`

| 字段 | 类型 | 说明 |
|---|---|---|
| `held` | `bool` | 是否在北向持仓名单中 |
| `shares_held` | `float \| None` | 持股数量 |
| `market_value` | `float \| None` | 持股市值 |
| `change_pct` | `float \| None` | 持股数量增减比例(%) |
| `note` | `str` | 备注 |

## 3.9 主题⑨ 股东户数 `shareholder_count`

类型：`list[ShareholderCount]`，默认最近 `AKSHARE_SHAREHOLDER_PERIODS` 期（默认 4）

| 字段 | 类型 | 说明 |
|---|---|---|
| `date` | `str` | 统计截止日 |
| `count` | `int \| None` | 股东户数 |
| `change_pct` | `float \| None` | 增减比例(%) |

## 3.10 主题⑩ 分红历史 `dividend_history`

类型：`list[DividendRecord]`，默认最近 `AKSHARE_DIVIDEND_YEARS` 年（默认 5）

| 字段 | 类型 | 说明 |
|---|---|---|
| `year` | `str` | 年度 |
| `dividend_per_share` | `float \| None` | 累计股息(元/股) |
| `ex_date` | `str` | 除权除息日 |

## 3.11 主题⑪ 业绩预告 `earnings_forecast`

| 字段 | 类型 | 说明 |
|---|---|---|
| `latest_period` | `str \| None` | 最新预告报告期 |
| `forecast_type` | `str \| None` | 业绩变动类型 |
| `forecast_range` | `str \| None` | 预测内容 |
| `available` | `bool` | 是否有业绩预告 |

## 3.12 主题⑫ 股权质押 `pledge_ratio`

| 字段 | 类型 | 说明 |
|---|---|---|
| `ratio_pct` | `float \| None` | 质押比例(%) |
| `pledged_shares` | `float \| None` | 质押股数 |
| `risk_level` | `"低"\|"中"\|"高"\|"极高"` | 质押风险等级 |

---

## 4. 测试时的状态判定规则

用于判断“拿不到数据”是否符合设计预期。

1. `topic_status = "ok"`  
主题采集成功（允许内部部分字段为 `null`）。

2. `topic_status = "no_data"`  
接口调用成功，但业务上确实无记录。当前典型是 `earnings_forecast`。

3. `topic_status = "failed"`  
接口异常、超时、返回空表、关键匹配失败等导致主题失败。

4. 顶层容错  
单主题失败不应中断整轮采集；失败原因应写入 `meta.data_errors`。

---

## 5. 建议给测试 AI 的最小覆盖目标

1. 验证 12 个主题键是否都存在于输出 JSON。
2. 验证 `meta.topic_status` 是否包含 12 个主题状态。
3. 对每个主题按本清单检查字段名是否完整。
4. 对 `no_data` 场景（业绩预告）验证 `available=false` + 状态为 `no_data`。
5. 对 `failed` 场景验证对应主题为 `null` 或缺失业务数据，并在 `meta.data_errors` 有明确信息。


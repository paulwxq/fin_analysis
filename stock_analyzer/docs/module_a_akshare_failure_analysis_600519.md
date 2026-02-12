# Module A AKShare 执行失败分析（600519.SH 贵州茅台）

## 1. 执行上下文
- 命令：`python stock_analyzer/run_module_a.py 600519.SH 贵州茅台`
- 输出文件：`output/600519_akshare_data.json`
- 汇总结果：`successful_topics = 9/12`，`failed = 3`，`data_errors = 7`

---

## 2. 硬失败主题（topic_status = failed）

### 2.1 `realtime_quote`
- 失败日志：
  - `ConnectionError - ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) (stock_zh_a_spot_em)`
- 失败原因：
  - 行情源站连接被对端中断，未拿到全市场实时行情表。
- 缺失数据：
  - 整个 `realtime_quote` 为 `null`（价格、涨跌幅、成交额、PE/PB 等全部缺失）。

### 2.2 `financial_indicators`
- 失败日志：
  - `financial_indicators: 返回数据为空 (stock_financial_analysis_indicator)`
- 失败原因：
  - 接口调用成功但返回空 DataFrame，采集器按失败处理。
- 缺失数据：
  - 整个 `financial_indicators` 为 `null`（近 N 期财务指标全部缺失）。

### 2.3 `sector_flow`
- 失败日志：
  - `sector_flow_industry: ConnectionError ... (stock_sector_fund_flow_rank)`
  - `sector_flow_concept: ConnectionError ... (stock_sector_fund_flow_rank)`
- 失败原因：
  - 行业资金流和概念资金流两个子接口均连接中断。
- 缺失数据：
  - 整个 `sector_flow` 为 `null`（行业排名、行业净流入、热门概念 Top5 全缺失）。

---

## 3. 软失败（topic_status = ok，但关键字段为空）

### 3.1 `valuation_history`（部分字段缺失）
- 相关日志：
  - `stock_a_lg_indicator 不可用，回退到 stock_zh_valuation_baidu`
  - `valuation_history_baidu:ps_ttm: TypeError - 'NoneType' object is not subscriptable`
  - `valuation_history_baidu:dv_ttm: TypeError - 'NoneType' object is not subscriptable`
- 原因判断：
  - 主接口不存在，回退接口可获取 `PE/PB`，但 `PS/股息率` 指标在当前源返回结构不稳定或无数据。
- 缺失字段：
  - `valuation_history.current_ps_ttm = null`
  - `valuation_history.current_dv_ttm = null`

### 3.2 `valuation_vs_industry`（结构成功但值全空）
- 日志显示：
  - `[valuation_vs_industry] fetched successfully: 8 rows`
- 结果现象：
  - `stock_pe / industry_avg_pe / industry_median_pe / stock_pb / industry_avg_pb` 全为 `null`
- 原因判断：
  - 数据表返回成功，但目标列名与解析逻辑不匹配（列名变更或字段映射差异）。

### 3.3 `northbound`（持有状态有，持仓数值缺失）
- 日志显示：
  - `[northbound] fetched successfully: 2767 rows`
- 结果现象：
  - `held = true`，但 `shares_held / market_value / change_pct` 为 `null`
- 原因判断：
  - 代码命中股票成功，但数值列名或披露字段与预期不一致。

---

## 4. 非失败但“无业务数据”

### `earnings_forecast`（topic_status = no_data）
- 日志：
  - `最近 4 个季度均未找到 600519 的业绩预告（API 正常，该股票无预告）`
- 含义：
  - 接口调用成功，但目标股票在最近 4 个季度中无匹配记录，不属于接口异常。

---

## 5. 可交给测试 AI 的用例清单

以下用例用于验证“确实拿不到数据”而非“代码直接崩溃”：

1. `realtime_quote` 连接中断
- 模拟 `stock_zh_a_spot_em` 抛 `ConnectionError/RemoteDisconnected`
- 断言：`topic_status["realtime_quote"] == "failed"` 且 `realtime_quote is None`

2. `financial_indicators` 空表
- 模拟 `stock_financial_analysis_indicator` 返回空 DataFrame
- 断言：`topic_status["financial_indicators"] == "failed"` 且字段为 `None`

3. `sector_flow` 双子接口都失败
- 模拟行业/概念两路接口都抛连接异常
- 断言：`topic_status["sector_flow"] == "failed"` 且 `sector_flow is None`

4. `valuation_history` 回退路径仅部分可用
- 模拟 `stock_a_lg_indicator` 不存在
- 模拟百度接口只返回 `PE/PB`，`PS/DV` 抛异常
- 断言：`topic_status["valuation_history"] == "ok"` 且 `current_ps_ttm/current_dv_ttm is None`

5. `valuation_vs_industry` 返回表但目标列不匹配
- 模拟接口返回 DataFrame，但不含预期列名
- 断言：主题 `ok`，估值字段全为 `None`，`relative_valuation == "数据不足，无法判断"`

6. `northbound` 命中代码但数值列缺失
- 模拟 `代码` 列可命中，数值列缺失
- 断言：`held == true` 且 `shares_held/market_value/change_pct is None`

7. `earnings_forecast` 无业务数据
- 模拟最近 4 季度接口都成功返回但不含目标代码
- 断言：`topic_status["earnings_forecast"] == "no_data"`，`available == false`

---

## 6. 结论
- 本次最核心的“拿不到”是三块硬失败：`realtime_quote`、`financial_indicators`、`sector_flow`。
- 另外三块是“接口有返回但字段映射不到”：`valuation_history`（PS/DV）、`valuation_vs_industry`、`northbound`。
- 建议测试 AI 先按第 5 节建立回归测试，确保这些场景至少稳定产出可解释的 `topic_status + data_errors`。

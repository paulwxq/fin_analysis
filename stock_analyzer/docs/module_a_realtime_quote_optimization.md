# Tech Note: Module A 实时行情接口优化方案

**日期**：2026-02-17  
**状态**：待实施 (Proposed)  
**涉及模块**：Module A (`module_a_akshare.py`)

---

## 1. 背景与问题
当前 `realtime_quote` (Topic 2) 主题使用 `ak.stock_zh_a_spot_em()` 接口。
- **机制**：该接口拉取全市场（5400+ 只股票）的实时快照，然后在本地按代码筛选。
- **痛点**：
  - **数据冗余**：下载数 MB 数据只为取 1 行。
  - **超时风险**：在网络波动或交易所繁忙时，极易触发 60s 超时限制，导致整个 Module A 变慢。
  - **数据精度**：Spot 接口提供的“60日涨跌幅”有时未及时处理除权除息。

## 2. 优化目标
将“全市场扫描”模式改为“单股精准查询”模式，同时提升历史涨跌幅计算的准确性。

## 3. 新方案设计

采用 **双接口组合** 策略替代原有单一大接口：

### 3.1 实时盘口快照 (基础行情)
使用 `ak.stock_bid_ask_em(symbol=...)` 获取毫秒级实时数据。
- **优势**：支持单股查询，响应通常 < 500ms。
- **覆盖字段**：最新价、涨跌幅、成交量、成交额、换手率、量比。

### 3.2 历史区间涨跌幅 (增强计算)
使用 `ak.stock_zh_a_hist(period="daily", start_date="20250101", adjust="qfq")` 获取日线数据。
- **用途**：
  - **年初至今 (YTD)**：`最新收盘 / 年初首日收盘 - 1`
  - **60日涨跌幅**：`最新收盘 / T-60日收盘 - 1`
- **优势**：
  - 基于前复权 (QFQ) 价格计算，彻底消除分红送配导致的计算失真。
  - 数据量极小（仅需拉取当年至今+60天的数据），速度快。

### 3.3 字段去重
- **PE (TTM) / PB**：不再从实时行情接口获取。
- **理由**：Module A 的 Topic 4 (`valuation_history`) 专门负责估值，使用更专业的 `stock_a_lg_indicator` 或 `stock_zh_valuation_baidu` 接口，数据质量更高。此处移除可减少冗余。

## 4. 字段映射与迁移表

| 输出字段 (`RealtimeQuote`) | 旧来源 (`stock_zh_a_spot_em`) | 新来源 | 说明 |
| :--- | :--- | :--- | :--- |
| `price` | 最新价 | `stock_bid_ask_em` ("最新") | |
| `change_pct` | 涨跌幅 | `stock_bid_ask_em` ("涨幅") | |
| `volume` | 成交量 | `stock_bid_ask_em` ("总手") | |
| `turnover` | 成交额 | `stock_bid_ask_em` ("金额") | |
| `turnover_rate` | 换手率 | `stock_bid_ask_em` ("换手") | |
| `volume_ratio` | 量比 | `stock_bid_ask_em` ("量比") | |
| `pe_ttm` | 市盈率-动态 | **移除** | 已由 `valuation_history` 覆盖；此处设为 None |
| `pb` | 市净率 | **移除** | 已由 `valuation_history` 覆盖；此处设为 None |
| `change_60d_pct` | 60日涨跌幅 | `stock_zh_a_hist` (计算) | 更精准 (QFQ) |
| `change_ytd_pct` | 年初至今涨跌幅 | `stock_zh_a_hist` (计算) | 更精准 (QFQ) |

## 5. 预期收益
1.  **稳定性**：彻底解决 Topic 2 的超时问题，成功率预计提升至 99.9%。
2.  **准确性**：YTD 和 60日涨幅基于复权数据，不再受除权干扰，对首席分析师判断趋势更有利。
3.  **速度**：该主题采集耗时预计从 10s-60s 降至 1-2s。

## 6. 实施步骤
1. 修改 `stock_analyzer/module_a_akshare.py`。
2. 重写 `_collect_realtime_quote` 方法。
3. 实现 `_fetch_precise_price_changes` 辅助方法。
4. 验证 Pydantic 模型兼容性（`pe_ttm` 和 `pb` 为 Optional，置空不报错）。

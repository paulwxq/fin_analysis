# 设计文档：Module D 多维数据 Markdown 序列化方案

## 1. 设计动机

### 1.1 现状量化分析

当前系统直接将 Module A/B/C 的 Pydantic 模型（`model_dump()` → `json.dumps`）推入 Module D 提示词。
以实际运行日志（600583 海油工程）为基线，prompt payload 的各区段字符分布如下：

| 区段 | 字符数 | 行数 | 占比 |
|------|--------|------|------|
| `<akshare_data>` (Module A) | 32,566 | 1,519 | **80.7%** |
| `<web_research>` (Module B) | 4,677 | 130 | 11.6% |
| `<technical_analysis>` (Module C) | 2,787 | 44 | 6.9% |
| `<data_quality_report>` | 270 | 12 | 0.7% |
| **总计** | **~40,000** | **~1,710** | — |

### 1.2 核心痛点

1. **Token 冗余**：Module A JSON 占 80.7%，其中 `business_composition` 一个字段就包含 200+ 条记录，
   `"type"` / `"item"` / `"revenue_ratio"` / `"gross_margin"` 四个键名各重复约 200 次。
2. **对比困难**：`financial_indicators` 含 8 期 × 9 字段 = 72 个重复键名的嵌套结构，
   LLM 在长 JSON 中做时间序列趋势对比时注意力容易分散。
3. **阅读直观性差**：JSON 缺乏层级感，无法像专业研报那样通过表格快速定位核心矛盾。

### 1.3 预期收益

- **Token 压缩 ~50-60%**：JSON 语法噪音（引号、括号、重复键名）全部消除
- **推理质量提升**：表格化后趋势对比一目了然（如 ROE 8 期变化、主营结构占比变化）
- **调试友好**：开发者在日志中也能快速理解输入给 LLM 的内容

---

## 2. 核心设计原则

1. **脱水（Dehydration）**：移除系统级/日志级字段，仅保留业务数据（详见 §3）
2. **忠实（Fidelity）**：转换格式但不丢弃业务数据。特例：`business_composition` 裁剪为最近 2 个年度（见 §4.1.15）
3. **语义化（Semantic Formatting）**：
   - **表格化**：财务指标、持仓、估值等序列数据转为 Markdown Table
   - **结构化**：新闻、优势、风险等描述性数据转为层级列表
   - **看板化**：技术指标和核心估值转为"键值面板"
4. **中性呈现**：不在数据区段插入引导性解释文字，避免预判偏见

---

## 3. 脱水字段清单

以下字段从 Markdown 输出中剥离（不影响中间 JSON 文件）。
它们的有效信息已通过 `data_quality_report` 独立提供给 LLM。

### 3.1 Module A (`AKShareData.meta`)

| 字段 | 处置 | 原因 |
|------|------|------|
| `meta.symbol` | 保留 | 用于 Markdown 标题 |
| `meta.name` | 保留 | 用于 Markdown 标题 |
| `meta.query_time` | 剥离 | 系统时间戳，LLM 无需 |
| `meta.data_errors` | 剥离 | 已汇总至 `data_quality_report` |
| `meta.successful_topics` | 剥离 | 已汇总至 `data_quality_report` |
| `meta.topic_status` | 剥离 | 已汇总至 `data_quality_report` |

### 3.2 Module B (`WebResearchResult.meta`)

| 字段 | 处置 | 原因 |
|------|------|------|
| `meta.symbol` | 剥离 | 冗余（标题已有） |
| `meta.name` | 剥离 | 冗余 |
| `meta.search_time` | 剥离 | 系统时间戳 |
| `meta.search_config` | 剥离 | 内部调参信息 |
| `meta.total_learnings` | 剥离 | 已汇总至 `data_quality_report` |
| `meta.total_sources_consulted` | 剥离 | 已汇总至 `data_quality_report` |
| `meta.raw_learnings` | 剥离 | fallback 标志已汇总至 `data_quality_report` |

### 3.3 Module C (`TechnicalAnalysisResult.meta`)

| 字段 | 处置 | 原因 |
|------|------|------|
| `meta.*` | 全部剥离 | `data_quality_report` 已含 confidence 和 warnings |

---

## 4. 转换规则（字段级映射）

### 4.1 Module A：结构化数据仪表盘（重点优化）

> Module A 贡献 80.7% 的 prompt 体积，是本方案的核心收益来源。

#### 4.1.1 `company_info` → 键值面板

```markdown
### 公司概况
- 行业：油服工程
- 上市日期：20020205
- 总市值：303.30 亿元 | 流通市值：303.30 亿元
- 总股本：44.21 亿股 | 流通股：44.21 亿股
```

null 时显示 `—`。

#### 4.1.2 `realtime_quote` → 键值面板

整块为 null 时输出一行说明：

```markdown
### 实时行情
（数据缺失）
```

有数据时：

```markdown
### 实时行情
- 最新价：6.86 | 涨跌幅：2.50% | 换手率：3.12%
- 成交量：xxx | 成交额：xxx | 量比：1.23
- PE(TTM)：15.00 | PB：1.12
- 60日涨跌幅：24.05% | 年初至今：40.29%
```

#### 4.1.3 `financial_indicators` → 横向表格

行=指标，列=报告期（最近 8 期）。百分比字段保留 2 位小数。

```markdown
### 财务指标（近8期）

| 指标 | 2025-09-30 | 2025-06-30 | ... | 2023-12-31 |
|------|-----------|-----------|-----|-----------|
| EPS(元) | 0.36 | 0.25 | ... | 0.37 |
| 每股净资产(元) | 6.10 | 5.99 | ... | 5.61 |
| ROE(%) | 6.27% | 4.12% | ... | 6.67% |
| 毛利率(%) | 14.38% | 16.25% | ... | 10.75% |
| 净利率(%) | 9.34% | 9.93% | ... | 5.30% |
| 营收增长(%) | -13.54% | -15.72% | ... | 4.75% |
| 利润增长(%) | -8.01% | -8.21% | ... | 11.08% |
| 资产负债率(%) | 39.35% | 40.37% | ... | 38.09% |
| 流动比率 | 1.71 | 1.60 | ... | 1.57 |
```

#### 4.1.4 `valuation_history` → 键值面板

```markdown
### 估值历史
- PE(TTM)：15.00 | PB：1.12
- PE历史分位：45.00% | PB历史分位：81.80%
- PS(TTM)：— | 股息率(TTM)：—
- 分位解读：PE历史分位45.0%，处于中等位置；PB历史分位81.8%，处于极高位置（历史顶部区域）
```

#### 4.1.5 `valuation_vs_industry` → 对比表格

```markdown
### 估值-行业对比

| 指标 | 个股 | 行业均值 | 行业中位数 |
|------|------|---------|-----------|
| PE | 15.00 | 61.57 | 40.82 |
| PB | 1.12 | 4.05 | — |

相对估值判断：明显低于行业平均
```

#### 4.1.6 `fund_flow.recent_days` → 日期表格

```markdown
### 个股资金流向（近5日）

| 日期 | 主力净流入(万元) | 占比(%) |
|------|-----------------|---------|
| 2026-02-13 | -8,170.87 | -10.78% |
| 2026-02-12 | 7,556.47 | 5.93% |
| ... | ... | ... |
```

#### 4.1.7 `fund_flow.summary` → 键值对

```markdown
- 近5日主力净流入合计：16,503.81 万元
- 近10日主力净流入合计：23,498.86 万元
- 趋势：近5日主力净流入，近10日整体净流入
```

#### 4.1.8 `sector_flow` → 键值面板 + 概念简表

```markdown
### 板块资金流向
- 所属行业：油服工程 | 行业排名：413
- 行业今日主力净流入：-49,905.56 万元

热门概念 Top5：

| 概念 | 主力净流入(万元) |
|------|-----------------|
| 存储芯片 | 421,506.28 |
| 冷链物流 | 189,640.78 |
| ... | ... |
```

#### 4.1.9 `northbound` → 键值面板

```markdown
### 北向资金
- 是否持有：是
- 持股数量：23,148.12 万股 | 持股市值：126,388.73 万元
- 增减比例：-0.44%
- 备注：北向资金披露规则2024年8月后有变化，数据仅供参考
```

未持有时：`- 是否持有：否`（后续字段省略）

#### 4.1.10 `shareholder_count` → 时间序列表格

```markdown
### 股东户数变动

| 截止日 | 股东户数 | 增减(%) |
|--------|---------|---------|
| 2025-09-30 | 78,886 | -15.77% |
| 2025-06-30 | 93,652 | -3.93% |
| ... | ... | ... |
```

#### 4.1.11 `dividend_history` → 时间序列表格

```markdown
### 分红历史

| 年度 | 累计股息(元/股) | 除权除息日 |
|------|----------------|-----------|
| 2025 | 2.01 | 2025-05-08 |
| 2024 | 1.47 | 2024-06-18 |
| ... | ... | ... |
```

#### 4.1.12 `earnings_forecast` → 条件输出

`available=false` 时：

```markdown
### 业绩预告
（暂无业绩预告数据）
```

`available=true` 时：

```markdown
### 业绩预告
- 报告期：2025-06-30 | 变动类型：略增
- 预告内容：xxx
```

#### 4.1.13 `pledge_ratio` → 键值面板

```markdown
### 股权质押
- 质押比例：0.00% | 风险等级：低
```

#### 4.1.14 `consensus_forecast` → 表格

```markdown
### 一致预期

| 年度 | 机构数 | 归母净利润均值(亿元) | 行业平均(亿元) |
|------|--------|---------------------|---------------|
| 2025 | 6 | 0.53 | 1.62 |
| 2026 | 6 | 0.61 | 1.93 |
| 2027 | 5 | 0.66 | 2.24 |
```

#### 4.1.15 `institutional_holdings` → 简表

```markdown
### 机构持仓

| 类型 | 机构 | 持股比例(%) |
|------|------|-----------|
| 基金 | 南方中证500ETF | 0.75% |
| 全国社保 | 全国社保基金四零二组合 | 0.00% |
```

空列表时：`（无机构持仓数据）`

#### 4.1.16 `business_composition` → 按最近 2 个年度分组

**裁剪规则**：
- 原始数据包含 8 期（对应 `financial_indicators` 的 8 个报告期），约 200+ 条记录
- 只保留最近 **2 个年度的年报数据**（`report_date` 以 `12-31` 结尾的最近 2 期）
- 每个年度按"按产品分类"和"按地区分类"分别输出表格
- 过滤掉 `type` 为空字符串且 `item` 含"平衡项目"的行
- `revenue_ratio` 从小数转为百分比，`gross_margin` 同理

**实现说明**：
- `business_composition` 列表本身没有 `report_date` 字段
- 需要根据 `financial_indicators` 的年报期数（以 `12-31` 结尾）来确定切分点
- 原始数据按报告期顺序排列，每期的记录数不固定
- 采用分组策略：先识别出每期的记录块边界，再取最近 2 个年报期的块

```markdown
### 主营结构（2024年度）

**按产品分类：**

| 项目 | 收入占比 | 毛利率 |
|------|---------|--------|
| 海洋工程总承包项目收入 | 75.39% | — |
| 海洋工程非总承包项目收入 | 16.24% | — |
| 非海洋工程项目收入 | 7.99% | — |
| 其他(补充) | 0.38% | 41.22% |

**按地区分类：**

| 地区 | 收入占比 | 毛利率 |
|------|---------|--------|
| 境内 | 80.70% | 13.04% |
| 境外 | 19.30% | 9.10% |
```

### 4.2 Module B：深度调研简报（轻量改造）

Module B 本身以文本描述为主（仅占 11.6%），改造主要目标是结构化呈现。

#### 4.2.1 `news_summary` → 情感标记列表

```markdown
### 舆情汇总

**正面新闻：**
- [+][高] 海油工程2024年归母净利润同比增长33.38%，海外订单创历史新高 — 2024年，海油工程实现营业收入299.54亿元...（来源：公司年报、券商研报，2025-04-30）
- [+][高] '海葵一号'成功交付... — ...（来源：...，2024-04-26）

**负面新闻：**
- [-][中] 关联交易依赖度上升... — ...（来源：...，2025-04-30）

**中性新闻：**
- [~][中] 公司获多家券商覆盖... — ...（来源：...，2024-03-29）
```

#### 4.2.2 `competitive_advantage` → 段落

```markdown
### 核心竞争力
- 描述：海油工程是国内唯一具备海洋油气工程EPCI全产业链能力的总承包商...
- 护城河类型：技术壁垒 + 规模效应 + 客户资源 + 资质垄断
- 市场地位：亚洲最大海洋能源工程EPCI总承包商...
```

#### 4.2.3 `industry_outlook` → 段落 + 列表

```markdown
### 行业展望（油服工程）
展望：行业前景乐观，进入新一轮景气周期...

关键驱动力：
1. 全球及中国海洋油气资本开支持续增长
2. ...

关键风险：
1. 国际油价波动影响石油公司资本开支节奏
2. ...
```

#### 4.2.4 `risk_events` → 分类列表

```markdown
### 风险事件
- 监管风险：信息不足
- 诉讼风险：近三年未发现行政处罚...
- 管理层风险：信息不足
- 其他风险：公司存在大额对外担保...
```

#### 4.2.5 `analyst_opinions` → 简表

```markdown
### 分析师观点
- 评级分布：买入 2 | 持有 0 | 卖出 0
- 平均目标价：6.87 元

| 券商 | 评级 | 目标价(元) | 日期 |
|------|------|-----------|------|
| 民生证券 | 推荐 | 6.75 | 2024-03-29 |
| 天风证券 | 买入 | 6.59 | 2021-12-31 |
```

#### 4.2.6 `search_confidence`

追加在 Module B 区段末尾：

```markdown
搜索置信度：高
```

### 4.3 Module C：技术面扫描仪（轻量改造）

Module C 仅占 6.9%，本身以文本描述为主。改造目标是更紧凑的结构化呈现。

#### 4.3.1 核心指标面板

```markdown
### 技术面总览
- 评分：7.5/10 | 信号：看多 | 置信度：0.72
```

#### 4.3.2 各分析维度 → 段落

```markdown
### 趋势分析
- 均线排列：多头排列（MA5>MA10>MA20>MA60）
- 价格 vs MA20：收盘价位于MA20上方约25.38%
- 近6月涨幅：24.05% | 近12月涨幅：40.29%
- 趋势判断：海油工程当前呈现典型的中长期上升趋势格局...

### 动量分析
- MACD：MACD位于零轴上方，柱状图放大
- RSI：67.04 — RSI指标当前读数为67.04...
- KDJ：KDJ指标当前呈现中性震荡状态...

### 波动性分析
- 布林位置：价格接近或突破布林上轨
- 布林带宽：布林带开口呈现扩大态势...

### 量价分析
- 量能对比：近3月量能与年内均量接近...
- 量价关系：价涨量缩特征显现...
```

#### 4.3.3 关键支撑/阻力位

```markdown
### 关键价位

| 类型 | 第一位 | 第二位 |
|------|--------|--------|
| 支撑 | **5.18** | **4.76** |
| 阻力 | **7.42** | **7.42** |
```

#### 4.3.4 技术总结

```markdown
### 技术总结
海油工程（600583）月线技术面呈现积极向好格局...
```

### 4.4 Data Quality Report

保持 JSON 格式不变（仅 270 字符，已足够紧凑），继续使用 `<data_quality_report>` XML 标签包裹，
因为 system prompt（`CHIEF_ANALYST_SYSTEM_PROMPT`）中多处引用了该标签名。

---

## 5. 数字格式化规范

| 数据类型 | 原始值示例 | 格式化后 | 规则 |
|----------|-----------|----------|------|
| 百分比字段（名称含 `%` 或 `pct`/`ratio`/`margin`/`growth`） | `14.377411509656` | `14.38%` | 保留 2 位小数 + `%` |
| 比例字段（`revenue_ratio` 等 0-1 范围） | `0.75388` | `75.39%` | × 100 后保留 2 位小数 + `%` |
| 金额（亿元级） | `303.3049` | `303.30` | 保留 2 位小数 |
| 金额（万元级） | `3714368.0` | `371.44` | ÷ 10000 保留 2 位小数，标注万元 |
| EPS / 每股净资产 | `6.103824171722` | `6.10` | 保留 2 位小数 |
| 流动比率 | `1.70812684249` | `1.71` | 保留 2 位小数 |
| null / None | `null` | `—` | em dash |

---

## 6. Prompt 合并模板

```
你现在担任首席分析师的角色。你的任务是整合并分析以下 Markdown 格式的多维数据，
输出一份专业的、具备深度洞察力的投资综合判定报告。

数据来源说明：
1. **结构化财务数据**（Module A）：包含公司基础信息及15个维度的财务与经营数据。
2. **深度调研报告**（Module B）：基于全网搜索的舆情、竞争力、行业前景与风险分析。
3. **技术面分析**（Module C）：基于月线级别的趋势、动量、波动与量价分析。
4. **数据质量报告**：各模块执行质量摘要，请据此调整结论的审慎程度。

---

# 一、结构化财务数据（Module A）

{MARKDOWN_MODULE_A}

---

# 二、深度调研报告（Module B）

{MARKDOWN_MODULE_B}

---

# 三、技术面分析（Module C）

{MARKDOWN_MODULE_C}

---

# 四、数据质量报告

<data_quality_report>
{QUALITY_JSON}
</data_quality_report>
```

**设计要点**：
- 使用 Markdown 一级标题（`#`）分隔四大区段，二级/三级标题留给各模块内部使用
- 不插入"专家解释"或引导性文字，避免预判偏见
- `data_quality_report` 保持 JSON + XML 标签，因 system prompt 中有引用

---

## 7. 实现清单

### 7.1 新建文件：`stock_analyzer/markdown_formatter.py`

```python
"""Markdown formatters for Module A/B/C data serialization."""

from stock_analyzer.module_a_models import AKShareData
from stock_analyzer.models import WebResearchResult
from stock_analyzer.module_c_models import TechnicalAnalysisResult


# ── 公开接口 ──────────────────────────────────────────────

def format_akshare_markdown(data: AKShareData) -> str:
    """将 Module A 的 AKShareData 转为 Markdown 字符串。"""
    ...

def format_web_research_markdown(data: WebResearchResult) -> str:
    """将 Module B 的 WebResearchResult 转为 Markdown 字符串。"""
    ...

def format_technical_markdown(data: TechnicalAnalysisResult) -> str:
    """将 Module C 的 TechnicalAnalysisResult 转为 Markdown 字符串。"""
    ...


# ── 工具函数 ──────────────────────────────────────────────

def _to_table(headers: list[str], rows: list[list[str]]) -> str:
    """生成 Markdown 表格字符串。"""
    ...

def _fmt_pct(value: float | None) -> str:
    """格式化百分比字段：14.377 → '14.38%'，None → '—'"""
    ...

def _fmt_ratio(value: float | None) -> str:
    """格式化比例字段（0-1 范围）：0.75388 → '75.39%'，None → '—'"""
    ...

def _fmt_amount(value: float | None, divisor: float = 1.0) -> str:
    """格式化金额：保留2位小数，None → '—'"""
    ...

def _fmt_val(value: object) -> str:
    """通用 null-safe 格式化：None → '—'，float 保留2位小数"""
    ...
```

### 7.2 修改文件：`stock_analyzer/module_d_chief.py`

修改 `_build_chief_user_message`：

```python
# 替换前（4 次 json.dumps）
akshare_json = json.dumps(context["akshare_data_full"], ...)
web_json = json.dumps(context["web_research_full"], ...)
...

# 替换后（3 次 format_*_markdown + 1 次 json.dumps）
from stock_analyzer.markdown_formatter import (
    format_akshare_markdown,
    format_web_research_markdown,
    format_technical_markdown,
)

akshare_md = format_akshare_markdown(akshare_data)
web_md = format_web_research_markdown(web_research)
tech_md = format_technical_markdown(technical_analysis)
quality_json = json.dumps(context["data_quality_report"], ...)
```

函数签名变更：`_build_chief_user_message` 需接收原始 Pydantic 模型而非仅 context dict。

### 7.3 修改文件：`stock_analyzer/prompts.py`

`CHIEF_ANALYST_SYSTEM_PROMPT` 第一行：
- 旧：`你将收到模块A/模块B/模块C的全量原始数据`
- 新：`你将收到模块A/模块B/模块C的结构化 Markdown 格式数据`

### 7.4 新建测试：`stock_analyzer/tests/test_markdown_formatter.py`

覆盖项：
- `format_akshare_markdown`：含预期表头、null 值显示 `—`、百分比格式正确
- `format_web_research_markdown`：含 `[+]`/`[-]`/`[~]` 标记
- `format_technical_markdown`：含评分/信号/置信度面板
- `_fmt_pct` / `_fmt_ratio` / `_fmt_val`：边界值测试
- `business_composition` 裁剪：验证只输出最近 2 个年度
- 全 null 场景：所有可选字段为 None 时不崩溃

---

## 8. 不变项

以下内容本方案不修改：

- `build_chief_context()` 仍构建 dict（供中间 JSON 文件使用）
- `_strip_noise_fields()` 仍用于中间 JSON 输出
- `_save_intermediate_results()` 仍保存 JSON 格式
- `data_quality_report` 仍以 JSON 输出（仅 270 字符，无需转 Markdown）
- `CHIEF_ANALYST_SYSTEM_PROMPT` 的输出 JSON 结构要求、评分维度、否决规则等均不变

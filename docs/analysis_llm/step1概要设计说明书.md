# 股票推荐系统 Step 1 概要设计说明书

## 文档版本信息

| 版本 | 日期 | 更新说明 |
|------|------|----------|
| v1.1 | 2026-02-02 | 基于 HTML 设计文档生成，包含并发编排与重试机制详情 |

## 1. 系统概述

### 1.1 核心目标
Step 1 是数据收集阶段，旨在通过并行执行多个专家 Agent，收集高质量的原始数据，包括公司新闻、板块热度分析和月 K 线技术评估。

**关键原则：**
- **只负责收集与格式清洗**：确保数据格式正确、字段完整。
- **不进行业务决策**：数据的利好/利空矛盾将被保留，留给 Step 2 进行综合研判。
- **高效并发**：利用 MAF 框架的并发能力提升响应速度。

### 1.2 技术架构
- **框架**：Microsoft Agent Framework (Python 1.0.0b260130)
- **编排模式**：`ConcurrentBuilder` (并行执行)
- **核心组件**：
  - **Executor Unit**：封装 "Agent -> Checker -> Retry" 的原子执行单元
  - **SimpleMerger**：负责无损合并并行任务的结果

---

## 2. 详细架构设计

### 2.1 整体流程

系统接收股票代码作为输入，启动三个并行的执行单元，最终汇总输出。

```mermaid
graph TD
    Input[输入：股票代码 (如 TSLA)] --> Parallel{ConcurrentBuilder 并行执行}
    
    Parallel --> Unit1[单元1: NewsSearchUnit]
    Parallel --> Unit2[单元2: SectorAnalysisUnit]
    Parallel --> Unit3[单元3: KLineAnalysisUnit]
    
    subgraph Unit1 [NewsSearchUnit]
        A1[Agent 1: 新闻搜索] --> C1[Checker 1: 格式检查]
        C1 -- 失败 --> A1
        C1 -- 通过 --> Out1[输出新闻数据]
    end
    
    subgraph Unit2 [SectorAnalysisUnit]
        A2[Agent 2: 板块分析] --> C2[Checker 2: 格式检查]
        C2 -- 失败 --> A2
        C2 -- 通过 --> Out2[输出板块数据]
    end
    
    subgraph Unit3 [KLineAnalysisUnit]
        A3[Agent 3: K线分析] --> C3[Checker 3: 格式检查]
        C3 -- 失败 --> A3
        C3 -- 通过 --> Out3[输出K线数据]
    end
    
    Out1 --> Merger[SimpleMerger: 数据合并]
    Out2 --> Merger
    Out3 --> Merger
    
    Merger --> Output[输出：Step 2 输入数据]
```

### 2.2 核心特性
1.  **真正的并行执行**：三个单元互不阻塞，相比串行执行可提升整体响应速度。
2.  **独立的重试机制**：每个单元内部维护独立的重试循环（默认 **3次**）。当 Agent 执行失败或 Checker 不通过时会触发重试。
3.  **职责单一的 Checker**：Checker 仅充当"质检员"，检查数据规格（JSON 格式、字段约束、数值范围），严禁越俎代庖进行业务逻辑判断。

---

## 3. 执行单元详细设计

### 3.1 单元 1: NewsSearchUnit (新闻搜索)

**Agent 1 职责**：搜索最近 12 个月的财经新闻，提取摘要并进行情感分类。

**特殊约束与配置**：
*   **数量限制**：
    *   正面新闻 (`positive_news`)：最多 **5** 条。
    *   负面新闻 (`negative_news`)：最多 **5** 条。
    *   *注*：若搜索结果过多，Agent 需自行筛选最具代表性的新闻。
*   **内容处理**：必须生成 **摘要**，严禁直接返回长篇原文；每条新闻字符长度 **≤ 500**。
*   **综合摘要**：生成一段 `news_summary` 提供整体视图。
*   **情感打分**：`sentiment_score` 范围为 -1 (极负) 到 1 (极正)。

**Checker 1 检查项**：
- ✅ JSON 格式合法。
- ✅ 必需字段 (`positive_news`, `negative_news`, `news_summary`) 存在。
- ✅ 新闻列表长度均 ≤ 5。
- ✅ 每条新闻字符长度 ≤ 500。
- ✅ `sentiment_score` 在 [-1, 1] 之间。
- ❌ **不检查**：新闻内容的真实性、与板块分析的一致性。

### 3.2 单元 2: SectorAnalysisUnit (板块分析)

**Agent 2 职责**：识别股票所属板块，分析板块热度与趋势。

**数据字段**：
*   `sector_name`: 板块名称 (如 "新能源汽车")。
*   `heat_index`: 热度指数 (0-100)。
*   `trend`: 趋势描述 (如 "上升", "震荡", "下降")。
*   `capital_flow`: 资金流向描述。

**Checker 2 检查项**：
- ✅ JSON 格式合法。
- ✅ `heat_index` 在 [0, 100] 之间。
- ✅ 必需字段完整 (需包含 `capital_flow`)。
- ❌ **不检查**：热度数值是否"合理"。

### 3.3 单元 3: KLineAnalysisUnit (K线分析)

**Agent 3 职责**：基于 **月 K 线** 数据进行技术面分析，给出操作建议。**注意：必须明确分析的是月线级别数据。**

**数据字段**：
*   `technical_indicators`: 技术指标对象 (MACD, RSI, KDJ 等)。
*   `support_level`: 支撑位价格。
*   `resistance_level`: 阻力位价格。
*   `trend_analysis`: 趋势分析文本。
*   `buy_suggestion`: 购买建议 (枚举值: `强烈买入`, `买入`, `持有`, `卖出`, `强烈卖出`)。

**Checker 3 检查项**：
- ✅ JSON 格式合法。
- ✅ 关键价格字段为数值类型。
- ✅ `buy_suggestion` 必须为以下值之一: `强烈买入`, `买入`, `持有`, `卖出`, `强烈卖出`。
- ❌ **不检查**：技术分析结论是否与基本面矛盾。

---

## 4. 数据接口定义

### 4.1 输入数据
```json
{
  "stock_code": "TSLA"
}
```

### 4.2 输出数据 (Step 2 的输入)
**说明：以下所有字段均为必选项。**
```json
{
  "timestamp": "2026-02-02T10:30:00Z",
  "news": {
    "stock_code": "TSLA",
    "positive_news": [
      "Q3交付量达43.5万辆超预期，同比增长27%...",
      "上海超级工厂二期项目顺利投产..."
    ],
    "negative_news": [
      "CEO马斯克因社交媒体言论引发争议...",
      "因零部件供应问题，部分订单交付延期..."
    ],
    "news_summary": "特斯拉Q3表现强劲...但面临舆论和供应链压力...",
    "sentiment_score": 0.5
  },
  "sector": {
    "stock_code": "TSLA",
    "sector_name": "新能源汽车",
    "heat_index": 78.5,
    "trend": "上升",
    "capital_flow": "大额资金持续流入..."
  },
  "kline": {
    "stock_code": "TSLA",
    "technical_indicators": { "MACD": 0.35, "RSI": 62.8 },
    "support_level": 220.0,
    "resistance_level": 265.0,
    "trend_analysis": "短期上升趋势明确...",
    "buy_suggestion": "强烈买入"
  }
}
```

### 4.3 字段说明（必选）

| 字段 | 含义 |
|------|------|
| `news_summary` | 正/负新闻的整体概括摘要，提供全局视角。 |
| `sentiment_score` | 新闻整体情绪得分，范围 -1 到 1，用于量化情绪倾向。 |
| `sector_name` | 股票所属板块名称，用于建立行业背景。 |
| `trend` | 板块趋势方向（如“上升/震荡/下降”）。 |
| `capital_flow` | 板块资金流向的描述性摘要（流入/流出/中性等）。 |
| `technical_indicators` | 月 K 线技术指标集合（如 MACD/RSI/KDJ 等），用于量化技术面信号。 |
| `support_level` | 技术分析中的支撑位价格。 |
| `resistance_level` | 技术分析中的阻力位价格。 |
| `timestamp` | Step 1 输出时间戳（建议 ISO 8601，UTC）。 |

---

## 5. 配置参数说明

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `max_retries` | 3 | 每个单元内部“Agent → Checker”循环的最大重试次数（含 Checker 不通过或 Agent 失败）。超过次数将抛出异常。 |
| `news_limit_pos` | 5 | 正面新闻最大条数。 |
| `news_limit_neg` | 5 | 负面新闻最大条数。 |
| `news_item_max_chars` | 800 | 每条新闻字符长度上限。 |

## 6. 异常处理策略

1.  **重试失败**：若某单元在 `max_retries` 次尝试后仍无法通过 Checker，该单元将抛出异常。
2.  **整体策略（定论）**：
    *   **严格模式** (默认)：任一单元最终失败，则 Step 1 整体标记为失败，不传递残缺数据给 Step 2。
    *   **降级模式** (可选配置)：允许部分单元失败，失败字段标记为 `null`，Step 2 根据现有数据继续分析并注明数据不完整。

---

*文档生成时间：2026-02-02*

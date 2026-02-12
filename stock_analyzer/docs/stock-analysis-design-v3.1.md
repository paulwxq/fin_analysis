# A股智能投研系统 — 概要设计 V3

## 一、项目概述

### 1.1 目标

对 A 股个股进行多维度投资价值分析，输出评分和投资建议。

**输入：** 股票代码 + 股票名称

**输出：**
- 总评分：0~10 分（首席分析师综合给出）
- 分项评分：各维度 0~10 分
- 分析报告：1000字以内
- 投资建议：买入/持有/卖出（1个月、6个月、1年）

### 1.2 技术栈

| 组件 | 选型 |
|------|------|
| 编排框架 | Microsoft Agent Framework `1.0.0b260130` |
| Python | 3.12.x |
| 依赖管理 | uv |
| 金融数据 | AKShare |
| 技术指标 | pandas-ta |
| LLM | GPT-4o / DeepSeek |

---

## 二、核心设计思路

### 2.1 三模块架构

整个系统分为 **三个数据准备模块** + **一个AI综合判定模块**：

```
┌─────────────────────────────────────────────────────────┐
│                     数据准备阶段（并行）                   │
│                                                         │
│  模块A：AKShare数据采集        → akshare_data.json       │
│  （纯代码，不需要AI）                                     │
│                                                         │
│  模块B：网络搜索与摘要          → web_research.json       │
│  （Agent + 搜索工具，多轮深度搜索）                       │
│                                                         │
│  模块C：月K线技术分析           → technical_analysis.json │
│  （Agent + pandas-ta，数值推理）                         │
│                                                         │
└──────────────────────┬──────────────────────────────────┘
                       │ 三份JSON合并
                       ▼
┌─────────────────────────────────────────────────────────┐
│  模块D：首席分析师（Agent）                               │
│  • 审阅三份报告                                          │
│  • 独立给出最终评分 0~10                                  │
│  • 撰写1000字以内投资建议                                 │
│  • 给出1月/6月/1年投资建议                                │
│                                                         │
│  输出 → final_report.json                               │
└─────────────────────────────────────────────────────────┘
```

### 2.2 为什么这样设计

| 设计决策 | 理由 |
|---------|------|
| AKShare数据不经过AI | AKShare返回的是结构化数据，拼接即可，不需要AI理解和总结，省token省钱 |
| 网络搜索单独模块 | 搜索需要多轮迭代（广度+深度），和AKShare的一次性调用逻辑完全不同 |
| 月K线单独模块 | 技术分析需要先计算指标再让AI推理，是"计算+推理"的混合流程 |
| 最终只用一个首席分析师 | 减少AI调用次数，所有原始数据已经准备好，一个强力模型足以综合判断 |

---

## 三、模块A：AKShare 数据采集

### 3.1 设计原则

- **纯Python代码**，不涉及AI/Agent
- 调用AKShare函数获取数据，整理后写入JSON文件
- 每个数据主题放在JSON的一个顶层key下
- 需要处理AKShare的各种异常（接口不可用、数据为空等）
- 需要注意AKShare不同函数的**股票代码格式不一致**问题

### 3.2 AKShare 股票代码格式速查

> ⚠️ 这是AKShare最大的坑之一，不同函数要求的代码格式不同：

| 格式 | 示例 | 使用的函数 |
|------|------|-----------|
| 纯6位数字 | `"000001"` | `stock_zh_a_hist`, `stock_individual_info_em`, `stock_news_em` |
| 小写前缀 | `"sh600519"` | `stock_history_dividend` |
| 大写前缀 | `"SZ000001"` | `stock_zh_valuation_comparison_em` |
| 代码+市场参数 | `stock="000001"`, `market="sz"` | `stock_individual_fund_flow` |

建议封装一个统一的代码转换工具函数：

```python
def format_symbol(code: str, style: str) -> str:
    """
    统一股票代码格式转换
    code: 纯6位数字，如 "000001"
    style: "bare" / "lower" / "upper"
    """
    prefix = "sh" if code.startswith("6") else "sz"
    if style == "bare":
        return code
    elif style == "lower":
        return f"{prefix}{code}"
    elif style == "upper":
        return f"{prefix.upper()}{code}"
    return code

def get_market(code: str) -> str:
    """返回市场标识：sh 或 sz"""
    return "sh" if code.startswith("6") else "sz"
```

### 3.3 数据采集清单

以下是需要从AKShare获取的全部数据，按主题分组：

#### 主题1：公司基本信息

```python
# 函数：ak.stock_individual_info_em(symbol="000001")
# 入参：纯6位代码
# 返回：DataFrame，两列 (item, value)
# 内容：总市值、流通市值、行业、上市时间、总股本、流通股等
```

#### 主题2：实时行情快照

```python
# 函数：ak.stock_zh_a_spot_em()
# 入参：无参数（返回全市场数据，需自行筛选）
# 返回：DataFrame，含 代码/名称/最新价/涨跌幅/成交量/成交额/
#       市盈率-动态/市净率/总市值/流通市值/换手率/量比/60日涨跌幅/年初至今涨跌幅
# 注意：该函数返回全部5000+只股票，需按代码过滤
```

#### 主题3：财务分析指标

```python
# 函数：ak.stock_financial_analysis_indicator(stock="000001")
# 入参：纯6位代码（参数名是 stock，不是 symbol）
# 返回：DataFrame，65+列财务指标，按报告期排列
# 内容：每股收益、每股净资产、ROE、毛利率、净利率、
#       营收增长率、净利润增长率、资产负债率、流动比率等
# 建议：只取最近4-8期数据，避免数据量过大
```

#### 主题4：估值历史数据（用于计算历史分位数）

```python
# 函数：ak.stock_a_lg_indicator(stock="000001")
# 入参：纯6位代码（参数名是 stock）
# 返回：DataFrame，英文列名：trade_date, pe, pe_ttm, pb, ps, ps_ttm, 
#       dv_ratio, dv_ttm, total_mv
# 注意：这是少数用英文列名的函数
# 用途：计算当前PE/PB处于历史什么分位数
```

#### 主题5：行业估值对比

```python
# 函数：ak.stock_zh_valuation_comparison_em(symbol="SZ000001")
# 入参：大写前缀代码
# 返回：DataFrame，含该股票PE/PB/PS与行业平均、中位数的对比
```

#### 主题6：个股资金流向

```python
# 函数：ak.stock_individual_fund_flow(stock="000001", market="sz")
# 入参：纯6位代码 + 市场参数
# 返回：DataFrame，最近约100个交易日的资金流向
# 内容：主力净流入、超大单、大单、中单、小单的净流入金额和比例
# 注意：market参数必须匹配，6开头用"sh"，0/3开头用"sz"
```

#### 主题7：板块资金流向

```python
# 函数：ak.stock_board_industry_fund_flow_rank_em(indicator="今日")
# 入参：indicator 可选 "今日" / "5日" / "10日"
# 返回：DataFrame，全部行业板块按资金流向排名

# 函数：ak.stock_board_concept_fund_flow_rank_em(indicator="今日")
# 入参：同上
# 返回：DataFrame，全部概念板块按资金流向排名
```

#### 主题8：北向资金持仓

```python
# 函数：ak.stock_hsgt_hold_stock_em(market="北向", indicator="今日排行")
# 入参：market="北向"/"沪股通"/"深股通", indicator="今日排行"~"年排行"
# 返回：DataFrame，北向资金个股持仓排名
# ⚠️ 注意：2024年8月起，北向资金个股披露规则有变，数据可能不完整
```

#### 主题9：股东户数

```python
# 函数：ak.stock_zh_a_gdhs_detail_em(symbol="000001")
# 入参：纯6位代码
# 返回：DataFrame，历史股东户数变化
# 用途：判断筹码集中度趋势
```

#### 主题10：分红历史

```python
# 函数：ak.stock_history_dividend(symbol="sh600519", indicator="分红")
# 入参：小写前缀代码，indicator="分红"/"配股"
# 返回：DataFrame，历史分红记录
```

#### 主题11：业绩预告

```python
# 函数：ak.stock_yjyg_em(date="20231231")
# 入参：日期，格式 YYYYMMDD，必须是季度末日期
# 返回：DataFrame，全市场业绩预告
# 注意：返回全市场数据，需自行筛选目标股票
```

#### 主题12：股权质押

```python
# 函数：ak.stock_gpzy_pledge_ratio_em()
# 入参：无参数（返回全市场数据）
# 返回：DataFrame，全部上市公司的质押比例
# 注意：返回全市场数据，需自行筛选
```

### 3.4 输出JSON Schema

```json
{
  "meta": {
    "symbol": "000001",
    "name": "平安银行",
    "query_time": "2025-02-06T10:30:00",
    "data_errors": []
  },
  
  "company_info": {
    "industry": "银行",
    "listing_date": "1991-04-03",
    "total_market_cap": 2156.8,
    "circulating_market_cap": 2156.8,
    "total_shares": 19405.9,
    "circulating_shares": 19405.9
  },
  
  "realtime_quote": {
    "price": 11.12,
    "change_pct": 1.28,
    "volume": 58923100,
    "turnover": 652830000,
    "pe_ttm": 5.23,
    "pb": 0.56,
    "turnover_rate": 0.30,
    "volume_ratio": 1.15,
    "change_60d_pct": 8.5,
    "change_ytd_pct": 12.3
  },
  
  "financial_indicators": [
    {
      "report_date": "2024-09-30",
      "eps": 1.58,
      "net_asset_per_share": 19.82,
      "roe": 11.23,
      "gross_margin": null,
      "net_margin": 35.6,
      "revenue_growth": 8.5,
      "profit_growth": 2.3,
      "debt_ratio": 92.1,
      "current_ratio": null
    }
  ],
  
  "valuation_history": {
    "current_pe_ttm": 5.23,
    "current_pb": 0.56,
    "pe_percentile": 23.5,
    "pb_percentile": 12.8,
    "current_ps_ttm": 1.85,
    "current_dv_ttm": 5.2,
    "history_summary": "PE历史分位23.5%，处于偏低位置"
  },
  
  "valuation_vs_industry": {
    "stock_pe": 5.23,
    "industry_avg_pe": 5.85,
    "industry_median_pe": 5.12,
    "stock_pb": 0.56,
    "industry_avg_pb": 0.62,
    "relative_valuation": "略低于行业平均"
  },
  
  "fund_flow": {
    "recent_5d": [
      {
        "date": "2025-02-05",
        "main_net_inflow": -2356.8,
        "main_net_inflow_pct": -3.21
      }
    ],
    "summary": {
      "main_net_inflow_5d_total": -8523.5,
      "main_net_inflow_10d_total": 3256.2,
      "trend": "近5日主力净流出，但近10日整体小幅净流入"
    }
  },
  
  "sector_flow": {
    "industry_name": "银行",
    "industry_rank": 15,
    "industry_net_inflow_today": -125600,
    "concept_boards": ["沪深300", "MSCI中国", "上证50"],
    "hot_concepts_top5": []
  },
  
  "northbound": {
    "held": true,
    "shares_held": 125600,
    "market_value": 1396672,
    "change_pct": -2.3,
    "note": "北向资金披露规则2024年8月后有变化，数据仅供参考"
  },
  
  "shareholder_count": [
    {
      "date": "2024-09-30",
      "count": 685234,
      "change_pct": -3.2
    },
    {
      "date": "2024-06-30",
      "count": 707902,
      "change_pct": -1.5
    }
  ],
  
  "dividend_history": [
    {
      "year": "2023",
      "dividend_per_share": 0.582,
      "ex_date": "2024-07-11"
    }
  ],
  
  "earnings_forecast": {
    "latest_period": "2024-12-31",
    "forecast_type": "略增",
    "forecast_range": "净利润增长 0%~15%",
    "available": true
  },
  
  "pledge_ratio": {
    "ratio_pct": 0.85,
    "pledged_shares": 16500,
    "risk_level": "低"
  }
}
```

### 3.5 异常处理策略

```python
import akshare as ak
import json
from typing import Any

class AKShareCollector:
    """AKShare 数据采集器，带统一异常处理"""
    
    def __init__(self, symbol: str, name: str):
        self.symbol = symbol
        self.name = name
        self.errors: list[str] = []
        self.data: dict[str, Any] = {}
    
    def safe_call(self, key: str, func, *args, **kwargs) -> Any:
        """
        安全调用AKShare函数，失败时记录错误但不中断流程
        """
        try:
            df = func(*args, **kwargs)
            if df is None or df.empty:
                self.errors.append(f"{key}: 返回数据为空")
                return None
            return df
        except Exception as e:
            self.errors.append(f"{key}: {type(e).__name__} - {str(e)[:100]}")
            return None
    
    def collect_all(self) -> dict:
        """采集全部数据，返回完整JSON"""
        
        # 主题1：公司基本信息
        df = self.safe_call(
            "company_info",
            ak.stock_individual_info_em,
            symbol=self.symbol
        )
        if df is not None:
            self.data["company_info"] = self._parse_company_info(df)
        
        # 主题2：实时行情（从全市场数据中筛选）
        df = self.safe_call(
            "realtime_quote",
            ak.stock_zh_a_spot_em
        )
        if df is not None:
            row = df[df["代码"] == self.symbol]
            if not row.empty:
                self.data["realtime_quote"] = self._parse_quote(row.iloc[0])
        
        # ... 其他主题类似 ...
        
        # 组装最终JSON
        return {
            "meta": {
                "symbol": self.symbol,
                "name": self.name,
                "query_time": datetime.now().isoformat(),
                "data_errors": self.errors,
            },
            **self.data,
        }
```

### 3.6 关于AKShare的注意事项

| 注意事项 | 说明 |
|---------|------|
| 频率限制 | AKShare底层是爬虫，东方财富等网站会封IP。建议每次调用间隔3-5秒 |
| 接口不稳定 | 接口经常因数据源网站改版而失效，需要及时更新AKShare版本 |
| 全市场返回 | 部分函数（行情快照、质押比例、业绩预告）返回全市场数据，需自行过滤 |
| 列名为中文 | 绝大多数函数返回中文列名，代码中需要用中文字符串索引 |
| 日期格式 | 大多数函数用 `"YYYYMMDD"` 格式，少数用 `"YYYY-MM-DD"` |
| 建议串行调用 | 不要并行调用多个AKShare函数，容易触发封IP |

---

## 四、模块B：网络搜索与摘要（Deep Research）

### 4.1 设计原则

- 采用 **Deep Research 递归搜索**模式：对每个搜索主题执行 `breadth=3, depth=3` 的深度研究
- 搜索工具使用 **Tavily Search API**（已配置在项目依赖中）
- 核心思路：**先广度发散，再深度聚焦，逐层累积知识**
- 每层搜索自动提取 learnings（知识点）和 follow-up questions（追问方向）
- 下一层搜索基于上一层的 learnings 生成更精准的查询
- breadth 逐层自动减半（`max(1, breadth // 2)`），形成倒金字塔收拢结构
- 所有主题的研究结果最终合并、去重，由 LLM 生成结构化的摘要报告

### 4.2 搜索主题规划

需要通过网络深度搜索获取的信息（AKShare无法覆盖的），共 **5 个主题**，每个主题独立执行 Deep Research：

| 主题ID | 搜索主题 | 研究目标 | 初始搜索词示例 |
|--------|---------|---------|---------------|
| T1 | 近期重大新闻 | 了解近期影响股价的事件（正面+负面） | `"{公司名} 最新消息 2025"` |
| T2 | 公司竞争优势 | 了解护城河、核心竞争力、市场地位 | `"{公司名} 核心竞争力 行业地位"` |
| T3 | 行业前景 | 了解所在行业的发展趋势和政策环境 | `"{行业名} 行业前景 2025"` |
| T4 | 风险事件 | 了解潜在的负面信息、监管和诉讼 | `"{公司名} 风险 处罚 诉讼"` |
| T5 | 机构观点 | 了解券商/基金的评级和目标价 | `"{公司名} 研报 评级 目标价"` |

### 4.3 Deep Research 递归搜索策略

#### 4.3.1 核心递归机制

每个搜索主题独立执行以下递归流程（`breadth=3, depth=3`）：

```python
async def deep_research(
    query: str,
    breadth: int,
    depth: int,
    learnings: list[str] = [],
    visited_urls: list[str] = [],
) -> ResearchResult:
    """
    递归深度搜索：
    1. 根据当前 query + 已有 learnings，由 LLM 生成 breadth 个搜索查询
    2. 并行调用 Tavily 执行搜索
    3. 从搜索结果中提取 learnings 和 follow-up questions
    4. 如果 depth > 1，则递归调用自身（breadth 减半，depth 减1）
    5. 所有分支的 learnings 合并去重后返回
    """
    # Step 1: LLM 生成搜索查询（数量 = breadth）
    serp_queries = await generate_serp_queries(
        query=query,
        num_queries=breadth,
        learnings=learnings,
    )

    all_learnings = list(learnings)
    all_urls = list(visited_urls)

    # Step 2: 并行执行所有查询
    for serp_query in serp_queries:
        # 2a. 调用 Tavily Search
        result = await tavily_search(serp_query.query)

        # 2b. LLM 提取知识点和追问方向
        processed = await process_serp_result(
            query=serp_query.query,
            search_results=result,
        )
        all_learnings.extend(processed.learnings)
        all_urls.extend(processed.urls)

        # Step 3: 判断是否继续深入
        new_depth = depth - 1
        new_breadth = max(1, breadth // 2)

        if new_depth > 0:
            # Step 4: 递归 — 基于 follow-up questions 继续深入
            next_query = (
                f"Previous research goal: {serp_query.research_goal}\n"
                f"Follow-up directions:\n"
                + "\n".join(f"- {q}" for q in processed.follow_up_questions)
            )
            deeper_result = await deep_research(
                query=next_query,
                breadth=new_breadth,
                depth=new_depth,
                learnings=all_learnings,
                visited_urls=all_urls,
            )
            all_learnings = deeper_result.learnings
            all_urls = deeper_result.visited_urls

    # Step 5: 合并去重
    return ResearchResult(
        learnings=list(set(all_learnings)),
        visited_urls=list(set(all_urls)),
    )
```

#### 4.3.2 Breadth 递减与搜索规模

| 轮次 | depth | breadth | 每分支查询数 | 该轮总查询数 | 累积 learnings（估算）|
|------|-------|---------|------------|------------|---------------------|
| 第1轮 | 3 | 3 | 3 | 3 | ~9 |
| 第2轮 | 2 | 1 | 1 | 3（3个分支各1个） | ~18 |
| 第3轮 | 1 | 1 | 1 | 3（3个分支各1个） | ~27 |
| **合计** | — | — | — | **~9次 Tavily 调用** | **去重后 ~20-25** |

**单个主题**约 9 次 Tavily 搜索调用，**5 个主题总计约 45 次调用**。

#### 4.3.3 每轮的提示词演进

Deep Research 的核心优势在于**提示词的动态演进**，无需预设多个模板：

**第1轮（无历史 learnings）— 广度发散：**

```
请为以下研究主题生成 3 个搜索查询。

<topic>平安银行 近期重大新闻 正面和负面事件</topic>
```

**第2轮（带累积 learnings）— 深度聚焦：**

```
请为以下研究主题生成 1 个更精准的搜索查询。

<topic>
Previous research goal: 了解平安银行近期影响股价的重大事件
Follow-up directions:
- 平安银行2024年年报具体盈利数据？
- 平安银行零售业务转型最新进展？
- 平安银行不良贷款率变化趋势？
</topic>

以下是前几轮研究中已获得的知识点，请据此生成更有针对性的查询：
<learnings>
- 平安银行2024年净利润同比增长2.1%，营收1600亿元
- 零售AUM突破4万亿，同比增长12%
- 2024Q3不良贷款率1.06%，环比下降2BP
</learnings>
```

**第3轮（带更多 learnings）— 精准验证：**

```
<topic>
Previous research goal: 深入了解平安银行不良贷款率变化趋势
Follow-up directions:
- 平安银行房地产贷款敞口具体数据？
- 与招商银行不良率对比？
</topic>

<learnings>
... 共约18条累积知识点 ...
</learnings>
```

### 4.4 Tavily Search 工具配置

```python
from tavily import AsyncTavilyClient

tavily_client = AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

async def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """
    调用 Tavily Search API 执行搜索
    
    Args:
        query: 搜索查询词
        max_results: 每次搜索返回的最大结果数
    
    Returns:
        搜索结果列表，每项包含 title, url, content
    
    Tavily 优势：
    - 返回结构化的网页内容摘要，无需额外爬取
    - 支持 search_depth="advanced" 获取更详细内容
    - 原生支持异步调用，适合并发场景
    """
    response = await tavily_client.search(
        query=query,
        max_results=max_results,
        search_depth="advanced",    # 获取更详细的内容
        include_answer=False,       # 不需要 Tavily 生成答案
        include_raw_content=False,  # 不需要原始 HTML
    )
    return response.get("results", [])
```

### 4.5 LLM 辅助函数设计

#### 4.5.1 生成搜索查询

```python
async def generate_serp_queries(
    query: str,
    num_queries: int,
    learnings: list[str] = [],
) -> list[SerpQuery]:
    """
    由 LLM 根据研究主题和已有知识，生成搜索查询
    
    输入：研究主题 + 已有 learnings
    输出：num_queries 个搜索查询（含 query 和 research_goal）
    """
    prompt = f"请为以下研究主题生成 {num_queries} 个搜索查询。\n\n"
    prompt += f"<topic>{query}</topic>\n"
    
    if learnings:
        prompt += "\n以下是前几轮研究中已获得的知识点，请据此生成更有针对性的查询：\n"
        prompt += "<learnings>\n"
        for l in learnings:
            prompt += f"- {l}\n"
        prompt += "</learnings>\n"
    
    prompt += (
        "\n要求：\n"
        "- 查询应具体且有针对性，适合搜索引擎\n"
        "- 如果有已知知识点，应避免重复搜索已知信息\n"
        "- 每个查询附带 research_goal 说明研究目的\n"
    )
    
    # 使用结构化输出
    result = await llm_call(prompt, response_format=SerpQueryList)
    return result.queries


class SerpQuery(BaseModel):
    """单个搜索查询"""
    query: str = Field(description="搜索引擎查询词")
    research_goal: str = Field(description="该查询的研究目标和期望发现")


class SerpQueryList(BaseModel):
    """搜索查询列表"""
    queries: list[SerpQuery]
```

#### 4.5.2 提取知识点

```python
async def process_serp_result(
    query: str,
    search_results: list[dict],
) -> ProcessedResult:
    """
    由 LLM 从 Tavily 搜索结果中提取结构化知识点和追问方向
    
    输入：搜索查询 + Tavily 返回的搜索结果
    输出：learnings（知识点列表）+ follow_up_questions（追问方向）
    """
    # 拼接搜索结果内容
    contents = "\n\n".join(
        f"<source url=\"{r['url']}\">\n{r['content']}\n</source>"
        for r in search_results
        if r.get("content")
    )
    
    prompt = (
        f"以下是针对查询 <query>{query}</query> 的搜索结果。\n"
        f"请从中提取关键知识点（learnings）和值得追问的方向。\n\n"
        f"<search_results>\n{contents}\n</search_results>\n\n"
        f"要求：\n"
        f"- learnings 应信息密集，包含具体的实体、数字、日期\n"
        f"- learnings 之间不应重复\n"
        f"- follow_up_questions 应指向当前结果未能充分覆盖的方向\n"
        f"- 最多提取 5 个 learnings 和 3 个 follow_up_questions\n"
    )
    
    result = await llm_call(prompt, response_format=ProcessedResult)
    return result


class ProcessedResult(BaseModel):
    """搜索结果处理后的输出"""
    learnings: list[str] = Field(description="从搜索结果中提取的知识点")
    follow_up_questions: list[str] = Field(description="值得继续深入的追问方向")
    urls: list[str] = Field(default_factory=list, description="来源URL列表")
```

### 4.6 整体执行流程

```
5个搜索主题（并行执行 Deep Research）
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  T1: 近期新闻 ──→ deep_research(breadth=3, depth=3)     │
│  T2: 竞争优势 ──→ deep_research(breadth=3, depth=3)     │
│  T3: 行业前景 ──→ deep_research(breadth=3, depth=3)     │
│  T4: 风险事件 ──→ deep_research(breadth=3, depth=3)     │
│  T5: 机构观点 ──→ deep_research(breadth=3, depth=3)     │
│                                                          │
│  每个主题约 9 次 Tavily 调用，产出 ~20-25 个 learnings    │
│                                                          │
└──────────────────────┬───────────────────────────────────┘
                       │ 5个主题共计约 100-125 个 learnings
                       ▼
┌──────────────────────────────────────────────────────────┐
│  合并去重所有 learnings                                   │
│  → 去重后约 80-100 个独特知识点                           │
│                                                          │
│  LLM 综合生成结构化摘要报告                               │
│  → web_research.json                                     │
└──────────────────────────────────────────────────────────┘
```

**编排代码：**

```python
async def run_web_research(symbol: str, name: str, industry: str) -> dict:
    """
    对5个主题并行执行 Deep Research，然后合并生成报告
    """
    # 定义5个研究主题
    topics = [
        f"{name} 最新消息 近期重大新闻 影响股价事件",
        f"{name} 核心竞争力 护城河 市场地位 竞争优势",
        f"{industry}行业 发展前景 政策环境 市场趋势 2025",
        f"{name} 风险事件 处罚 诉讼 监管 负面消息",
        f"{name} 研报 券商评级 目标价 机构观点",
    ]

    # 并行执行5个主题的 Deep Research
    research_tasks = [
        deep_research(
            query=topic,
            breadth=3,
            depth=3,
            learnings=[],
            visited_urls=[],
        )
        for topic in topics
    ]
    results = await asyncio.gather(*research_tasks, return_exceptions=True)

    # 合并所有 learnings 并去重
    all_learnings = set()
    all_urls = set()
    for r in results:
        if isinstance(r, ResearchResult):
            all_learnings.update(r.learnings)
            all_urls.update(r.visited_urls)

    # LLM 综合生成结构化报告
    report = await generate_web_research_report(
        symbol=symbol,
        name=name,
        industry=industry,
        learnings=list(all_learnings),
    )

    return report
```

### 4.7 最终报告生成

所有主题的 learnings 合并后，由 LLM 一次性生成结构化的摘要报告：

```python
async def generate_web_research_report(
    symbol: str,
    name: str,
    industry: str,
    learnings: list[str],
) -> WebResearchResult:
    """
    将所有 Deep Research 的 learnings 汇总，生成结构化报告
    """
    prompt = (
        f"你是一位专业的金融研究员。以下是对股票 {symbol} {name}（{industry}行业）"
        f"进行多轮深度网络搜索后积累的全部知识点。\n\n"
        f"请基于这些知识点，生成结构化的投资研究摘要。\n\n"
        f"<learnings>\n"
        + "\n".join(f"- {l}" for l in learnings)
        + "\n</learnings>\n\n"
        f"要求：\n"
        f"- 按照输出 Schema 的字段分类整理信息\n"
        f"- 正面和负面新闻分开归类\n"
        f"- 包含具体数据、日期、来源\n"
        f"- 对信息可信度给出客观评估\n"
    )

    result = await llm_call(prompt, response_format=WebResearchResult)
    return result
```

### 4.8 输出JSON Schema

```json
{
  "meta": {
    "symbol": "000001",
    "name": "平安银行",
    "search_time": "2025-02-06T10:35:00",
    "search_config": {
      "topics_count": 5,
      "breadth": 3,
      "depth": 3,
      "queries_per_topic": 9,
      "total_queries": 45
    },
    "total_learnings": 85,
    "total_sources_consulted": 60
  },
  
  "news_summary": {
    "positive": [
      {
        "title": "平安银行2024年净利润同比增长2.1%",
        "summary": "...",
        "source": "东方财富",
        "date": "2025-01-28",
        "importance": "高"
      }
    ],
    "negative": [
      {
        "title": "...",
        "summary": "...",
        "source": "...",
        "date": "...",
        "importance": "中"
      }
    ],
    "neutral": []
  },
  
  "competitive_advantage": {
    "description": "背靠平安集团，零售转型成效显著...",
    "moat_type": "品牌+渠道+科技",
    "market_position": "股份制银行第一梯队"
  },
  
  "industry_outlook": {
    "industry": "银行",
    "outlook": "中性偏积极",
    "key_drivers": ["净息差企稳", "资产质量改善", "政策支持"],
    "key_risks": ["房地产敞口", "利率下行压力"]
  },
  
  "risk_events": {
    "regulatory": "无近期处罚",
    "litigation": "无重大诉讼",
    "management": "管理层稳定",
    "other": ""
  },
  
  "analyst_opinions": {
    "buy_count": 12,
    "hold_count": 5,
    "sell_count": 0,
    "average_target_price": 13.5,
    "recent_reports": [
      {
        "broker": "中信证券",
        "rating": "买入",
        "target_price": 14.0,
        "date": "2025-01-15"
      }
    ]
  },
  
  "search_confidence": "中"
}
```

### 4.9 搜索规模与成本估算

| 指标 | 数值 |
|------|------|
| 搜索主题数 | 5 |
| 每主题 Tavily 调用次数 | ~9（3+3+3） |
| 总 Tavily 调用次数 | ~45 |
| 每主题 LLM 调用次数 | ~18（9次生成查询 + 9次提取知识） + 1次生成报告 |
| 总 LLM 调用次数 | ~96 |
| 每主题 learnings | ~20-25（去重后） |
| 总 learnings | ~80-100（去重后） |
| 预计单次搜索耗时 | 2-5分钟（5个主题并行） |

**成本控制策略：**
- 5 个主题**并行**执行，大幅缩短总耗时
- 同一主题内的同层查询也**并行**执行（`asyncio.gather`）
- `generate_serp_queries` 和 `process_serp_result` 可使用较小的模型（如 DeepSeek）降低成本
- 最终报告生成使用较强模型（如 GPT-4o）保证质量
- Tavily 的 `search_depth="advanced"` 直接返回内容摘要，无需额外爬取网页

---

## 五、模块C：月K线技术分析

### 5.1 设计原则

- 通过AKShare API直接获取月K线数据（**不再需要用户提供或从数据库读取**）
- 用pandas-ta**计算**技术指标（纯代码，不需要AI）
- 再把计算后的数据**连同技术指标**一起发给Agent分析
- Agent基于数值数据进行技术面推理和评分

### 5.2 流程

```
AKShare获取月K线数据
ak.stock_zh_a_hist(symbol, period="monthly", 
                   start_date="20000101", adjust="qfq")
           │
           │ 返回DataFrame，约100~300条记录
           ▼
    ┌──────────────┐
    │ pandas-ta    │  ← 纯代码计算，不需要AI
    │ 计算技术指标  │
    │ MA/MACD/RSI  │
    │ BOLL/KDJ等   │
    └──────┬───────┘
           │ 原始数据 + 技术指标
           ▼
    ┌──────────────┐
    │ 技术分析Agent │  ← AI推理
    │ 分析趋势      │
    │ 识别形态      │
    │ 给出评分      │
    └──────┬───────┘
           │
           ▼
    technical_analysis.json
```

### 5.3 获取月K线数据

```python
import akshare as ak

def fetch_monthly_kline(symbol: str) -> pd.DataFrame:
    """
    通过AKShare获取指定股票从2000年至今的月K线数据（前复权）
    
    函数：ak.stock_zh_a_hist()
    入参：
      - symbol: 纯6位代码，如 "603080"
      - period: "monthly"
      - start_date: "20000101"
      - adjust: "qfq"（前复权）
    
    返回DataFrame列：
      日期, 股票代码, 开盘, 收盘, 最高, 最低, 
      成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
    
    注意：
      - 上市较晚的股票，数据从上市月份开始
      - 典型数据量：上市7年的股票约98条记录，上市25年的约300条
      - 数据量很小（~5KB JSON），LLM完全可以处理
    """
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="monthly",
        start_date="20000101",
        adjust="qfq",
    )
    return df
```

**实际返回数据示例（603080，2018年上市）：**

```
          日期    股票代码    开盘    收盘    最高    最低     成交量          成交额    振幅   涨跌幅   涨跌额   换手率
0   2018-01-31  603080  14.26  35.51  53.82  14.26  1323043  6.164e+09  342.81  207.71  23.97  372.69
1   2018-02-28  603080  34.64  26.87  40.04  24.56  1122214  3.665e+09   43.59  -24.33  -8.64  316.12
2   2018-03-30  603080  26.98  28.72  36.04  23.82  1624739  5.327e+09   45.48    6.89   1.85  457.67
...（共约98条记录）
```

### 5.4 技术指标计算（纯代码部分）

```python
import pandas as pd
import pandas_ta as ta

def compute_technical_indicators(kline_df: pd.DataFrame) -> pd.DataFrame:
    """
    基于月K线数据计算技术指标
    
    入参：fetch_monthly_kline() 返回的DataFrame
    列名：日期, 股票代码, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
    """
    df = kline_df.copy()
    
    # AKShare返回的是中文列名，pandas-ta需要英文列名
    column_map = {
        "开盘": "open", "收盘": "close", 
        "最高": "high", "最低": "low", "成交量": "volume"
    }
    df = df.rename(columns=column_map)
    
    # 均线系统
    df.ta.sma(length=5, append=True)    # MA5（5个月）
    df.ta.sma(length=10, append=True)   # MA10（10个月）
    df.ta.sma(length=20, append=True)   # MA20（20个月）
    df.ta.sma(length=60, append=True)   # MA60（60个月，约5年）
    
    # MACD
    df.ta.macd(append=True)             # MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
    
    # RSI
    df.ta.rsi(length=14, append=True)   # RSI_14
    
    # 布林带
    df.ta.bbands(length=20, append=True)  # BBL_20, BBM_20, BBU_20
    
    # KDJ
    df.ta.stoch(append=True)            # STOCHk_14_3_3, STOCHd_14_3_3
    
    return df
```

### 5.5 技术分析Agent

```python
technical_agent = ChatAgent(
    chat_client=client,
    name="technical_analyst",
    description="基于月K线数据和技术指标进行技术面分析",
    instructions="""你是一位资深A股技术分析师。你将收到一只股票的月K线数据和技术指标。

    请从以下角度分析：
    1. **长期趋势**：
       - MA5/MA10/MA20/MA60的排列关系（多头/空头/缠绕）
       - 价格相对均线的位置
       - 近6个月和近12个月的涨跌幅
       
    2. **动量指标**：
       - MACD柱状图方向（放大/缩小）、金叉/死叉
       - RSI超买(>70)或超卖(<30)
       - KDJ的位置和交叉
       
    3. **波动性**：
       - 布林带开口方向（收窄=即将变盘，张开=趋势延续）
       - 价格在布林带中的位置（上轨/中轨/下轨附近）
       
    4. **量价关系**：
       - 近期成交量相比前期均量的变化
       - 价涨量增（健康）还是价涨量缩（警惕）
       
    5. **关键价位**：
       - 近期支撑位和压力位
       
    请给出0-10的技术面评分和分析摘要。
    注意：你收到的是数值数据，请基于数据客观分析，不要猜测。
    """,
    default_options={
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    },
)
```

> 兼容性说明：当前项目使用 `agent-framework==1.0.0b260130`，技术分析Agent按模块B同款模式实现：
> `response_format={"type":"json_object"}`，随后手动 `json.loads + TechnicalAnalysisResult.model_validate`。

### 5.6 输出JSON Schema

```json
{
  "meta": {
    "symbol": "000001",
    "name": "平安银行",
    "analysis_time": "2025-02-06T10:32:00",
    "data_range": "2000-01 ~ 2025-01",
    "total_months": 300
  },
  
  "score": 6.5,
  "signal": "看多",
  "confidence": 0.7,
  
  "trend_analysis": {
    "ma_alignment": "多头排列（MA5>MA10>MA20）",
    "price_vs_ma20": "价格在MA20上方",
    "trend_6m": "上涨 +12.3%",
    "trend_12m": "上涨 +8.5%",
    "trend_judgment": "中期上升趋势"
  },
  
  "momentum": {
    "macd_status": "MACD金叉后柱状图放大",
    "rsi_value": 58.3,
    "rsi_status": "中性偏强",
    "kdj_status": "K线上穿D线，金叉"
  },
  
  "volatility": {
    "boll_position": "价格在中轨和上轨之间",
    "boll_width": "布林带收窄，可能即将变盘"
  },
  
  "volume_analysis": {
    "recent_vs_avg": "近3月成交量为前期均量的1.2倍",
    "volume_price_relation": "量价配合良好"
  },
  
  "key_levels": {
    "support_1": 10.5,
    "support_2": 9.8,
    "resistance_1": 12.0,
    "resistance_2": 13.5
  },
  
  "summary": "该股月线级别处于中期上升趋势，均线多头排列，MACD金叉后动能增强..."
}
```

---

## 六、模块D：首席分析师（最终综合判定）

### 6.1 设计原则

- 接收三个模块的JSON输出作为输入
- 独立给出最终综合评分（0-10），不是各模块分数的加权
- 给出三个时间窗口的投资建议
- 撰写1000字以内的投资分析报告

### 6.2 Agent设计

```python
chief_analyst = ChatAgent(
    chat_client=client,
    name="chief_analyst",
    description="首席投资分析师，综合所有信息给出最终投资建议",
    instructions="""你是一位首席投资分析师。你将收到三份分析报告：

    1. **AKShare结构化数据**（akshare_data.json）：
       包含公司基本信息、估值数据、资金流向、股东结构、财务指标等客观数据。
       
    2. **网络搜索研究报告**（web_research.json）：
       包含近期新闻摘要、竞争优势、行业前景、风险事件、机构观点。
       
    3. **技术分析报告**（technical_analysis.json）：
       包含月K线技术分析评分、趋势判断、动量指标、量价关系。
       注意：模块C现使用嵌套结构（`trend_analysis.*`, `momentum.*` 等），
       模块D解析字段时需按新路径读取。

    你的任务：
    
    一、给出**分项评分**（每项0-10分）：
       - 技术面评分：参考技术分析报告中的评分
       - 基本面评分：根据财务指标、竞争优势、管理层情况
       - 估值评分：根据PE/PB历史分位、行业对比、PEG
       - 资金面评分：根据主力资金流向、北向资金、板块热度
       - 情绪面评分：根据新闻情绪、机构评级、市场热度
    
    二、给出**最终综合评分**（0-10分）：
       - 这不是分项评分的简单平均
       - 你需要综合判断，一个严重风险可以大幅拉低总分
       - 评分标准：0-2极差，3-4较差，5中性，6-7良好，8-10优秀
    
    三、给出**三个时间窗口的投资建议**：
       - 1个月（短期）：更看重技术面、资金面
       - 6个月（中期）：更看重估值、基本面
       - 1年（长期）：更看重基本面、行业前景
       每个建议选择：强烈买入/买入/持有/卖出/强烈卖出
    
    四、撰写**1000字以内的投资分析报告**：
       - 开头一句话概括总体评价
       - 分析各维度的亮点和风险
       - 明确给出投资建议和理由
       - 提示主要风险因素
    """,
    response_format=FinalReport,
    temperature=0.3,
)
```

### 6.3 最终输出JSON Schema

```json
{
  "meta": {
    "symbol": "000001",
    "name": "平安银行",
    "analysis_time": "2025-02-06T10:40:00"
  },
  
  "dimension_scores": {
    "technical": { "score": 6.5, "brief": "中期上升趋势，均线多头排列" },
    "fundamental": { "score": 7.0, "brief": "ROE稳定，资产质量改善" },
    "valuation": { "score": 7.5, "brief": "PE历史分位23%，明显低估" },
    "capital_flow": { "score": 5.5, "brief": "主力近5日小幅流出，北向持仓稳定" },
    "sentiment": { "score": 6.0, "brief": "机构普遍看好，无重大负面" }
  },
  
  "overall_score": 6.8,
  
  "advice": [
    {
      "timeframe": "1个月",
      "recommendation": "持有",
      "reasoning": "技术面偏多但短期涨幅已较大，资金面信号中性"
    },
    {
      "timeframe": "6个月",
      "recommendation": "买入",
      "reasoning": "估值处于历史低位，基本面持续改善，中期有估值修复空间"
    },
    {
      "timeframe": "1年",
      "recommendation": "买入",
      "reasoning": "银行板块估值修复逻辑不变，分红收益率有吸引力"
    }
  ],
  
  "report": "平安银行当前整体投资价值良好（6.8/10）。从估值角度看...",
  
  "key_catalysts": [
    "净息差企稳回升",
    "资产质量持续改善",
    "高股息率吸引配置资金"
  ],
  
  "primary_risks": [
    "房地产贷款敞口仍需关注",
    "宏观经济下行压力",
    "利率持续下行挤压息差"
  ]
}
```

---

## 七、MAF编排方式

### 7.1 整体编排

```python
import asyncio
import json
from datetime import datetime

async def analyze_stock(symbol: str, name: str):
    """
    主入口：分析一只股票
    
    Args:
        symbol: 股票代码 (纯6位数字)
        name: 公司名称
    """
    
    # ── 阶段1：数据准备（三模块并行） ──
    
    # 模块A：AKShare数据采集（纯代码，不需要AI）
    # 模块C的计算部分：获取月K线 + 计算技术指标（纯代码，不需要AI）
    # 模块B：网络搜索（需要AI Agent）
    # 模块C的推理部分：技术分析（需要AI Agent）
    
    # A和C的计算部分可以先同步执行（都是纯代码，很快）
    # 注意：AKShare调用之间建议间隔3-5秒，避免封IP
    akshare_data = collect_akshare_data(symbol, name)
    lookback_months = TECH_AGENT_LOOKBACK_MONTHS  # from stock_analyzer.config
    
    kline_df = fetch_monthly_kline(symbol)          # 从AKShare获取月K线
    kline_with_indicators = compute_technical_indicators(kline_df)
    kline_json = kline_with_indicators.tail(lookback_months).to_json(
        orient="records", date_format="iso", force_ascii=False
    )  # 默认取最近36个月数据（由配置 TECH_AGENT_LOOKBACK_MONTHS 控制）
    
    # 然后B和C的推理部分并行执行（都需要调用LLM）
    industry = akshare_data.get("company_info", {}).get("industry", "")
    
    web_task = web_research_agent.run(
        f"请对股票 {symbol} {name}（{industry}行业）进行网络深度研究。"
        f"需要搜索近期新闻、竞争优势、行业前景、风险事件、机构观点。"
        f"请进行3轮搜索。"
    )
    
    tech_task = technical_agent.run(
        f"请分析股票 {symbol} {name} 的月K线技术面。\n\n"
        f"以下是含技术指标的月K线数据（最近{lookback_months}个月，来自AKShare前复权数据）：\n"
        f"{kline_json}"
    )
    
    web_result, tech_result = await asyncio.gather(
        web_task, tech_task,
        return_exceptions=True
    )
    
    # 解析结果
    web_research = parse_result(web_result, "web_research")
    technical_analysis = parse_result(tech_result, "technical_analysis")
    
    # ── 阶段2：首席分析师综合判定 ──
    
    chief_input = f"""
请综合以下三份报告，给出最终投资建议。

## 报告1：AKShare结构化数据
{json.dumps(akshare_data, ensure_ascii=False, indent=2)}

## 报告2：网络搜索研究
{json.dumps(web_research, ensure_ascii=False, indent=2)}

## 报告3：技术分析报告
{json.dumps(technical_analysis, ensure_ascii=False, indent=2)}
"""
    
    final_result = await chief_analyst.run(chief_input)
    final_report = FinalReport.model_validate_json(final_result.text)
    
    return final_report
```

### 7.2 编排选择说明

本项目**不使用** MAF的ConcurrentBuilder，理由如下：

| 方面 | ConcurrentBuilder | asyncio.gather |
|------|-------------------|----------------|
| 适用场景 | 多个Agent处理同一输入 | 多个Agent处理不同输入 |
| 输入差异化 | 困难（所有Agent收到相同消息） | 简单（每个Agent独立传参） |
| 与纯代码混合 | 不支持（只能编排Agent） | 自然支持（代码和Agent混在一起） |

由于我们的场景是：
- 模块A是纯代码，不是Agent
- 模块B和模块C的输入内容完全不同
- 需要先执行纯代码，再执行Agent

所以直接使用`asyncio.gather`并行执行B和C更合适。MAF的ChatAgent在这里作为**单独的Agent运行**，不需要复杂的编排模式。

### 7.3 MAF在本项目中的使用方式

```
MAF的使用：
├── ChatAgent × 3（Web搜索Agent、技术分析Agent、首席分析师Agent）
├── 工具函数（Web Search Tool 绑定到搜索Agent）
├── 结构化输出（response_format=Pydantic模型）
└── 对话管理（ChatAgent自带的多轮工具调用能力）

MAF未使用：
├── ConcurrentBuilder（输入差异化需求不匹配）
├── SequentialBuilder（不是线性流水线）
├── GroupChat（不需要Agent间对话）
├── MagenticBuilder（任务已预定义）
└── HandoffBuilder（不需要动态路由）
```

---

## 八、Pydantic数据模型汇总

```python
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime

# ── 模块B输出 ──

class NewsItem(BaseModel):
    title: str
    summary: str
    source: str
    date: str
    importance: Literal["高", "中", "低"]

class WebResearchResult(BaseModel):
    """网络搜索模块的输出"""
    news_positive: list[NewsItem] = Field(default_factory=list)
    news_negative: list[NewsItem] = Field(default_factory=list)
    competitive_advantage: str = Field(max_length=300)
    industry_outlook: str = Field(max_length=300)
    risk_events: str = Field(max_length=300)
    analyst_buy_count: int = 0
    analyst_hold_count: int = 0
    analyst_sell_count: int = 0
    average_target_price: float | None = None
    search_confidence: Literal["高", "中", "低"]

# ── 模块C输出（已升级为嵌套结构） ──
# 说明：
# 1) 旧版扁平字段（ma_alignment/macd_status/rsi_value 等）已弃用；
# 2) 以 module_c_technical_analysis_detail_design.md 为准；
# 3) 模块D读取路径需改为 trend_analysis.* / momentum.* / key_levels.*。

class TrendAnalysis(BaseModel):
    ma_alignment: str = Field(max_length=50)
    price_vs_ma20: str = Field(max_length=80)
    trend_6m: str = Field(max_length=80)
    trend_12m: str = Field(max_length=80)
    trend_judgment: str = Field(max_length=100)

class MomentumAnalysis(BaseModel):
    macd_status: str = Field(max_length=80)
    rsi_value: float | None = None
    rsi_status: str = Field(max_length=40)
    kdj_status: str = Field(max_length=80)

class VolatilityAnalysis(BaseModel):
    boll_position: str = Field(max_length=80)
    boll_width: str = Field(max_length=80)

class VolumeAnalysis(BaseModel):
    recent_vs_avg: str = Field(max_length=100)
    volume_price_relation: str = Field(max_length=100)

class KeyLevels(BaseModel):
    support_1: float | None = None
    support_2: float | None = None
    resistance_1: float | None = None
    resistance_2: float | None = None

class TechnicalAnalysisResult(BaseModel):
    """技术分析模块的输出"""
    score: float = Field(ge=0, le=10)
    signal: Literal["强烈看多", "看多", "中性", "看空", "强烈看空"]
    confidence: float = Field(ge=0, le=1)
    trend_analysis: TrendAnalysis
    momentum: MomentumAnalysis
    volatility: VolatilityAnalysis
    volume_analysis: VolumeAnalysis
    key_levels: KeyLevels
    summary: str = Field(max_length=300)

# ── 模块D输出 ──

class DimensionBrief(BaseModel):
    score: float = Field(ge=0, le=10)
    brief: str = Field(max_length=50)

class TimeframeAdvice(BaseModel):
    timeframe: Literal["1个月", "6个月", "1年"]
    recommendation: Literal["强烈买入", "买入", "持有", "卖出", "强烈卖出"]
    reasoning: str = Field(max_length=100)

class FinalReport(BaseModel):
    """首席分析师的最终输出"""
    dimension_scores: dict[str, DimensionBrief]
    overall_score: float = Field(ge=0, le=10)
    advice: list[TimeframeAdvice]
    report: str = Field(max_length=1000)
    key_catalysts: list[str] = Field(max_length=3)
    primary_risks: list[str] = Field(max_length=3)
```

---

## 九、项目结构

**说明：** `stock_analyzer` 是当前项目（`fin_analysis`）的一个功能模块，不是独立项目。它使用项目根目录的 `pyproject.toml` 文件管理依赖。

```
stock_analyzer/                     # 股票分析模块目录
├── __init__.py
├── main.py                         # 入口 + 编排逻辑
├── models.py                       # Pydantic 数据模型
├── utils.py                        # 股票代码格式转换等工具
├── module_a_akshare.py             # 模块A：AKShare数据采集
├── module_b_websearch.py           # 模块B：网络搜索Agent
├── module_c_technical.py           # 模块C：技术分析（计算+Agent）
├── module_d_chief.py               # 模块D：首席分析师Agent
├── output/                         # 分析结果输出目录
│   ├── 000001_akshare_data.json
│   ├── 000001_web_research.json
│   ├── 000001_technical_analysis.json
│   └── 000001_final_report.json
├── tests/
│   ├── test_akshare_collector.py
│   ├── test_technical.py
│   └── test_integration.py
└── docs/                           # 文档目录
    └── stock-analysis-design-v3.1.md
```

### 依赖配置

**本模块使用项目根目录的 `pyproject.toml` 文件。** 所需的依赖已在根目录的 `pyproject.toml` 中配置：

```toml
# 位置：/opt/fin_analysis/pyproject.toml
[project]
name = "fin_analysis_loader"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "agent-framework==1.0.0b260130",
    "akshare>=1.18.22",              # ✓ 已配置，用于获取A股数据
    "pandas>=2.3.3",                 # ✓ 已配置
    "pydantic>=2.12.5",              # ✓ 已配置
    # 其他项目依赖...
]
```

**stock_analyzer 模块需要的额外依赖：**

如果需要使用 pandas-ta 进行技术指标计算，需要在根目录的 `pyproject.toml` 中添加：

```toml
dependencies = [
    # ... 现有依赖 ...
    "pandas-ta>=0.3.14b0",  # 技术指标计算库（模块C必需）
]
```

---

## 十、关键设计决策总结

| 决策 | 选择 | 理由 |
|------|------|------|
| 架构模式 | 三模块+首席分析师 | 数据获取和AI分析分离，职责清晰 |
| AKShare模块 | 纯代码，不用AI | 结构化数据直接拼接即可，省token |
| 网络搜索模块 | 独立Agent，3轮搜索 | 搜索需要迭代深入，与数据采集逻辑不同 |
| 技术分析 | 代码计算指标 + AI推理 | 计算交给pandas-ta，推理交给LLM |
| 月K线数据 | 用数值不用图片 | 300条记录约2KB，比视觉分析准确得多 |
| 编排方式 | asyncio.gather | 比MAF的ConcurrentBuilder更灵活 |
| MAF使用范围 | 仅ChatAgent + 工具 | 利用其多轮对话和结构化输出能力 |
| 评分机制 | 首席分析师独立评分 | 允许非线性判断，一票否决 |
| 中间结果 | 全部输出为JSON文件 | 方便调试、缓存、复用 |

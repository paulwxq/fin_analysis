# 基于MAF Magentic的股票分析多Agent系统设计方案

## 1. 系统概述

### 1.1 目标
使用Microsoft Agent Framework (python-1.0.0b260128) 的Magentic编排功能，构建一个智能股票评估系统，专门分析具有"平底锅"特征的股票（曾经高位，后续长期震荡），判断其6个月内的上涨潜力。

### 1.2 核心能力
- 自动分析股票所属板块及板块热度
- 搜索公司最新背景和动态
- 评估板块趋势和相关性
- 基于K线数据和板块信息进行综合判断
- 生成结构化分析报告和评分

## 2. Agent架构设计

### 2.1 整体架构（Magentic模式）

```
┌─────────────────────────────────────────────────┐
│          MagenticManager (Orchestrator)         │
│  - 任务分解与动态规划                             │
│  - 双账本维护(Task Ledger + Progress Ledger)     │
│  - 决策评估与结果综合                             │
└──────────────┬──────────────────────────────────┘
               │
    ┌──────────┴──────────┬──────────┬──────────┬──────────┐
    │                     │          │          │          │
┌───▼────┐  ┌──────▼──────┐  ┌─────▼─────┐  ┌──▼────┐  ┌─▼─────┐
│ Stock  │  │   Sector    │  │  Company  │  │ Tech  │  │Report │
│Data    │  │   Research  │  │  Research │  │Analyst│  │Writer │
│Agent   │  │   Agent     │  │   Agent   │  │Agent  │  │Agent  │
└────────┘  └─────────────┘  └───────────┘  └───────┘  └───────┘
```

### 2.2 各Agent职责定义

#### 2.2.1 StockDataAgent（数据获取专家）
**角色**：负责从数据库读取股票K线数据，提供基础数据支持

**核心能力**：
- 连接PostgreSQL数据库
- 查询指定股票的月K线历史数据
- 计算关键技术指标（振幅、成交量变化等）
- 识别"平底锅"形态特征参数

**工具函数**：
```python
async def query_stock_kline(code: str, months: int = 12) -> pd.DataFrame
async def calculate_volatility(data: pd.DataFrame) -> dict
async def detect_pan_bottom_features(data: pd.DataFrame) -> dict
```

#### 2.2.2 SectorResearchAgent（板块研究专家）
**角色**：分析股票所属板块及板块热度趋势

**核心能力**：
- Web搜索股票所属的行业板块（主板块+概念板块）
- 搜索板块最近3-6个月的新闻热度
- 分析板块政策支持力度
- 对比同板块其他龙头股表现

**工具函数**：
```python
async def search_stock_sectors(code: str, name: str) -> List[str]
async def analyze_sector_hotness(sector: str, months: int = 6) -> dict
async def get_sector_policy_support(sector: str) -> dict
async def compare_sector_leaders(sector: str, code: str) -> dict
```

**示例提示词**：
```
你是板块研究专家。请使用web_search工具：
1. 搜索"{stock_name} 所属板块 概念"，识别该股票的主要板块
2. 搜索"{sector} 板块 最近6个月 趋势 新闻"，分析热度
3. 搜索"{sector} 政策支持 2024 2025"，了解政策方向
4. 对比同板块龙头股的近期表现
```

#### 2.2.3 CompanyResearchAgent（公司研究专家）
**角色**：深度研究公司基本面和最新动态

**核心能力**：
- 搜索公司最新财报和业绩预告
- 识别公司近期重大事件（并购、新产品、合同等）
- 分析公司在行业中的竞争地位
- 评估管理层动向

**工具函数**：
```python
async def search_company_news(code: str, name: str, months: int = 6) -> List[dict]
async def analyze_financial_events(code: str) -> dict
async def assess_competitive_position(name: str, sector: str) -> dict
```

**示例提示词**：
```
你是公司研究专家。请使用web_search工具：
1. 搜索"{company_name} 最新财报 业绩"
2. 搜索"{company_name} 重大事件 2024 2025"
3. 搜索"{company_name} {sector} 市场份额 竞争"
4. 识别可能的催化剂事件
```

#### 2.2.4 TechnicalAnalystAgent（技术分析专家）
**角色**：基于K线图和技术指标进行分析

**核心能力**：
- 读取PNG格式的K线图（通过vision能力）
- 识别关键技术形态（平底锅、突破信号等）
- 计算支撑位和阻力位
- 评估突破概率

**工具函数**：
```python
async def analyze_kline_chart(image_path: str) -> dict
async def calculate_support_resistance(data: pd.DataFrame) -> dict
async def evaluate_breakout_probability(data: pd.DataFrame, sectors_info: dict) -> float
```

**示例提示词**：
```
你是技术分析专家。请分析：
1. 根据提供的月K线图，识别当前形态
2. 判断股票是否处于平底锅形态的末期
3. 评估成交量变化趋势
4. 结合板块信息，判断突破向上的概率
```

#### 2.2.5 ReportWriterAgent（报告撰写专家）
**角色**：综合各方信息，生成结构化分析报告

**核心能力**：
- 整合所有Agent的研究结果
- 生成Markdown格式报告
- 计算综合推荐评分（0-10分）
- 提炼核心推荐理由
- 将结果写入数据库

**输出格式**：
```markdown
# {股票代码} {股票名称} 分析报告

## 基本信息
- 代码：{code}
- 当前价格：{price}
- 分析时间：{datetime}

## 平底锅形态分析
- 高点时间：{peak_time}
- 高点价格：{peak_price}
- 震荡时长：{duration}
- 当前位置：{position}

## 板块分析
- 主要板块：{sectors}
- 板块热度评分：{hotness_score}/10
- 政策支持：{policy_support}
- 板块趋势：{trend}

## 公司基本面
- 最新动态：{news}
- 催化剂事件：{catalysts}
- 竞争地位：{position}

## 技术分析
- 支撑位：{support}
- 阻力位：{resistance}
- 突破概率：{probability}

## 综合评估
- 推荐评分：{score}/10
- 推荐理由：{reasons}
- 风险提示：{risks}

## 建议
{recommendation}
```

## 3. Magentic Workflow实现

### 3.1 核心代码结构

```python
from agent_framework import (
    MagenticBuilder,
    ChatAgent,
    StandardMagenticManager,
    WorkflowOutputEvent,
    RequestInfoEvent,
    AgentRunUpdateEvent
)
from agent_framework.openai import OpenAIChatClient
import asyncio
import asyncpg
from pathlib import Path

# 3.1.1 初始化LLM客户端
chat_client = OpenAIChatClient(
    model="gpt-4o",  # Manager需要强推理能力
    api_key="your-api-key"
)

# 3.1.2 创建专家Agents
stock_data_agent = ChatAgent(
    name="StockDataAgent",
    description="专门负责从PostgreSQL数据库读取股票K线数据，计算技术指标，识别平底锅形态特征",
    model=chat_client,
    tools=[query_stock_kline, calculate_volatility, detect_pan_bottom_features]
)

sector_research_agent = ChatAgent(
    name="SectorResearchAgent", 
    description="负责使用web_search工具搜索股票所属板块、分析板块热度趋势、政策支持和龙头股对比",
    model=chat_client,
    tools=[web_search, search_stock_sectors, analyze_sector_hotness]
)

company_research_agent = ChatAgent(
    name="CompanyResearchAgent",
    description="负责使用web_search工具深度研究公司最新财报、重大事件、竞争地位和催化剂",
    model=chat_client,
    tools=[web_search, search_company_news, analyze_financial_events]
)

technical_analyst_agent = ChatAgent(
    name="TechnicalAnalystAgent",
    description="负责分析K线图形态、计算支撑阻力位、评估突破概率，具备图像识别能力",
    model=chat_client,
    tools=[analyze_kline_chart, calculate_support_resistance]
)

report_writer_agent = ChatAgent(
    name="ReportWriterAgent",
    description="负责综合所有研究结果，生成Markdown分析报告，计算推荐评分，并将结果写入数据库",
    model=chat_client,
    tools=[write_report, insert_to_database]
)

# 3.1.3 创建Manager Agent
manager_agent = ChatAgent(
    name="StockAnalysisManager",
    description="股票分析任务的总指挥，负责任务分解、动态规划和质量控制",
    model=chat_client
)

# 3.1.4 构建Magentic Workflow
workflow = (
    MagenticBuilder()
    .participants(
        stock_data_agent,
        sector_research_agent, 
        company_research_agent,
        technical_analyst_agent,
        report_writer_agent
    )
    .with_standard_manager(
        agent=manager_agent,
        max_stall_count=3,  # 3轮无进展判定停滞
        max_reset_count=2    # 最多2次重置
    )
    .with_plan_review(enable=True)  # 启用人工审查
    .build()
)
```

### 3.2 任务执行流程

```python
async def analyze_stock(stock_code: str):
    """分析单支股票"""
    
    # 准备上下文信息
    task = f"""
    请分析股票 {stock_code} 是否值得购买。该股票已被初步筛选，具有"平底锅"特征。
    
    你需要协调各专家Agent完成以下工作：
    1. 从数据库获取该股票的月K线数据（至少12个月）
    2. 识别股票所属的主要板块和概念板块
    3. 深度研究各板块最近3-6个月的热度和趋势
    4. 调查公司最近6个月的重大事件和基本面变化
    5. 基于K线图进行技术分析
    6. 综合判断该股票在6个月内上涨的可能性
    7. 生成详细的Markdown分析报告
    8. 将评分和理由写入数据库
    
    注意：
    - 平底锅特征意味着股票曾经有过高位，之后长期小幅震荡
    - 重点关注板块是否有催化剂、公司是否有重大利好
    - 最终给出0-10分的推荐评分和简明理由
    """
    
    pending_responses = None
    output_event = None
    
    # 事件驱动循环
    while not output_event:
        if pending_responses:
            stream = workflow.send_responses_streaming(pending_responses)
        else:
            stream = workflow.run_stream(task)
        
        pending_responses = None
        
        async for event in stream:
            # 实时显示Agent输出
            if isinstance(event, AgentRunUpdateEvent):
                if event.data.text:
                    print(f"[{event.executor_id}]: {event.data.text}", end="", flush=True)
            
            # 人工计划审查
            elif isinstance(event, RequestInfoEvent):
                if hasattr(event.data, 'plan'):
                    print("\n\n" + "="*50)
                    print("【Manager提出的执行计划】")
                    print(event.data.plan.text)
                    print("="*50 + "\n")
                    
                    user_input = input("审批计划 (回车=批准, 输入文字=修改): ")
                    
                    if user_input.strip() == "":
                        response = event.data.approve()
                        print("✓ 计划已批准\n")
                    else:
                        response = event.data.revise(user_input)
                        print("✓ 计划已修改\n")
                    
                    pending_responses = {event.request_id: response}
            
            # 任务完成
            elif isinstance(event, WorkflowOutputEvent):
                output_event = event
                print("\n\n" + "#"*50)
                print("分析完成！")
                print("#"*50)
                return event.data

# 批量分析
async def batch_analyze(stock_codes: List[str]):
    """批量分析多支股票"""
    for code in stock_codes:
        print(f"\n开始分析股票: {code}")
        try:
            result = await analyze_stock(code)
            print(f"✓ {code} 分析完成")
        except Exception as e:
            print(f"✗ {code} 分析失败: {e}")
        print("\n" + "-"*80 + "\n")

if __name__ == "__main__":
    # 示例：分析300444.SZ
    asyncio.run(analyze_stock("300444.SZ"))
```

## 4. 工具函数实现示例

### 4.1 数据库连接工具

```python
import asyncpg
import pandas as pd
from typing import Dict, List
from datetime import datetime, timedelta

class StockDatabase:
    """股票数据库操作类"""
    
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None
    
    async def connect(self):
        """创建连接池"""
        self.pool = await asyncpg.create_pool(
            dsn=self.dsn,
            min_size=2,
            max_size=10
        )
    
    async def query_kline_data(
        self, 
        code: str, 
        months: int = 12
    ) -> pd.DataFrame:
        """查询K线数据"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months*30)
        
        query = """
            SELECT month, code, name, open, high, low, close, volume, amount
            FROM stock_monthly_kline
            WHERE code = $1 
              AND month >= $2 
              AND month <= $3
            ORDER BY month ASC
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, code, start_date, end_date)
            df = pd.DataFrame(rows, columns=[
                'month', 'code', 'name', 'open', 'high', 
                'low', 'close', 'volume', 'amount'
            ])
            return df
    
    async def insert_analysis_result(
        self,
        code: str,
        score: float,
        reason: str
    ):
        """插入分析结果"""
        query = """
            INSERT INTO stock_analysis_results 
            (code, recommendation_score, reason, created_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (code) 
            DO UPDATE SET 
                recommendation_score = EXCLUDED.recommendation_score,
                reason = EXCLUDED.reason,
                created_at = EXCLUDED.created_at
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                query, 
                code, 
                score, 
                reason, 
                datetime.now()
            )

# 创建全局数据库实例
db = StockDatabase("postgresql://user:password@localhost/fin_db")
```

### 4.2 技术指标计算工具

```python
def calculate_technical_indicators(df: pd.DataFrame) -> Dict:
    """计算技术指标"""
    
    # 识别平底锅特征
    peak_idx = df['close'].idxmax()
    peak_price = df.loc[peak_idx, 'close']
    peak_time = df.loc[peak_idx, 'month']
    current_price = df.iloc[-1]['close']
    
    # 计算震荡期间的振幅
    oscillation_data = df[df.index > peak_idx]
    volatility = (oscillation_data['high'] - oscillation_data['low']).mean() / oscillation_data['close'].mean()
    
    # 成交量趋势
    volume_trend = "递增" if oscillation_data['volume'].iloc[-3:].mean() > oscillation_data['volume'].iloc[-6:-3].mean() else "递减"
    
    return {
        "peak_price": float(peak_price),
        "peak_time": str(peak_time),
        "current_price": float(current_price),
        "price_drop_pct": float((current_price - peak_price) / peak_price * 100),
        "oscillation_months": len(oscillation_data),
        "volatility": float(volatility),
        "volume_trend": volume_trend,
        "is_pan_bottom": volatility < 0.15 and len(oscillation_data) >= 6
    }
```

### 4.3 Web搜索工具（使用MAF内置）

```python
from agent_framework.tools import WebSearchTool

# 在创建Agent时注入web_search工具
web_search_tool = WebSearchTool()

# 在Agent的工具列表中添加
sector_research_agent = ChatAgent(
    name="SectorResearchAgent",
    description="...",
    model=chat_client,
    tools=[web_search_tool, ...]  # 添加web搜索能力
)
```

## 5. 数据库表设计

### 5.1 分析结果表

```sql
CREATE TABLE IF NOT EXISTS stock_analysis_results (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL,
    recommendation_score DECIMAL(3,1) CHECK (recommendation_score >= 0 AND recommendation_score <= 10),
    reason TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- 详细分析数据（JSON格式）
    analysis_detail JSONB,
    
    -- 唯一约束：每个股票只保留最新一次分析
    CONSTRAINT unique_stock_code UNIQUE (code)
);

-- 创建索引
CREATE INDEX idx_analysis_score ON stock_analysis_results(recommendation_score DESC);
CREATE INDEX idx_analysis_time ON stock_analysis_results(created_at DESC);
```

### 5.2 分析详情字段说明

```python
analysis_detail = {
    "basic_info": {
        "name": "股票名称",
        "current_price": 10.5,
        "peak_price": 25.3,
        "oscillation_months": 18
    },
    "sectors": {
        "main_sectors": ["新能源", "光伏"],
        "concept_sectors": ["碳中和", "储能"],
        "hotness_scores": {"新能源": 8.5, "光伏": 7.2}
    },
    "company": {
        "recent_news": [...],
        "catalysts": [...],
        "financial_health": "良好"
    },
    "technical": {
        "support_level": 9.8,
        "resistance_level": 12.5,
        "breakout_probability": 0.65
    },
    "risk_factors": [...]
}
```

## 6. 高级特性

### 6.1 Checkpointing（状态持久化）

对于复杂的分析任务，建议启用checkpointing：

```python
from agent_framework import FileCheckpointStorage

# 创建checkpoint存储
checkpoint_storage = FileCheckpointStorage("./checkpoints")

workflow = (
    MagenticBuilder()
    .participants(...)
    .with_standard_manager(...)
    .with_checkpointing(checkpoint_storage)  # 启用状态保存
    .build()
)
```

好处：
- 分析中断可以恢复
- 人工审批后可以继续
- 便于调试和追溯

### 6.2 停滞检测与人工干预

```python
workflow = (
    MagenticBuilder()
    .participants(...)
    .with_standard_manager(
        max_stall_count=3,
        max_reset_count=2
    )
    .with_human_input_on_stall()  # 停滞时请求人工指导
    .build()
)
```

### 6.3 可观测性（OpenTelemetry）

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# 配置遥测
provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="localhost:4317"))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
```

## 7. 最佳实践建议

### 7.1 Agent设计原则
1. **单一职责**：每个Agent专注一个领域，description要清晰
2. **工具充分**：为Agent配备足够的工具函数
3. **提示词优化**：在Agent的system_message中提供详细指导

### 7.2 Manager配置
1. 使用GPT-4o或更强模型作为Manager
2. 合理设置max_stall_count（建议3-5）
3. 启用plan_review在关键决策点

### 7.3 成本控制
1. 限制web_search次数（在tools中设置quota）
2. 使用checkpoint避免重复计算
3. 对简单任务可以跳过某些Agent

### 7.4 质量保证
1. Manager应验证Agent输出的质量
2. 对关键数据（如评分）设置合理性检查
3. 在任务账本中明确成功标准

## 8. 部署建议

### 8.1 开发环境
```bash
pip install agent-framework-python==1.0.0b260128
pip install asyncpg pandas numpy
pip install openai  # 或其他LLM provider
```

### 8.2 生产环境
1. 使用Docker容器化
2. 配置连接池和资源限制
3. 设置监控和告警
4. 实现重试和错误恢复机制

### 8.3 性能优化
1. 并行处理多支股票（使用asyncio.gather）
2. 缓存板块信息（Redis）
3. 批量数据库操作

## 9. 示例执行流程

### 输入
```python
await analyze_stock("300444.SZ")
```

### Manager的任务分解（Task Ledger示例）
```
Facts:
- 股票代码: 300444.SZ
- 需要判断6个月内上涨潜力
- 已知具有平底锅特征

Plan:
1. [StockDataAgent] 从数据库获取300444.SZ的12个月K线数据
2. [StockDataAgent] 计算技术指标，验证平底锅特征
3. [SectorResearchAgent] 搜索该股票所属板块
4. [SectorResearchAgent] 分析各板块最近3-6个月热度
5. [CompanyResearchAgent] 搜索公司最新新闻和财报
6. [CompanyResearchAgent] 识别催化剂事件
7. [TechnicalAnalystAgent] 分析K线图，计算支撑阻力位
8. [TechnicalAnalystAgent] 评估突破概率
9. [ReportWriterAgent] 综合所有信息生成报告
10. [ReportWriterAgent] 计算推荐评分并写入数据库
```

### 执行输出示例
```
[StockAnalysisManager]: 收到任务，开始分析300444.SZ...

[StockDataAgent]: 正在从数据库查询300444.SZ的K线数据...
[StockDataAgent]: 获取到12个月数据，共12条记录
[StockDataAgent]: 识别到平底锅特征：峰值25.6元(2015年6月)，当前11.5元，震荡102个月

[SectorResearchAgent]: 正在搜索300444.SZ所属板块...
[SectorResearchAgent]: 识别到主板块：工业母机、专用设备
[SectorResearchAgent]: 识别到概念板块：工业4.0、高端装备
[SectorResearchAgent]: 正在分析"工业母机"板块热度...
[SectorResearchAgent]: 工业母机板块热度评分8.5/10，政策大力支持

[CompanyResearchAgent]: 正在搜索公司最新动态...
[CompanyResearchAgent]: 发现重要信息：公司近期获得某大型订单...

[TechnicalAnalystAgent]: 分析K线形态...
[TechnicalAnalystAgent]: 支撑位10.8元，阻力位12.5元，突破概率70%

[ReportWriterAgent]: 正在生成分析报告...
[ReportWriterAgent]: 综合评分: 7.5/10
[ReportWriterAgent]: 推荐理由: 板块政策强支持，公司获重大订单，技术面底部震荡充分
[ReportWriterAgent]: 结果已写入数据库

任务完成！
```

## 10. 扩展方向

### 10.1 增加更多专家Agent
- RiskAssessmentAgent（风险评估）
- MacroEconomyAgent（宏观经济分析）
- SentimentAnalysisAgent（舆情分析）

### 10.2 多模态能力
- 使用GPT-4o的vision能力直接分析K线图
- 生成图表和可视化报告

### 10.3 实时更新
- 定期re-analysis已分析的股票
- 追踪推荐股票的实际表现
- 模型自我学习和优化

---

## 总结

这个设计方案充分利用了MAF Magentic的核心能力：
- ✅ 通过Manager实现动态任务分解和自适应规划
- ✅ 5个专家Agent各司其职，避免单一模型能力不足
- ✅ 双账本机制保证任务不遗漏、不重复
- ✅ 人在回路机制在关键决策点提供监督
- ✅ 事件驱动架构便于监控和调试
- ✅ 完整的数据闭环（数据库→分析→数据库）

这种架构既保证了分析的深度和准确性，又保持了灵活性和可扩展性。

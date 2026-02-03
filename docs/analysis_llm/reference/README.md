# 股票分析多Agent系统

基于 Microsoft Agent Framework (python-1.0.0b260128) Magentic编排的智能股票评估系统。

## 📋 项目简介

本系统使用MAF的Magentic编排模式，通过5个专家Agent协作完成股票分析：

1. **StockDataAgent** - 数据获取专家：从PostgreSQL读取K线数据，计算技术指标
2. **SectorResearchAgent** - 板块研究专家：分析板块热度、趋势和政策支持
3. **CompanyResearchAgent** - 公司研究专家：调研公司基本面和重大事件
4. **TechnicalAnalystAgent** - 技术分析专家：计算支撑阻力位，评估突破概率
5. **ReportWriterAgent** - 报告撰写专家：生成分析报告和推荐评分

系统专门针对具有"平底锅"特征的股票（曾经高位，后长期震荡），判断其6个月内的上涨潜力。

## 🎯 核心特性

- ✅ **Magentic智能编排**：Manager动态分解任务，自适应规划
- ✅ **双账本机制**：任务账本 + 进度账本，确保分析完整性
- ✅ **人在回路**：关键决策点支持人工审批
- ✅ **Web搜索能力**：自动搜索板块热度和公司动态
- ✅ **数据库集成**：读取历史K线，保存分析结果
- ✅ **结构化输出**：Markdown报告 + 数据库记录

## 🛠️ 技术栈

- **框架**：Microsoft Agent Framework (python-1.0.0b260128)
- **LLM**：OpenAI GPT-4o（推荐）
- **数据库**：PostgreSQL
- **数据处理**：pandas, numpy
- **异步**：asyncio, asyncpg

## 📦 安装

### 1. 克隆项目

```bash
git clone <your-repo>
cd stock-analysis-magentic
```

### 2. 创建虚拟环境

```bash
python3.12 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑.env文件，填写实际配置
vim .env
```

必需配置项：
```bash
DATABASE_DSN=postgresql://user:password@host:port/database
OPENAI_API_KEY=sk-your-api-key-here
```

### 5. 初始化数据库

```bash
# 运行数据库初始化脚本
python database.py
```

这将创建 `stock_analysis_results` 表。

## 🚀 使用方法

### 分析单支股票

```bash
python stock_analyzer.py
```

默认会分析 `300444.SZ`。修改 `stock_analyzer.py` 的 `main()` 函数来分析其他股票：

```python
# 分析单支股票
result = await analyzer.analyze_stock("300444.SZ")

# 分析结果
if result:
    print(f"推荐评分: {result['score']}/10")
    print(f"推荐理由: {result['reason']}")
```

### 批量分析

```python
# 在stock_analyzer.py的main()函数中取消注释：
stock_list = ["300444.SZ", "000001.SZ", "600519.SH"]
results = await analyzer.batch_analyze(stock_list, delay_seconds=10)

for code, result in results.items():
    if result:
        print(f"{code}: {result['score']}/10")
```

### 查看分析结果

```python
# 查询数据库
from database import StockDatabase
import asyncio

async def view_results():
    db = StockDatabase("postgresql://...")
    await db.connect()
    
    # 查看top推荐
    tops = await db.get_top_recommendations(limit=10, min_score=7.0)
    for item in tops:
        print(f"{item['code']}: {item['recommendation_score']}分 - {item['reason']}")
    
    await db.close()

asyncio.run(view_results())
```

## 📊 数据库结构

### stock_monthly_kline（输入表）

存储股票月K线数据：

```sql
CREATE TABLE stock_monthly_kline (
    month TIMESTAMP,
    code VARCHAR(20),
    name VARCHAR(50),
    open DECIMAL,
    high DECIMAL,
    low DECIMAL,
    close DECIMAL,
    volume BIGINT,
    amount DECIMAL
);
```

### stock_analysis_results（输出表）

存储分析结果：

```sql
CREATE TABLE stock_analysis_results (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    recommendation_score DECIMAL(3,1) CHECK (recommendation_score >= 0 AND recommendation_score <= 10),
    reason TEXT NOT NULL,
    analysis_detail JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 🎛️ 配置说明

### 环境变量

| 变量 | 说明 | 默认值 | 必需 |
|------|------|--------|------|
| DATABASE_DSN | PostgreSQL连接字符串 | - | ✅ |
| OPENAI_API_KEY | OpenAI API密钥 | - | ✅ |
| LLM_MODEL | 使用的模型 | gpt-4o | ❌ |
| MAX_STALL_COUNT | 最大停滞次数 | 3 | ❌ |
| ENABLE_PLAN_REVIEW | 启用计划审查 | true | ❌ |
| AUTO_APPROVE_PLAN | 自动批准计划 | false | ❌ |

### Magentic参数调优

```python
# 在stock_analyzer.py中调整
workflow = (
    MagenticBuilder()
    .participants(...)
    .with_standard_manager(
        agent=manager_agent,
        max_stall_count=3,    # 增加以提高鲁棒性
        max_reset_count=2     # 减少以节省Token
    )
    .with_plan_review(enable=True)  # 开发时启用，生产时可关闭
    .build()
)
```

## 📝 输出示例

### 控制台输出

```
============================================================
开始分析股票: 300444.SZ
分析时间: 2026-01-30 15:30:00
============================================================

[StockAnalysisManager]: 收到任务，开始制定分析计划...

========================================
【Manager提出的执行计划 - 需要您的审批】
========================================
1. [StockDataAgent] 查询300444.SZ的12个月K线数据
2. [StockDataAgent] 计算技术指标和平底锅特征
3. [SectorResearchAgent] 搜索股票所属板块
4. [SectorResearchAgent] 分析板块热度和趋势
5. [CompanyResearchAgent] 搜索公司最新动态
6. [CompanyResearchAgent] 识别催化剂事件
7. [TechnicalAnalystAgent] 计算支撑阻力位
8. [TechnicalAnalystAgent] 评估突破概率
9. [ReportWriterAgent] 生成分析报告
10. [ReportWriterAgent] 保存到数据库
========================================

>> 计划已批准，继续执行...

[StockDataAgent]: 正在查询数据库...
[StockDataAgent]: 获取到12条月K线记录
[StockDataAgent]: 峰值25.6元(2015-06)，当前11.5元，震荡102个月

[SectorResearchAgent]: 搜索板块信息...
[SectorResearchAgent]: 识别到板块：工业母机、专用设备
[SectorResearchAgent]: 板块热度评分：8.5/10

[CompanyResearchAgent]: 搜索公司新闻...
[CompanyResearchAgent]: 发现重大订单签订...

[TechnicalAnalystAgent]: 支撑10.8元，阻力12.5元，突破概率70%

[ReportWriterAgent]: 生成报告完成
[ReportWriterAgent]: 推荐评分7.5/10
[ReportWriterAgent]: 已保存到数据库

############################################################
分析完成！
############################################################

✓ 300444.SZ 分析成功完成

最终结果:
  推荐评分: 7.5/10
  推荐理由: 板块政策强支持，公司获重大订单，技术面底部震荡充分
```

### Markdown报告

```markdown
# 300444.SZ 国机精工 投资分析报告

生成时间：2026-01-30 15:30:00

## 📊 基本信息
- 当前价格: 11.50元
- 峰值价格: 25.60元 (2015-06)
- 震荡时长: 102个月

## 🔍 平底锅形态分析
- 形态成熟度: 末期
- 震荡区间: 10.8-12.5元
- 当前位置: 中位
- 成交量趋势: 温和放量

## 📈 板块分析
- 主要板块: 工业母机、专用设备
- 概念板块: 工业4.0、高端装备
- 板块热度: 8.5/10分
- 政策支持: 强
- 关键催化剂: 国产替代加速、制造业转型升级

## 🏢 公司基本面
- 财务状况: 改善
- 重大事件: 签订XX亿重大订单
- 竞争地位: 行业前三
- 主要风险: 市场竞争加剧

## 📉 技术分析
- 支撑位: 10.80元
- 阻力位: 12.50元
- 突破概率: 70%

## 💡 综合评估
**推荐评分: 7.5/10**

**推荐理由**:
板块政策强支持，公司获重大订单，技术面底部震荡充分，6个月内突破概率较高

**风险提示**:
需关注订单执行进度和市场竞争态势

---
*本报告由AI生成，仅供参考，不构成投资建议*
```

## 🔧 开发指南

### 添加新的Agent

1. 在 `agents.py` 中定义新Agent：

```python
def create_new_agent(chat_client: OpenAIChatClient) -> ChatAgent:
    system_message = """你是xxx专家..."""
    
    tools = [your_tools]
    
    return ChatAgent(
        name="NewAgent",
        description="新Agent的职责描述",
        model=chat_client,
        system_message=system_message,
        tools=tools
    )
```

2. 在 `stock_analyzer.py` 中注册：

```python
new_agent = create_new_agent(chat_client)

workflow = (
    MagenticBuilder()
    .participants(
        stock_data_agent,
        sector_research_agent,
        company_research_agent,
        technical_analyst_agent,
        report_writer_agent,
        new_agent  # 添加新Agent
    )
    .with_standard_manager(...)
    .build()
)
```

### 添加新的工具函数

在 `tools.py` 中定义：

```python
def new_tool() -> Tool:
    async def new_function(param: str) -> str:
        # 实现工具逻辑
        return result
    
    return Tool(
        function=new_function,
        name="new_tool",
        description="工具描述"
    )
```

### 自定义评分算法

修改 `ReportWriterAgent` 的 `system_message`：

```python
system_message = """
评分算法：
基础分 = 3分
板块评分（最高4分）:  # 调整权重
- ...
"""
```

## 🐛 故障排查

### 常见问题

**Q: 数据库连接失败**
```
A: 检查DATABASE_DSN格式和数据库服务状态
   正确格式: postgresql://user:password@host:port/database
```

**Q: Agent停滞不前**
```
A: 增加max_stall_count或检查工具函数是否正常工作
   可以在Manager的system_message中增加更详细的指导
```

**Q: OpenAI API超时**
```
A: 
1. 检查网络连接
2. 降低temperature（减少生成时间）
3. 在config中增加timeout设置
```

**Q: 评分不合理**
```
A: 检查各Agent输出的数据质量
   调整ReportWriterAgent的评分算法权重
```

## 📚 相关文档

- [MAF官方文档](https://learn.microsoft.com/en-us/agent-framework/)
- [Magentic编排文档](https://learn.microsoft.com/en-us/agent-framework/user-guide/workflows/orchestrations/magentic)
- [项目设计文档](./stock_analysis_magentic_design.md)

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT License

## ⚠️ 免责声明

本系统生成的分析报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。

---

**开发者**: Claude & You
**版本**: 1.0.0
**最后更新**: 2026-01-30

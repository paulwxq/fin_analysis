# 快速开始指南

## 前置要求

1. **Python 3.12+** 已安装
2. **PostgreSQL数据库** 已运行，包含 `stock_monthly_kline` 表
3. **OpenAI API Key** 已获取

## 5分钟快速开始

### 步骤1: 安装依赖

```bash
# 创建虚拟环境
python3.12 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 步骤2: 配置环境

```bash
# 复制配置文件
cp .env.example .env

# 编辑配置（使用你喜欢的编辑器）
nano .env
```

**必须修改的配置项**：
```bash
DATABASE_DSN=postgresql://你的用户名:你的密码@localhost:5432/fin_db
OPENAI_API_KEY=sk-你的API密钥
```

### 步骤3: 初始化数据库

```bash
# 创建分析结果表
python database.py
```

你应该看到：
```
✓ 数据库连接成功
✓ stock_analysis_results表已创建/验证
```

### 步骤4: 运行第一次分析

```bash
# 默认分析300444.SZ
python stock_analyzer.py
```

## 执行流程

1. **系统初始化**
   - 连接数据库
   - 初始化LLM客户端
   - 创建5个专家Agent
   - 构建Magentic Workflow

2. **Manager生成计划**
   ```
   ========================================
   【Manager提出的执行计划】
   ========================================
   1. [StockDataAgent] 查询K线数据
   2. [StockDataAgent] 计算技术指标
   3. [SectorResearchAgent] 搜索板块
   ...
   ```

3. **人工审批**（如果启用）
   ```
   请输入 (回车=批准, 文字=修改意见, 'q'=取消):
   ```
   - 按回车 → 批准并继续
   - 输入文字 → 根据意见修改计划
   - 输入 'q' → 取消任务

4. **自动执行**
   - Manager按计划调度各Agent
   - 实时显示执行过程
   - 自动处理错误和重试

5. **生成结果**
   - Markdown格式报告
   - 推荐评分（0-10分）
   - 保存到数据库

## 修改分析目标

编辑 `stock_analyzer.py` 的 `main()` 函数：

```python
async def main():
    config = Config.from_env()
    analyzer = StockAnalyzer(config)
    await analyzer.initialize()
    
    # 修改这里 - 分析你想要的股票
    result = await analyzer.analyze_stock("你的股票代码.SZ")
    
    # 或批量分析
    # stock_list = ["300444.SZ", "000001.SZ", "600519.SH"]
    # results = await analyzer.batch_analyze(stock_list)
    
    await analyzer.close()
```

## 查看分析结果

### 方法1: 直接查询数据库

```sql
-- 查看所有分析结果
SELECT code, recommendation_score, reason, created_at 
FROM stock_analysis_results 
ORDER BY recommendation_score DESC;

-- 查看高分推荐
SELECT * FROM stock_analysis_results 
WHERE recommendation_score >= 7.0
ORDER BY recommendation_score DESC;
```

### 方法2: 使用Python脚本

创建 `view_results.py`：

```python
from database import StockDatabase
import asyncio

async def main():
    db = StockDatabase("postgresql://...")
    await db.connect()
    
    # 获取top 10推荐
    tops = await db.get_top_recommendations(limit=10, min_score=7.0)
    
    print("\n📊 Top推荐股票:")
    print("-" * 80)
    for item in tops:
        print(f"{item['code']:15} {item['recommendation_score']}/10  {item['reason']}")
    print("-" * 80)
    
    await db.close()

asyncio.run(main())
```

## 调试技巧

### 1. 启用详细日志

```bash
# 在.env中设置
LOG_LEVEL=DEBUG
```

### 2. 自动批准计划（跳过人工审批）

```bash
# 在.env中设置
AUTO_APPROVE_PLAN=true
```

### 3. 减少Token消耗

```python
# 在stock_analyzer.py中修改
.with_standard_manager(
    max_stall_count=2,  # 减少停滞容忍度
    max_reset_count=1   # 减少重置次数
)
```

### 4. 测试单个Agent

创建 `test_agent.py`：

```python
from agents import create_stock_data_agent
from agent_framework.openai import OpenAIChatClient
from database import StockDatabase
import asyncio

async def test():
    client = OpenAIChatClient(model="gpt-4o", api_key="...")
    db = StockDatabase("postgresql://...")
    await db.connect()
    
    agent = create_stock_data_agent(client, db)
    
    # 测试Agent
    result = await agent.run("查询300444.SZ的K线数据")
    print(result)
    
    await db.close()

asyncio.run(test())
```

## 常见问题速查

### Q: 如何更换股票代码？
```python
# 修改stock_analyzer.py中的
await analyzer.analyze_stock("你的代码.SZ")
```

### Q: 如何批量分析？
```python
stock_list = ["代码1.SZ", "代码2.SH", "代码3.SZ"]
results = await analyzer.batch_analyze(stock_list, delay_seconds=10)
```

### Q: 如何禁用人工审批？
```bash
# .env中设置
ENABLE_PLAN_REVIEW=false
```

### Q: 数据库表不存在？
```bash
python database.py  # 运行初始化脚本
```

### Q: API超时？
```bash
# .env中降低temperature或增加timeout
LLM_TEMPERATURE=0.3
```

## 下一步

- 📖 阅读 [README.md](./README.md) 了解完整功能
- 📝 阅读 [stock_analysis_magentic_design.md](./stock_analysis_magentic_design.md) 了解系统设计
- 🔧 自定义Agent和评分算法
- 🚀 部署到生产环境

## 获取帮助

- 检查日志文件
- 查看MAF官方文档
- 提交Issue到项目仓库

---

**祝你分析愉快！** 📈

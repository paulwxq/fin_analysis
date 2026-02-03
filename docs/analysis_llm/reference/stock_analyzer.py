"""
股票分析多Agent系统 - 主程序
基于Microsoft Agent Framework (python-1.0.0b260128) Magentic编排
"""

import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

from agent_framework import (
    MagenticBuilder,
    ChatAgent,
    StandardMagenticManager,
    WorkflowOutputEvent,
    RequestInfoEvent,
    AgentRunUpdateEvent,
    MagenticPlanReviewRequest
)
from agent_framework.openai import OpenAIChatClient

from agents import (
    create_stock_data_agent,
    create_sector_research_agent,
    create_company_research_agent,
    create_technical_analyst_agent,
    create_report_writer_agent
)
from database import StockDatabase
from config import Config


class StockAnalyzer:
    """股票分析系统主类"""
    
    def __init__(self, config: Config):
        self.config = config
        self.db = StockDatabase(config.database_dsn)
        self.workflow = None
        
    async def initialize(self):
        """初始化系统"""
        # 连接数据库
        await self.db.connect()
        print("✓ 数据库连接成功")
        
        # 创建LLM客户端
        chat_client = OpenAIChatClient(
            model=self.config.llm_model,
            api_key=self.config.openai_api_key,
            temperature=0.7
        )
        print(f"✓ LLM客户端初始化完成 (模型: {self.config.llm_model})")
        
        # 创建各个专家Agent
        stock_data_agent = create_stock_data_agent(chat_client, self.db)
        sector_research_agent = create_sector_research_agent(chat_client)
        company_research_agent = create_company_research_agent(chat_client)
        technical_analyst_agent = create_technical_analyst_agent(chat_client)
        report_writer_agent = create_report_writer_agent(chat_client, self.db)
        print("✓ 5个专家Agent创建完成")
        
        # 创建Manager Agent
        manager_agent = ChatAgent(
            name="StockAnalysisManager",
            description="股票分析任务的总指挥，负责协调各专家Agent完成股票评估任务",
            model=chat_client,
            system_message="""
你是一位资深的股票分析经理。你需要协调5位专家完成股票分析任务：
1. StockDataAgent - 数据获取专家
2. SectorResearchAgent - 板块研究专家  
3. CompanyResearchAgent - 公司研究专家
4. TechnicalAnalystAgent - 技术分析专家
5. ReportWriterAgent - 报告撰写专家

你的职责：
- 将复杂任务分解为清晰的子任务
- 根据执行情况动态调整计划
- 确保信息收集全面且高质量
- 最终生成有价值的投资建议

分析重点：
- 股票的"平底锅"形态是否成熟
- 板块是否有催化剂和政策支持
- 公司基本面是否改善
- 技术面是否具备突破条件
"""
        )
        
        # 构建Magentic Workflow
        self.workflow = (
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
                max_stall_count=self.config.max_stall_count,
                max_reset_count=self.config.max_reset_count
            )
            .with_plan_review(enable=self.config.enable_plan_review)
            .build()
        )
        print("✓ Magentic Workflow构建完成")
        print("\n" + "="*60)
        print("系统初始化完成，准备开始分析")
        print("="*60 + "\n")
    
    async def analyze_stock(
        self, 
        stock_code: str,
        verbose: bool = True
    ) -> Optional[Dict]:
        """
        分析单支股票
        
        Args:
            stock_code: 股票代码，如 "300444.SZ"
            verbose: 是否显示详细输出
            
        Returns:
            分析结果字典，包含评分、理由等
        """
        # 构建任务描述
        task = f"""
请分析股票 {stock_code} 是否值得在未来6个月内买入。

背景信息：
- 该股票已被初步筛选，具有"平底锅"特征（曾经高位，后长期震荡）
- 我们需要评估其在震荡末期是否有向上突破的潜力

请协调各专家Agent完成以下工作：

1. 【数据获取】(StockDataAgent)
   - 从PostgreSQL数据库获取该股票过去12-24个月的月K线数据
   - 计算关键技术指标
   - 验证平底锅形态特征的参数

2. 【板块研究】(SectorResearchAgent)  
   - 使用web_search识别该股票所属的主要板块和概念板块
   - 分析各板块最近3-6个月的新闻热度和政策支持力度
   - 对比同板块龙头股的表现
   - 评估板块的未来趋势

3. 【公司研究】(CompanyResearchAgent)
   - 使用web_search搜索公司最近6个月的重大新闻
   - 关注：财报、重大合同、新产品、管理层变动等
   - 识别可能的催化剂事件
   - 评估公司在行业中的竞争地位

4. 【技术分析】(TechnicalAnalystAgent)
   - 分析K线图形态（如有PNG图片可读取）
   - 计算支撑位和阻力位
   - 评估成交量变化趋势
   - 结合板块信息判断向上突破的概率

5. 【报告生成】(ReportWriterAgent)
   - 综合所有研究结果
   - 生成结构化的Markdown分析报告
   - 计算综合推荐评分（0-10分）
   - 提炼核心推荐理由（100字以内）
   - 将结果写入数据库的stock_analysis_results表

评分标准：
- 0-3分：不建议购买（板块冷淡、公司基本面差、技术面弱）
- 4-6分：观望（有一定机会但不确定性大）
- 7-8分：建议关注（板块有热度、有催化剂、技术面改善）
- 9-10分：强烈推荐（多重利好叠加、突破概率高）

请确保分析过程严谨、数据来源可靠、结论有理有据。
"""
        
        print(f"\n{'='*60}")
        print(f"开始分析股票: {stock_code}")
        print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        pending_responses = None
        output_event = None
        
        try:
            # 事件驱动执行循环
            while not output_event:
                # 根据是否有待发送的响应选择执行方式
                if pending_responses:
                    stream = self.workflow.send_responses_streaming(pending_responses)
                else:
                    stream = self.workflow.run_stream(task)
                
                pending_responses = None
                
                # 处理事件流
                async for event in stream:
                    # Agent输出事件
                    if isinstance(event, AgentRunUpdateEvent):
                        if verbose and event.data.text:
                            print(f"[{event.executor_id}]: {event.data.text}", end="", flush=True)
                    
                    # 计划审查请求（人在回路）
                    elif isinstance(event, RequestInfoEvent):
                        if isinstance(event.data, MagenticPlanReviewRequest):
                            review_request = event.data
                            
                            print("\n\n" + "="*60)
                            print("【Manager提出的执行计划 - 需要您的审批】")
                            print("="*60)
                            print(review_request.plan.text)
                            print("="*60 + "\n")
                            
                            if self.config.auto_approve_plan:
                                print(">> 自动批准模式：计划已批准\n")
                                response = review_request.approve()
                            else:
                                user_input = input("请输入 (回车=批准, 文字=修改意见, 'q'=取消): ").strip()
                                
                                if user_input.lower() == 'q':
                                    print(">> 用户取消分析任务\n")
                                    return None
                                elif user_input == "":
                                    print(">> 计划已批准，继续执行...\n")
                                    response = review_request.approve()
                                else:
                                    print(f">> 计划已根据意见修改: {user_input}\n")
                                    response = review_request.revise(user_input)
                            
                            pending_responses = {event.request_id: response}
                    
                    # 工作流完成事件
                    elif isinstance(event, WorkflowOutputEvent):
                        output_event = event
                        
                        if verbose:
                            print("\n\n" + "#"*60)
                            print("分析完成！")
                            print("#"*60)
            
            # 解析结果
            result = output_event.data
            print(f"\n✓ {stock_code} 分析成功完成")
            return result
            
        except Exception as e:
            print(f"\n✗ {stock_code} 分析失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    async def batch_analyze(
        self,
        stock_codes: List[str],
        delay_seconds: int = 5
    ) -> Dict[str, Optional[Dict]]:
        """
        批量分析多支股票
        
        Args:
            stock_codes: 股票代码列表
            delay_seconds: 每次分析之间的延迟（秒），避免API限流
            
        Returns:
            {stock_code: result} 字典
        """
        results = {}
        total = len(stock_codes)
        
        print(f"\n开始批量分析 {total} 支股票")
        print("="*60 + "\n")
        
        for i, code in enumerate(stock_codes, 1):
            print(f"\n进度: [{i}/{total}] 分析 {code}")
            
            result = await self.analyze_stock(code, verbose=False)
            results[code] = result
            
            if result:
                score = result.get('score', 'N/A')
                print(f"  评分: {score}/10")
            
            # 延迟避免限流
            if i < total:
                print(f"  等待 {delay_seconds} 秒...")
                await asyncio.sleep(delay_seconds)
            
            print("-"*60)
        
        # 汇总统计
        successful = sum(1 for r in results.values() if r is not None)
        print(f"\n批量分析完成: {successful}/{total} 成功")
        
        return results
    
    async def close(self):
        """关闭资源"""
        if self.db and self.db.pool:
            await self.db.pool.close()
            print("\n✓ 数据库连接已关闭")


async def main():
    """主函数"""
    # 加载配置
    config = Config.from_env()
    
    # 创建分析器
    analyzer = StockAnalyzer(config)
    await analyzer.initialize()
    
    # 示例1: 分析单支股票
    result = await analyzer.analyze_stock("300444.SZ")
    
    if result:
        print("\n最终结果:")
        print(f"  推荐评分: {result.get('score', 'N/A')}/10")
        print(f"  推荐理由: {result.get('reason', 'N/A')}")
    
    # 示例2: 批量分析（取消注释以启用）
    # stock_list = ["300444.SZ", "000001.SZ", "600519.SH"]
    # results = await analyzer.batch_analyze(stock_list, delay_seconds=10)
    
    # 关闭资源
    await analyzer.close()


if __name__ == "__main__":
    asyncio.run(main())

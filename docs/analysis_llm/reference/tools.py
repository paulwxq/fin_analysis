"""
工具函数模块
定义各Agent使用的工具函数
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json

from agent_framework.tools import Tool, web_search
from database import StockDatabase


# ========== StockDataAgent 工具 ==========

def query_stock_kline_tool(db: StockDatabase) -> Tool:
    """创建查询K线数据的工具"""
    
    async def query_stock_kline(
        code: str,
        months: int = 12
    ) -> str:
        """
        从数据库查询股票的月K线数据
        
        Args:
            code: 股票代码，如 "300444.SZ"
            months: 查询最近几个月的数据，默认12个月
            
        Returns:
            JSON格式的K线数据
        """
        try:
            df = await db.query_kline_data(code, months)
            
            if df.empty:
                return json.dumps({
                    "success": False,
                    "message": f"未找到股票 {code} 的数据",
                    "data": None
                }, ensure_ascii=False)
            
            # 转换为可序列化的格式
            data_dict = {
                "success": True,
                "code": code,
                "name": df.iloc[0]['name'] if not df.empty else "",
                "records": len(df),
                "start_month": str(df.iloc[0]['month']),
                "end_month": str(df.iloc[-1]['month']),
                "data": df.to_dict('records')
            }
            
            return json.dumps(data_dict, ensure_ascii=False, default=str)
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"查询失败: {str(e)}",
                "data": None
            }, ensure_ascii=False)
    
    return Tool(
        function=query_stock_kline,
        name="query_stock_kline",
        description="从PostgreSQL数据库查询指定股票的月K线历史数据"
    )


def calculate_indicators_tool() -> Tool:
    """创建计算技术指标的工具"""
    
    async def calculate_indicators(kline_data_json: str) -> str:
        """
        基于K线数据计算技术指标
        
        Args:
            kline_data_json: K线数据的JSON字符串（来自query_stock_kline）
            
        Returns:
            JSON格式的技术指标
        """
        try:
            data = json.loads(kline_data_json)
            
            if not data.get('success') or not data.get('data'):
                return json.dumps({
                    "success": False,
                    "message": "输入数据无效"
                }, ensure_ascii=False)
            
            df = pd.DataFrame(data['data'])
            
            # 转换数据类型
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 识别平底锅特征
            peak_idx = df['close'].idxmax()
            peak_price = float(df.loc[peak_idx, 'close'])
            peak_time = str(df.loc[peak_idx, 'month'])
            current_price = float(df.iloc[-1]['close'])
            
            # 震荡期数据
            oscillation_df = df[df.index > peak_idx] if peak_idx < len(df) - 1 else df.tail(6)
            
            # 计算振幅
            if not oscillation_df.empty:
                volatility = float(
                    (oscillation_df['high'] - oscillation_df['low']).mean() / 
                    oscillation_df['close'].mean()
                )
            else:
                volatility = 0.0
            
            # 成交量趋势
            if len(oscillation_df) >= 6:
                recent_volume = oscillation_df['volume'].iloc[-3:].mean()
                earlier_volume = oscillation_df['volume'].iloc[-6:-3].mean()
                volume_trend = "递增" if recent_volume > earlier_volume * 1.1 else \
                              "递减" if recent_volume < earlier_volume * 0.9 else "平稳"
            else:
                volume_trend = "数据不足"
            
            # 当前位置
            if not oscillation_df.empty:
                osc_high = float(oscillation_df['high'].max())
                osc_low = float(oscillation_df['low'].min())
                position_pct = (current_price - osc_low) / (osc_high - osc_low) * 100 if osc_high > osc_low else 50
                
                if position_pct < 33:
                    position = "低位"
                elif position_pct > 67:
                    position = "高位"
                else:
                    position = "中位"
            else:
                position = "无法判断"
                osc_high = current_price
                osc_low = current_price
            
            # 判断是否符合平底锅特征
            is_pan_bottom = (
                volatility < 0.15 and  # 振幅小于15%
                len(oscillation_df) >= 6 and  # 至少震荡6个月
                (peak_price - current_price) / peak_price > 0.3  # 从峰值回落超过30%
            )
            
            indicators = {
                "success": True,
                "pan_bottom_features": {
                    "is_pan_bottom": is_pan_bottom,
                    "peak_price": peak_price,
                    "peak_time": peak_time,
                    "current_price": current_price,
                    "price_drop_pct": round((current_price - peak_price) / peak_price * 100, 2),
                    "oscillation_months": len(oscillation_df),
                    "oscillation_range": {
                        "high": float(osc_high),
                        "low": float(osc_low)
                    }
                },
                "technical_indicators": {
                    "volatility": round(volatility, 4),
                    "volume_trend": volume_trend,
                    "current_position": position
                },
                "summary": f"该股票从{peak_time}的峰值{peak_price}元回落至当前{current_price}元，"
                          f"在震荡区间({osc_low:.2f}-{osc_high:.2f}元)内已震荡{len(oscillation_df)}个月，"
                          f"振幅{volatility*100:.1f}%，成交量{volume_trend}，当前处于震荡区间{position}。"
            }
            
            return json.dumps(indicators, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"计算失败: {str(e)}"
            }, ensure_ascii=False)
    
    return Tool(
        function=calculate_indicators,
        name="calculate_indicators",
        description="基于K线数据计算技术指标和平底锅形态特征"
    )


# ========== SectorResearchAgent 工具 ==========

def web_search_tool() -> Tool:
    """Web搜索工具（使用MAF内置）"""
    return web_search


def search_sectors_tool() -> Tool:
    """创建搜索股票所属板块的工具"""
    
    async def search_sectors(
        stock_code: str,
        stock_name: str
    ) -> str:
        """
        搜索股票所属的行业板块和概念板块
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            JSON格式的板块信息
        """
        # 这里实际应该调用web_search，这里提供框架
        # 在实际使用中，Agent会自己调用web_search
        
        return json.dumps({
            "message": "请使用web_search工具搜索以下关键词:",
            "search_queries": [
                f"{stock_name} 所属板块",
                f"{stock_name} 行业分类",
                f"{stock_name} 概念股",
                f"{stock_code} 板块"
            ],
            "tips": "从搜索结果中提取主板块（如'新能源'、'半导体'）和概念板块（如'碳中和'、'工业4.0'）"
        }, ensure_ascii=False)
    
    return Tool(
        function=search_sectors,
        name="search_sectors",
        description="生成搜索股票所属板块的查询建议"
    )


def analyze_sector_hotness_tool() -> Tool:
    """创建分析板块热度的工具"""
    
    async def analyze_sector_hotness(
        sector_name: str,
        months: int = 6
    ) -> str:
        """
        分析板块的热度趋势
        
        Args:
            sector_name: 板块名称
            months: 分析最近几个月
            
        Returns:
            板块热度分析建议
        """
        current_year = datetime.now().year
        previous_year = current_year - 1
        
        return json.dumps({
            "message": f"请使用web_search工具搜索以下关键词来分析'{sector_name}'板块热度:",
            "search_queries": [
                f"{sector_name}板块 {current_year} 趋势",
                f"{sector_name} 政策支持 {previous_year} {current_year}",
                f"{sector_name} 龙头股 涨幅",
                f"{sector_name}行业 投资机会"
            ],
            "analysis_framework": {
                "新闻热度": "统计最近3-6个月的相关新闻数量和质量",
                "政策支持": "查找国家或地方政策、产业规划",
                "资金流向": "观察板块内龙头股的表现和成交量",
                "行业景气度": "关注行业订单、业绩增长等数据"
            },
            "scoring_guide": {
                "8-10分": "多重政策利好 + 龙头股大涨 + 媒体高度关注",
                "5-7分": "有一定支持 + 行业稳定发展",
                "1-4分": "缺乏关注 + 政策支持弱 + 资金流出"
            }
        }, ensure_ascii=False)
    
    return Tool(
        function=analyze_sector_hotness,
        name="analyze_sector_hotness",
        description="生成分析板块热度的搜索策略和评分指南"
    )


# ========== CompanyResearchAgent 工具 ==========

def search_company_news_tool() -> Tool:
    """创建搜索公司新闻的工具"""
    
    async def search_company_news(
        stock_code: str,
        stock_name: str,
        months: int = 6
    ) -> str:
        """
        生成搜索公司新闻的查询策略
        
        Args:
            stock_code: 股票代码
            stock_name: 公司名称
            months: 搜索最近几个月
            
        Returns:
            搜索策略建议
        """
        current_year = datetime.now().year
        
        return json.dumps({
            "message": f"请使用web_search工具搜索以下关键词来调研{stock_name}:",
            "search_categories": {
                "财务信息": [
                    f"{stock_name} 财报 {current_year}",
                    f"{stock_name} 业绩预告",
                    f"{stock_code} 营收 净利润"
                ],
                "重大事件": [
                    f"{stock_name} 重大合同 {current_year}",
                    f"{stock_name} 新产品 新技术",
                    f"{stock_name} 并购 合作"
                ],
                "竞争地位": [
                    f"{stock_name} 市场份额",
                    f"{stock_name} 行业地位 排名",
                    f"{stock_name} 竞争对手"
                ],
                "风险因素": [
                    f"{stock_name} 负面新闻",
                    f"{stock_name} 诉讼 处罚",
                    f"{stock_name} 风险提示"
                ]
            },
            "catalyst_checklist": [
                "重大合同签订（特别是超过年营收10%的订单）",
                "新产品发布（技术突破、市场前景好）",
                "业绩超预期（增长率显著高于行业平均）",
                "政策倾斜（获得政府补贴、项目支持）",
                "资产注入（大股东注入优质资产）",
                "管理层增持（表明内部看好）"
            ],
            "evaluation_framework": {
                "财务健康": "营收和利润是否持续增长",
                "事件影响": "重大事件对未来业绩的提升程度",
                "竞争优势": "是否有独特技术或市场地位",
                "风险程度": "是否存在重大不确定性"
            }
        }, ensure_ascii=False)
    
    return Tool(
        function=search_company_news,
        name="search_company_news",
        description="生成搜索公司新闻和基本面信息的查询策略"
    )


# ========== TechnicalAnalystAgent 工具 ==========

def analyze_kline_image_tool() -> Tool:
    """创建分析K线图片的工具"""
    
    async def analyze_kline_image(
        image_path: str
    ) -> str:
        """
        分析K线图图片（如果提供）
        
        Args:
            image_path: K线图PNG文件路径
            
        Returns:
            图片分析结果
        """
        # 在实际实现中，这里会使用GPT-4o的vision能力
        # 或其他图像识别模型
        
        if not Path(image_path).exists():
            return json.dumps({
                "success": False,
                "message": f"图片文件不存在: {image_path}"
            }, ensure_ascii=False)
        
        return json.dumps({
            "success": True,
            "message": "图片分析功能需要vision模型支持",
            "tip": "建议基于K线数据进行技术分析，效果更可靠"
        }, ensure_ascii=False)
    
    return Tool(
        function=analyze_kline_image,
        name="analyze_kline_image",
        description="分析PNG格式的K线图（需要vision模型支持）"
    )


def calculate_support_resistance_tool() -> Tool:
    """创建计算支撑阻力位的工具"""
    
    async def calculate_support_resistance(
        kline_data_json: str,
        sector_hotness_score: float = 5.0,
        has_catalyst: bool = False
    ) -> str:
        """
        计算支撑位、阻力位和突破概率
        
        Args:
            kline_data_json: K线数据JSON
            sector_hotness_score: 板块热度评分(0-10)
            has_catalyst: 是否有重大催化剂
            
        Returns:
            技术分析结果
        """
        try:
            data = json.loads(kline_data_json)
            
            if not data.get('success') or not data.get('data'):
                return json.dumps({
                    "success": False,
                    "message": "输入数据无效"
                }, ensure_ascii=False)
            
            df = pd.DataFrame(data['data'])
            
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 找到峰值后的震荡区间
            peak_idx = df['close'].idxmax()
            oscillation_df = df[df.index > peak_idx] if peak_idx < len(df) - 1 else df.tail(12)
            
            if oscillation_df.empty:
                oscillation_df = df.tail(6)
            
            # 计算支撑位和阻力位
            support_level = float(oscillation_df['low'].min())
            resistance_level = float(oscillation_df['high'].max())
            current_price = float(df.iloc[-1]['close'])
            
            # 形态成熟度评分（0-10）
            oscillation_months = len(oscillation_df)
            if oscillation_months >= 18:
                maturity_score = 10
            elif oscillation_months >= 12:
                maturity_score = 7
            elif oscillation_months >= 6:
                maturity_score = 5
            else:
                maturity_score = 3
            
            # 成交量评分（0-10）
            if len(oscillation_df) >= 6:
                recent_volume = oscillation_df['volume'].iloc[-3:].mean()
                earlier_volume = oscillation_df['volume'].iloc[-6:-3].mean()
                
                if recent_volume > earlier_volume * 1.3:
                    volume_score = 8  # 明显放量
                elif recent_volume > earlier_volume * 1.1:
                    volume_score = 6  # 温和放量
                elif recent_volume > earlier_volume * 0.9:
                    volume_score = 5  # 平稳
                else:
                    volume_score = 3  # 缩量
            else:
                volume_score = 5
            
            # 计算突破概率
            # 权重：形态成熟度30%，板块热度40%，催化剂30%
            catalyst_score = 8 if has_catalyst else 3
            
            breakout_probability = (
                maturity_score * 0.3 +
                sector_hotness_score * 0.4 +
                catalyst_score * 0.3
            ) * 10  # 转换为百分比
            
            breakout_probability = min(95, max(10, breakout_probability))  # 限制在10-95%
            
            # 目标价位（假设突破后上涨空间）
            if breakout_probability > 70:
                upside_potential = 0.3  # 30%上涨空间
            elif breakout_probability > 50:
                upside_potential = 0.2
            else:
                upside_potential = 0.1
            
            target_price = resistance_level * (1 + upside_potential)
            
            result = {
                "success": True,
                "support_level": round(support_level, 2),
                "resistance_level": round(resistance_level, 2),
                "current_price": round(current_price, 2),
                "technical_scores": {
                    "maturity_score": maturity_score,
                    "volume_score": volume_score,
                    "sector_score": sector_hotness_score,
                    "catalyst_score": catalyst_score
                },
                "breakout_analysis": {
                    "probability_pct": round(breakout_probability, 1),
                    "target_price": round(target_price, 2),
                    "upside_potential_pct": round(upside_potential * 100, 1)
                },
                "summary": f"当前价格{current_price:.2f}元，支撑位{support_level:.2f}元，"
                          f"阻力位{resistance_level:.2f}元。"
                          f"综合形态成熟度、板块热度和催化剂因素，"
                          f"预计6个月内突破阻力位的概率为{breakout_probability:.0f}%。"
            }
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"计算失败: {str(e)}"
            }, ensure_ascii=False)
    
    return Tool(
        function=calculate_support_resistance,
        name="calculate_support_resistance",
        description="计算支撑位、阻力位和向上突破概率"
    )


# ========== ReportWriterAgent 工具 ==========

def generate_markdown_report_tool() -> Tool:
    """创建生成Markdown报告的工具"""
    
    async def generate_markdown_report(
        stock_code: str,
        stock_name: str,
        analysis_data: str
    ) -> str:
        """
        生成Markdown格式的分析报告
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            analysis_data: 所有分析数据的JSON字符串
            
        Returns:
            Markdown格式的报告
        """
        try:
            data = json.loads(analysis_data)
            
            report = f"""# {stock_code} {stock_name} 投资分析报告

生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 📊 基本信息

{data.get('basic_info', '暂无数据')}

## 🔍 平底锅形态分析

{data.get('pan_bottom_analysis', '暂无数据')}

## 📈 板块分析

{data.get('sector_analysis', '暂无数据')}

## 🏢 公司基本面

{data.get('company_analysis', '暂无数据')}

## 📉 技术分析

{data.get('technical_analysis', '暂无数据')}

## 💡 综合评估

{data.get('evaluation', '暂无数据')}

---
*本报告由AI生成，仅供参考，不构成投资建议*
"""
            
            return report
            
        except Exception as e:
            return f"# 报告生成失败\n\n错误信息：{str(e)}"
    
    return Tool(
        function=generate_markdown_report,
        name="generate_markdown_report",
        description="基于分析数据生成Markdown格式的投资分析报告"
    )


def save_to_database_tool(db: StockDatabase) -> Tool:
    """创建保存结果到数据库的工具"""
    
    async def save_to_database(
        stock_code: str,
        recommendation_score: float,
        reason: str,
        analysis_detail: Optional[str] = None
    ) -> str:
        """
        将分析结果保存到数据库
        
        Args:
            stock_code: 股票代码
            recommendation_score: 推荐评分(0-10)
            reason: 推荐理由（简短，100字以内）
            analysis_detail: 详细分析数据（JSON字符串，可选）
            
        Returns:
            保存结果
        """
        try:
            # 验证评分范围
            if not 0 <= recommendation_score <= 10:
                return json.dumps({
                    "success": False,
                    "message": f"评分必须在0-10之间，当前值: {recommendation_score}"
                }, ensure_ascii=False)
            
            # 解析详细数据
            detail_dict = None
            if analysis_detail:
                try:
                    detail_dict = json.loads(analysis_detail)
                except:
                    pass
            
            # 保存到数据库
            await db.insert_analysis_result(
                code=stock_code,
                score=recommendation_score,
                reason=reason,
                detail=detail_dict
            )
            
            return json.dumps({
                "success": True,
                "message": f"成功保存 {stock_code} 的分析结果",
                "code": stock_code,
                "score": recommendation_score
            }, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"保存失败: {str(e)}"
            }, ensure_ascii=False)
    
    return Tool(
        function=save_to_database,
        name="save_to_database",
        description="将分析结果（评分、理由、详情）保存到stock_analysis_results表"
    )


# 导出所有工具创建函数
__all__ = [
    'query_stock_kline_tool',
    'calculate_indicators_tool',
    'web_search_tool',
    'search_sectors_tool',
    'analyze_sector_hotness_tool',
    'search_company_news_tool',
    'analyze_kline_image_tool',
    'calculate_support_resistance_tool',
    'generate_markdown_report_tool',
    'save_to_database_tool'
]

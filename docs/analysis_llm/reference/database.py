"""
数据库操作模块
负责PostgreSQL数据库的连接和操作
"""

import asyncpg
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json


class StockDatabase:
    """股票数据库操作类"""
    
    def __init__(self, dsn: str):
        """
        初始化数据库连接
        
        Args:
            dsn: PostgreSQL连接字符串
                 格式: postgresql://user:password@host:port/database
                 示例: postgresql://postgres:password@localhost:5432/fin_db
        """
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """创建连接池"""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            
            # 测试连接
            async with self.pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                print(f"数据库连接成功: {version.split(',')[0]}")
    
    async def query_kline_data(
        self,
        code: str,
        months: int = 12
    ) -> pd.DataFrame:
        """
        查询股票的月K线数据
        
        Args:
            code: 股票代码，如 "300444.SZ"
            months: 查询最近几个月的数据
            
        Returns:
            包含K线数据的DataFrame
        """
        if self.pool is None:
            raise RuntimeError("数据库未连接，请先调用connect()")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 30)
        
        query = """
            SELECT 
                month, 
                code, 
                name, 
                open, 
                high, 
                low, 
                close, 
                volume, 
                amount
            FROM stock_monthly_kline
            WHERE code = $1 
              AND month >= $2 
              AND month <= $3
            ORDER BY month ASC
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, code, start_date, end_date)
            
            if not rows:
                return pd.DataFrame()
            
            # 转换为DataFrame
            data = []
            for row in rows:
                data.append({
                    'month': row['month'],
                    'code': row['code'],
                    'name': row['name'],
                    'open': float(row['open']) if row['open'] else None,
                    'high': float(row['high']) if row['high'] else None,
                    'low': float(row['low']) if row['low'] else None,
                    'close': float(row['close']) if row['close'] else None,
                    'volume': int(row['volume']) if row['volume'] else 0,
                    'amount': float(row['amount']) if row['amount'] else 0.0
                })
            
            return pd.DataFrame(data)
    
    async def insert_analysis_result(
        self,
        code: str,
        score: float,
        reason: str,
        detail: Optional[Dict] = None
    ):
        """
        插入或更新股票分析结果
        
        Args:
            code: 股票代码
            score: 推荐评分 (0-10)
            reason: 推荐理由
            detail: 详细分析数据（可选）
        """
        if self.pool is None:
            raise RuntimeError("数据库未连接，请先调用connect()")
        
        # 转换detail为JSONB
        detail_json = json.dumps(detail, ensure_ascii=False) if detail else None
        
        query = """
            INSERT INTO stock_analysis_results 
            (code, recommendation_score, reason, analysis_detail, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            ON CONFLICT (code) 
            DO UPDATE SET 
                recommendation_score = EXCLUDED.recommendation_score,
                reason = EXCLUDED.reason,
                analysis_detail = EXCLUDED.analysis_detail,
                created_at = EXCLUDED.created_at
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                code,
                score,
                reason,
                detail_json,
                datetime.now()
            )
    
    async def get_analysis_result(
        self,
        code: str
    ) -> Optional[Dict]:
        """
        获取股票的分析结果
        
        Args:
            code: 股票代码
            
        Returns:
            分析结果字典，如果不存在返回None
        """
        if self.pool is None:
            raise RuntimeError("数据库未连接，请先调用connect()")
        
        query = """
            SELECT 
                code,
                recommendation_score,
                reason,
                analysis_detail,
                created_at
            FROM stock_analysis_results
            WHERE code = $1
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, code)
            
            if not row:
                return None
            
            return {
                'code': row['code'],
                'recommendation_score': float(row['recommendation_score']),
                'reason': row['reason'],
                'analysis_detail': dict(row['analysis_detail']) if row['analysis_detail'] else None,
                'created_at': row['created_at'].isoformat()
            }
    
    async def get_top_recommendations(
        self,
        limit: int = 10,
        min_score: float = 7.0
    ) -> List[Dict]:
        """
        获取评分最高的股票推荐
        
        Args:
            limit: 返回数量
            min_score: 最低评分要求
            
        Returns:
            推荐股票列表
        """
        if self.pool is None:
            raise RuntimeError("数据库未连接，请先调用connect()")
        
        query = """
            SELECT 
                code,
                recommendation_score,
                reason,
                created_at
            FROM stock_analysis_results
            WHERE recommendation_score >= $1
            ORDER BY recommendation_score DESC, created_at DESC
            LIMIT $2
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, min_score, limit)
            
            results = []
            for row in rows:
                results.append({
                    'code': row['code'],
                    'recommendation_score': float(row['recommendation_score']),
                    'reason': row['reason'],
                    'created_at': row['created_at'].isoformat()
                })
            
            return results
    
    async def create_tables(self):
        """
        创建必要的数据库表（如果不存在）
        """
        if self.pool is None:
            raise RuntimeError("数据库未连接，请先调用connect()")
        
        # 创建分析结果表
        create_results_table = """
            CREATE TABLE IF NOT EXISTS stock_analysis_results (
                id SERIAL PRIMARY KEY,
                code VARCHAR(20) NOT NULL,
                recommendation_score DECIMAL(3,1) CHECK (recommendation_score >= 0 AND recommendation_score <= 10),
                reason TEXT NOT NULL,
                analysis_detail JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT unique_stock_code UNIQUE (code)
            );
            
            CREATE INDEX IF NOT EXISTS idx_analysis_score 
            ON stock_analysis_results(recommendation_score DESC);
            
            CREATE INDEX IF NOT EXISTS idx_analysis_time 
            ON stock_analysis_results(created_at DESC);
            
            COMMENT ON TABLE stock_analysis_results IS '股票分析结果表';
            COMMENT ON COLUMN stock_analysis_results.code IS '股票代码';
            COMMENT ON COLUMN stock_analysis_results.recommendation_score IS '推荐评分(0-10)';
            COMMENT ON COLUMN stock_analysis_results.reason IS '推荐理由(简短)';
            COMMENT ON COLUMN stock_analysis_results.analysis_detail IS '详细分析数据(JSON)';
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(create_results_table)
            print("✓ stock_analysis_results表已创建/验证")
    
    async def close(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            self.pool = None


# 示例：独立运行时测试数据库连接
async def test_database():
    """测试数据库连接和操作"""
    
    # 替换为你的实际数据库连接
    dsn = "postgresql://postgres:password@localhost:5432/fin_db"
    
    db = StockDatabase(dsn)
    
    try:
        # 连接数据库
        await db.connect()
        
        # 创建表
        await db.create_tables()
        
        # 查询K线数据
        print("\n测试查询K线数据...")
        df = await db.query_kline_data("300444.SZ", months=12)
        print(f"查询到 {len(df)} 条记录")
        if not df.empty:
            print(df.head())
        
        # 插入测试结果
        print("\n测试插入分析结果...")
        await db.insert_analysis_result(
            code="300444.SZ",
            score=7.5,
            reason="板块政策支持强，技术面底部震荡充分",
            detail={
                "sector_score": 8.5,
                "company_score": 7.0,
                "technical_score": 7.0
            }
        )
        print("✓ 插入成功")
        
        # 查询结果
        print("\n测试查询分析结果...")
        result = await db.get_analysis_result("300444.SZ")
        print(f"查询结果: {result}")
        
        # 获取top推荐
        print("\n测试获取top推荐...")
        tops = await db.get_top_recommendations(limit=5, min_score=7.0)
        print(f"找到 {len(tops)} 个高评分推荐")
        for item in tops:
            print(f"  {item['code']}: {item['recommendation_score']}分")
        
    finally:
        await db.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_database())

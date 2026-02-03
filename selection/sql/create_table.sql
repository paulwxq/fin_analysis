-- =========================================
-- "平底锅"形态初筛结果表（SQL粗筛）
-- =========================================
CREATE TABLE IF NOT EXISTS stock_flatbottom_preselect (
    -- 股票基本信息
    code VARCHAR(20) PRIMARY KEY,          -- 股票代码（主键）
    name VARCHAR(100),

    -- 筛选指标
    current_price NUMERIC(10, 2),
    history_high NUMERIC(10, 2),
    glory_ratio NUMERIC(10, 2),
    glory_type VARCHAR(20),
    drawdown_pct NUMERIC(10, 2),
    box_range_pct NUMERIC(10, 2),
    volatility_ratio NUMERIC(10, 4),
    price_position NUMERIC(10, 4),

    -- 精筛指标
    slope NUMERIC(10, 6),
    r_squared NUMERIC(10, 4),
    score NUMERIC(10, 2),

    -- 元数据
    screening_preset VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_flatbottom_preselect_score ON stock_flatbottom_preselect(score DESC);
CREATE INDEX IF NOT EXISTS idx_flatbottom_preselect_updated_at ON stock_flatbottom_preselect(updated_at);

-- 添加表注释
COMMENT ON TABLE stock_flatbottom_preselect IS '平底锅形态候选股票SQL初筛结果（每个股票只保留最新一条记录）';

-- 添加字段注释
COMMENT ON COLUMN stock_flatbottom_preselect.code IS '股票代码（主键，如 600000.SH, 000001.SZ）';
COMMENT ON COLUMN stock_flatbottom_preselect.name IS '股票名称';
COMMENT ON COLUMN stock_flatbottom_preselect.current_price IS '当前价格（元，筛选使用绝对值判断）';
COMMENT ON COLUMN stock_flatbottom_preselect.history_high IS '历史高点价格（默认120个月内，元）';
COMMENT ON COLUMN stock_flatbottom_preselect.glory_ratio IS '辉煌度：双轨指标（正价段用倍率，高/低；负价段回退为归一化振幅）';
COMMENT ON COLUMN stock_flatbottom_preselect.glory_type IS '辉煌度类型：ratio（倍率语义，正价段）/ amplitude（归一化振幅，负价回退）';
COMMENT ON COLUMN stock_flatbottom_preselect.drawdown_pct IS '回撤幅度（%）：(当前价 - 历史高点) / ABS(历史高点) × 100，负数表示跌幅';
COMMENT ON COLUMN stock_flatbottom_preselect.box_range_pct IS '箱体振幅（%）：近期波动幅度，(近期最高 - 近期最低) / MAX(ABS(近期最高), ABS(近期最低)) × 100';
COMMENT ON COLUMN stock_flatbottom_preselect.volatility_ratio IS '波动率收敛比：近期标准差 / 历史标准差，小于1表示波动收敛';
COMMENT ON COLUMN stock_flatbottom_preselect.price_position IS '价格在箱体中的位置：0-1之间，0表示箱体底部，1表示箱体顶部';
COMMENT ON COLUMN stock_flatbottom_preselect.slope IS '趋势斜率：线性回归计算的价格走势斜率，正数上涨、负数下跌';
COMMENT ON COLUMN stock_flatbottom_preselect.r_squared IS '拟合度 R²：线性回归的拟合优度，0-1之间，越大表示走势越规律';
COMMENT ON COLUMN stock_flatbottom_preselect.score IS '综合得分：加权计算的总分，得分越高表示越符合平底锅形态';
COMMENT ON COLUMN stock_flatbottom_preselect.screening_preset IS '筛选时使用的预设配置（conservative/balanced/aggressive）';
COMMENT ON COLUMN stock_flatbottom_preselect.created_at IS '记录首次创建时间';
COMMENT ON COLUMN stock_flatbottom_preselect.updated_at IS '记录最后更新时间';

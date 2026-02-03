"""
配置管理模块
管理系统的所有配置项
"""

import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class Config:
    """系统配置类"""
    
    # ========== 数据库配置 ==========
    database_dsn: str  # PostgreSQL连接字符串
    
    # ========== LLM配置 ==========
    openai_api_key: str
    llm_model: str = "gpt-4o"  # 推荐使用gpt-4o或更强模型作为Manager
    llm_temperature: float = 0.7
    
    # ========== Magentic配置 ==========
    max_stall_count: int = 3  # 连续无进展的最大次数
    max_reset_count: int = 2  # 允许重置计划的最大次数
    enable_plan_review: bool = True  # 是否启用人工计划审查
    auto_approve_plan: bool = False  # 是否自动批准计划（调试用）
    
    # ========== 分析配置 ==========
    default_lookback_months: int = 12  # 默认查询K线数据的月数
    sector_analysis_months: int = 6  # 板块分析的时间范围
    company_research_months: int = 6  # 公司研究的时间范围
    
    # ========== 输出配置 ==========
    output_dir: Path = Path("./outputs")  # 报告输出目录
    save_reports_to_file: bool = True  # 是否将报告保存为文件
    
    # ========== 日志配置 ==========
    log_level: str = "INFO"
    enable_telemetry: bool = False  # 是否启用OpenTelemetry
    
    @classmethod
    def from_env(cls) -> "Config":
        """
        从环境变量加载配置
        
        环境变量：
        - DATABASE_DSN: PostgreSQL连接字符串（必需）
        - OPENAI_API_KEY: OpenAI API密钥（必需）
        - LLM_MODEL: 使用的模型，默认gpt-4o
        - MAX_STALL_COUNT: 最大停滞次数，默认3
        - ENABLE_PLAN_REVIEW: 是否启用计划审查，默认true
        """
        
        # 必需配置
        database_dsn = os.getenv("DATABASE_DSN")
        if not database_dsn:
            raise ValueError(
                "DATABASE_DSN环境变量未设置！\n"
                "请设置: export DATABASE_DSN='postgresql://user:password@host:port/database'"
            )
        
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY环境变量未设置！\n"
                "请设置: export OPENAI_API_KEY='sk-...'"
            )
        
        # 可选配置
        return cls(
            database_dsn=database_dsn,
            openai_api_key=openai_api_key,
            llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            max_stall_count=int(os.getenv("MAX_STALL_COUNT", "3")),
            max_reset_count=int(os.getenv("MAX_RESET_COUNT", "2")),
            enable_plan_review=os.getenv("ENABLE_PLAN_REVIEW", "true").lower() == "true",
            auto_approve_plan=os.getenv("AUTO_APPROVE_PLAN", "false").lower() == "true",
            default_lookback_months=int(os.getenv("DEFAULT_LOOKBACK_MONTHS", "12")),
            sector_analysis_months=int(os.getenv("SECTOR_ANALYSIS_MONTHS", "6")),
            company_research_months=int(os.getenv("COMPANY_RESEARCH_MONTHS", "6")),
            output_dir=Path(os.getenv("OUTPUT_DIR", "./outputs")),
            save_reports_to_file=os.getenv("SAVE_REPORTS", "true").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            enable_telemetry=os.getenv("ENABLE_TELEMETRY", "false").lower() == "true"
        )
    
    @classmethod
    def from_file(cls, config_file: str = ".env") -> "Config":
        """
        从.env文件加载配置
        
        Args:
            config_file: 配置文件路径
        """
        if Path(config_file).exists():
            # 简单的.env文件解析
            with open(config_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip().strip('"').strip("'")
        
        return cls.from_env()
    
    def validate(self):
        """验证配置的有效性"""
        errors = []
        
        # 验证数据库DSN格式
        if not self.database_dsn.startswith("postgresql://"):
            errors.append("DATABASE_DSN必须以'postgresql://'开头")
        
        # 验证API Key
        if not self.openai_api_key.startswith("sk-"):
            errors.append("OPENAI_API_KEY格式不正确")
        
        # 验证数值范围
        if not 1 <= self.max_stall_count <= 10:
            errors.append("max_stall_count必须在1-10之间")
        
        if not 1 <= self.max_reset_count <= 5:
            errors.append("max_reset_count必须在1-5之间")
        
        if not 0.0 <= self.llm_temperature <= 2.0:
            errors.append("llm_temperature必须在0-2之间")
        
        if errors:
            raise ValueError("配置验证失败:\n" + "\n".join(f"- {e}" for e in errors))
    
    def create_output_dir(self):
        """创建输出目录"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def __str__(self) -> str:
        """配置信息摘要（隐藏敏感信息）"""
        return f"""
股票分析系统配置
==================
数据库: {self.database_dsn.split('@')[1] if '@' in self.database_dsn else '***'}
LLM模型: {self.llm_model}
Temperature: {self.llm_temperature}
Max Stall: {self.max_stall_count}
Max Reset: {self.max_reset_count}
计划审查: {'启用' if self.enable_plan_review else '禁用'}
自动批准: {'是' if self.auto_approve_plan else '否'}
输出目录: {self.output_dir}
==================
"""


# 创建示例.env文件
def create_example_env():
    """创建示例.env文件"""
    
    example_content = """# 股票分析系统配置文件
# 请复制此文件为.env并填写实际值

# ========== 必需配置 ==========
# PostgreSQL数据库连接字符串
DATABASE_DSN=postgresql://postgres:your_password@localhost:5432/fin_db

# OpenAI API密钥
OPENAI_API_KEY=sk-your-api-key-here

# ========== 可选配置 ==========
# LLM模型选择（推荐gpt-4o或更强模型作为Manager）
LLM_MODEL=gpt-4o

# LLM Temperature（0-2，越高越随机）
LLM_TEMPERATURE=0.7

# Magentic编排配置
MAX_STALL_COUNT=3
MAX_RESET_COUNT=2
ENABLE_PLAN_REVIEW=true
AUTO_APPROVE_PLAN=false

# 分析配置
DEFAULT_LOOKBACK_MONTHS=12
SECTOR_ANALYSIS_MONTHS=6
COMPANY_RESEARCH_MONTHS=6

# 输出配置
OUTPUT_DIR=./outputs
SAVE_REPORTS=true

# 日志配置
LOG_LEVEL=INFO
ENABLE_TELEMETRY=false
"""
    
    with open(".env.example", "w", encoding="utf-8") as f:
        f.write(example_content)
    
    print("✓ 已创建 .env.example 文件")
    print("请复制为 .env 并填写实际配置")


if __name__ == "__main__":
    # 创建示例配置文件
    create_example_env()
    
    # 测试配置加载（如果.env存在）
    if Path(".env").exists():
        try:
            config = Config.from_file(".env")
            config.validate()
            print(config)
        except Exception as e:
            print(f"配置加载失败: {e}")
    else:
        print("\n提示：请先创建.env文件")

"""Configuration for stock analyzer module B."""

import os

from dotenv import load_dotenv

load_dotenv()

# DashScope / Qwen
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL: str = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# Tavily
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

# Model selection
MODEL_QUERY_AGENT: str = os.getenv("MODEL_QUERY_AGENT", "qwen-plus")
MODEL_EXTRACT_AGENT: str = os.getenv("MODEL_EXTRACT_AGENT", "qwen-plus")
MODEL_REPORT_AGENT: str = os.getenv("MODEL_REPORT_AGENT", "qwen-plus")

# Deep research params
DEFAULT_BREADTH: int = int(os.getenv("DEFAULT_BREADTH", "3"))
DEFAULT_DEPTH: int = int(os.getenv("DEFAULT_DEPTH", "2"))
TAVILY_MAX_RESULTS: int = int(os.getenv("TAVILY_MAX_RESULTS", "5"))

# Timeout and concurrency
API_TIMEOUT: float = float(os.getenv("API_TIMEOUT", "120.0"))
TAVILY_TIMEOUT: float = float(os.getenv("TAVILY_TIMEOUT", "30.0"))
TOPIC_CONCURRENCY_LIMIT: int = int(os.getenv("TOPIC_CONCURRENCY_LIMIT", "3"))

# Logging
LOG_LEVEL_CONSOLE: str = os.getenv("LOG_LEVEL_CONSOLE", "INFO")
LOG_LEVEL_FILE: str = os.getenv("LOG_LEVEL_FILE", "DEBUG")
LOG_FILE_PATH: str = os.getenv("LOG_FILE_PATH", "logs/stock_analyzer.log")

# ============================================================
# Module A: AKShare data collection config
# ============================================================

# AKShare call interval seconds (avoid source-site anti-crawling limits)
AKSHARE_CALL_INTERVAL: float = float(os.getenv("AKSHARE_CALL_INTERVAL", "3.0"))

# AKShare per-call timeout seconds
AKSHARE_CALL_TIMEOUT: float = float(os.getenv("AKSHARE_CALL_TIMEOUT", "30.0"))

# Retry times when one AKShare call hits timeout (in addition to first attempt)
AKSHARE_TIMEOUT_RETRIES: int = int(os.getenv("AKSHARE_TIMEOUT_RETRIES", "3"))

# Number of recent periods for financial indicators
AKSHARE_FINANCIAL_PERIODS: int = int(os.getenv("AKSHARE_FINANCIAL_PERIODS", "8"))

# Number of recent days for fund flow detail
AKSHARE_FUND_FLOW_DAYS: int = int(os.getenv("AKSHARE_FUND_FLOW_DAYS", "5"))

# Number of recent periods for shareholder count
AKSHARE_SHAREHOLDER_PERIODS: int = int(
    os.getenv("AKSHARE_SHAREHOLDER_PERIODS", "4")
)

# Number of recent years for dividend history
AKSHARE_DIVIDEND_YEARS: int = int(os.getenv("AKSHARE_DIVIDEND_YEARS", "5"))

# Circuit breaker threshold for consecutive timeouts
AKSHARE_MAX_CONSECUTIVE_TIMEOUTS: int = int(
    os.getenv("AKSHARE_MAX_CONSECUTIVE_TIMEOUTS", "3")
)

# TTL for full-market data cache reuse in batch mode
AKSHARE_MARKET_CACHE_TTL_SEC: int = int(
    os.getenv("AKSHARE_MARKET_CACHE_TTL_SEC", "300")
)

# ============================================================
# Module C: technical analysis config
# ============================================================

# LLM model used by technical analysis agent
MODEL_TECHNICAL_AGENT: str = os.getenv("MODEL_TECHNICAL_AGENT", "qwen-plus")

# AKShare monthly k-line fetch params
TECH_START_DATE: str = os.getenv("TECH_START_DATE", "20000101")
TECH_ADJUST: str = os.getenv("TECH_ADJUST", "qfq")

# How many recent months to send to LLM
TECH_AGENT_LOOKBACK_MONTHS: int = int(
    os.getenv("TECH_AGENT_LOOKBACK_MONTHS", "36")
)

# Minimum monthly bars to enter full technical pipeline
TECH_MIN_MONTHS: int = int(os.getenv("TECH_MIN_MONTHS", "24"))

# Minimum monthly bars to use MA60 long-trend judgement
TECH_LONG_TREND_MIN_MONTHS: int = int(
    os.getenv("TECH_LONG_TREND_MIN_MONTHS", "60")
)

# Indicator params
TECH_MA_SHORT: int = int(os.getenv("TECH_MA_SHORT", "5"))
TECH_MA_MID: int = int(os.getenv("TECH_MA_MID", "10"))
TECH_MA_LONG: int = int(os.getenv("TECH_MA_LONG", "20"))
TECH_MA_TREND: int = int(os.getenv("TECH_MA_TREND", "60"))
TECH_RSI_LENGTH: int = int(os.getenv("TECH_RSI_LENGTH", "14"))
TECH_BOLL_LENGTH: int = int(os.getenv("TECH_BOLL_LENGTH", "20"))
TECH_KDJ_K: int = int(os.getenv("TECH_KDJ_K", "14"))
TECH_KDJ_D: int = int(os.getenv("TECH_KDJ_D", "3"))
TECH_KDJ_SMOOTH: int = int(os.getenv("TECH_KDJ_SMOOTH", "3"))

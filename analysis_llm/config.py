"""Configuration for Step 1 and Step 2 analysis pipeline."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# API Configuration
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# Model configuration
MODEL_NEWS_AGENT = "qwen-plus"
MODEL_SECTOR_AGENT = "qwen-plus"
MODEL_KLINE_AGENT = "qwen-vl-max"

# Checker models
MODEL_CHECKER_NEWS = "qwen-plus"
MODEL_CHECKER_SECTOR = "qwen-plus"
MODEL_CHECKER_KLINE = "qwen-plus"

MAX_RETRIES = 3
NEWS_LIMIT_POS = 5
NEWS_LIMIT_NEG = 5
NEWS_ITEM_MAX_CHARS = 800

# Search Configuration
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
SEARCH_PROVIDER = "tavily"  # 可选: "serper" 或 "tavily"

# --- Step 2 Configuration ---

# Model Selection (Independent of Step 1)
# Manager: 负责调度，需强推理能力
MODEL_MANAGER = "qwen-plus"
# ScoreAgent: 负责生成，需搜索 + 推理
# qwen-max
MODEL_SCORE_AGENT = "qwen3-max"
# ReviewAgent: 负责质检，需强逻辑 (使用 DeepSeek API)
MODEL_REVIEW_AGENT = "deepseek-chat"

# Workflow Constraints
MAX_ITERATIONS = 10  # Magentic 循环上限 (约 5 轮 Review)

# Prompt Constraints
SUMMARY_REASON_MIN_CHARS = 100
SUMMARY_REASON_MAX_CHARS = 1000

# Timeout Configuration (新增)
API_TIMEOUT = 180.0  # 秒，用于所有 API 调用（增加以应对长上下文场景）

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = PROJECT_ROOT / "logs" / "analysis_llm.log"
IMAGE_DIR = PROJECT_ROOT / "output"

# Logging configuration
LOG_LEVEL_CONSOLE = logging.INFO
LOG_LEVEL_FILE = logging.DEBUG

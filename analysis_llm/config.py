"""Configuration for Step 1 analysis pipeline."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# API Configuration
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

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
SEARCH_PROVIDER = "serper"  # Options: "tavily", "serper"

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = PROJECT_ROOT / "logs" / "analysis_llm.log"
IMAGE_DIR = PROJECT_ROOT / "output"

# Logging configuration
LOG_LEVEL_CONSOLE = logging.INFO
LOG_LEVEL_FILE = logging.DEBUG

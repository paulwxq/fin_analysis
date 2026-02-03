"""Utility helpers for Step 1 pipeline."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from agent_framework import Content

from . import config

LOGGER_NAME = "analysis_llm"


def init_logging() -> logging.Logger:
    """Initialize logging to console and file."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    log_path = Path(config.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(config.LOG_LEVEL_CONSOLE)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(config.LOG_LEVEL_FILE)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # 同时也配置 qwen3 的日志，以便查看底层 payload
    qwen3_logger = logging.getLogger("qwen3")
    qwen3_logger.setLevel(logging.DEBUG)
    qwen3_logger.addHandler(console_handler)
    qwen3_logger.addHandler(file_handler)

    return logger


def extract_json_str(raw_text: str) -> str:
    """Extract the first JSON object from raw text."""
    if not raw_text:
        raise ValueError("Empty response text")

    # 1) Code block fenced JSON
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    # 2) Scan for first balanced JSON object
    start = raw_text.find("{")
    if start == -1:
        raise ValueError("No JSON object start found")

    in_string = False
    escape = False
    depth = 0
    for idx in range(start, len(raw_text)):
        ch = raw_text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw_text[start: idx + 1].strip()

    raise ValueError("Unbalanced JSON braces")


def load_image_content(image_path: Path) -> Content:
    """Create Content from local image path with file:// URI."""
    uri = f"file://{image_path}"
    return Content.from_uri(uri=uri, media_type="image/png")


def safe_json_dumps(payload: object) -> str:
    """Serialize payload to JSON string with UTF-8 characters."""
    return json.dumps(payload, ensure_ascii=False)

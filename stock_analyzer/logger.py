"""Logging configuration for stock analyzer."""

import logging
import sys
from pathlib import Path

from stock_analyzer.config import LOG_FILE_PATH, LOG_LEVEL_CONSOLE, LOG_LEVEL_FILE


def setup_logger(name: str = "stock_analyzer") -> logging.Logger:
    """Create and configure logger once."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL_CONSOLE.upper(), logging.INFO))
    console_formatter = logging.Formatter(
        fmt="%(levelname)s - %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    log_file = Path(LOG_FILE_PATH)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(getattr(logging, LOG_LEVEL_FILE.upper(), logging.DEBUG))
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()

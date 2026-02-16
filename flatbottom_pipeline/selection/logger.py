"""Logging configuration for selection module."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Import logging configuration from config module
from flatbottom_pipeline.selection import config


def setup_logger(name: str = 'selection', log_level: str = 'INFO') -> logging.Logger:
    """
    Setup logger with console and file handlers.

    Configuration is loaded from flatbottom_pipeline.selection.config module:
    - CONSOLE_LOG_LEVEL: Console handler level
    - FILE_LOG_LEVEL: File handler level
    - LOG_FORMAT_CONSOLE: Console message format
    - LOG_FORMAT_FILE: File message format
    - LOG_DATE_FORMAT: Timestamp format
    - LOG_DIR: Log directory path
    - LOG_FILE: Log file name
    - LOG_MAX_BYTES: Max size before rotation
    - LOG_BACKUP_COUNT: Number of backup files to keep

    Args:
        name: Logger name
        log_level: Logger level (overrides config if provided)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Use the most verbose level among logger/handlers so DEBUG isn't filtered out
    console_level = getattr(logging, config.CONSOLE_LOG_LEVEL.upper())
    file_level = getattr(logging, config.FILE_LOG_LEVEL.upper())
    requested_level = getattr(logging, log_level.upper()) if log_level else None
    base_level = min(level for level in (console_level, file_level, requested_level) if level is not None)
    logger.setLevel(base_level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Create logs directory if not exists
    log_dir = Path(__file__).resolve().parents[2] / config.LOG_DIR
    log_dir.mkdir(exist_ok=True)

    # Console handler (use config level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.CONSOLE_LOG_LEVEL.upper()))
    console_formatter = logging.Formatter(
        config.LOG_FORMAT_CONSOLE,
        datefmt=config.LOG_DATE_FORMAT
    )
    console_handler.setFormatter(console_formatter)

    # File handler (use config level) with rotation
    log_file = log_dir / config.LOG_FILE
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, config.FILE_LOG_LEVEL.upper()))
    file_formatter = logging.Formatter(
        config.LOG_FORMAT_FILE,
        datefmt=config.LOG_DATE_FORMAT
    )
    file_handler.setFormatter(file_formatter)

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Module-level logger instance
logger = setup_logger()

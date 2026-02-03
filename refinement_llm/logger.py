import logging
import os
import sys
from .config import RefinementConfig

class LoggerConfig:
    @staticmethod
    def setup_logger(name: str) -> logging.Logger:
        """
        Configure a logger with both console (INFO) and file (DEBUG) handlers.
        """
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG) # Base level

        # Clear existing handlers to prevent duplicates
        if logger.hasHandlers():
            logger.handlers.clear()

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 1. File Handler
        log_dir = RefinementConfig.LOG_DIR
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, RefinementConfig.LOG_FILE)
        
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(getattr(logging, RefinementConfig.FILE_LOG_LEVEL.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # 2. Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, RefinementConfig.CONSOLE_LOG_LEVEL.upper()))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger

    @staticmethod
    def set_debug_mode():
        """
        Enable debug logging for all application loggers.
        """
        # List of loggers used in the application
        # Since we initialized them with simple names in other modules
        target_loggers = ["main", "db_handler", "image_loader", "llm_analyzer"]
        
        for name in target_loggers:
            logger = logging.getLogger(name)
            logger.setLevel(logging.DEBUG)
            for handler in logger.handlers:
                handler.setLevel(logging.DEBUG)


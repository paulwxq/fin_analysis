import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class RefinementConfig:
    # LLM Configuration
    # Model name is defined here, NOT in .env
    DEFAULT_MODEL: str = "qwen-vl-plus"
    ENABLE_THINKING: bool = False
    
    # Image Configuration
    # Directory containing K-line charts (Must include MA30)
    DEFAULT_IMAGE_DIR: str = "./output"
    IMAGE_PATTERN: str = "*_kline.png"

    # Database Configuration
    DB_TABLE: str = "public.stock_flatbottom_refinement"
    
    # Construct Database URL from components if not provided directly
    _db_url = os.getenv("DATABASE_URL")
    if not _db_url:
        _user = os.getenv("DB_USER", "postgres")
        _pass = os.getenv("DB_PASS", "")
        _host = os.getenv("DB_HOST", "localhost")
        _port = os.getenv("DB_PORT", "5432")
        _name = os.getenv("DB_NAME", "fin_db")
        _db_url = f"postgresql://{_user}:{_pass}@{_host}:{_port}/{_name}"
    DATABASE_URL: str = _db_url

    # Logging Configuration
    LOG_DIR: str = "./logs"
    LOG_FILE: str = "refinement_llm.log"
    CONSOLE_LOG_LEVEL: str = "INFO"
    FILE_LOG_LEVEL: str = "DEBUG"

    # Analysis Configuration
    SCORE_THRESHOLD: float = 6.0

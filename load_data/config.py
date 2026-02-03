import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "fin_db")

# Construct DSN (Data Source Name)
# Priority: DB_DSN env var > Constructed string
_env_dsn = os.getenv("DB_DSN")
if _env_dsn:
    DB_DSN = _env_dsn
else:
    DB_DSN = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Data Configuration
DATA_DIR = os.getenv("DATA_DIR", "/mnt/d/BaiduNetdiskDownload/A股分时数据/A股_分时数据_沪深/1分钟_前复权_按年汇总")

# Performance & Concurrency
# Priority: MAX_WORKERS env var > Fixed Default (8)
_env_workers = os.getenv("MAX_WORKERS")
if _env_workers:
    MAX_WORKERS = int(_env_workers)
else:
    # Recommended for 8-core DB server
    MAX_WORKERS = 8

# Batch size for DB transactions (number of rows)
_env_batch = os.getenv("BATCH_SIZE")
if _env_batch:
    BATCH_SIZE = int(_env_batch)
else:
    BATCH_SIZE = 50000

# Error Tolerance Thresholds
MAX_SKIPPED_ROWS = 1000
MAX_SKIPPED_RATIO = 0.01 # 1%

# Data Cleaning Thresholds (Validation)
MAX_ABS_CHANGE_PCT = 10000.0  # 10,000%
MAX_ABS_AMPLITUDE = 10000.0   # 10,000%
MAX_ABS_AMOUNT = 1e12         # 1 Trillion
MAX_ABS_VOLUME = 1e11         # 100 Billion

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "load_errors.log"

# Application Settings
STANDARDIZE_CODE = True

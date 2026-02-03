from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class StockImage:
    stock_code: str      # Stock code (e.g., 000876.SZ)
    file_path: str       # Absolute or relative file path
    file_size: int       # File size in bytes
    valid: bool          # Validity flag

@dataclass
class AnalysisResult:
    stock_code: str              # Stock code
    score: float                 # Score (0-10)
    pattern_name: str            # Pattern name
    reasoning: str               # Analysis reasoning
    stage: str                   # Wyckoff/Weinstein Stage
    ma30_status: str             # Status of 30-month Moving Average
    volume_pattern: str          # Volume pattern description
    image_path: str              # Path of the analyzed image
    analysis_timestamp: datetime # Timestamp of analysis
    success: bool                # Success flag
    error_message: Optional[str] = None # Error message if failed

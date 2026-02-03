import os
import glob
from typing import List
from .config import RefinementConfig
from .models import StockImage
from .logger import LoggerConfig

logger = LoggerConfig.setup_logger("image_loader")

class ImageLoader:
    def __init__(self, base_dir: str):
        """Initialize image loader"""
        self.base_dir = base_dir

    def scan_images(self) -> List[StockImage]:
        """Scan and return all K-line images"""
        pattern = os.path.join(self.base_dir, RefinementConfig.IMAGE_PATTERN)
        files = glob.glob(pattern)
        
        images = []
        for filepath in files:
            if not self.validate_image(filepath):
                continue
                
            filename = os.path.basename(filepath)
            stock_code = self.extract_stock_code(filename)
            
            if not stock_code:
                logger.warning(f"Could not extract stock code from {filename}")
                continue
                
            file_size = os.path.getsize(filepath)
            
            images.append(StockImage(
                stock_code=stock_code,
                file_path=filepath,
                file_size=file_size,
                valid=True
            ))
            
        logger.info(f"Found {len(images)} valid images in {self.base_dir}")
        return images

    def extract_stock_code(self, filename: str) -> str:
        """
        Extract stock code from filename.
        Expected format: '000876.SZ_kline.png' -> '000876.SZ'
        """
        try:
            # Split by '_' and take the first part
            # Assumes format: CODE_kline.png
            parts = filename.split('_')
            if parts:
                return parts[0]
            return ""
        except Exception:
            return ""

    def validate_image(self, filepath: str) -> bool:
        """Validate if file is a valid image"""
        if not os.path.exists(filepath):
            return False
        if os.path.getsize(filepath) == 0:
            return False
        if not filepath.lower().endswith('.png'):
            return False
        return True

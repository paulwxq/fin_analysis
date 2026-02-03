import argparse
import asyncio
import os
import sys
from datetime import datetime

from .config import RefinementConfig
from .image_loader import ImageLoader
from .db_handler import DBHandler
from .llm_analyzer import LLMAnalyzer
from .logger import LoggerConfig

# Setup module-level logger
logger = LoggerConfig.setup_logger("main")

async def main_async(args):
    # 1. Initialize Configuration
    logger.info("Starting Refinement LLM Module...")
    
    model_name = args.model or RefinementConfig.DEFAULT_MODEL
    logger.info(f"Config -> Model: {model_name} | Enable Thinking: {RefinementConfig.ENABLE_THINKING}")
    
    # Load Environment Variables
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    db_url = os.getenv("DATABASE_URL") or RefinementConfig.DATABASE_URL
    
    if not api_key:
        logger.error("API Key not found. Please set DASHSCOPE_API_KEY or OPENAI_API_KEY in .env")
        sys.exit(1)
        
    if not db_url:
        logger.error("Database URL not found. Please set DATABASE_URL in .env")
        sys.exit(1)

    # 2. Components Initialization
    db_handler = DBHandler(db_url)
    image_loader = ImageLoader(args.image_dir or RefinementConfig.DEFAULT_IMAGE_DIR)
    
    analyzer = LLMAnalyzer(
        model_name=args.model or RefinementConfig.DEFAULT_MODEL,
        api_key=api_key,
        base_url=base_url
    )

    # 3. Database Preparation
    logger.info("Initializing database table...")
    db_handler.init_table()
    logger.info("Truncating target table...")
    db_handler.truncate_table()

    # 4. Scan Images
    logger.info("Scanning for K-line images...")
    images = image_loader.scan_images()
    if not images:
        logger.warning("No images found. Exiting.")
        return

    # Filter by limit if needed (for testing)
    if args.limit and args.limit > 0:
        images = images[:args.limit]
        logger.info(f"Limiting analysis to first {args.limit} images.")

    # 5. Batch Analysis
    logger.info(f"Starting analysis for {len(images)} images with concurrency {args.concurrency}...")
    start_time = datetime.now()
    
    results = await analyzer.batch_analyze(images, concurrency=args.concurrency)
    
    duration = datetime.now() - start_time
    logger.info(f"Analysis completed in {duration}.")

    # 6. Save Results
    # Filter by threshold if requested (optional logic, but typically we save all and filter in SQL)
    # But design doc mentions threshold arg. Let's filter before insert if user wants only high scores?
    # Usually better to save all to see why some failed. 
    # Let's save all valid results, but log how many passed threshold.
    
    logger.info("Saving results to database...")
    inserted_count = db_handler.batch_insert(results)
    
    # 7. Summary
    high_score_count = sum(1 for r in results if r.success and r.score >= args.threshold)
    logger.info("="*40)
    logger.info(f"Total Processed: {len(images)}")
    logger.info(f"Successful: {sum(1 for r in results if r.success)}")
    logger.info(f"Failed: {sum(1 for r in results if not r.success)}")
    logger.info(f"High Score (>= {args.threshold}): {high_score_count}")
    logger.info(f"DB Inserted: {inserted_count}")
    logger.info("="*40)

def main():
    parser = argparse.ArgumentParser(description="Refinement LLM: Stock Pattern Analysis")
    
    parser.add_argument("--image-dir", type=str, help="Directory containing K-line images")
    parser.add_argument("--model", type=str, help="LLM Model name")
    parser.add_argument("--threshold", type=float, default=RefinementConfig.SCORE_THRESHOLD, help="Score threshold for summary")
    parser.add_argument("--batch-size", type=int, default=5, help="Batch size (Concurrency)") # Renaming to concurrency in logic
    parser.add_argument("--concurrency", type=int, default=5, help="Async concurrency limit")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of images to process (0 for all)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()
    
    if args.debug:
        # Reconfigure logger if debug flag is present
        LoggerConfig.set_debug_mode()

    asyncio.run(main_async(args))

if __name__ == "__main__":
    main()

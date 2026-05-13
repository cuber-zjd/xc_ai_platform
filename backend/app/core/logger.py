import os
import sys
from loguru import logger

# Configure Loguru
def setup_logging():
    # Remove default handler
    logger.remove()

    # Log Level based on environment (assuming DEBUG for dev, INFO for prod)
    log_level = "DEBUG" 

    # 1. Console Handler (Human Readable)
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    # 2. File Handler (JSON for better processing, rotating)
    # Ensure logs directory exists
    log_path = "logs/app.log"
    os.makedirs("logs", exist_ok=True)

    logger.add(
        log_path,
        rotation="500 MB",
        retention="10 days",
        level=log_level,
        serialize=True, # JSON Format
        encoding="utf-8",
        enqueue=True,
    )

    logger.info("Logging initialized 🚀")

# Export logger
__all__ = ["logger", "setup_logging"]

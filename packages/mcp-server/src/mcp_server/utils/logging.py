# src/ai_agent/utils/logging.py
import logging
from rich.logging import RichHandler
from rich.console import Console

def setup_logging():
    """Configure logging with rich handler"""
    logging.basicConfig(
        level="DEBUG",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    return logging.getLogger("ai_agent")

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name"""
    logger = logging.getLogger(name)
    if not logger.handlers:  # Only add handler if not already configured
        logger.addHandler(RichHandler(rich_tracebacks=True))
    return logger
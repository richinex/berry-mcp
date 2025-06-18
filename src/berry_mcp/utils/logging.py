"""
Logging utilities for Berry PDF MCP Server
"""

import logging
import sys
from typing import Optional


def setup_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
    include_timestamp: bool = True
) -> None:
    """
    Set up logging configuration for the MCP server.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string for log messages
        include_timestamp: Whether to include timestamp in log messages
    """
    # Convert string level to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Default format
    if format_string is None:
        if include_timestamp:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        else:
            format_string = "%(name)s - %(levelname)s - %(message)s"
    
    # Configure logging
    logging.basicConfig(
        level=log_level,
        format=format_string,
        stream=sys.stdout,
        force=True  # Override any existing configuration
    )
    
    # Set up logger for this package
    logger = logging.getLogger("berry_pdf_mcp")
    logger.setLevel(log_level)
    
    logger.info(f"Logging configured at {level} level")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Name of the logger (typically __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(f"berry_pdf_mcp.{name}")
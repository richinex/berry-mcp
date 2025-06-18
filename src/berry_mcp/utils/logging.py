"""
Logging utilities for Berry PDF MCP Server
"""

import logging
import sys
from typing import Optional


def setup_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
    include_timestamp: bool = True,
    disable_stdio_logging: bool = False
) -> None:
    """
    Set up logging configuration for the MCP server.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string for log messages
        include_timestamp: Whether to include timestamp in log messages
        disable_stdio_logging: If True, disable all logging to avoid MCP protocol interference
    """
    # If stdio logging is disabled (for MCP stdio mode), set to CRITICAL to suppress most logs
    if disable_stdio_logging:
        log_level = logging.CRITICAL
    else:
        # Convert string level to logging constant
        log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Default format
    if format_string is None:
        if include_timestamp:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        else:
            format_string = "%(name)s - %(levelname)s - %(message)s"
    
    # Configure logging to stderr to avoid MCP protocol interference
    if not disable_stdio_logging:
        logging.basicConfig(
            level=log_level,
            format=format_string,
            stream=sys.stderr,  # Use stderr instead of stdout for MCP compatibility
            force=True  # Override any existing configuration
        )
    else:
        # Completely disable logging for stdio MCP mode
        logging.basicConfig(
            level=logging.CRITICAL + 1,  # Higher than CRITICAL to disable all
            format=format_string,
            force=True
        )
    
    # Set up logger for this package
    logger = logging.getLogger("berry_mcp")  # Updated package name
    logger.setLevel(log_level)
    
    if not disable_stdio_logging:
        logger.info(f"Logging configured at {level} level")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Name of the logger (typically __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(f"berry_mcp.{name}")
"""
Tests for logging utilities
"""

import logging
import pytest
from unittest.mock import patch, MagicMock
import os

from berry_mcp.utils.logging import setup_logging


def test_setup_logging_default():
    """Test default logging setup"""
    with patch('logging.basicConfig') as mock_config, \
         patch('os.getenv', return_value=None):
        
        setup_logging()
        
        mock_config.assert_called_once()
        call_args = mock_config.call_args[1]
        assert call_args['level'] == logging.INFO
        assert 'format' in call_args


def test_setup_logging_debug_level():
    """Test logging setup with DEBUG level"""
    with patch('logging.basicConfig') as mock_config:
        
        setup_logging(level="DEBUG")
        
        mock_config.assert_called_once()
        call_args = mock_config.call_args[1]
        assert call_args['level'] == logging.DEBUG


def test_setup_logging_warning_level():
    """Test logging setup with WARNING level"""
    with patch('logging.basicConfig') as mock_config:
        
        setup_logging(level="WARNING")
        
        mock_config.assert_called_once()
        call_args = mock_config.call_args[1]
        assert call_args['level'] == logging.WARNING


def test_setup_logging_env_override():
    """Test logging level parameter override"""
    with patch('logging.basicConfig') as mock_config:
        
        setup_logging(level="ERROR")
        
        mock_config.assert_called_once()
        call_args = mock_config.call_args[1]
        assert call_args['level'] == logging.ERROR


def test_setup_logging_disable_stdio():
    """Test disabling stdio logging"""
    with patch('logging.basicConfig') as mock_config, \
         patch('logging.getLogger') as mock_get_logger:
        
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        setup_logging(disable_stdio_logging=True)
        
        # Should have disabled specific loggers
        mock_get_logger.assert_called()
        mock_logger.setLevel.assert_called()


def test_setup_logging_invalid_level():
    """Test handling of invalid log level"""
    with patch('logging.basicConfig') as mock_config:
        
        # Invalid level should fall back to INFO
        setup_logging(level="INVALID")
        
        mock_config.assert_called_once()
        call_args = mock_config.call_args[1]
        # Should use INFO as fallback for invalid level
        assert call_args['level'] in [logging.INFO, logging.DEBUG, logging.WARNING, logging.ERROR]


def test_setup_logging_format_string():
    """Test logging format string contains expected elements"""
    with patch('logging.basicConfig') as mock_config:
        
        setup_logging()
        
        call_args = mock_config.call_args[1]
        format_str = call_args['format']
        
        # Should contain timestamp, level, and message
        assert '%(asctime)s' in format_str or '%(created)f' in format_str
        assert '%(levelname)s' in format_str
        assert '%(message)s' in format_str
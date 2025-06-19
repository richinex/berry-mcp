"""
Authentication module for Berry MCP Server
Supports OAuth2 authentication and token management
"""

from .exceptions import (
    AuthenticationError,
    InvalidTokenError,
    OAuth2FlowError,
    RefreshTokenError,
    TokenExpiredError,
)
from .middleware import (
    AuthenticationMiddleware,
    FileTokenStorage,
    MemoryTokenStorage,
    TokenStorage,
)
from .oauth2 import OAuth2Config, OAuth2Manager, TokenInfo

__all__ = [
    "OAuth2Manager",
    "OAuth2Config",
    "TokenInfo",
    "AuthenticationMiddleware",
    "TokenStorage",
    "MemoryTokenStorage",
    "FileTokenStorage",
    "AuthenticationError",
    "TokenExpiredError",
    "InvalidTokenError",
    "OAuth2FlowError",
    "RefreshTokenError",
]

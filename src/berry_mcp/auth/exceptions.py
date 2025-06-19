"""
Authentication-related exceptions for Berry MCP Server
"""


class AuthenticationError(Exception):
    """Base exception for authentication-related errors"""
    pass


class TokenExpiredError(AuthenticationError):
    """Raised when an authentication token has expired"""
    pass


class InvalidTokenError(AuthenticationError):
    """Raised when an authentication token is invalid or malformed"""
    pass


class OAuth2FlowError(AuthenticationError):
    """Raised when there's an error in the OAuth2 flow"""
    pass


class RefreshTokenError(AuthenticationError):
    """Raised when token refresh fails"""
    pass
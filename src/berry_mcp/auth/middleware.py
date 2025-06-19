"""
Authentication middleware for Berry MCP Server
Handles OAuth2 token validation and refresh
"""

import logging
from collections.abc import Callable
from typing import Any, Optional

try:
    from fastapi import HTTPException, Request, Response
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    Request = None  # type: ignore
    Response = None  # type: ignore
    HTTPException = None  # type: ignore
    HTTPBearer = None  # type: ignore
    HTTPAuthorizationCredentials = None  # type: ignore

from .exceptions import AuthenticationError, InvalidTokenError, TokenExpiredError
from .oauth2 import OAuth2Manager, TokenInfo

logger = logging.getLogger(__name__)


class AuthenticationMiddleware:
    """Middleware for handling OAuth2 authentication in MCP servers"""

    def __init__(
        self,
        oauth_manager: OAuth2Manager | None = None,
        required_scopes: list[str] | None = None,
        auto_refresh: bool = True,
    ) -> None:
        self.oauth_manager = oauth_manager
        self.required_scopes = required_scopes or []
        self.auto_refresh = auto_refresh
        self._security = HTTPBearer(auto_error=False) if FASTAPI_AVAILABLE else None

    async def authenticate_request(self, request: Any) -> TokenInfo | None:
        """Authenticate an incoming request"""
        if not FASTAPI_AVAILABLE:
            logger.warning("FastAPI not available, skipping authentication")
            return None

        if not self.oauth_manager:
            logger.warning("No OAuth manager configured, skipping authentication")
            return None

        # Extract token from request
        token = await self._extract_token(request)
        if not token:
            return None

        try:
            # Validate token
            if not await self.oauth_manager.validate_token(token):
                raise InvalidTokenError("Token validation failed")

            # Check if token is expired and refresh if needed
            token_info = self.oauth_manager.get_token_info()
            if token_info and token_info.is_expired() and self.auto_refresh:
                try:
                    token_info = await self.oauth_manager.refresh_token()
                    logger.info("Token refreshed successfully")
                except Exception as e:
                    logger.error(f"Token refresh failed: {e}")
                    raise TokenExpiredError("Token expired and refresh failed")

            return token_info

        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise AuthenticationError(f"Authentication failed: {e}")

    async def _extract_token(self, request: Any) -> str | None:
        """Extract token from request headers"""
        if not FASTAPI_AVAILABLE or not self._security:
            return None

        try:
            credentials = await self._security(request)
            if credentials:
                return str(credentials.credentials)
        except Exception as e:
            logger.debug(f"Failed to extract token: {e}")

        return None

    def create_auth_header(self, token: str) -> dict[str, str]:
        """Create authorization header with token"""
        return {"Authorization": f"Bearer {token}"}

    async def middleware_function(
        self, request: Any, call_next: Callable[[Any], Any]
    ) -> Any:
        """FastAPI middleware function"""
        if not FASTAPI_AVAILABLE:
            return await call_next(request)

        try:
            # Authenticate request
            token_info = await self.authenticate_request(request)

            # Add token info to request state
            if hasattr(request, "state"):
                request.state.token_info = token_info
                request.state.authenticated = token_info is not None

            # Process request
            response = await call_next(request)
            return response

        except TokenExpiredError:
            if FASTAPI_AVAILABLE:
                raise HTTPException(status_code=401, detail="Token expired")
            raise
        except InvalidTokenError:
            if FASTAPI_AVAILABLE:
                raise HTTPException(status_code=401, detail="Invalid token")
            raise
        except AuthenticationError as e:
            if FASTAPI_AVAILABLE:
                raise HTTPException(status_code=401, detail=str(e))
            raise


class TokenStorage:
    """Simple token storage interface"""

    async def store_token(self, key: str, token_info: TokenInfo) -> None:
        """Store token information"""
        raise NotImplementedError

    async def retrieve_token(self, key: str) -> TokenInfo | None:
        """Retrieve token information"""
        raise NotImplementedError

    async def remove_token(self, key: str) -> None:
        """Remove token information"""
        raise NotImplementedError


class MemoryTokenStorage(TokenStorage):
    """In-memory token storage (for development/testing)"""

    def __init__(self) -> None:
        self._tokens: dict[str, TokenInfo] = {}

    async def store_token(self, key: str, token_info: TokenInfo) -> None:
        """Store token in memory"""
        self._tokens[key] = token_info
        logger.debug(f"Stored token for key: {key}")

    async def retrieve_token(self, key: str) -> TokenInfo | None:
        """Retrieve token from memory"""
        token_info = self._tokens.get(key)
        if token_info:
            logger.debug(f"Retrieved token for key: {key}")
        return token_info

    async def remove_token(self, key: str) -> None:
        """Remove token from memory"""
        if key in self._tokens:
            del self._tokens[key]
            logger.debug(f"Removed token for key: {key}")


class FileTokenStorage(TokenStorage):
    """File-based token storage with JSON serialization"""

    def __init__(self, storage_dir: str = ".berry_mcp_tokens") -> None:
        import os

        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def _get_token_file(self, key: str) -> str:
        """Get file path for token key"""
        import os

        safe_key = key.replace("/", "_").replace("\\", "_")
        return os.path.join(self.storage_dir, f"{safe_key}.json")

    async def store_token(self, key: str, token_info: TokenInfo) -> None:
        """Store token to file"""
        import json

        import aiofiles  # type: ignore

        file_path = self._get_token_file(key)
        try:
            async with aiofiles.open(file_path, "w") as f:
                await f.write(json.dumps(token_info.to_dict(), indent=2))
            logger.debug(f"Stored token to file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to store token: {e}")

    async def retrieve_token(self, key: str) -> TokenInfo | None:
        """Retrieve token from file"""
        import json
        import os

        import aiofiles  # type: ignore

        file_path = self._get_token_file(key)
        if not os.path.exists(file_path):
            return None

        try:
            async with aiofiles.open(file_path) as f:
                data = json.loads(await f.read())
            token_info = TokenInfo.from_dict(data)
            logger.debug(f"Retrieved token from file: {file_path}")
            return token_info
        except Exception as e:
            logger.error(f"Failed to retrieve token: {e}")
            return None

    async def remove_token(self, key: str) -> None:
        """Remove token file"""
        import os

        file_path = self._get_token_file(key)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Removed token file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to remove token file: {e}")

"""
OAuth2 authentication manager for Berry MCP Server
Supports standard OAuth2 flows with token management
"""

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None  # type: ignore

from .exceptions import OAuth2FlowError, RefreshTokenError, TokenExpiredError

logger = logging.getLogger(__name__)


@dataclass
class OAuth2Config:
    """Configuration for OAuth2 authentication"""

    client_id: str
    client_secret: str
    authorization_url: str
    token_url: str
    redirect_uri: str = "http://localhost:8080/oauth/callback"
    scope: str = ""
    use_pkce: bool = True


@dataclass
class TokenInfo:
    """Information about an OAuth2 token"""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None
    expires_at: float | None = None

    def __post_init__(self) -> None:
        """Calculate expiration time if expires_in is provided"""
        if self.expires_in and not self.expires_at:
            self.expires_at = time.time() + self.expires_in

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if token is expired (with optional buffer)"""
        if not self.expires_at:
            return False
        return time.time() >= (self.expires_at - buffer_seconds)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenInfo":
        """Create from dictionary"""
        return cls(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in"),
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope"),
            expires_at=data.get("expires_at"),
        )


class OAuth2Manager:
    """Manages OAuth2 authentication flows and token lifecycle"""

    def __init__(self, config: OAuth2Config) -> None:
        self.config = config
        self._token_info: TokenInfo | None = None
        self._http_client: Any | None = None

        if not HTTPX_AVAILABLE:
            logger.warning("httpx not available, OAuth2 functionality limited")

    @property
    def http_client(self) -> Any:
        """Get or create HTTP client"""
        if not HTTPX_AVAILABLE:
            raise OAuth2FlowError("httpx required for OAuth2 functionality")

        if not self._http_client:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge"""
        # Generate code verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(96)).decode(
            "utf-8"
        )
        code_verifier = code_verifier.rstrip("=")

        # Generate code challenge
        challenge_bytes = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode("utf-8")
        code_challenge = code_challenge.rstrip("=")

        return code_verifier, code_challenge

    def build_authorization_url(
        self, state: str | None = None
    ) -> tuple[str, str | None]:
        """Build OAuth2 authorization URL"""
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": self.config.redirect_uri,
        }

        if self.config.scope:
            params["scope"] = self.config.scope

        if state:
            params["state"] = state

        code_verifier = None
        if self.config.use_pkce:
            code_verifier, code_challenge = self.generate_pkce_pair()
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        query_string = urllib.parse.urlencode(params)
        auth_url = f"{self.config.authorization_url}?{query_string}"

        return auth_url, code_verifier

    async def exchange_code_for_token(
        self, authorization_code: str, code_verifier: str | None = None
    ) -> TokenInfo:
        """Exchange authorization code for access token"""
        data = {
            "grant_type": "authorization_code",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": authorization_code,
            "redirect_uri": self.config.redirect_uri,
        }

        if code_verifier:
            data["code_verifier"] = code_verifier

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        try:
            response = await self.http_client.post(
                self.config.token_url, data=data, headers=headers
            )
            response.raise_for_status()

            token_data = response.json()
            self._token_info = TokenInfo(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in"),
                refresh_token=token_data.get("refresh_token"),
                scope=token_data.get("scope"),
            )

            logger.info("Successfully obtained OAuth2 access token")
            return self._token_info

        except Exception as e:
            logger.error(f"Failed to exchange authorization code: {e}")
            raise OAuth2FlowError(f"Token exchange failed: {e}")

    async def refresh_token(self) -> TokenInfo:
        """Refresh the access token using refresh token"""
        if not self._token_info or not self._token_info.refresh_token:
            raise RefreshTokenError("No refresh token available")

        data = {
            "grant_type": "refresh_token",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "refresh_token": self._token_info.refresh_token,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        try:
            response = await self.http_client.post(
                self.config.token_url, data=data, headers=headers
            )
            response.raise_for_status()

            token_data = response.json()

            # Update token info, preserve refresh token if not provided
            self._token_info = TokenInfo(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in"),
                refresh_token=token_data.get(
                    "refresh_token", self._token_info.refresh_token
                ),
                scope=token_data.get("scope"),
            )

            logger.info("Successfully refreshed OAuth2 access token")
            return self._token_info

        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            raise RefreshTokenError(f"Token refresh failed: {e}")

    async def get_valid_token(self) -> str:
        """Get a valid access token, refreshing if necessary"""
        if not self._token_info:
            raise TokenExpiredError("No token available")

        if self._token_info.is_expired():
            if self._token_info.refresh_token:
                await self.refresh_token()
            else:
                raise TokenExpiredError("Token expired and no refresh token available")

        return self._token_info.access_token

    def set_token_info(self, token_info: TokenInfo) -> None:
        """Set token info directly (for loading from storage)"""
        self._token_info = token_info
        logger.info("Token info loaded")

    def get_token_info(self) -> TokenInfo | None:
        """Get current token info"""
        return self._token_info

    def clear_token_info(self) -> None:
        """Clear current token info"""
        self._token_info = None
        logger.info("Token info cleared")

    async def validate_token(self, token: str) -> bool:
        """Validate an access token by making a test request"""
        # This would depend on the specific OAuth2 provider
        # For now, just check if it's not empty and looks like a token
        return bool(token and len(token) > 10)


class QuickOAuthFlow:
    """Simplified OAuth flow for MCP inspector integration"""

    def __init__(self, oauth_manager: OAuth2Manager, callback_port: int = 8080) -> None:
        self.oauth_manager = oauth_manager
        self.callback_port = callback_port
        self._server: Any | None = None
        self._result: TokenInfo | None = None
        self._error: str | None = None

    async def start_flow(self) -> TokenInfo:
        """Start the OAuth flow and wait for completion"""
        if not HTTPX_AVAILABLE:
            raise OAuth2FlowError("httpx required for OAuth2 flow")

        # Generate state and PKCE parameters
        state = secrets.token_urlsafe(32)
        auth_url, code_verifier = self.oauth_manager.build_authorization_url(state)

        # Start callback server
        await self._start_callback_server(state, code_verifier)

        logger.info(f"OAuth2 authorization URL: {auth_url}")
        logger.info("Please visit the URL above to complete authentication")

        # Wait for callback
        timeout = 300  # 5 minutes
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self._result:
                return self._result
            if self._error:
                raise OAuth2FlowError(self._error)
            await asyncio.sleep(0.1)

        raise OAuth2FlowError("OAuth flow timed out")

    async def _start_callback_server(
        self, state: str, code_verifier: str | None
    ) -> None:
        """Start HTTP server to handle OAuth callback"""
        # This would need a proper HTTP server implementation
        # For now, we'll provide the structure
        logger.info(f"Callback server would start on port {self.callback_port}")
        # Implementation would depend on having FastAPI or similar available

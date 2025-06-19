"""
Enhanced transport layer with OAuth2 authentication and elicitation support
"""

import logging
from typing import Any, Optional

from ..auth import AuthenticationMiddleware, OAuth2Manager
from ..elicitation import ElicitationManager, SSEElicitationHandler
from .transport import SSETransport

# Optional FastAPI imports
try:
    from fastapi import BackgroundTasks, Depends, FastAPI, Request
    from fastapi.security import HTTPBearer

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None  # type: ignore
    Request = None  # type: ignore
    BackgroundTasks = None  # type: ignore
    Depends = None  # type: ignore
    HTTPBearer = None  # type: ignore

logger = logging.getLogger(__name__)


class EnhancedSSETransport(SSETransport):
    """Enhanced SSE transport with OAuth2 and elicitation support"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        oauth_manager: OAuth2Manager | None = None,
        require_auth: bool = False,
    ) -> None:
        super().__init__(host, port)
        self.oauth_manager = oauth_manager
        self.require_auth = require_auth
        self.auth_middleware: AuthenticationMiddleware | None = None
        self.elicitation_manager: ElicitationManager | None = None

        if oauth_manager:
            self.auth_middleware = AuthenticationMiddleware(oauth_manager)

        # Setup elicitation support
        if FASTAPI_AVAILABLE:
            self.elicitation_manager = ElicitationManager(
                handler=SSEElicitationHandler(self)
            )

    async def connect(self) -> None:
        """Configure FastAPI routes with enhanced features"""
        if not self.app:
            raise RuntimeError(
                "EnhancedSSETransport requires an assigned FastAPI app instance"
            )

        logger.info(
            "EnhancedSSETransport: Configuring routes with OAuth2 and elicitation support"
        )

        # Setup authentication if required
        auth_scheme = (
            HTTPBearer(auto_error=self.require_auth) if FASTAPI_AVAILABLE else None
        )

        # Add enhanced routes
        if FASTAPI_AVAILABLE:
            # Main endpoints with optional authentication
            if self.require_auth and auth_scheme:
                self.app.post("/")(
                    self._create_authenticated_handler(self._handle_message)
                )
                self.app.post("/message")(
                    self._create_authenticated_handler(self._handle_message)
                )
            else:
                self.app.post("/")(self._handle_message)
                self.app.post("/message")(self._handle_message)

            # SSE endpoint
            self.app.get("/sse", response_class=lambda: None)(self._handle_sse)
            self.app.post("/sse")(self._handle_sse_post)

            # Health and status endpoints
            self.app.get("/ping")(self._handle_ping)
            self.app.get("/health")(self._handle_health)

            # OAuth2 endpoints
            if self.oauth_manager:
                self.app.get("/oauth/authorize")(self._handle_oauth_authorize)
                self.app.post("/oauth/callback")(self._handle_oauth_callback)
                self.app.post("/oauth/refresh")(self._handle_oauth_refresh)

            # Elicitation endpoints
            if self.elicitation_manager:
                self.app.post("/elicitation/response")(
                    self._handle_elicitation_response
                )
                self.app.get("/elicitation/active")(self._handle_list_active_prompts)

        logger.info(
            f"EnhancedSSETransport: Ready with authentication={'enabled' if self.require_auth else 'disabled'}"
        )

    def _create_authenticated_handler(self, handler):
        """Create an authenticated version of a handler"""
        if not FASTAPI_AVAILABLE or not self.auth_middleware:
            return handler

        async def authenticated_handler(
            request: Request, background_tasks: BackgroundTasks
        ):
            # Authenticate request
            try:
                token_info = await self.auth_middleware.authenticate_request(request)
                if self.require_auth and not token_info:
                    from fastapi import HTTPException

                    raise HTTPException(
                        status_code=401, detail="Authentication required"
                    )

                # Add token info to request
                if hasattr(request, "state"):
                    request.state.token_info = token_info
                    request.state.authenticated = token_info is not None

                return await handler(request, background_tasks)

            except Exception as e:
                logger.error(f"Authentication error: {e}")
                if self.require_auth:
                    from fastapi import HTTPException

                    raise HTTPException(status_code=401, detail="Authentication failed")
                return await handler(request, background_tasks)

        return authenticated_handler

    async def _handle_health(self, request: Request = None) -> Any:
        """Enhanced health check endpoint"""
        if not FASTAPI_AVAILABLE:
            return {"error": "FastAPI not available"}

        from fastapi.responses import JSONResponse

        health_info = {
            "status": "healthy",
            "timestamp": __import__("time").time(),
            "connected_clients": len(self.clients),
            "features": {
                "oauth2": self.oauth_manager is not None,
                "elicitation": self.elicitation_manager is not None,
                "authentication_required": self.require_auth,
            },
        }

        if self.elicitation_manager:
            health_info["active_prompts"] = len(
                self.elicitation_manager.get_active_prompts()
            )

        return JSONResponse(health_info)

    async def _handle_oauth_authorize(self, request: Request) -> Any:
        """Handle OAuth2 authorization endpoint"""
        if not self.oauth_manager or not FASTAPI_AVAILABLE:
            from fastapi import HTTPException

            raise HTTPException(status_code=501, detail="OAuth2 not configured")

        try:
            auth_url, code_verifier = self.oauth_manager.build_authorization_url()

            # Store code verifier in session (simplified for demo)
            # In production, use proper session management

            from fastapi.responses import JSONResponse

            return JSONResponse(
                {
                    "authorization_url": auth_url,
                    "state": "generated_state",  # Should be properly generated
                    "code_verifier": code_verifier,  # Should be stored securely
                }
            )

        except Exception as e:
            logger.error(f"OAuth authorization error: {e}")
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="Authorization failed")

    async def _handle_oauth_callback(self, request: Request) -> Any:
        """Handle OAuth2 callback endpoint"""
        if not self.oauth_manager or not FASTAPI_AVAILABLE:
            from fastapi import HTTPException

            raise HTTPException(status_code=501, detail="OAuth2 not configured")

        try:
            body = await request.json()
            authorization_code = body.get("code")
            code_verifier = body.get("code_verifier")

            if not authorization_code:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=400, detail="Missing authorization code"
                )

            # Exchange code for token
            token_info = await self.oauth_manager.exchange_code_for_token(
                authorization_code, code_verifier
            )

            from fastapi.responses import JSONResponse

            return JSONResponse(
                {
                    "access_token": token_info.access_token,
                    "token_type": token_info.token_type,
                    "expires_in": token_info.expires_in,
                    "scope": token_info.scope,
                }
            )

        except Exception as e:
            logger.error(f"OAuth callback error: {e}")
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="Token exchange failed")

    async def _handle_oauth_refresh(self, request: Request) -> Any:
        """Handle OAuth2 token refresh endpoint"""
        if not self.oauth_manager or not FASTAPI_AVAILABLE:
            from fastapi import HTTPException

            raise HTTPException(status_code=501, detail="OAuth2 not configured")

        try:
            token_info = await self.oauth_manager.refresh_token()

            from fastapi.responses import JSONResponse

            return JSONResponse(
                {
                    "access_token": token_info.access_token,
                    "token_type": token_info.token_type,
                    "expires_in": token_info.expires_in,
                    "scope": token_info.scope,
                }
            )

        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="Token refresh failed")

    async def _handle_elicitation_response(self, request: Request) -> Any:
        """Handle elicitation response from client"""
        if not self.elicitation_manager or not FASTAPI_AVAILABLE:
            from fastapi import HTTPException

            raise HTTPException(status_code=501, detail="Elicitation not supported")

        try:
            body = await request.json()
            prompt_id = body.get("prompt_id")
            response = body.get("response")

            if not prompt_id:
                from fastapi import HTTPException

                raise HTTPException(status_code=400, detail="Missing prompt_id")

            await self.elicitation_manager.handle_response(prompt_id, response)

            from fastapi.responses import JSONResponse

            return JSONResponse({"status": "received"})

        except Exception as e:
            logger.error(f"Elicitation response error: {e}")
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="Failed to process response")

    async def _handle_list_active_prompts(self, request: Request = None) -> Any:
        """List active elicitation prompts"""
        if not self.elicitation_manager or not FASTAPI_AVAILABLE:
            from fastapi import HTTPException

            raise HTTPException(status_code=501, detail="Elicitation not supported")

        try:
            prompts = self.elicitation_manager.get_active_prompts()
            prompt_data = [prompt.to_dict() for prompt in prompts]

            from fastapi.responses import JSONResponse

            return JSONResponse({"active_prompts": prompt_data})

        except Exception as e:
            logger.error(f"List prompts error: {e}")
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="Failed to list prompts")

    async def send_elicitation_prompt(self, prompt: Any) -> Any:
        """Send an elicitation prompt and wait for response"""
        if not self.elicitation_manager:
            logger.warning("Elicitation not supported")
            return None

        return await self.elicitation_manager._execute_prompt(prompt)

    def get_token_info(self) -> Any | None:
        """Get current OAuth2 token info"""
        if self.oauth_manager:
            return self.oauth_manager.get_token_info()
        return None

    async def validate_request_auth(self, request: Request) -> bool:
        """Validate request authentication"""
        if not self.auth_middleware:
            return not self.require_auth  # Allow if auth not required

        try:
            token_info = await self.auth_middleware.authenticate_request(request)
            return token_info is not None
        except Exception as e:
            logger.error(f"Auth validation error: {e}")
            return False

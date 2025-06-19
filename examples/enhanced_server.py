"""
Enhanced Berry MCP Server example with OAuth2 and elicitation features
Demonstrates the new authentication and human-in-the-loop capabilities
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from berry_mcp.auth import OAuth2Config, OAuth2Manager
from berry_mcp.core.enhanced_transport import EnhancedSSETransport
from berry_mcp.core.server import MCPServer
from berry_mcp.elicitation import CapabilityBuilder, ElicitationManager, PromptBuilder
from berry_mcp.tools.decorators import tool
from berry_mcp.utils.logging import setup_logging

try:
    import uvicorn
    from fastapi import FastAPI

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("FastAPI not available. Please install with: pip install fastapi uvicorn")
    sys.exit(1)

logger = logging.getLogger(__name__)


class EnhancedMCPServer:
    """Enhanced MCP server with OAuth2 and elicitation support"""

    def __init__(self):
        self.server = MCPServer(name="enhanced-berry-mcp", version="1.0.0")
        self.app = FastAPI(title="Enhanced Berry MCP Server")
        self.transport = None
        self.oauth_manager = None
        self.elicitation_manager = None

        # Setup OAuth2 if configured
        self._setup_oauth2()

        # Setup transport
        self._setup_transport()

        # Register enhanced tools
        self._register_tools()

    def _setup_oauth2(self):
        """Setup OAuth2 configuration"""
        oauth_config = OAuth2Config(
            client_id=os.getenv("OAUTH_CLIENT_ID", "demo_client"),
            client_secret=os.getenv("OAUTH_CLIENT_SECRET", "demo_secret"),
            authorization_url=os.getenv(
                "OAUTH_AUTH_URL", "https://example.com/oauth/authorize"
            ),
            token_url=os.getenv("OAUTH_TOKEN_URL", "https://example.com/oauth/token"),
            redirect_uri=os.getenv(
                "OAUTH_REDIRECT_URI", "http://localhost:8080/oauth/callback"
            ),
            scope=os.getenv("OAUTH_SCOPE", "read write"),
        )

        # Only setup OAuth if client ID is properly configured
        if oauth_config.client_id != "demo_client":
            self.oauth_manager = OAuth2Manager(oauth_config)
            logger.info("OAuth2 authentication enabled")
        else:
            logger.info("OAuth2 not configured (using demo credentials)")

    def _setup_transport(self):
        """Setup enhanced SSE transport"""
        require_auth = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

        self.transport = EnhancedSSETransport(
            host="localhost",
            port=8080,
            oauth_manager=self.oauth_manager,
            require_auth=require_auth,
        )

        # Assign FastAPI app
        self.transport.app = self.app
        self.elicitation_manager = self.transport.elicitation_manager

        logger.info(f"Enhanced transport configured (auth_required={require_auth})")

    def _register_tools(self):
        """Register enhanced tools with elicitation and schemas"""

        @tool(description="Interactive file processor with user confirmation")
        async def process_file_interactive(
            file_path: str, operation: str = "read"
        ) -> dict:
            """Process a file with user confirmation and streaming results"""

            # Use elicitation for user confirmation
            if self.elicitation_manager:
                confirmed = await self.elicitation_manager.prompt_confirmation(
                    title="File Operation Confirmation",
                    message=f"Do you want to {operation} the file: {file_path}?",
                    default=False,
                    timeout=60,
                )

                if not confirmed:
                    return {"error": "Operation cancelled by user", "success": False}

            # Simulate file processing
            result = {
                "success": True,
                "file_path": file_path,
                "operation": operation,
                "size": 1024,
                "processed_at": "2024-01-01T12:00:00Z",
            }

            return result

        @tool(description="Search with user-defined parameters")
        async def search_with_options(query: str) -> dict:
            """Search with user-configurable options"""

            if self.elicitation_manager:
                # Get search options from user
                search_type = await self.elicitation_manager.prompt_choice(
                    title="Search Type",
                    message="Select the type of search to perform:",
                    choices=[
                        ("web", "Web Search"),
                        ("files", "File Search"),
                        ("code", "Code Search"),
                    ],
                    timeout=30,
                )

                # Get additional parameters
                max_results = await self.elicitation_manager.prompt_input(
                    title="Max Results",
                    message="How many results do you want?",
                    default="10",
                    pattern=r"^\d+$",
                    timeout=30,
                )

                if not max_results.isdigit():
                    max_results = "10"
            else:
                search_type = "web"
                max_results = "10"

            # Simulate search
            results = [
                {
                    "title": f"Result {i+1} for '{query}'",
                    "url": f"https://example.com/{i}",
                }
                for i in range(min(int(max_results), 5))
            ]

            return {
                "query": query,
                "search_type": search_type,
                "max_results": int(max_results),
                "total_results": len(results),
                "results": results,
            }

        @tool(description="Tool requiring authentication")
        async def secure_operation(data: str) -> dict:
            """Perform a secure operation that requires authentication"""

            # Check if user is authenticated
            token_info = None
            if self.transport and hasattr(self.transport, "get_token_info"):
                token_info = self.transport.get_token_info()

            if self.oauth_manager and not token_info:
                return {
                    "error": "Authentication required",
                    "auth_url": "/oauth/authorize",
                    "success": False,
                }

            # Simulate secure operation
            return {
                "success": True,
                "data": f"Processed: {data}",
                "authenticated": token_info is not None,
                "timestamp": "2024-01-01T12:00:00Z",
            }

        # Register tools with the server
        self.server.tool_registry.tool()(process_file_interactive)
        self.server.tool_registry.tool()(search_with_options)
        self.server.tool_registry.tool()(secure_operation)

        # Register capabilities if elicitation manager is available
        if self.elicitation_manager:
            # File processing capability
            file_capability = CapabilityBuilder.create_file_tool_capability(
                name="process_file_interactive",
                description="Interactive file processor with user confirmation",
                supports_streaming=False,
            )
            self.elicitation_manager.register_capability(file_capability)

            # Search capability
            search_capability = CapabilityBuilder.create_search_tool_capability(
                name="search_with_options",
                description="Search with user-configurable options",
                requires_auth=False,
            )
            self.elicitation_manager.register_capability(search_capability)

            # Secure operation capability
            secure_capability = CapabilityBuilder.create_api_tool_capability(
                name="secure_operation",
                description="Secure operation requiring authentication",
                dependencies=["oauth2"],
            )
            self.elicitation_manager.register_capability(secure_capability)

        logger.info("Enhanced tools registered with capabilities")

    async def start(self):
        """Start the enhanced MCP server"""
        try:
            # Connect transport
            await self.transport.connect()
            await self.server.connect(self.transport)

            logger.info("Enhanced MCP Server starting...")
            logger.info("Features enabled:")
            logger.info(
                f"  - OAuth2 Authentication: {'Yes' if self.oauth_manager else 'No'}"
            )
            logger.info(
                f"  - Elicitation (Human-in-the-loop): {'Yes' if self.elicitation_manager else 'No'}"
            )
            logger.info("  - Enhanced SSE Transport: Yes")

            if self.oauth_manager:
                logger.info("OAuth2 Endpoints:")
                logger.info("  - GET  /oauth/authorize - Start OAuth flow")
                logger.info("  - POST /oauth/callback  - OAuth callback")
                logger.info("  - POST /oauth/refresh   - Refresh token")

            if self.elicitation_manager:
                logger.info("Elicitation Endpoints:")
                logger.info("  - POST /elicitation/response - Submit prompt response")
                logger.info("  - GET  /elicitation/active   - List active prompts")

            logger.info("Standard Endpoints:")
            logger.info("  - POST / or /message - MCP requests")
            logger.info("  - GET  /sse         - Server-Sent Events")
            logger.info("  - GET  /health      - Health check")
            logger.info("  - GET  /ping        - Simple ping")

            # Start FastAPI server
            config = uvicorn.Config(
                app=self.app, host="localhost", port=8080, log_level="info"
            )
            server = uvicorn.Server(config)

            await server.serve()

        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Shutdown the server gracefully"""
        logger.info("Shutting down enhanced MCP server...")

        if self.transport:
            await self.transport.close()

        if self.oauth_manager:
            await self.oauth_manager.close()

        logger.info("Enhanced MCP server stopped")


async def main():
    """Main entry point"""
    setup_logging(level=os.getenv("BERRY_MCP_LOG_LEVEL", "INFO"))

    server = EnhancedMCPServer()
    await server.start()


if __name__ == "__main__":
    if not FASTAPI_AVAILABLE:
        print("This example requires FastAPI and uvicorn.")
        print("Install with: pip install fastapi uvicorn")
        sys.exit(1)

    print("🚀 Enhanced Berry MCP Server")
    print("Features: OAuth2 Authentication + Human-in-the-loop Elicitation")
    print("Configure OAuth2 with environment variables:")
    print("  OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, OAUTH_AUTH_URL, OAUTH_TOKEN_URL")
    print("Set REQUIRE_AUTH=true to require authentication for all requests")
    print()

    asyncio.run(main())

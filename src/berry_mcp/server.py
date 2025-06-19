"""
Main entry point for Berry MCP Server
"""

import argparse
import asyncio
import os
import sys
from typing import Any

from .core.server import MCPServer
from .core.transport import SSETransport, StdioTransport
from .utils.logging import setup_logging


async def run_stdio_server(tool_modules: Any = None, server_name: str | None = None, log_level: str = "INFO") -> None:
    """Run MCP server with stdio transport"""
    # Disable logging for stdio mode to avoid MCP protocol interference
    setup_logging(level=log_level, disable_stdio_logging=True)

    # Create server with configurable name
    name = server_name or os.getenv("BERRY_MCP_SERVER_NAME", "berry-mcp-server")
    server = MCPServer(name=name or "berry-mcp-server")

    # Load tool modules if specified
    if tool_modules:
        for module in tool_modules:
            server.tool_registry.auto_discover_tools(module)
    else:
        # Auto-discover from default tools package
        from . import tools

        server.tool_registry.auto_discover_tools(tools)

    transport = StdioTransport()
    await server.run(transport)


async def run_http_server(host: str = "localhost", port: int = 8000) -> None:
    """Run MCP server with HTTP/SSE transport"""
    try:
        import uvicorn
        from fastapi import FastAPI
    except ImportError:
        print("FastAPI and uvicorn required for HTTP server mode", file=sys.stderr)
        sys.exit(1)

    setup_logging(level="INFO")

    # Create FastAPI app
    app = FastAPI(title="Berry MCP Server", version="0.1.0")

    # Create server and transport
    server = MCPServer()
    transport = SSETransport(host, port)
    transport.app = app

    # Auto-discover tools from tools package
    from . import tools

    server.tool_registry.auto_discover_tools(tools)

    # Connect server to transport AFTER tools are loaded
    await server.connect(transport)

    # Add a GET root endpoint for info (POST handled by transport)
    @app.get("/")
    async def root() -> dict[str, Any]:
        return {
            "message": "Berry MCP Server",
            "version": "0.1.0",
            "transport": "HTTP/SSE",
            "tools_count": len(server.tool_registry.tools),
            "endpoints": {
                "root": "POST / - Send MCP messages (VS Code compatible)",
                "message": "POST /message - Send MCP messages",
                "sse": "GET /sse - Server-sent events stream",
                "ping": "GET /ping - Health check",
            },
        }

    # Start the server
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


def cli_main() -> None:
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Berry MCP Server - Universal MCP server framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  BERRY_MCP_SERVER_NAME    Server name identifier
  BERRY_MCP_LOG_LEVEL      Logging level (DEBUG, INFO, WARNING, ERROR)
  BERRY_MCP_TOOLS_PATH     Comma-separated paths to tool modules

Examples:
  # Run with stdio (for VS Code integration)
  berry-mcp
  
  # Run HTTP server
  berry-mcp --transport http --port 8080
  
  # With custom tools module
  BERRY_MCP_TOOLS_PATH=my_tools berry-mcp
""",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.getenv("BERRY_MCP_TRANSPORT", "stdio"),
        help="Transport method (default: stdio, env: BERRY_MCP_TRANSPORT)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("BERRY_MCP_HOST", "localhost"),
        help="Host for HTTP transport (default: localhost, env: BERRY_MCP_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("BERRY_MCP_PORT", "8000")),
        help="Port for HTTP transport (default: 8000, env: BERRY_MCP_PORT)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=os.getenv("BERRY_MCP_LOG_LEVEL", "INFO"),
        help="Logging level (default: INFO, env: BERRY_MCP_LOG_LEVEL)",
    )
    parser.add_argument(
        "--server-name",
        default=os.getenv("BERRY_MCP_SERVER_NAME"),
        help="Server name identifier (env: BERRY_MCP_SERVER_NAME)",
    )
    parser.add_argument(
        "--tools-path",
        default=os.getenv("BERRY_MCP_TOOLS_PATH"),
        help="Comma-separated paths to tool modules (env: BERRY_MCP_TOOLS_PATH)",
    )

    args = parser.parse_args()

    # Load custom tool modules if specified
    tool_modules = None
    if args.tools_path:
        import importlib

        tool_modules = []
        for path in args.tools_path.split(","):
            path = path.strip()
            if path:
                try:
                    module = importlib.import_module(path)
                    tool_modules.append(module)
                except ImportError as e:
                    print(
                        f"Warning: Could not import tool module '{path}': {e}",
                        file=sys.stderr,
                    )

    try:
        if args.transport == "stdio":
            asyncio.run(
                run_stdio_server(
                    tool_modules=tool_modules,
                    server_name=args.server_name,
                    log_level=args.log_level,
                )
            )
        elif args.transport == "http":
            asyncio.run(run_http_server(args.host, args.port))
    except KeyboardInterrupt:
        print("Server stopped by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        sys.exit(1)


# For backwards compatibility
async def main() -> None:
    """Main entry point (backwards compatibility)"""
    await run_stdio_server()


if __name__ == "__main__":
    cli_main()

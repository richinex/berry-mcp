"""
Examples demonstrating different transport modes for Berry PDF MCP Server
"""

import asyncio
import json

from berry_pdf_mcp import MCPServer, SSETransport, StdioTransport
from berry_pdf_mcp.utils.logging import setup_logging


async def example_stdio_transport():
    """Example using stdio transport (typical MCP usage)"""
    print("=== Stdio Transport Example ===")
    setup_logging(level="INFO")

    server = MCPServer(name="stdio-example")
    transport = StdioTransport()

    # This would normally run the full server loop
    # For demonstration, we'll just show the setup
    await server.connect(transport)

    # Auto-discover tools
    from berry_pdf_mcp.tools import pdf_tools

    server.tool_registry.auto_discover_tools(pdf_tools)

    print(f"Server connected with {len(server.tool_registry.list_tools())} tools")
    print("Available tools:", server.tool_registry.list_tools())

    await transport.close()


async def example_http_transport():
    """Example using HTTP/SSE transport"""
    print("\n=== HTTP/SSE Transport Example ===")

    try:
        import uvicorn
        from fastapi import FastAPI
    except ImportError:
        print("FastAPI not available, skipping HTTP example")
        return

    setup_logging(level="INFO")

    # Create FastAPI app
    app = FastAPI(title="Example MCP Server")

    # Create server and transport
    server = MCPServer(name="http-example")
    transport = SSETransport("localhost", 8001)
    transport.app = app

    # Connect and setup
    await server.connect(transport)

    # Auto-discover tools
    from berry_pdf_mcp.tools import pdf_tools

    server.tool_registry.auto_discover_tools(pdf_tools)

    print(
        f"HTTP Server setup complete with {len(server.tool_registry.list_tools())} tools"
    )
    print("Would start server on http://localhost:8001")
    print("Endpoints:")
    print("  GET  / - Server info")
    print("  GET  /ping - Health check")
    print("  GET  /sse - Server-sent events")
    print("  POST /message - Send MCP messages")


async def test_mcp_protocol():
    """Test MCP protocol message handling"""
    print("\n=== MCP Protocol Test ===")
    setup_logging(level="DEBUG")

    server = MCPServer(name="protocol-test")

    # Auto-discover tools
    from berry_pdf_mcp.tools import pdf_tools

    server.tool_registry.auto_discover_tools(pdf_tools)

    # Test initialize message
    init_message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"clientInfo": {"name": "test-client", "version": "1.0.0"}},
    }

    response = await server.protocol.handle_message(init_message)
    print("Initialize response:")
    print(json.dumps(response, indent=2))

    # Test tools/list message
    list_message = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

    response = await server.protocol.handle_message(list_message)
    print("\nTools list response:")
    print(json.dumps(response, indent=2))


async def example_http_client():
    """Example HTTP client for testing SSE transport"""
    print("\n=== HTTP Client Example ===")

    try:
        import aiohttp
    except ImportError:
        print("aiohttp not available, skipping HTTP client example")
        return

    # This would connect to a running HTTP MCP server
    server_url = "http://localhost:8000"

    async with aiohttp.ClientSession() as session:
        try:
            # Test ping endpoint
            async with session.get(f"{server_url}/ping") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Server ping successful: {data}")
                else:
                    print(f"Server not available at {server_url}")
                    return

            # Example message to send
            mcp_message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            }

            # Send message via POST
            async with session.post(
                f"{server_url}/message",
                json=mcp_message,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 202:
                    data = await response.json()
                    print(f"Message accepted: {data}")

            # Connect to SSE stream (this would run continuously)
            print("Would connect to SSE stream at /sse for real-time responses")

        except aiohttp.ClientError as e:
            print(f"HTTP client error: {e}")
        except Exception as e:
            print(f"Error: {e}")


class MockTransport:
    """Mock transport for testing"""

    def __init__(self):
        self.messages = []
        self.closed = False

    async def connect(self):
        pass

    async def send(self, message):
        self.messages.append(message)
        print(f"Mock transport sent: {json.dumps(message, indent=2)}")

    async def receive(self):
        return None

    async def close(self):
        self.closed = True

    def set_message_handler(self, handler):
        pass


async def example_custom_transport():
    """Example using custom transport"""
    print("\n=== Custom Transport Example ===")

    server = MCPServer(name="custom-transport-example")
    transport = MockTransport()

    await server.connect(transport)

    # Auto-discover tools
    from berry_pdf_mcp.tools import pdf_tools

    server.tool_registry.auto_discover_tools(pdf_tools)

    # Test a tool call
    test_message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "read_pdf_text", "arguments": {"path": "nonexistent.pdf"}},
    }

    response = await server.protocol.handle_message(test_message)
    await transport.send(response)

    print(f"Transport captured {len(transport.messages)} messages")
    await transport.close()


async def main():
    """Run all examples"""
    print("Berry PDF MCP Server Transport Examples")
    print("=" * 50)

    await example_stdio_transport()
    await example_http_transport()
    await test_mcp_protocol()
    await example_custom_transport()

    print("\n=== HTTP Client Test ===")
    print("To test HTTP client, first start the server with:")
    print("  python -m berry_pdf_mcp.server --transport http --port 8000")
    print("Then run:")
    print("  python examples/transport_examples.py --test-client")


if __name__ == "__main__":
    import sys

    if "--test-client" in sys.argv:
        asyncio.run(example_http_client())
    else:
        asyncio.run(main())

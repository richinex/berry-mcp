"""
Example usage of Berry MCP Server
"""

import asyncio
import json

from berry_mcp import MCPServer
from berry_mcp.utils.logging import setup_logging
from berry_mcp.utils.validation import set_workspace


async def main():
    """Example of how to use Berry MCP Server"""

    # Set up logging
    setup_logging(level="INFO")

    # Set workspace directory
    set_workspace("./examples/workspace")

    # Create server
    server = MCPServer(name="example-server", version="1.0.0")

    # Auto-discover tools from custom module
    from . import custom_tools

    server.tool_registry.auto_discover_tools(custom_tools)

    # Manual tool registration example
    def manual_tool(message: str) -> str:
        """A manually registered tool"""
        return f"Manual tool says: {message}"

    server.tool_registry.register_function(
        manual_tool,
        name="manual_example",
        description="Example of manual tool registration",
    )

    # List available tools
    print("Available tools:")
    for tool_name in server.tool_registry.list_tools():
        print(f"  - {tool_name}")

    # Example tool execution (normally done via MCP protocol)
    print("\nTesting tool execution:")

    # Test sum_numbers tool
    sum_tool = server.tool_registry.get_tool("sum_numbers")
    if sum_tool:
        result = sum_tool(numbers=[1, 2, 3, 4, 5])
        print(f"sum_numbers([1,2,3,4,5]) = {result}")

    # Test text transformation
    transform_tool = server.tool_registry.get_tool("transform_text")
    if transform_tool:
        result = transform_tool(text="Hello World", to_upper=True)
        print(f"transform_text('Hello World', to_upper=True) = {result}")

    # Test async tool
    async_tool = server.tool_registry.get_tool("async_process_text")
    if async_tool:
        result = await async_tool(text="async test", delay_seconds=0.5)
        print(f"async_process_text result = {result}")

    # Test PDF tool if available
    pdf_tool = server.tool_registry.get_tool("read_pdf_text")
    if pdf_tool:
        print("\nPDF tool is available. You can test it with:")
        print("  result = await pdf_tool(path='example.pdf')")

    print("\nServer setup complete. To run as MCP server:")
    print("  python -m berry_mcp.server")


class MCPServerTester:
    """Helper class for testing MCP server functionality"""

    def __init__(self, server: MCPServer):
        self.server = server

    async def test_initialize(self):
        """Test initialization message"""
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "test-client", "version": "1.0.0"}},
        }

        response = await self.server._handle_message(message)
        print("Initialize response:", json.dumps(response, indent=2))
        return response

    async def test_list_tools(self):
        """Test tools/list message"""
        message = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

        response = await self.server._handle_message(message)
        print("List tools response:", json.dumps(response, indent=2))
        return response

    async def test_call_tool(self, tool_name: str, arguments: dict):
        """Test tools/call message"""
        message = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        response = await self.server._handle_message(message)
        print(f"Call tool {tool_name} response:", json.dumps(response, indent=2))
        return response


async def test_mcp_protocol():
    """Test MCP protocol messages"""
    print("\n=== Testing MCP Protocol ===")

    # Set up server
    setup_logging(level="DEBUG")
    server = MCPServer(name="test-server")

    # Add custom tools
    from . import custom_tools

    server.tool_registry.auto_discover_tools(custom_tools)

    # Create tester
    tester = MCPServerTester(server)

    # Test initialization
    await tester.test_initialize()

    # Test list tools
    await tester.test_list_tools()

    # Test tool execution
    await tester.test_call_tool("sum_numbers", {"numbers": [10, 20, 30]})
    await tester.test_call_tool(
        "transform_text", {"text": "test message", "to_upper": False}
    )


if __name__ == "__main__":
    print("Berry MCP Server Examples")
    print("=" * 40)

    # Run basic example
    asyncio.run(main())

    # Run protocol test
    asyncio.run(test_mcp_protocol())

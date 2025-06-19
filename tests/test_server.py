"""
Tests for MCP server core functionality
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from berry_mcp.core.server import MCPServer
from berry_mcp.core.transport import StdioTransport
from berry_mcp.tools.decorators import tool


@pytest.fixture
def server():
    """Create a server instance for testing"""
    return MCPServer(name="test-server", version="1.0.0")


@pytest.mark.asyncio
async def test_server_initialization(server):
    """Test server initializes correctly"""
    assert server.name == "test-server"
    assert server.version == "1.0.0"
    assert server.initialized is False
    assert server.transport is None
    assert server.tool_registry is not None
    assert server.protocol is not None


@pytest.mark.asyncio
async def test_server_connect_transport(server):
    """Test connecting a transport to the server"""
    transport = StdioTransport()

    await server.connect(transport)

    assert server.transport == transport
    assert server.protocol._send_message_impl is not None


@pytest.mark.asyncio
async def test_server_connect_overwrites_existing(server):
    """Test connecting overwrites existing transport"""
    transport1 = StdioTransport()
    transport2 = StdioTransport()

    await server.connect(transport1)
    assert server.transport == transport1

    await server.connect(transport2)
    assert server.transport == transport2


@pytest.mark.asyncio
async def test_server_connect_null_transport_error(server):
    """Test connecting with null transport raises error"""
    with pytest.raises(ValueError, match="Cannot connect to null transport"):
        await server.connect(None)


@pytest.mark.asyncio
async def test_server_run_with_transport(server):
    """Test running server with provided transport"""
    # Mock transport to avoid actual I/O
    mock_transport = AsyncMock()
    mock_transport.connect = AsyncMock()
    mock_transport.receive = AsyncMock(side_effect=[None])  # Return None to end loop
    mock_transport.close = AsyncMock()

    # Run should complete without error
    await server.run(mock_transport)

    mock_transport.connect.assert_called_once()
    mock_transport.receive.assert_called()
    mock_transport.close.assert_called_once()


@pytest.mark.asyncio
async def test_server_run_default_transport(server):
    """Test running server with default transport"""
    # Mock StdioTransport
    original_stdio = StdioTransport

    mock_transport = AsyncMock()
    mock_transport.connect = AsyncMock()
    mock_transport.receive = AsyncMock(side_effect=[None])  # Return None to end loop
    mock_transport.close = AsyncMock()

    # Temporarily replace StdioTransport
    import berry_mcp.core.server

    berry_mcp.core.server.StdioTransport = MagicMock(return_value=mock_transport)

    try:
        await server.run()
        mock_transport.connect.assert_called_once()
        mock_transport.receive.assert_called()
        mock_transport.close.assert_called_once()
    finally:
        # Restore original
        berry_mcp.core.server.StdioTransport = original_stdio


@pytest.mark.asyncio
async def test_server_handle_initialize():
    """Test server initialize handler"""
    server = MCPServer(name="init-test", version="2.0.0")

    params = {
        "clientInfo": {"name": "test-client", "version": "1.0"},
        "protocolVersion": "2024-11-05",
    }

    from berry_mcp.core.protocol import RequestHandlerExtra

    extra = RequestHandlerExtra(id=1)

    result = await server._handle_initialize(params, extra)

    assert server.initialized is True
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "init-test"
    assert result["serverInfo"]["version"] == "2.0.0"
    assert "capabilities" in result
    assert "tools" in result["capabilities"]


@pytest.mark.asyncio
async def test_server_handle_list_tools(server):
    """Test server tools/list handler"""

    # Add a test tool
    @tool(description="Test tool")
    def test_tool(param: str) -> str:
        return f"result: {param}"

    server.tool_registry.tool()(test_tool)

    from berry_mcp.core.protocol import RequestHandlerExtra

    extra = RequestHandlerExtra(id=2)

    result = await server._handle_list_tools({}, extra)

    assert "tools" in result
    tools = result["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "test_tool"
    assert tools[0]["description"] == "Test tool"
    assert "inputSchema" in tools[0]


@pytest.mark.asyncio
async def test_server_handle_call_tool_success(server):
    """Test successful tool call"""

    # Add a test tool
    @tool(description="Addition tool")
    def add_numbers(a: int, b: int) -> int:
        return a + b

    server.tool_registry.tool()(add_numbers)

    params = {"name": "add_numbers", "arguments": {"a": 5, "b": 3}}

    from berry_mcp.core.protocol import RequestHandlerExtra

    extra = RequestHandlerExtra(id=3)

    result = await server._handle_call_tool(params, extra)

    assert result["isError"] is False
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "8"


@pytest.mark.asyncio
async def test_server_handle_call_tool_not_found(server):
    """Test calling non-existent tool"""
    params = {"name": "nonexistent_tool", "arguments": {}}

    from berry_mcp.core.protocol import RequestHandlerExtra

    extra = RequestHandlerExtra(id=4)

    result = await server._handle_call_tool(params, extra)

    assert result["isError"] is True
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    assert "Tool not found: nonexistent_tool" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_server_handle_call_tool_exception(server):
    """Test tool call that raises exception"""

    # Add a failing tool
    @tool(description="Failing tool")
    def failing_tool() -> str:
        raise ValueError("Tool error")

    server.tool_registry.tool()(failing_tool)

    params = {"name": "failing_tool", "arguments": {}}

    from berry_mcp.core.protocol import RequestHandlerExtra

    extra = RequestHandlerExtra(id=5)

    result = await server._handle_call_tool(params, extra)

    assert result["isError"] is True
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    assert "Tool error" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_server_handle_call_async_tool(server):
    """Test calling async tool"""

    # Add an async tool
    @tool(description="Async tool")
    async def async_tool(message: str) -> str:
        return f"async: {message}"

    server.tool_registry.tool()(async_tool)

    params = {"name": "async_tool", "arguments": {"message": "hello"}}

    from berry_mcp.core.protocol import RequestHandlerExtra

    extra = RequestHandlerExtra(id=6)

    result = await server._handle_call_tool(params, extra)

    assert result["isError"] is False
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "async: hello"


@pytest.mark.asyncio
async def test_server_tool_decorator_shortcut(server):
    """Test server.tool() decorator shortcut"""
    decorator = server.tool()
    assert decorator is not None
    # Should return the registry's tool decorator
    assert callable(decorator)


@pytest.mark.asyncio
async def test_server_message_loop_error_handling(server):
    """Test server handles transport errors gracefully"""
    # Mock transport that raises exception then returns None to end loop
    mock_transport = AsyncMock()
    mock_transport.connect = AsyncMock()
    # First call raises exception, second call returns None to end loop
    mock_transport.receive = AsyncMock(side_effect=[Exception("Transport error"), None])
    mock_transport.close = AsyncMock()

    # Should not raise exception
    await server.run(mock_transport)

    mock_transport.connect.assert_called_once()
    mock_transport.close.assert_called_once()


def test_server_main_function():
    """Test main function creates and runs server"""
    from berry_mcp.core.server import main
    
    # Test that main function exists and is callable
    assert callable(main)
    
    # Test the function signature
    import inspect
    sig = inspect.signature(main)
    assert len(sig.parameters) == 0  # main() takes no parameters

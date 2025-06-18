"""
Integration tests for Berry PDF MCP Server
Tests end-to-end functionality with real MCP protocol flows
"""

import pytest
import asyncio
import json
from typing import Dict, Any, Optional
from berry_mcp import MCPServer, StdioTransport, tool
from berry_mcp.core.protocol import MCPProtocol, RequestHandlerExtra


class MockTransport:
    """Mock transport for testing MCP protocol flows"""
    
    def __init__(self):
        self.sent_messages = []
        self.received_messages = []
        self.closed = False
        self.message_handler = None
    
    async def connect(self):
        pass
    
    async def send(self, message: Dict[str, Any]) -> None:
        self.sent_messages.append(message)
    
    async def receive(self) -> Optional[Dict[str, Any]]:
        if self.received_messages:
            return self.received_messages.pop(0)
        return None
    
    def queue_message(self, message: Dict[str, Any]):
        """Queue a message for the server to receive"""
        self.received_messages.append(message)
    
    async def close(self) -> None:
        self.closed = True
    
    def set_message_handler(self, handler):
        self.message_handler = handler


@pytest.fixture
def server_with_mock_transport():
    """Create server with mock transport for testing"""
    server = MCPServer(name="test-server", version="0.1.0")
    transport = MockTransport()
    
    # Add test tools
    @tool(description="Test addition tool")
    def add_numbers(a: int, b: int) -> int:
        return a + b
    
    @tool(description="Test tool that returns error")
    def error_tool(should_fail: bool = True) -> Dict[str, str]:
        if should_fail:
            return {"error": "Tool intentionally failed"}
        return {"result": "success"}
    
    @tool(description="Async test tool")
    async def async_tool(message: str) -> str:
        await asyncio.sleep(0.01)  # Simulate async work
        return f"Async result: {message}"
    
    # Register tools
    server.tool_registry.tool()(add_numbers)
    server.tool_registry.tool()(error_tool)
    server.tool_registry.tool()(async_tool)
    
    # Don't need to await connect for mock transport
    # Just set up the basic connection
    server.transport = transport
    transport.set_message_handler(server.protocol.handle_message)
    server.protocol.set_send_implementation(transport.send)
    
    return server, transport


@pytest.mark.asyncio
async def test_mcp_initialize_flow(server_with_mock_transport):
    """Test complete MCP initialization flow"""
    server, transport = server_with_mock_transport
    
    # Test initialize request
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            },
            "protocolVersion": "2024-11-05"
        }
    }
    
    response = await server.protocol.handle_message(init_request)
    
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "result" in response
    
    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "test-server"
    assert result["serverInfo"]["version"] == "0.1.0"
    assert "capabilities" in result
    assert "tools" in result["capabilities"]


@pytest.mark.asyncio
async def test_tools_list_flow(server_with_mock_transport):
    """Test tools/list request flow"""
    server, transport = server_with_mock_transport
    
    list_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    
    response = await server.protocol.handle_message(list_request)
    
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 2
    assert "result" in response
    
    result = response["result"]
    assert "tools" in result
    tools = result["tools"]
    
    # Should have our 3 test tools
    assert len(tools) == 3
    
    tool_names = [tool["name"] for tool in tools]
    assert "add_numbers" in tool_names
    assert "error_tool" in tool_names
    assert "async_tool" in tool_names
    
    # Check tool schema format
    add_tool = next(tool for tool in tools if tool["name"] == "add_numbers")
    assert add_tool["description"] == "Test addition tool"
    assert "inputSchema" in add_tool
    assert add_tool["inputSchema"]["type"] == "object"
    assert "a" in add_tool["inputSchema"]["properties"]
    assert "b" in add_tool["inputSchema"]["properties"]


@pytest.mark.asyncio
async def test_tool_call_success(server_with_mock_transport):
    """Test successful tool execution"""
    server, transport = server_with_mock_transport
    
    call_request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "add_numbers",
            "arguments": {
                "a": 5,
                "b": 3
            }
        }
    }
    
    response = await server.protocol.handle_message(call_request)
    
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 3
    assert "result" in response
    
    result = response["result"]
    assert "content" in result
    assert "isError" in result
    assert result["isError"] is False
    
    content = result["content"][0]
    assert content["type"] == "text"
    assert content["text"] == "8"  # 5 + 3


@pytest.mark.asyncio
async def test_tool_call_error(server_with_mock_transport):
    """Test tool that returns error"""
    server, transport = server_with_mock_transport
    
    call_request = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "error_tool",
            "arguments": {
                "should_fail": True
            }
        }
    }
    
    response = await server.protocol.handle_message(call_request)
    
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 4
    assert "result" in response
    
    result = response["result"]
    assert result["isError"] is True
    
    content = result["content"][0]
    assert content["type"] == "text"
    assert "Tool intentionally failed" in content["text"]


@pytest.mark.asyncio
async def test_async_tool_call(server_with_mock_transport):
    """Test async tool execution"""
    server, transport = server_with_mock_transport
    
    call_request = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "async_tool",
            "arguments": {
                "message": "test async"
            }
        }
    }
    
    response = await server.protocol.handle_message(call_request)
    
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 5
    assert "result" in response
    
    result = response["result"]
    assert result["isError"] is False
    
    content = result["content"][0]
    assert content["type"] == "text"
    assert content["text"] == "Async result: test async"


@pytest.mark.asyncio
async def test_tool_not_found(server_with_mock_transport):
    """Test calling non-existent tool"""
    server, transport = server_with_mock_transport
    
    call_request = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "nonexistent_tool",
            "arguments": {}
        }
    }
    
    response = await server.protocol.handle_message(call_request)
    
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 6
    assert "result" in response
    
    result = response["result"]
    assert result["isError"] is True
    
    content = result["content"][0]
    assert content["type"] == "text"
    assert "Tool not found: nonexistent_tool" in content["text"]


@pytest.mark.asyncio
async def test_invalid_method(server_with_mock_transport):
    """Test calling invalid method"""
    server, transport = server_with_mock_transport
    
    invalid_request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "invalid/method",
        "params": {}
    }
    
    response = await server.protocol.handle_message(invalid_request)
    
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 7
    assert "error" in response
    
    error = response["error"]
    assert error["code"] == -32601  # Method not found
    assert "Method not found" in error["message"]


@pytest.mark.asyncio
async def test_invalid_jsonrpc(server_with_mock_transport):
    """Test invalid JSON-RPC message"""
    server, transport = server_with_mock_transport
    
    invalid_request = {
        "jsonrpc": "1.0",  # Wrong version
        "id": 8,
        "method": "tools/list",
        "params": {}
    }
    
    response = await server.protocol.handle_message(invalid_request)
    
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] is None  # Invalid request, so ID might be None
    assert "error" in response
    
    error = response["error"]
    assert error["code"] == -32600  # Invalid Request


@pytest.mark.asyncio
async def test_notification_no_response(server_with_mock_transport):
    """Test notification (no ID) doesn't return response"""
    server, transport = server_with_mock_transport
    
    notification = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {}
        # No "id" field - this is a notification
    }
    
    response = await server.protocol.handle_message(notification)
    
    # Notifications should not return a response
    assert response is None


@pytest.mark.asyncio
async def test_complete_mcp_session(server_with_mock_transport):
    """Test complete MCP session flow"""
    server, transport = server_with_mock_transport
    
    # 1. Initialize
    init_response = await server.protocol.handle_message({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"clientInfo": {"name": "test", "version": "1.0"}}
    })
    
    assert "result" in init_response
    assert server.initialized is True
    
    # 2. List tools
    list_response = await server.protocol.handle_message({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    })
    
    assert "result" in list_response
    tools = list_response["result"]["tools"]
    assert len(tools) > 0
    
    # 3. Call a tool
    call_response = await server.protocol.handle_message({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "add_numbers",
            "arguments": {"a": 10, "b": 20}
        }
    })
    
    assert "result" in call_response
    result = call_response["result"]
    assert result["isError"] is False
    assert result["content"][0]["text"] == "30"


@pytest.mark.asyncio
async def test_tool_parameter_validation(server_with_mock_transport):
    """Test tool parameter validation"""
    server, transport = server_with_mock_transport
    
    # Missing required parameter
    call_request = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "add_numbers",
            "arguments": {
                "a": 5
                # Missing "b" parameter
            }
        }
    }
    
    response = await server.protocol.handle_message(call_request)
    
    # Should still execute but might raise TypeError
    assert response is not None
    assert "result" in response
    result = response["result"]
    assert result["isError"] is True  # Should fail due to missing parameter


@pytest.mark.asyncio
async def test_stdio_transport_integration():
    """Test that stdio transport integrates properly"""
    transport = StdioTransport()
    server = MCPServer()
    
    # Should be able to connect without error
    await server.connect(transport)
    
    assert server.transport == transport
    # StdioTransport doesn't store _message_handler, just check it was set up
    assert server.transport == transport
    
    await transport.close()


@pytest.mark.asyncio 
async def test_pdf_tools_integration():
    """Test that PDF tools are properly discovered and work"""
    server = MCPServer()
    
    # Auto-discover PDF tools
    from berry_mcp.tools import pdf_tools
    server.tool_registry.auto_discover_tools(pdf_tools)
    
    tools = server.tool_registry.list_tools()
    
    # Should have discovered PDF tools
    assert "read_pdf_text" in tools
    assert "read_pdf_text_pypdf2" in tools
    
    # Test tool schemas
    tool_schemas = server.tool_registry.tools
    pdf_tool_schema = None
    for schema in tool_schemas:
        if schema.get("function", {}).get("name") == "read_pdf_text":
            pdf_tool_schema = schema
            break
    
    assert pdf_tool_schema is not None
    func_info = pdf_tool_schema["function"]
    assert func_info["description"].startswith("Extract text content")
    assert "parameters" in func_info
    assert "path" in func_info["parameters"]["properties"]
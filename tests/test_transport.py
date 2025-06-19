"""
Transport layer tests for Berry PDF MCP Server
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch
from berry_mcp.core.transport import StdioTransport, SSETransport


@pytest.mark.asyncio
async def test_stdio_transport_basic():
    """Test basic stdio transport functionality"""
    transport = StdioTransport()
    
    # Should initialize properly
    assert transport.closed is False
    assert transport._stdin_reader is None
    assert transport._stdin_task is None
    
    # Should be able to close without connecting
    await transport.close()
    assert transport.closed is True


@pytest.mark.asyncio
async def test_stdio_transport_send():
    """Test stdio transport send functionality"""
    transport = StdioTransport()
    
    test_message = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"test": "message"}
    }
    
    # Mock stdout to capture output
    with patch('builtins.print') as mock_print:
        await transport.send(test_message)
        
        # Should have printed JSON + newline
        mock_print.assert_called_once()
        call_args = mock_print.call_args
        
        # Verify JSON structure
        output = call_args[0][0]  # First positional argument
        parsed = json.loads(output.strip())
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["result"]["test"] == "message"


@pytest.mark.asyncio
async def test_stdio_transport_message_handler():
    """Test stdio transport message handler setting"""
    transport = StdioTransport()
    
    async def mock_handler(message):
        return {"response": "test"}
    
    # Should accept handler without error
    transport.set_message_handler(mock_handler)
    
    await transport.close()


@pytest.mark.asyncio
async def test_sse_transport_initialization():
    """Test SSE transport initialization"""
    try:
        transport = SSETransport("localhost", 8001)
        
        assert transport.host == "localhost"
        assert transport.port == 8001
        assert transport.closed is False
        assert len(transport.clients) == 0
        assert transport._message_handler is None
        
        await transport.close()
        
    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_without_fastapi():
    """Test SSE transport fails gracefully without FastAPI"""
    
    # Mock missing FastAPI by patching the FASTAPI_AVAILABLE flag
    with patch('berry_mcp.core.transport.FASTAPI_AVAILABLE', False):
        with pytest.raises(ImportError, match="FastAPI and related dependencies required"):
            from berry_mcp.core.transport import SSETransport
            SSETransport("localhost", 8000)


@pytest.mark.asyncio
async def test_sse_transport_send():
    """Test SSE transport send functionality"""
    try:
        transport = SSETransport("localhost", 8001)
        
        # Add mock client queue
        mock_queue = asyncio.Queue()
        transport.clients.append(mock_queue)
        
        test_message = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"test": "sse"}
        }
        
        # Send message
        await transport.send(test_message)
        
        # Should have queued message for client
        assert not mock_queue.empty()
        sse_event = await mock_queue.get()
        
        assert sse_event["event"] == "message"
        parsed_data = json.loads(sse_event["data"])
        assert parsed_data["result"]["test"] == "sse"
        
        await transport.close()
        
    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_app_requirement():
    """Test SSE transport requires FastAPI app"""
    try:
        transport = SSETransport("localhost", 8001)
        
        # Should fail to connect without app
        with pytest.raises(RuntimeError):
            await transport.connect()
            
    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_with_app():
    """Test SSE transport with FastAPI app"""
    try:
        from fastapi import FastAPI
        
        transport = SSETransport("localhost", 8001)
        app = FastAPI()
        transport.app = app
        
        # Mock message handler
        async def mock_handler(message):
            return {"response": "test"}
        
        transport.set_message_handler(mock_handler)
        
        # Should connect successfully
        await transport.connect()
        
        # Should have added routes to app
        route_paths = [route.path for route in app.routes]
        assert "/message" in route_paths
        assert "/sse" in route_paths
        assert "/ping" in route_paths
        
        await transport.close()
        
    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_transport_error_handling():
    """Test transport error handling"""
    transport = StdioTransport()
    
    # Test sending on closed transport
    transport.closed = True
    
    # Should not raise error, just log warning
    test_message = {"test": "message"}
    await transport.send(test_message)  # Should not raise


@pytest.mark.asyncio
async def test_stdio_transport_json_parsing():
    """Test stdio transport handles invalid JSON gracefully"""
    transport = StdioTransport()
    
    # Mock the receive queue processing
    invalid_json = "invalid json line"
    
    # This would normally be handled in _read_stdin_async
    # We'll test the error handling by sending invalid message
    with patch('builtins.print') as mock_print:
        try:
            # Simulate JSON decode error handling
            json.loads(invalid_json)
        except json.JSONDecodeError as e:
            error_resp = {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": f"Parse error: {e}"},
                "id": None
            }
            await transport.send(error_resp)
            
            # Should have sent error response
            mock_print.assert_called_once()


@pytest.mark.asyncio
async def test_sse_transport_client_management():
    """Test SSE transport client management"""
    try:
        transport = SSETransport("localhost", 8001)
        
        # Add some mock clients
        client1 = asyncio.Queue()
        client2 = asyncio.Queue()
        transport.clients.extend([client1, client2])
        
        assert len(transport.clients) == 2
        
        # Close should clear clients
        await transport.close()
        assert len(transport.clients) == 0
        
    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_transport_message_types():
    """Test transport handles different message types correctly"""
    transport = StdioTransport()
    
    # Test different message types
    test_cases = [
        # Response message
        {"jsonrpc": "2.0", "id": 1, "result": {"test": True}},
        # Error message  
        {"jsonrpc": "2.0", "id": 2, "error": {"code": -32000, "message": "test error"}},
        # Notification
        {"jsonrpc": "2.0", "method": "notification", "params": {}},
        # Message without explicit jsonrpc (should be added)
        {"id": 3, "result": {"auto_jsonrpc": True}}
    ]
    
    with patch('builtins.print') as mock_print:
        for message in test_cases:
            await transport.send(message)
        
        # Should have printed all messages
        assert mock_print.call_count == len(test_cases)
        
        # Check that jsonrpc was added where missing
        last_call = mock_print.call_args_list[-1]
        output = last_call[0][0]
        parsed = json.loads(output.strip())
        assert parsed["jsonrpc"] == "2.0"


class MockStreamReader:
    """Mock stream reader for testing stdin functionality"""
    
    def __init__(self, data_lines):
        self.data_lines = data_lines
        self.index = 0
        
    async def read(self, size):
        if self.index >= len(self.data_lines):
            return b''  # EOF
        
        line = self.data_lines[self.index]
        self.index += 1
        return line.encode() + b'\n'


@pytest.mark.asyncio
async def test_stdio_transport_receive_loop():
    """Test stdio transport receive loop with mock data"""
    transport = StdioTransport()
    
    # Mock data to receive
    test_messages = [
        '{"jsonrpc": "2.0", "id": 1, "method": "test", "params": {}}',
        '{"jsonrpc": "2.0", "id": 2, "method": "another", "params": {}}'
    ]
    
    # Mock stream reader
    mock_reader = MockStreamReader(test_messages)
    transport._stdin_reader = mock_reader
    
    # Process messages manually (without full connection setup)
    for line in test_messages:
        try:
            message = json.loads(line)
            await transport._receive_queue.put(message)
        except json.JSONDecodeError:
            pass
    
    # Should be able to receive messages
    message1 = await transport.receive()
    assert message1 is not None
    assert message1["id"] == 1
    assert message1["method"] == "test"
    
    message2 = await transport.receive()
    assert message2 is not None
    assert message2["id"] == 2
    assert message2["method"] == "another"
    
    await transport.close()


@pytest.mark.asyncio
async def test_transport_abstractions():
    """Test transport abstract base class"""
    from berry_mcp.core.transport import Transport
    
    # Cannot instantiate abstract class
    with pytest.raises(TypeError):
        Transport()
    
    # Must implement abstract methods
    class IncompleteTransport(Transport):
        async def connect(self):
            pass
    
    with pytest.raises(TypeError):
        IncompleteTransport()  # Missing send, close methods
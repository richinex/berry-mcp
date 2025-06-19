"""
Transport layer tests for Berry PDF MCP Server
"""

import asyncio
import json
import time
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from berry_mcp.core.transport import SSETransport, StdioTransport


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

    test_message = {"jsonrpc": "2.0", "id": 1, "result": {"test": "message"}}

    # Mock stdout to capture output
    with patch("builtins.print") as mock_print:
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
    with patch("berry_mcp.core.transport.FASTAPI_AVAILABLE", False):
        with pytest.raises(
            ImportError, match="FastAPI and related dependencies required"
        ):
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

        test_message = {"jsonrpc": "2.0", "id": 1, "result": {"test": "sse"}}

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
    with patch("builtins.print") as mock_print:
        try:
            # Simulate JSON decode error handling
            json.loads(invalid_json)
        except json.JSONDecodeError as e:
            error_resp = {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": f"Parse error: {e}"},
                "id": None,
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
        {"id": 3, "result": {"auto_jsonrpc": True}},
    ]

    with patch("builtins.print") as mock_print:
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
            return b""  # EOF

        line = self.data_lines[self.index]
        self.index += 1
        return line.encode() + b"\n"


@pytest.mark.asyncio
async def test_stdio_transport_receive_loop():
    """Test stdio transport receive loop with mock data"""
    transport = StdioTransport()

    # Mock data to receive
    test_messages = [
        '{"jsonrpc": "2.0", "id": 1, "method": "test", "params": {}}',
        '{"jsonrpc": "2.0", "id": 2, "method": "another", "params": {}}',
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


@pytest.mark.asyncio
async def test_stdio_transport_connect_error_handling():
    """Test stdio transport connection error handling"""
    transport = StdioTransport()

    # Mock connection failure
    with patch("asyncio.get_running_loop") as mock_loop:
        mock_loop.side_effect = Exception("Connection failed")

        await transport.connect()

        # Should handle error gracefully
        assert transport.closed is True
        assert transport._stdin_task is None


@pytest.mark.asyncio
async def test_stdio_transport_already_connected():
    """Test stdio transport handles already connected state"""
    transport = StdioTransport()

    # Mock an active task
    mock_task = asyncio.create_task(asyncio.sleep(1))
    transport._stdin_task = mock_task

    with patch("asyncio.get_running_loop") as mock_loop:
        await transport.connect()

        # Should not try to connect again
        mock_loop.assert_not_called()

    # Clean up
    mock_task.cancel()
    try:
        await mock_task
    except asyncio.CancelledError:
        pass
    await transport.close()


@pytest.mark.asyncio
async def test_stdio_transport_stdin_reader_error():
    """Test stdio transport handles stdin reader errors"""
    transport = StdioTransport()

    # Test the _read_stdin_async method with no reader
    transport._stdin_reader = None

    await transport._read_stdin_async()

    # Should handle gracefully and close
    assert transport.closed is True


@pytest.mark.asyncio
async def test_stdio_transport_receive_eof():
    """Test stdio transport handles EOF correctly"""
    transport = StdioTransport()

    # Mock reader that returns empty bytes (EOF)
    class EOFReader:
        async def read(self, size):
            return b""  # EOF

    transport._stdin_reader = EOFReader()

    await transport._read_stdin_async()

    # Should close on EOF
    assert transport.closed is True


@pytest.mark.asyncio
async def test_stdio_transport_json_decode_error():
    """Test stdio transport handles JSON decode errors"""
    transport = StdioTransport()

    # Mock reader with invalid JSON
    class InvalidJSONReader:
        def __init__(self):
            self.call_count = 0

        async def read(self, size):
            self.call_count += 1
            if self.call_count == 1:
                return b"invalid json here\n"  # Invalid JSON
            return b""  # EOF after invalid JSON

    transport._stdin_reader = InvalidJSONReader()

    with patch.object(transport, "send") as mock_send:
        await transport._read_stdin_async()

        # Should have sent error response
        mock_send.assert_called_once()
        error_msg = mock_send.call_args[0][0]
        assert error_msg["error"]["code"] == -32700
        assert "Parse error" in error_msg["error"]["message"]


@pytest.mark.asyncio
async def test_stdio_transport_task_cancellation():
    """Test stdio transport handles task cancellation"""
    transport = StdioTransport()

    # Mock reader that will be cancelled
    class CancellableReader:
        async def read(self, size):
            await asyncio.sleep(10)  # Long sleep to allow cancellation

    transport._stdin_reader = CancellableReader()

    # Start the reader task
    task = asyncio.create_task(transport._read_stdin_async())

    # Let it start
    await asyncio.sleep(0.01)

    # Cancel the task
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass  # Expected


@pytest.mark.asyncio
async def test_stdio_transport_unexpected_error():
    """Test stdio transport handles unexpected errors"""
    transport = StdioTransport()

    # Mock reader that raises unexpected error
    class ErrorReader:
        def __init__(self):
            self.call_count = 0

        async def read(self, size):
            self.call_count += 1
            if self.call_count == 1:
                raise RuntimeError("Unexpected error")
            return b""  # EOF

    transport._stdin_reader = ErrorReader()

    await transport._read_stdin_async()

    # Should close on unexpected error
    assert transport.closed is True


@pytest.mark.asyncio
async def test_stdio_transport_receive_closed():
    """Test stdio transport receive when closed"""
    transport = StdioTransport()
    transport.closed = True

    # Should return None when closed and queue empty
    result = await transport.receive()
    assert result is None


@pytest.mark.asyncio
async def test_stdio_transport_close_task_timeout():
    """Test stdio transport close with task timeout"""
    transport = StdioTransport()

    # Mock a task that won't cancel quickly
    async def slow_task():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            await asyncio.sleep(2)  # Delay cancellation
            raise

    transport._stdin_task = asyncio.create_task(slow_task())

    # Close should handle timeout
    await transport.close()

    # Should be closed regardless
    assert transport.closed is True


@pytest.mark.asyncio
async def test_stdio_transport_close_task_error():
    """Test stdio transport close with task error"""
    transport = StdioTransport()

    # Mock a task that raises error during cancellation
    async def error_task():
        await asyncio.sleep(10)

    task = asyncio.create_task(error_task())
    transport._stdin_task = task

    # Mock the task to raise error when awaited
    with patch.object(asyncio, "wait_for") as mock_wait:
        mock_wait.side_effect = Exception("Task error")

        await transport.close()

        # Should handle error and still close
        assert transport.closed is True


@pytest.mark.asyncio
async def test_stdio_transport_message_type_detection():
    """Test stdio transport message type detection"""
    transport = StdioTransport()

    # Test different message types
    assert transport._get_message_type({"result": "test"}) == "response"
    assert transport._get_message_type({"error": {"code": -1}}) == "error"
    assert transport._get_message_type({"method": "test"}) == "notification"
    assert transport._get_message_type({"id": 1}) == "unknown"


@pytest.mark.asyncio
async def test_sse_transport_message_handler():
    """Test SSE transport message handler"""
    try:
        transport = SSETransport("localhost", 8001)

        async def test_handler(message):
            return {"response": "test"}

        transport.set_message_handler(test_handler)

        assert transport._message_handler == test_handler

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_send_closed():
    """Test SSE transport send when closed"""
    try:
        transport = SSETransport("localhost", 8001)
        transport.closed = True

        # Should handle send gracefully when closed
        await transport.send({"test": "message"})

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_send_serialization_error():
    """Test SSE transport handles serialization errors"""
    try:
        transport = SSETransport("localhost", 8001)

        # Add mock client
        mock_queue = asyncio.Queue()
        transport.clients.append(mock_queue)

        # Try to send non-serializable data
        class NonSerializable:
            pass

        message = {"data": NonSerializable()}

        await transport.send(message)

        # Queue should remain empty due to serialization error
        assert mock_queue.empty()

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_client_queue_full():
    """Test SSE transport handles full client queues"""
    try:
        transport = SSETransport("localhost", 8001)

        # Create a full queue
        full_queue = asyncio.Queue(maxsize=1)
        await full_queue.put("blocking_item")
        transport.clients.append(full_queue)

        # Should handle queue full gracefully
        await transport.send({"test": "message"})

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_client_timeout():
    """Test SSE transport handles client timeouts"""
    try:
        transport = SSETransport("localhost", 8001)

        # Mock queue that times out
        class TimeoutQueue:
            async def put(self, item, timeout=None):
                await asyncio.sleep(1)  # Will timeout

        timeout_queue = TimeoutQueue()
        transport.clients.append(timeout_queue)

        # Should handle timeout gracefully
        await transport.send({"test": "message"})

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_receive_not_applicable():
    """Test SSE transport receive method"""
    try:
        transport = SSETransport("localhost", 8001)

        # Should return None and log warning
        result = await transport.receive()
        assert result is None

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_already_closed():
    """Test SSE transport close when already closed"""
    try:
        transport = SSETransport("localhost", 8001)
        transport.closed = True

        # Should handle double close gracefully
        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_transport_base_receive_not_implemented():
    """Test base transport receive raises NotImplementedError"""
    from berry_mcp.core.transport import Transport

    class MinimalTransport(Transport):
        async def connect(self):
            pass

        async def send(self, message):
            pass

        async def close(self):
            pass

    transport = MinimalTransport()

    with pytest.raises(NotImplementedError):
        await transport.receive()


@pytest.mark.asyncio
async def test_stdio_transport_empty_lines():
    """Test stdio transport handles empty lines"""
    transport = StdioTransport()

    # Mock reader with empty lines
    class EmptyLineReader:
        def __init__(self):
            self.call_count = 0

        async def read(self, size):
            self.call_count += 1
            if self.call_count == 1:
                return b"\n\n   \n"  # Empty lines and whitespace
            elif self.call_count == 2:
                return b'{"jsonrpc": "2.0", "id": 1}\n'
            return b""  # EOF

    transport._stdin_reader = EmptyLineReader()

    await transport._read_stdin_async()

    # Should have processed the valid JSON message
    message = await transport.receive()
    assert message is not None
    assert message["id"] == 1


@pytest.mark.asyncio
async def test_sse_transport_ping_endpoint():
    """Test SSE transport ping endpoint"""
    try:
        from fastapi import FastAPI

        transport = SSETransport("localhost", 8001)
        app = FastAPI()
        transport.app = app

        await transport.connect()

        # Mock request
        mock_request = MagicMock()
        mock_request.client = None

        # Test ping endpoint
        response = await transport._handle_ping(mock_request)

        assert response.status_code == 200
        content = response.body.decode()
        data = json.loads(content)
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "connected_clients" in data

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_handle_message_invalid_json():
    """Test SSE transport handles invalid JSON in HTTP requests"""
    try:
        from fastapi import FastAPI, Request, BackgroundTasks

        transport = SSETransport("localhost", 8001)
        app = FastAPI()
        transport.app = app

        # Mock request with invalid JSON
        mock_request = AsyncMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b"invalid json")
        mock_background = MagicMock(spec=BackgroundTasks)

        response = await transport._handle_message(mock_request, mock_background)

        assert response.status_code == 400
        content = json.loads(response.body.decode())
        assert "Invalid JSON" in content["error"]

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_handle_message_missing_method():
    """Test SSE transport handles missing method parameter"""
    try:
        from fastapi import FastAPI, Request, BackgroundTasks

        transport = SSETransport("localhost", 8001)
        app = FastAPI()
        transport.app = app

        # Mock request with missing method
        mock_request = AsyncMock(spec=Request)
        request_data = {"jsonrpc": "2.0", "id": 1, "params": {}}
        mock_request.body = AsyncMock(return_value=json.dumps(request_data).encode())
        mock_background = MagicMock(spec=BackgroundTasks)

        response = await transport._handle_message(mock_request, mock_background)

        assert response.status_code == 400
        content = json.loads(response.body.decode())
        assert "Missing method parameter" in content["error"]

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_handle_initialize():
    """Test SSE transport handles initialize method"""
    try:
        from fastapi import FastAPI, Request, BackgroundTasks

        transport = SSETransport("localhost", 8001)
        app = FastAPI()
        transport.app = app

        # Mock handler
        async def mock_handler(message):
            return {"jsonrpc": "2.0", "id": 1, "result": {"initialized": True}}

        transport.set_message_handler(mock_handler)

        # Mock initialize request
        mock_request = AsyncMock(spec=Request)
        request_data = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        mock_request.body = AsyncMock(return_value=json.dumps(request_data).encode())
        mock_background = MagicMock(spec=BackgroundTasks)

        response = await transport._handle_message(mock_request, mock_background)

        assert response.status_code == 200
        content = json.loads(response.body.decode())
        assert content["result"]["initialized"] is True

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_background_execution_handler_exception():
    """Test SSE transport background execution when handler raises exception"""
    try:
        transport = SSETransport("localhost", 8001)

        # Mock handler that raises exception
        async def mock_handler(message):
            raise ValueError("Handler error")

        transport.set_message_handler(mock_handler)

        # Mock send method to capture error
        sent_messages = []

        async def mock_send(message):
            sent_messages.append(message)

        transport.send = mock_send

        request_data = {"jsonrpc": "2.0", "id": 1, "method": "test", "params": {}}

        await transport._run_handler_background(request_data)

        # Should have sent error message
        assert len(sent_messages) == 1
        error_msg = sent_messages[0]
        assert "Background execution failed" in error_msg["error"]["message"]

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")


@pytest.mark.asyncio
async def test_sse_transport_send_different_event_types():
    """Test SSE transport sends different event types correctly"""
    try:
        transport = SSETransport("localhost", 8001)

        # Add mock client
        mock_queue = asyncio.Queue()
        transport.clients.append(mock_queue)

        # Test different message types
        test_cases = [
            ({"method": "notifications/progress", "params": {}}, "progress"),
            ({"method": "notifications/info", "params": {}}, "system"),
            ({"result": {"data": "test"}}, "message"),
        ]

        for message, expected_event in test_cases:
            await transport.send(message)

            sse_event = await mock_queue.get()
            assert sse_event["event"] == expected_event

        await transport.close()

    except ImportError:
        pytest.skip("FastAPI not available")

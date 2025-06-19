"""
Tests for MCP protocol handling
"""

import pytest

from berry_mcp.core.protocol import MCPProtocol, RequestHandlerExtra


@pytest.fixture
def protocol():
    """Create a protocol instance for testing"""
    return MCPProtocol()


@pytest.mark.asyncio
async def test_protocol_invalid_jsonrpc_version(protocol):
    """Test handling of invalid JSON-RPC version"""
    message = {
        "jsonrpc": "1.0",  # Invalid version
        "id": 1,
        "method": "test",
        "params": {},
    }

    response = await protocol.handle_message(message)

    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] is None
    assert "error" in response
    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "Invalid Request"
    assert response["error"]["data"] == "Invalid JSON-RPC version"


@pytest.mark.asyncio
async def test_protocol_missing_method(protocol):
    """Test handling of missing method parameter"""
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "params": {},
        # No method field
    }

    response = await protocol.handle_message(message)

    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "error" in response
    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "Invalid Request"
    assert response["error"]["data"] == "'method' parameter is missing"


@pytest.mark.asyncio
async def test_protocol_method_not_found(protocol):
    """Test handling of unregistered method"""
    message = {"jsonrpc": "2.0", "id": 1, "method": "nonexistent_method", "params": {}}

    response = await protocol.handle_message(message)

    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "error" in response
    assert response["error"]["code"] == -32601
    assert "Method not found" in response["error"]["message"]


@pytest.mark.asyncio
async def test_protocol_handler_exception(protocol):
    """Test handling of exceptions in request handlers"""

    async def failing_handler(params, extra):
        raise ValueError("Test exception")

    protocol.set_request_handler("failing_method", failing_handler)

    message = {"jsonrpc": "2.0", "id": 1, "method": "failing_method", "params": {}}

    response = await protocol.handle_message(message)

    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "error" in response
    assert response["error"]["code"] == -32000
    assert "Server error executing method" in response["error"]["message"]
    assert "ValueError: Test exception" in response["error"]["message"]


@pytest.mark.asyncio
async def test_protocol_notification_no_response(protocol):
    """Test that notifications don't return responses"""

    async def test_handler(params, extra):
        return {"result": "success"}

    protocol.set_request_handler("notification_method", test_handler)

    # Notification (no id field)
    message = {"jsonrpc": "2.0", "method": "notification_method", "params": {}}

    response = await protocol.handle_message(message)

    # Notifications should not return a response
    assert response is None


@pytest.mark.asyncio
async def test_protocol_success_response_formatting(protocol):
    """Test successful response formatting"""

    async def success_handler(params, extra):
        return {"data": "test_result", "count": 42}

    protocol.set_request_handler("success_method", success_handler)

    message = {
        "jsonrpc": "2.0",
        "id": 123,
        "method": "success_method",
        "params": {"input": "test"},
    }

    response = await protocol.handle_message(message)

    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 123
    assert "result" in response
    assert response["result"]["data"] == "test_result"
    assert response["result"]["count"] == 42


@pytest.mark.asyncio
async def test_protocol_handler_with_params(protocol):
    """Test handler receives correct parameters and extra info"""

    received_params = None
    received_extra = None

    async def param_handler(params, extra):
        nonlocal received_params, received_extra
        received_params = params
        received_extra = extra
        return {"received": True}

    protocol.set_request_handler("param_method", param_handler)

    message = {
        "jsonrpc": "2.0",
        "id": 456,
        "method": "param_method",
        "params": {"test_param": "test_value", "number": 123},
    }

    response = await protocol.handle_message(message)

    assert response is not None
    assert received_params == {"test_param": "test_value", "number": 123}
    assert isinstance(received_extra, RequestHandlerExtra)
    assert received_extra.id == 456


@pytest.mark.asyncio
async def test_protocol_send_notification(protocol):
    """Test sending notifications"""
    sent_messages = []

    async def mock_sender(message):
        sent_messages.append(message)

    protocol.set_send_implementation(mock_sender)

    await protocol.send_notification("test_notification", {"param": "value"})

    assert len(sent_messages) == 1
    message = sent_messages[0]
    assert message["jsonrpc"] == "2.0"
    assert message["method"] == "test_notification"
    assert message["params"] == {"param": "value"}
    assert "id" not in message


@pytest.mark.asyncio
async def test_protocol_send_notification_no_params(protocol):
    """Test sending notifications without parameters"""
    sent_messages = []

    async def mock_sender(message):
        sent_messages.append(message)

    protocol.set_send_implementation(mock_sender)

    await protocol.send_notification("simple_notification")

    assert len(sent_messages) == 1
    message = sent_messages[0]
    assert message["jsonrpc"] == "2.0"
    assert message["method"] == "simple_notification"
    assert message["params"] == {}


@pytest.mark.asyncio
async def test_protocol_send_notification_no_sender(protocol):
    """Test sending notification without configured sender"""
    # No sender configured - should not raise exception
    await protocol.send_notification("test_notification", {"param": "value"})
    # Should complete without error


@pytest.mark.asyncio
async def test_protocol_error_formatting():
    """Test error response formatting"""
    protocol = MCPProtocol()

    error_response = protocol._format_error(123, -32600, "Test Error", "Test details")

    assert error_response["jsonrpc"] == "2.0"
    assert error_response["id"] == 123
    assert "error" in error_response
    assert error_response["error"]["code"] == -32600
    assert error_response["error"]["message"] == "Test Error"
    assert error_response["error"]["data"] == "Test details"


@pytest.mark.asyncio
async def test_protocol_error_formatting_no_details():
    """Test error response formatting without details"""
    protocol = MCPProtocol()

    error_response = protocol._format_error(456, -32601, "Simple Error")

    assert error_response["jsonrpc"] == "2.0"
    assert error_response["id"] == 456
    assert "error" in error_response
    assert error_response["error"]["code"] == -32601
    assert error_response["error"]["message"] == "Simple Error"


@pytest.mark.asyncio
async def test_protocol_result_formatting():
    """Test result response formatting"""
    protocol = MCPProtocol()

    result_data = {"success": True, "data": [1, 2, 3]}
    result_response = protocol._format_result(789, result_data)

    assert result_response["jsonrpc"] == "2.0"
    assert result_response["id"] == 789
    assert "result" in result_response
    assert result_response["result"] == result_data


@pytest.mark.asyncio
async def test_request_handler_extra():
    """Test RequestHandlerExtra class"""
    extra = RequestHandlerExtra(id=123)
    assert extra.id == 123

    extra_none = RequestHandlerExtra(id=None)
    assert extra_none.id is None

"""
MCP protocol implementation for Berry MCP Server
Handles JSON-RPC message parsing, routing, and formatting
"""

import json
import logging
import traceback
from collections.abc import Callable, Coroutine
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class RequestHandlerExtra(NamedTuple):
    """Extra information passed to request handlers"""

    id: str | int | None  # Request ID


class MCPProtocol:
    """Handles MCP JSON-RPC message parsing, routing, and formatting"""

    def __init__(self):
        self._request_handlers: dict[
            str,
            Callable[[dict[str, Any], RequestHandlerExtra], Coroutine[Any, Any, Any]],
        ] = {}
        self._send_message_impl: (
            Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None
        ) = None
        logger.debug("MCPProtocol initialized")

    def set_request_handler(
        self,
        method: str,
        handler: Callable[
            [dict[str, Any], RequestHandlerExtra], Coroutine[Any, Any, Any]
        ],
    ):
        """Register a handler for a specific request method"""
        self._request_handlers[method] = handler
        logger.debug(f"Registered request handler for method: {method}")

    async def handle_message(
        self, message_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Process an incoming message dictionary, route to handler, and format response.

        Args:
            message_data: The parsed JSON dictionary from the incoming message

        Returns:
            A dictionary representing the JSON-RPC response to be sent,
            or None if no response is required (e.g., for notifications)
        """
        response: dict[str, Any] | None = None
        request_id = message_data.get("id")
        method = message_data.get("method")
        params = message_data.get("params", {})

        # Prepare extra information for handlers
        extra = RequestHandlerExtra(id=request_id)

        # Basic JSON-RPC validation
        if message_data.get("jsonrpc") != "2.0":
            logger.warning(
                f"Invalid JSON-RPC version in message: {str(message_data)[:150]}"
            )
            return self._format_error(
                None, -32600, "Invalid Request", "Invalid JSON-RPC version"
            )

        if not method:
            logger.warning(f"Missing method in message: {str(message_data)[:150]}")
            return self._format_error(
                request_id, -32600, "Invalid Request", "'method' parameter is missing"
            )

        if method not in self._request_handlers:
            logger.warning(f"No handler found for method '{method}' (ID: {request_id})")
            return self._format_error(request_id, -32601, f"Method not found: {method}")

        # Call handler and process result
        handler = self._request_handlers[method]
        try:
            logger.debug(f"Calling handler for method '{method}' (ID: {request_id})")
            result_data = await handler(params, extra)
            logger.debug(
                f"Handler for '{method}' completed successfully, returned: {type(result_data)}"
            )

            if request_id is not None:
                # Request expecting a response
                logger.debug(f"Formatting result for '{method}' (ID: {request_id})")
                response = self._format_result(request_id, result_data)
            else:
                # Notification, no response needed
                logger.debug(f"Notification for method '{method}' processed")
                response = None

        except Exception as e:
            # Handle exceptions during handler execution
            error_type = type(e).__name__
            error_message = str(e)
            detailed_error = f"Server error executing method '{method}': {error_type}: {error_message}"

            logger.error(
                f"Exception during handler execution for '{method}' (ID: {request_id}): {detailed_error}",
                exc_info=True,
            )

            if request_id is not None:
                # Include traceback in debug mode
                error_data = (
                    traceback.format_exc()
                    if logger.isEnabledFor(logging.DEBUG)
                    else None
                )
                response = self._format_error(
                    req_id=request_id,
                    code=-32000,  # Generic server error
                    message=detailed_error,
                    data=error_data,
                )
            else:
                # Cannot send error response for notification
                response = None

        if response:
            logger.debug(
                f"Prepared response for ID {request_id}: {str(response)[:150]}..."
            )

        return response

    def _format_result(self, req_id: str | int | None, result: Any) -> dict[str, Any]:
        """Format a successful JSON-RPC response"""
        if req_id is None:
            logger.error("Attempted to format result for request with no ID")
            return {"jsonrpc": "2.0", "result": result, "id": None}

        # Test JSON serialization
        try:
            json.dumps(result)
            final_result = result
        except TypeError as e:
            logger.error(
                f"Result for request ID {req_id} is not JSON serializable: {e}"
            )
            final_result = f"[Non-Serializable Result: {type(result).__name__}] {str(result)[:500]}"
        except Exception as e:
            logger.error(
                f"Unexpected error during result serialization for ID {req_id}: {e}"
            )
            final_result = f"[Serialization Error: {e}]"

        return {"jsonrpc": "2.0", "id": req_id, "result": final_result}

    def _format_error(
        self, req_id: str | int | None, code: int, message: str, data: Any | None = None
    ) -> dict[str, Any]:
        """Format a JSON-RPC error response"""
        error_obj = {"code": code, "message": message}

        if data is not None:
            # Ensure data is serializable
            if isinstance(data, (str, int, float, bool, list, dict, type(None))):
                error_obj["data"] = data
            else:
                try:
                    data_str = str(data)
                    error_obj["data"] = (
                        f"Non-serializable data of type {type(data).__name__}: {data_str[:100]}"
                    )
                    logger.warning(
                        f"Error data contains non-standard type {type(data).__name__}"
                    )
                except Exception as str_err:
                    error_obj["data"] = (
                        f"Non-serializable data of type {type(data).__name__}, conversion failed: {str_err}"
                    )
                    logger.error(f"Failed to convert error data to string: {str_err}")

        return {"jsonrpc": "2.0", "id": req_id, "error": error_obj}

    # Notification sending
    def set_send_implementation(
        self, sender: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
    ):
        """Set the function used to send messages out via transport"""
        self._send_message_impl = sender
        logger.info("Send implementation configured for MCPProtocol")

    async def send_notification(
        self, method: str, params: dict[str, Any] | None = None
    ):
        """Build and send a JSON-RPC notification via the configured sender"""
        if not self._send_message_impl or not callable(self._send_message_impl):
            logger.error("Cannot send notification: No send implementation configured")
            return

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params if params is not None else {},
        }

        try:
            logger.debug(f"Sending notification: Method={method}")
            await self._send_message_impl(message)
        except Exception as e:
            logger.error(f"Failed to send notification '{method}': {e}", exc_info=True)

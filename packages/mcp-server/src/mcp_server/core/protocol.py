# packages/mcp-server/src/mcp_server/mcp/protocol.py
import asyncio
import json
import logging
import traceback
from typing import Dict, Any, Optional, Callable, Coroutine, NamedTuple

logger = logging.getLogger(__name__)

# Simplified Extra - no context needed, just carries the ID
class RequestHandlerExtra(NamedTuple):
    id: Optional[str | int] # Request ID

class MCPProtocol:
    """Handles MCP JSON-RPC message parsing, routing, and formatting."""

    def __init__(self):
        # Handler now only takes params and simple extra (just ID)
        # The handler coroutine is expected to return the result payload (any JSON-serializable type)
        # The handler should catch its own internal errors and return them as part of the result
        # payload if possible (e.g., {'error': 'description'}).
        # Only exceptions raised *by* the handler itself will trigger a JSON-RPC error response.
        self._request_handlers: Dict[str, Callable[[Dict[str, Any], RequestHandlerExtra], Coroutine[Any, Any, Any]]] = {}
        # Function used to send notifications back out (set by Transport)
        self._send_message_impl: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None
        logger.debug("MCPProtocol initialized.")

    def set_request_handler(self, method: str, handler: Callable[[Dict[str, Any], RequestHandlerExtra], Coroutine[Any, Any, Any]]):
        """Register a handler for a specific request method."""
        self._request_handlers[method] = handler
        logger.debug(f"Registered request handler for method: {method}")

    async def handle_message(self, message_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process an incoming message dictionary, route to handler, and format response.
        If the handler returns successfully (doesn't raise exception), its return value
        is placed in the 'result' field of the JSON-RPC response.
        If the handler raises an exception, a JSON-RPC error response is generated.

        Args:
            message_data: The parsed JSON dictionary from the incoming message.

        Returns:
            A dictionary representing the JSON-RPC response to be sent,
            or None if no response is required (e.g., for notifications or
            protocol errors where no ID was present).
        """
        response: Optional[Dict[str, Any]] = None
        request_id = message_data.get("id") # Can be str, int, or None
        method = message_data.get("method")
        params = message_data.get("params", {})

        # Prepare the simpler 'extra' information containing only the ID
        extra = RequestHandlerExtra(id=request_id)

        # --- Basic JSON-RPC Validation ---
        if message_data.get("jsonrpc") != "2.0":
            logger.warning(f"Received message with invalid 'jsonrpc' version: {str(message_data)[:150]}")
            # No reliable ID, return error format defined by spec (null id if possible)
            return self._format_error(None, -32600, "Invalid Request", "Invalid JSON-RPC version")

        if not method:
            logger.warning(f"Received message without 'method': {str(message_data)[:150]}")
            return self._format_error(request_id, -32600, "Invalid Request", "'method' parameter is missing")

        if method not in self._request_handlers:
            logger.warning(f"No handler found for method '{method}' (ID: {request_id}).")
            return self._format_error(request_id, -32601, f"Method not found: {method}")
        # --- End Validation ---

        # --- Call Handler and Process Result/Error ---
        handler = self._request_handlers[method]
        try:
            # Call the registered handler (e.g., MCPServer._handle_execute_tool)
            logger.debug(f"Calling handler for method '{method}' (ID: {request_id})")
            result_data = await handler(params, extra) # Pass params and simple extra
            logger.debug(f"Handler for '{method}' (ID: {request_id}) completed successfully, returned type: {type(result_data)}")

            # --- SIMPLIFIED LOGIC: ALWAYS format as success if handler doesn't raise exception ---
            # The interpretation of the result_data (whether it indicates success or failure
            # based on its internal structure, like exit_code or an 'error' key)
            # is left to the client (the agent/LLM). The server just passes it through.

            if request_id is not None:
                # It was a request expecting a response. Format the received result_data.
                logger.debug(f"Formatting result for '{method}' (ID: {request_id})")
                response = self._format_result(request_id, result_data)
            else:
                 # It was a Notification, no response needed.
                 logger.debug(f"Received Notification for method '{method}'. No response needed.")
                 response = None
            # --- END SIMPLIFIED LOGIC ---

        except Exception as e:
             # --- Handle Exceptions RAISED BY Handler Execution ---
             # This catches unexpected errors DURING handler execution (e.g., tool raised exception)
             error_type_name = type(e).__name__
             error_message = str(e)
             detailed_error_message = f"Server error executing method '{method}': {error_type_name}: {error_message}"
             logger.error(f"Exception *during* handler execution for method '{method}' (ID: {request_id}): {detailed_error_message}", exc_info=True)

             # Format a generic server error response IF a request ID exists
             if request_id is not None:
                 # Include traceback in 'data' only if debugging is enabled for security
                 error_data = traceback.format_exc() if logger.isEnabledFor(logging.DEBUG) else None
                 response = self._format_error(
                     req_id=request_id,
                     code=-32000, # Generic Server Error code
                     message=detailed_error_message, # Report the exception from the handler
                     data=error_data
                 )
             else:
                 # Cannot send error response for notification error
                 response = None
             # --- End Exception Handling ---

        if response:
            logger.debug(f"Prepared response for ID {request_id}: {str(response)[:150]}...")
        return response

    def _format_result(self, req_id: Optional[str | int], result: Any) -> Dict[str, Any]:
        """Formats a successful JSON-RPC response."""
        if req_id is None:
             logger.error("Attempted to format result for a request with no ID.")
             # Per spec, result MUST be sent if request ID was null (even if invalid request structure)
             # But for internal logic, we should only call this if ID was present.
             # Returning just the result technically violates spec if no ID.
             # However, our handle_message ensures we only call this if req_id is not None.
             return {"jsonrpc": "2.0", "result": result, "id": None} # Should not happen

        # Attempt to serialize result here to catch errors early
        try:
             # Test serialization - doesn't actually use the result, just checks validity
             json.dumps(result)
             final_result = result
        except TypeError as e:
             logger.error(f"Result for request ID {req_id} is not JSON serializable (Type: {type(result).__name__}). Sending string representation. Error: {e}")
             final_result = f"[Non-Serializable Result: {type(result).__name__}] {str(result)[:500]}..."
        except Exception as e:
             logger.error(f"Unexpected error during result serialization check for ID {req_id}: {e}")
             final_result = f"[Serialization Error: {e}]"


        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": final_result
        }

    def _format_error(self, req_id: Optional[str | int], code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
        """Formats a JSON-RPC error response."""
        error_obj = {"code": code, "message": message}
        if data is not None:
            # Ensure data is somewhat serializable if possible, or represent it
            if isinstance(data, (str, int, float, bool, list, dict, type(None))):
                 error_obj["data"] = data
            else:
                 try:
                     data_str = str(data)
                     error_obj["data"] = f"Non-serializable data of type {type(data).__name__}: {data_str[:100]}..."
                     logger.warning(f"Error 'data' field contains non-standard type {type(data).__name__}")
                 except Exception as str_err:
                     error_obj["data"] = f"Non-serializable data of type {type(data).__name__}, conversion failed: {str_err}"
                     logger.error(f"Failed to convert non-serializable error data to string: {str_err}")

        # According to JSON-RPC 2.0 spec, error responses SHOULD include the ID
        # of the request if available (null if not available, e.g. parse error before ID read)
        return {
            "jsonrpc": "2.0",
            "id": req_id, # Include original ID (which might be None)
            "error": error_obj
        }

    # --- Notification Sending ---
    def set_send_implementation(self, sender: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]):
        """Sets the function used to actually send messages out (e.g., via transport)."""
        self._send_message_impl = sender
        logger.info("Send implementation configured for MCPProtocol.")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Builds and sends a JSON-RPC notification via the configured sender."""
        # Check if sender implementation exists and is callable
        if not hasattr(self, '_send_message_impl') or not callable(self._send_message_impl):
            logger.error("Cannot send notification: No send implementation configured or callable.")
            return

        message = {
            "jsonrpc": "2.0",
            "method": method,
            # Ensure params field is present, even if empty, per spec
            "params": params if params is not None else {}
        }
        # No 'id' field for notifications

        try:
            log.debug(f"Sending notification: Method={method}, Params={str(params)[:100]}...")
            await self._send_message_impl(message)
        except Exception as e:
            logger.error(f"Failed to send notification '{method}': {e}", exc_info=True)
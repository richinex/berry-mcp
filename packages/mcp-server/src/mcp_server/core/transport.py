# packages/mcp-server/src/mcp_server/mcp/transport.py
import asyncio
import json
import sys
import time
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable, Coroutine, Tuple, Union

import uvicorn
# --- UPDATED Imports ---
# Add BackgroundTasks back
from fastapi import FastAPI, Request, Response, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
import logging

# --- REMOVED PubSub Imports ---

logger = logging.getLogger(__name__)

# --- Abstract Base Class (Transport - Simplified - Unchanged) ---
class Transport(ABC):
    @abstractmethod
    async def connect(self): pass
    @abstractmethod
    async def send(self, message: Dict[str, Any]) -> None: pass
    async def receive(self) -> Optional[Dict[str, Any]]: raise NotImplementedError
    @abstractmethod
    async def close(self) -> None: pass
    def set_message_handler(self, handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, Optional[Dict[str, Any]]]]): pass

# --- StdioTransport (Unchanged - Assuming it's correct) ---
# ... (StdioTransport code remains the same as in your first block) ...
class StdioTransport(Transport):
    """Transport using standard input/output for communication."""
    def __init__(self):
        self.closed = False
        self._receive_queue = asyncio.Queue()
        self._stdin_reader: Optional[asyncio.StreamReader] = None # Store reader
        self._stdin_task: Optional[asyncio.Task] = None
        logger.info("StdioTransport initialized.")

    async def connect(self):
        logger.info("StdioTransport.connect: Starting connection attempt.")
        if self._stdin_task and not self._stdin_task.done():
             logger.warning("StdioTransport: Already connected.")
             return

        try:
            loop = asyncio.get_running_loop()
            self._stdin_reader = asyncio.StreamReader(loop=loop)
            protocol = asyncio.StreamReaderProtocol(self._stdin_reader, loop=loop)
            logger.info("StdioTransport: About to connect read pipe to sys.stdin.")
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            logger.info("StdioTransport: Connected read pipe to sys.stdin successfully (according to asyncio).")
        except Exception as e:
            logger.error(f"StdioTransport: CRITICAL FAILURE in connect_read_pipe: {e}", exc_info=True)
            self.closed = True
            return

        logger.info("StdioTransport.connect: Creating _read_stdin_async task...")
        self._stdin_task = asyncio.create_task(self._read_stdin_async(), name="StdioReaderAsync")
        logger.info("StdioTransport.connect: _read_stdin_async task created. Connection process complete.")


    async def _read_stdin_async(self):
        logger.info("StdioTransport: _read_stdin_async TASK STARTED.")
        if not self._stdin_reader:
            logger.error("StdioTransport: _stdin_reader is None in _read_stdin_async! Cannot read.")
            self.closed = True
            await self._receive_queue.put(None)
            return

        buffer = b""
        read_count = 0
        while not self.closed:
            try:
                read_count += 1
                chunk = await self._stdin_reader.read(1024)

                if not chunk:
                    logger.info("StdioTransport: EOF received. Closing.")
                    self.closed = True
                    await self._receive_queue.put(None)
                    break

                buffer += chunk

                while b'\n' in buffer:
                    line_bytes, buffer = buffer.split(b'\n', 1)
                    line = line_bytes.decode('utf-8').strip()
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                        await self._receive_queue.put(message)
                    except json.JSONDecodeError as json_err:
                        logger.warning(f"StdioTransport: Invalid JSON received: {json_err}. Line: {line[:100]}...")
                        error_resp = { "jsonrpc": "2.0", "error": {"code": -32700, "message": f"Parse error: {json_err}"}, "id": None }
                        await self.send(error_resp)
                    except Exception as e:
                        logger.error(f"StdioTransport: Error processing line: {e}", exc_info=True)
                        error_resp = { "jsonrpc": "2.0", "error": {"code": -32603, "message": f"Internal error processing line: {e}"}, "id": None }
                        await self.send(error_resp)

            except asyncio.CancelledError:
                logger.info("StdioTransport: Async stdin reader task cancelled.")
                break
            except Exception as e:
                logger.error(f"StdioTransport: Unexpected error in _read_stdin_async loop #{read_count}: {e}", exc_info=True)
                self.closed = True
                await self._receive_queue.put(None)
                try:
                     error_resp = { "jsonrpc": "2.0", "error": {"code": -32000, "message": f"Internal server error in reader: {e}"}, "id": None }
                     await self.send(error_resp)
                except Exception as send_err:
                     logger.error(f"StdioTransport: Failed to send critical reader error back to client: {send_err}")
                break
        logger.info("StdioTransport: Async stdin reader task finished.")

    async def send(self, message: Dict[str, Any]) -> None:
        if self.closed:
            logger.warning("StdioTransport: Send attempt on closed transport.")
            return
        try:
            if "jsonrpc" not in message: message["jsonrpc"] = "2.0"
            message_json = json.dumps(message) + '\n'
            print(message_json, end='', flush=True)
            msg_type = "response" if "result" in message else "error" if "error" in message else "notification" if "method" in message else "unknown"
            msg_id = message.get("id", "N/A")
            logger.debug(f"StdioTransport: Sent {msg_type} (ID: {msg_id}) to stdout.")
        except TypeError as e:
             logger.error(f"StdioTransport: Error serializing message to JSON: {e}. Message: {str(message)[:200]}")
        except Exception as e:
             logger.error(f"StdioTransport: Error sending message to stdout: {e}")


    async def receive(self) -> Optional[Dict[str, Any]]:
        if self.closed and self._receive_queue.empty(): return None
        message = await self._receive_queue.get()
        if message is None: self.closed = True; return None
        self._receive_queue.task_done()
        return message

    def set_message_handler(self, handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, Optional[Dict[str, Any]]]]):
        logger.info("StdioTransport: Message handler set (Note: transport uses receive(), handler called externally).")
        pass

    async def close(self) -> None:
        if self.closed: logger.debug("StdioTransport: Already closed."); return
        logger.info("StdioTransport: Closing...")
        self.closed = True
        if self._stdin_task and not self._stdin_task.done():
            logger.debug("StdioTransport: Cancelling stdin reader task.")
            self._stdin_task.cancel()
            try: await asyncio.wait_for(self._stdin_task, timeout=1.0)
            except asyncio.CancelledError: logger.debug("StdioTransport: Stdin reader task cancellation confirmed.")
            except asyncio.TimeoutError: logger.warning("StdioTransport: Timeout waiting for stdin reader task to cancel.")
            except Exception as e: logger.warning(f"StdioTransport: Error during stdin task cancellation wait: {e}")
        if hasattr(self, '_receive_queue'):
             try: self._receive_queue.put_nowait(None)
             except asyncio.QueueFull: logger.warning("StdioTransport: Receive queue full during close, couldn't add None signal.")
             except Exception as e: logger.error(f"StdioTransport: Error putting None signal in queue during close: {e}")
        logger.info("StdioTransport: Closed.")

# --- SSE Transport Implementation (REVISED with BackgroundTasks for tools/call) ---
class SSETransport(Transport):
    """
    Transport using FastAPI with Server-Sent Events.
    Handles 'tools/call' via BackgroundTasks for immediate HTTP 202 response.
    Other methods are handled synchronously.
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.clients: List[asyncio.Queue] = []
        self.closed = False
        self._message_handler: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, Optional[Dict[str, Any]]]]] = None
        self.app: Optional[FastAPI] = None
        logger.info(f"SSETransport initialized for {host}:{port}. Communication via HTTP POST and SSE stream.")

    def set_message_handler(self, handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, Optional[Dict[str, Any]]]]):
        self._message_handler = handler
        logger.info("SSETransport: Message handler set.")

    async def connect(self):
        if not self.app:
            raise RuntimeError("SSETransport requires an assigned FastAPI app instance.")
        logger.info("SSETransport: Connecting (configuring routes)...")
        # --- ADD BackgroundTasks to _handle_message signature when registering ---
        self.app.post("/message")(self._handle_message)
        self.app.get("/sse", response_class=EventSourceResponse)(self._handle_sse)
        self.app.get("/ping")(self._handle_ping)
        logger.info(f"SSETransport setup complete. Ready for server on {self.host}:{self.port}.")

    async def _handle_ping(self, request: Request):
        return JSONResponse({ "status": "ok", "timestamp": time.time(), "instance_sse_clients": len(self.clients) })

    async def _handle_sse(self, request: Request):
        client_host = request.client.host if request.client else "unknown"
        client_port = request.client.port if request.client else 0
        client_id_str = f"{client_host}:{client_port}"
        logger.info(f"SSE connection request from [{client_id_str}]")
        client_queue = asyncio.Queue(maxsize=100)
        self.clients.append(client_queue)
        logger.info(f"SSE client connected (queue added) [{client_id_str}]. Total local clients: {len(self.clients)}")

        async def event_generator():
            logger.info(f"Starting SSE event generator for client [{client_id_str}]")
            client_disconnected = False
            keep_alive_interval = 15.0
            try:
                yield {"event": "system", "data": json.dumps({"type": "connected", "message": "SSE connection established"}), "id": f"conn_{uuid.uuid4().hex[:8]}"}
                while not client_disconnected:
                    try:
                        message_dict = await asyncio.wait_for(client_queue.get(), timeout=keep_alive_interval)
                        if isinstance(message_dict, dict):
                            yield message_dict
                        else:
                             logger.warning(f"Non-dict object received in SSE queue for [{client_id_str}]: {type(message_dict)}")
                        client_queue.task_done()
                    except asyncio.TimeoutError:
                        yield {"comment": f"keep-alive ts={int(time.time())}"}
                    except asyncio.QueueEmpty: await asyncio.sleep(0.1)
                    except Exception as yield_err:
                         err_str = str(yield_err).lower()
                         if "disconnected" in err_str or "client disconnected" in err_str or "connection closed" in err_str:
                             logger.info(f"SSE client [{client_id_str}] disconnected (error during yield): {yield_err}")
                         else:
                             logger.error(f"Error yielding SSE message for client [{client_id_str}]: {yield_err}", exc_info=True)
                         client_disconnected = True
                         await asyncio.sleep(0.1)
            except asyncio.CancelledError: logger.info(f"SSE event generator cancelled for client [{client_id_str}].")
            except Exception as e: logger.error(f"Fatal error in SSE event generator for client [{client_id_str}]: {e}", exc_info=True)
            finally:
                if client_queue in self.clients:
                    try: self.clients.remove(client_queue)
                    except ValueError: pass
                logger.info(f"SSE client disconnected [{client_id_str}]. Remaining local clients: {len(self.clients)}")
        return EventSourceResponse(event_generator())

    # --- NEW: Helper function for background execution ---
    async def _run_handler_background(self, request_data: Dict[str, Any]):
        """Runs the message handler in the background and sends result/error via SSE."""
        request_id = request_data.get('id')
        method = request_data.get('method', 'unknown_method')
        tool_name = request_data.get('params', {}).get('name', 'unknown_tool') # Best effort name
        log_prefix = f"[BG Task ID: {request_id}, Method: {method}]"
        logger.info(f"{log_prefix} Starting background execution.")

        if not self._message_handler:
            logger.error(f"{log_prefix} Cannot execute: No message handler configured.")
            err_resp_sse = {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Internal server error: No message handler configured for background execution"}, "id": request_id}
            try: await self.send(err_resp_sse)
            except Exception as e: logger.error(f"{log_prefix} Failed to send handler config error via SSE: {e}")
            return

        response_data = None
        try:
            # Call the original message handler (e.g., MCPProtocol.handle_message)
            # This will execute MCPServer._handle_execute_tool -> await tool_func(...)
            response_data = await self._message_handler(request_data)

            if isinstance(response_data, dict):
                logger.info(f"{log_prefix} Background execution complete. Sending result/error via SSE.")
                await self.send(response_data) # Send the final result/error via SSE
            elif response_data is None:
                 logger.warning(f"{log_prefix} Background handler returned None unexpectedly. Sending acknowledgement.")
                 accepted_msg = {"jsonrpc": "2.0", "id": request_id, "result": {"status": "processed_no_data", "message": f"Background task for method '{method}' processed, but handler returned no data."}}
                 await self.send(accepted_msg)
            else:
                logger.error(f"{log_prefix} Background handler returned invalid type: {type(response_data)}")
                err_resp_sse = {"jsonrpc": "2.0", "error": {"code": -32000, "message": f"Internal server error: Invalid handler response type in background task ({type(response_data).__name__})"}, "id": request_id}
                await self.send(err_resp_sse)

        except Exception as e:
            log_msg = f"Exception during background execution of method '{method}': {type(e).__name__}: {e}"
            logger.error(f"{log_prefix} {log_msg}", exc_info=True)
            err_resp_sse = {"jsonrpc": "2.0", "error": {"code": -32000, "message": log_msg}, "id": request_id}
            try: await self.send(err_resp_sse)
            except Exception as send_err: logger.error(f"{log_prefix} Failed to send background execution error ({type(e).__name__}) via SSE: {send_err}")

    # --- REVISED _handle_message with BackgroundTasks ---
    async def _handle_message(self, request: Request, background_tasks: BackgroundTasks):
        """
        Handles incoming HTTP POST requests.
        Uses BackgroundTasks for 'tools/call', returns 202 immediately.
        Processes other methods synchronously, returns 202/204 after sending SSE.
        """
        request_body_raw = await request.body()
        request_data = None
        request_id = None
        method = "unknown"

        try:
            # 1. Parse Request
            try: request_data = json.loads(request_body_raw)
            except json.JSONDecodeError as e:
                logger.warning(f"HTTP POST failed: Invalid JSON. Error: {e}, Body: {request_body_raw[:200]}...")
                err_resp = {"jsonrpc": "2.0", "error": {"code": -32700, "message": f"Parse error: {e}"}, "id": None}
                return JSONResponse(status_code=400, content=err_resp)

            if not isinstance(request_data, dict) or request_data.get("jsonrpc") != "2.0": raise ValueError("Invalid JSON-RPC structure")
            method = request_data.get("method"); request_id = request_data.get('id')
            if not method or not isinstance(method, str): raise ValueError("Invalid JSON-RPC method")
            log_prefix = f"[Request ID: {request_id}, Method: {method}]"
            logger.info(f"{log_prefix} HTTP POST Received.")

            # 2. Check Handler
            if not self._message_handler:
                logger.error(f"{log_prefix} Cannot handle: No message handler configured.")
                err_resp = {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found (no message handler)"}, "id": request_id}
                return JSONResponse(status_code=501, content=err_resp)

            # 3. --- Conditional Execution ---
            if method == "tools/call":
                # --- Background Handling for tools/call ---
                logger.info(f"{log_prefix} Scheduling background execution.")
                # Minimal validation before scheduling might be good, e.g., check params exist
                if not isinstance(request_data.get("params"), dict):
                    logger.warning(f"{log_prefix} Invalid 'tools/call' request: Missing or invalid 'params'.")
                    err_resp = {"jsonrpc": "2.0", "error": {"code": -32602, "message": "Invalid parameters for tools/call: Missing or invalid 'params' object"}, "id": request_id}
                    return JSONResponse(status_code=400, content=err_resp)

                # Schedule the actual handler call to run in the background
                background_tasks.add_task(self._run_handler_background, request_data)

                # Return HTTP 202 Accepted immediately
                ack_response = { "jsonrpc": "2.0", "id": request_id, "result": {"status": "accepted", "message": f"Request for '{method}' accepted for background execution. Result/status via SSE."} }
                return JSONResponse(status_code=202, content=ack_response)
                # --- End Background Handling ---

            else:
                # --- Synchronous Handling for other methods ---
                logger.debug(f"{log_prefix} Processing synchronously.")
                response_data = await self._message_handler(request_data)

                if isinstance(response_data, dict):
                    logger.debug(f"{log_prefix} Sending synchronous response via SSE.")
                    await self.send(response_data) # Send result/error via SSE
                    # Acknowledge HTTP request (use 202 Accepted as the work is done, SSE sent)
                    ack_response = { "jsonrpc": "2.0", "id": request_id, "result": {"status": "processed_sync", "message": "Request processed synchronously. Result sent via SSE."} }
                    return JSONResponse(status_code=202, content=ack_response)

                elif response_data is None:
                     if request_id is None: # Notification processed
                         logger.debug(f"{log_prefix} Notification processed synchronously.")
                         return Response(status_code=204) # No Content
                     else: # Request expected response but got none
                         logger.warning(f"{log_prefix} Synchronous handler returned None.")
                         accepted_msg = {"jsonrpc": "2.0", "id": request_id, "result": {"status": "processed_no_data", "message": "Sync request processed, handler returned no data."}}
                         await self.send(accepted_msg)
                         ack_response = { "jsonrpc": "2.0", "id": request_id, "result": {"status": "received_no_handler_data", "message": "Request received, handler returned no data. Status via SSE."} }
                         return JSONResponse(status_code=202, content=ack_response) # Still Accepted
                else: # Invalid handler response
                     logger.error(f"{log_prefix} Internal error: Invalid handler response type: {type(response_data)}")
                     err_resp_sse = {"jsonrpc": "2.0", "error": {"code": -32000, "message": f"Internal server error: Invalid handler response type ({type(response_data).__name__})"}, "id": request_id}
                     try: await self.send(err_resp_sse)
                     except Exception: pass
                     return JSONResponse(status_code=500, content=err_resp_sse) # Internal Server Error
                # --- End Synchronous Handling ---

        except ValueError as e: # JSON-RPC validation errors
             logger.warning(f"HTTP POST failed: Invalid JSON-RPC request (ID: {request_id}). Error: {e}")
             err_resp = {"jsonrpc": "2.0", "error": {"code": -32600, "message": f"Invalid Request: {e}"}, "id": request_id}
             return JSONResponse(status_code=400, content=err_resp)
        except Exception as e: # Other unexpected errors
            log_msg = f"Internal server error processing POST request (ID: {request_id}, Method: {method}): {type(e).__name__}"
            logger.error(f"{log_msg}: {e}", exc_info=True)
            err_resp = {"jsonrpc": "2.0", "error": {"code": -32000, "message": log_msg}, "id": request_id}
            # Try to send error via SSE if possible (best effort)
            if isinstance(err_resp, dict):
                try: await self.send(err_resp)
                except Exception as send_err: logger.error(f"Failed to send internal server error via SSE: {send_err}")
            return JSONResponse(status_code=500, content={"status": "error", "message": err_resp.get("error",{}).get("message","Internal Server Error")})


    async def send(self, message: Dict[str, Any]) -> None:
        if self.closed: return
        event_type = "message"
        method = message.get("method")
        if method == "notifications/progress": event_type = "progress"
        elif method and method.startswith("notifications/"): event_type = "system"
        if "jsonrpc" not in message and ("method" in message or "result" in message or "error" in message): message["jsonrpc"] = "2.0"
        msg_id = message.get('id', uuid.uuid4().hex[:8])
        track_id = f"sse_{msg_id}"
        try: data_str = json.dumps(message)
        except TypeError as e: logger.error(f"Could not serialize SSE data. TrackID: {track_id}. Error: {e}. Data: {str(message)[:200]}..."); return
        sse_event = {"event": event_type, "data": data_str, "id": track_id}
        for client_queue in list(self.clients):
            try: await asyncio.wait_for(client_queue.put(sse_event), timeout=0.5)
            except asyncio.QueueFull: logger.warning(f"SSE client queue full (TrackID: {track_id}). Skipping.")
            except asyncio.TimeoutError: logger.warning(f"Timeout putting in SSE queue (TrackID: {track_id}). Skipping.")
            except Exception as q_err: logger.error(f"Error putting in client queue (TrackID: {track_id}): {q_err}")

    async def receive(self) -> Optional[Dict[str, Any]]:
         logger.warning("SSETransport.receive() called, but is not applicable.")
         return None

    async def close(self) -> None:
        if self.closed: logger.debug("SSETransport: Already closed."); return
        logger.info("SSETransport: Closing...")
        self.closed = True
        logger.info(f"Clearing {len(self.clients)} remaining local SSE client queues...")
        sse_shutdown_event = {"event": "system", "data": json.dumps({"type": "shutdown", "reason": "server_stopping"}), "id": f"shut_{uuid.uuid4().hex[:8]}"}
        tasks = []
        for client_queue in list(self.clients):
            try: tasks.append(asyncio.create_task(asyncio.wait_for(client_queue.put(sse_shutdown_event), timeout=0.2)))
            except Exception as put_err: logger.warning(f"Error queueing shutdown event: {put_err}")
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        self.clients.clear()
        logger.info("SSETransport: Closed.")
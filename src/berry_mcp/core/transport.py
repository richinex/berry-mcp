"""
Transport layer implementations for Berry MCP Server
Supports both stdio and HTTP/SSE communication methods
"""

import asyncio
import json
import logging
import sys
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any

# Optional FastAPI imports for SSE transport
try:
    import uvicorn
    from fastapi import BackgroundTasks, FastAPI, Request, Response
    from fastapi.responses import JSONResponse, StreamingResponse
    from sse_starlette.sse import EventSourceResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

    # Create dummy classes for type hints when FastAPI is not available
    class Request:
        pass

    class Response:
        pass

    class BackgroundTasks:
        pass

    class JSONResponse:
        pass

    class EventSourceResponse:
        pass


logger = logging.getLogger(__name__)


class Transport(ABC):
    """Abstract base class for MCP transport implementations"""

    @abstractmethod
    async def connect(self):
        """Establish connection"""
        pass

    @abstractmethod
    async def send(self, message: dict[str, Any]) -> None:
        """Send a message"""
        pass

    async def receive(self) -> dict[str, Any] | None:
        """Receive a message (optional for some transports)"""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close the connection"""
        pass

    def set_message_handler(
        self,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any] | None]],
    ):
        """Set message handler (optional for some transports)"""
        pass


class StdioTransport(Transport):
    """Transport using standard input/output for communication"""

    def __init__(self):
        self.closed = False
        self._receive_queue = asyncio.Queue()
        self._stdin_reader: asyncio.StreamReader | None = None
        self._stdin_task: asyncio.Task | None = None
        logger.info("StdioTransport initialized")

    async def connect(self):
        """Connect to stdio streams"""
        logger.info("StdioTransport: Starting connection")
        if self._stdin_task and not self._stdin_task.done():
            logger.warning("StdioTransport: Already connected")
            return

        try:
            loop = asyncio.get_running_loop()
            self._stdin_reader = asyncio.StreamReader(loop=loop)
            protocol = asyncio.StreamReaderProtocol(self._stdin_reader, loop=loop)
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            logger.info("StdioTransport: Connected to stdin successfully")
        except Exception as e:
            logger.error(
                f"StdioTransport: Failed to connect to stdin: {e}", exc_info=True
            )
            self.closed = True
            return

        self._stdin_task = asyncio.create_task(
            self._read_stdin_async(), name="StdioReader"
        )
        logger.info("StdioTransport: Connection complete")

    async def _read_stdin_async(self):
        """Async stdin reader task"""
        logger.debug("StdioTransport: Starting stdin reader task")
        if not self._stdin_reader:
            logger.error("StdioTransport: No stdin reader available")
            self.closed = True
            await self._receive_queue.put(None)
            return

        buffer = b""
        while not self.closed:
            try:
                chunk = await self._stdin_reader.read(1024)

                if not chunk:
                    logger.info("StdioTransport: EOF received, closing")
                    self.closed = True
                    await self._receive_queue.put(None)
                    break

                buffer += chunk

                # Process complete lines
                while b"\n" in buffer:
                    line_bytes, buffer = buffer.split(b"\n", 1)
                    line = line_bytes.decode("utf-8").strip()
                    if not line:
                        continue

                    try:
                        message = json.loads(line)
                        await self._receive_queue.put(message)
                    except json.JSONDecodeError as e:
                        logger.warning(f"StdioTransport: Invalid JSON: {e}")
                        error_resp = {
                            "jsonrpc": "2.0",
                            "error": {"code": -32700, "message": f"Parse error: {e}"},
                            "id": None,
                        }
                        await self.send(error_resp)
                    except Exception as e:
                        logger.error(
                            f"StdioTransport: Error processing line: {e}", exc_info=True
                        )

            except asyncio.CancelledError:
                logger.info("StdioTransport: Reader task cancelled")
                break
            except Exception as e:
                logger.error(
                    f"StdioTransport: Unexpected error in reader: {e}", exc_info=True
                )
                self.closed = True
                await self._receive_queue.put(None)
                break

        logger.debug("StdioTransport: Reader task finished")

    async def send(self, message: dict[str, Any]) -> None:
        """Send message to stdout"""
        if self.closed:
            logger.warning("StdioTransport: Attempted send on closed transport")
            return

        try:
            if "jsonrpc" not in message:
                message["jsonrpc"] = "2.0"

            message_json = json.dumps(message) + "\n"
            print(message_json, end="", flush=True)

            msg_type = self._get_message_type(message)
            msg_id = message.get("id", "N/A")
            logger.debug(f"StdioTransport: Sent {msg_type} (ID: {msg_id})")

        except Exception as e:
            logger.error(f"StdioTransport: Error sending message: {e}")

    def _get_message_type(self, message: dict[str, Any]) -> str:
        """Determine message type for logging"""
        if "result" in message:
            return "response"
        elif "error" in message:
            return "error"
        elif "method" in message:
            return "notification"
        else:
            return "unknown"

    async def receive(self) -> dict[str, Any] | None:
        """Receive message from queue"""
        if self.closed and self._receive_queue.empty():
            return None

        message = await self._receive_queue.get()
        if message is None:
            self.closed = True
            return None

        self._receive_queue.task_done()
        return message

    def set_message_handler(
        self,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any] | None]],
    ):
        """Set message handler (stdio uses receive() pattern)"""
        logger.debug("StdioTransport: Message handler set")

    async def close(self) -> None:
        """Close the transport"""
        if self.closed:
            return

        logger.info("StdioTransport: Closing")
        self.closed = True

        if self._stdin_task and not self._stdin_task.done():
            self._stdin_task.cancel()
            try:
                await asyncio.wait_for(self._stdin_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.warning(f"StdioTransport: Error during task cancellation: {e}")

        # Signal queue
        try:
            self._receive_queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

        logger.info("StdioTransport: Closed")


class SSETransport(Transport):
    """Transport using FastAPI with Server-Sent Events"""

    def __init__(self, host: str = "localhost", port: int = 8000):
        if not FASTAPI_AVAILABLE:
            raise ImportError(
                "FastAPI and related dependencies required for SSETransport"
            )

        self.host = host
        self.port = port
        self.clients: list[asyncio.Queue] = []
        self.closed = False
        self._message_handler: Callable | None = None
        self.app: FastAPI | None = None
        logger.info(f"SSETransport initialized for {host}:{port}")

    def set_message_handler(
        self,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any] | None]],
    ):
        """Set message handler for incoming HTTP requests"""
        self._message_handler = handler
        logger.info("SSETransport: Message handler set")

    async def connect(self):
        """Configure FastAPI routes"""
        if not self.app:
            raise RuntimeError("SSETransport requires an assigned FastAPI app instance")

        logger.info("SSETransport: Configuring routes")

        # Add routes - VS Code sends messages to root path
        self.app.post("/")(self._handle_message)  # Primary endpoint for VS Code
        self.app.post("/message")(self._handle_message)  # Alternative endpoint
        self.app.get("/sse", response_class=EventSourceResponse)(self._handle_sse)
        self.app.post("/sse")(
            self._handle_sse_post
        )  # For VS Code MCP client compatibility
        self.app.get("/ping")(self._handle_ping)

        logger.info(f"SSETransport: Ready for server on {self.host}:{self.port}")

    async def _handle_ping(self, request: Request):
        """Health check endpoint"""
        return JSONResponse(
            {
                "status": "ok",
                "timestamp": time.time(),
                "connected_clients": len(self.clients),
            }
        )

    async def _handle_sse(self, request: Request):
        """Handle SSE connections"""
        client_info = (
            f"{request.client.host}:{request.client.port}"
            if request.client
            else "unknown"
        )
        logger.info(f"SSE connection from {client_info}")

        client_queue = asyncio.Queue(maxsize=100)
        self.clients.append(client_queue)
        logger.info(f"SSE client connected. Total clients: {len(self.clients)}")

        async def event_generator():
            logger.debug(f"Starting SSE event generator for {client_info}")
            try:
                # Send connection confirmation
                yield {
                    "event": "system",
                    "data": json.dumps(
                        {"type": "connected", "message": "SSE connection established"}
                    ),
                    "id": f"conn_{uuid.uuid4().hex[:8]}",
                }

                while not self.closed:
                    try:
                        # Wait for message with timeout for keep-alive
                        message_dict = await asyncio.wait_for(
                            client_queue.get(), timeout=15.0
                        )
                        if isinstance(message_dict, dict):
                            yield message_dict
                        client_queue.task_done()

                    except asyncio.TimeoutError:
                        # Send keep-alive
                        yield {"comment": f"keep-alive ts={int(time.time())}"}
                    except Exception as e:
                        logger.error(f"Error in SSE generator for {client_info}: {e}")
                        break

            except asyncio.CancelledError:
                logger.info(f"SSE generator cancelled for {client_info}")
            except Exception as e:
                logger.error(f"Fatal error in SSE generator for {client_info}: {e}")
            finally:
                if client_queue in self.clients:
                    try:
                        self.clients.remove(client_queue)
                    except ValueError:
                        pass
                logger.info(f"SSE client disconnected. Remaining: {len(self.clients)}")

        return EventSourceResponse(event_generator())

    async def _handle_sse_post(
        self, request: Request, background_tasks: BackgroundTasks
    ):
        """Handle POST requests to /sse endpoint (for VS Code MCP compatibility)"""
        return await self._handle_message(request, background_tasks)

    async def _run_handler_background(self, request_data: dict[str, Any]):
        """Run message handler in background and send result via SSE"""
        request_id = request_data.get("id")
        method = request_data.get("method", "unknown")
        logger.info(f"Background execution for {method} (ID: {request_id})")

        if not self._message_handler:
            logger.error("No message handler configured for background execution")
            error_resp = {
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": "No message handler configured"},
                "id": request_id,
            }
            await self.send(error_resp)
            return

        try:
            response_data = await self._message_handler(request_data)

            if isinstance(response_data, dict):
                logger.info(f"Background execution complete for {method}")
                await self.send(response_data)
            elif response_data is None:
                logger.warning(f"Background handler returned None for {method}")
                ack_msg = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "status": "processed",
                        "message": "Background task completed",
                    },
                }
                await self.send(ack_msg)
            else:
                logger.error(f"Invalid handler response type: {type(response_data)}")
                error_resp = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32000, "message": "Invalid handler response"},
                    "id": request_id,
                }
                await self.send(error_resp)

        except Exception as e:
            logger.error(
                f"Background execution failed for {method}: {e}", exc_info=True
            )
            error_resp = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000,
                    "message": f"Background execution failed: {str(e)}",
                },
                "id": request_id,
            }
            await self.send(error_resp)

    async def _handle_message(
        self, request: Request, background_tasks: BackgroundTasks
    ):
        """Handle incoming HTTP POST requests"""
        try:
            request_body = await request.body()
            request_data = json.loads(request_body)

            # Validate JSON-RPC structure
            if (
                not isinstance(request_data, dict)
                or request_data.get("jsonrpc") != "2.0"
            ):
                return JSONResponse(
                    status_code=400, content={"error": "Invalid JSON-RPC structure"}
                )

            method = request_data.get("method")
            request_id = request_data.get("id")

            if not method:
                return JSONResponse(
                    status_code=400, content={"error": "Missing method parameter"}
                )

            logger.info(f"HTTP POST received: {method} (ID: {request_id})")

            if not self._message_handler:
                return JSONResponse(
                    status_code=501, content={"error": "No message handler configured"}
                )

            # Handle initialize request directly with immediate JSON response
            if method == "initialize":
                logger.info("Processing initialize request synchronously")
                response_data = await self._message_handler(request_data)

                if isinstance(response_data, dict):
                    # For initialize, return the response directly in HTTP body
                    return JSONResponse(status_code=200, content=response_data)
                else:
                    logger.error(f"Invalid initialize response: {type(response_data)}")
                    return JSONResponse(
                        status_code=500,
                        content={
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {"code": -32000, "message": "Initialize failed"},
                        },
                    )

            # Handle tools/call in background for immediate response
            elif method == "tools/call":
                if not isinstance(request_data.get("params"), dict):
                    return JSONResponse(
                        status_code=400,
                        content={"error": "Invalid parameters for tools/call"},
                    )

                logger.info(f"Scheduling background execution for {method}")
                background_tasks.add_task(self._run_handler_background, request_data)

                return JSONResponse(
                    status_code=202,
                    content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "status": "accepted",
                            "message": "Request accepted for background execution",
                        },
                    },
                )
            else:
                # Handle other methods synchronously
                logger.debug(f"Processing {method} synchronously")
                response_data = await self._message_handler(request_data)

                if isinstance(response_data, dict):
                    await self.send(response_data)
                    return JSONResponse(
                        status_code=202,
                        content={
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "status": "processed",
                                "message": "Request processed",
                            },
                        },
                    )
                elif response_data is None:
                    if request_id is None:
                        return Response(status_code=204)  # Notification processed
                    else:
                        return JSONResponse(
                            status_code=202,
                            content={
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "result": {
                                    "status": "processed",
                                    "message": "Request processed",
                                },
                            },
                        )
                else:
                    logger.error(
                        f"Invalid handler response type: {type(response_data)}"
                    )
                    return JSONResponse(
                        status_code=500, content={"error": "Invalid handler response"}
                    )

        except json.JSONDecodeError as e:
            return JSONResponse(
                status_code=400, content={"error": f"Invalid JSON: {str(e)}"}
            )
        except Exception as e:
            logger.error(f"Error handling HTTP request: {e}", exc_info=True)
            return JSONResponse(
                status_code=500, content={"error": "Internal server error"}
            )

    async def send(self, message: dict[str, Any]) -> None:
        """Send message to all connected SSE clients"""
        if self.closed:
            return

        # Determine event type
        event_type = "message"
        method = message.get("method")
        if method == "notifications/progress":
            event_type = "progress"
        elif method and method.startswith("notifications/"):
            event_type = "system"

        # Ensure jsonrpc field
        if "jsonrpc" not in message:
            message["jsonrpc"] = "2.0"

        msg_id = message.get("id", uuid.uuid4().hex[:8])
        track_id = f"sse_{msg_id}"

        try:
            data_str = json.dumps(message)
        except TypeError as e:
            logger.error(f"Could not serialize SSE data: {e}")
            return

        sse_event = {"event": event_type, "data": data_str, "id": track_id}

        # Send to all connected clients
        for client_queue in list(self.clients):
            try:
                await asyncio.wait_for(client_queue.put(sse_event), timeout=0.5)
            except asyncio.QueueFull:
                logger.warning(f"SSE client queue full, skipping message {track_id}")
            except asyncio.TimeoutError:
                logger.warning(
                    f"Timeout sending to SSE client, skipping message {track_id}"
                )
            except Exception as e:
                logger.error(f"Error sending to SSE client: {e}")

    async def receive(self) -> dict[str, Any] | None:
        """SSE transport doesn't use receive pattern"""
        logger.warning("SSETransport.receive() called but not applicable")
        return None

    async def close(self) -> None:
        """Close SSE transport"""
        if self.closed:
            return

        logger.info("SSETransport: Closing")
        self.closed = True

        # Send shutdown event to all clients
        shutdown_event = {
            "event": "system",
            "data": json.dumps({"type": "shutdown", "reason": "server_stopping"}),
            "id": f"shut_{uuid.uuid4().hex[:8]}",
        }

        tasks = []
        for client_queue in list(self.clients):
            try:
                tasks.append(
                    asyncio.create_task(
                        asyncio.wait_for(client_queue.put(shutdown_event), timeout=0.2)
                    )
                )
            except Exception as e:
                logger.warning(f"Error queueing shutdown event: {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.clients.clear()
        logger.info("SSETransport: Closed")

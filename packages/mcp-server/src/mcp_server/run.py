#!/usr/bin/env python
# packages/mcp-server/src/mcp_server/run.py

# src/ai_agent/mcp/run_bridge_server.py

import os
import asyncio
import argparse
import logging
import traceback
import uuid
import time
import sys
import json
import pathlib
import inspect
from typing import Dict, Any, List, Callable, Coroutine, Optional, Union, Tuple

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError # Keep for general validation

# --- Import Core MCP Components ---
from mcp_server.core.server import MCPServer
from mcp_server.core.transport import SSETransport, StdioTransport, Transport # Import BOTH
from mcp_server.core.protocol import MCPProtocol
# --- REMOVED core.models import, as they are no longer used by the bridge ---
# from mcp_server.core.models import (...)

# --- Import Resource System ---
from mcp_server.core.resources import ResourceRegistry
from mcp_server.core.filesystem_provider import FileSystemProvider

# --- REMOVED PubSub Imports ---
# PubSubManager, RedisPubSubManager etc. are gone.

# --- Import Tooling ---
from mcp_server.tools.loader import load_default_tools
# --- IMPORT FILE TOOLS MODULE ---
from mcp_server.tools import file_tools

# --- REMOVED Celery Imports ---
# celery_execute_tool_task, CELERY_AVAILABLE are gone.


# --- Logging Setup ---
# Keep basic logging setup, adjusted loggers later
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s [%(levelname)s] %(message)s', handlers=[logging.FileHandler("mcp_server.log"), logging.StreamHandler(sys.stderr)], force=True)
logger = logging.getLogger("mcp_server")

# --- FastAPI App (Only used for SSE mode) ---
app = FastAPI(title="MCP Lean Server (SSE Mode)")

# --- Custom Exception Handlers (Only registered for SSE mode) ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    body_str = "N/A"
    try: body_str = exc.body.decode('utf-8') if isinstance(exc.body, bytes) else str(exc.body)
    except: pass
    logger.warning(f"Request validation error: {exc.errors()} for body: {body_str[:500]}...")
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": "Input validation failed", "detail": exc.errors()},
    )

@app.exception_handler(ValidationError) # Catch Pydantic errors from internal processing
async def pydantic_validation_exception_handler(request, exc: ValidationError):
    # This might still be relevant if tools use Pydantic models
    logger.error(f"Internal Pydantic validation error: {exc.errors()}", exc_info=False)
    return JSONResponse(
        status_code=400,
        content={"status": "error", "message": "Internal data validation error", "detail": exc.errors()},
    )

# --- REMOVED Redis Keys & Config ---
# CLIENT_SET_KEY, TASK_HASH_PREFIX etc. are gone.
# LUA_DEQUEUE_SCRIPT is gone.

# --- REMOVED ClientBridge Class ---
# The entire ClientBridge class definition is removed.


# --- Main Server Execution Logic ---
async def run_lean_server():
    """Sets up and runs the lean MCP Server based on transport choice."""
    parser = argparse.ArgumentParser(description="Run Lean MCP Server (Stdio or SSE)")
    parser.add_argument("--host", default="127.0.0.1", help="Host for FastAPI server (SSE mode)")
    parser.add_argument("--port", type=int, default=8000, help="Port for FastAPI server (SSE mode)")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"),
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Log level. Env: LOG_LEVEL")
    parser.add_argument("--transport", default="stdio", choices=["sse", "stdio"],
                        help="Communication transport ('sse' for HTTP/SSE, 'stdio' for standard I/O).")
    parser.add_argument("--workspace",
                        default=os.path.abspath(os.path.join(os.getcwd(), "agent_workspace")),
                        help="Path to the agent's workspace directory. Defaults to ./agent_workspace relative to CWD. Env: AGENT_WORKSPACE")
    parser.add_argument("--allow-path", action='append', default=[],
                        help="Relative path within workspace to allow resource access (can be repeated). Defaults to workspace root if none specified.")

    args = parser.parse_args()

    # --- Resolve Workspace Path and Configure File Tools ---
    try:
        # Resolve the path provided (or defaulted) by argparse into a Path object
        workspace_root = pathlib.Path(args.workspace).resolve()

        # --- CONFIGURE FILE TOOLS WORKSPACE ---
        # This MUST happen before tools are loaded or FileSystemProvider is initialized
        file_tools.set_tools_workspace(workspace_root)

        # --- Configure Logging (AFTER critical path setup) ---
        log_level_int = getattr(logging, args.log_level.upper(), logging.INFO)
        log_format = '%(asctime)s - %(name)s [%(levelname)s] %(message)s'

        logging.basicConfig(level=log_level_int, format=log_format, force=True) # Apply to root
        root_logger = logging.getLogger()
        if root_logger.hasHandlers(): root_logger.handlers.clear()
        root_logger.addHandler(logging.StreamHandler(sys.stderr))
        # root_logger.addHandler(logging.StreamHandler(sys.stdout))
        root_logger.setLevel(log_level_int)

        # Set levels for specific loggers (copy/adjust as needed from original)
        logging.getLogger("mcp_server").setLevel(log_level_int)
        logging.getLogger("MCPServer").setLevel(log_level_int)
        logging.getLogger("MCPProtocol").setLevel(log_level_int)
        logging.getLogger("StdioTransport").setLevel(log_level_int)
        logging.getLogger("SSETransport").setLevel(log_level_int)
        logging.getLogger("FileSystemProvider").setLevel(log_level_int)
        logging.getLogger("ToolRegistry").setLevel(log_level_int)
        logging.getLogger(file_tools.__name__).setLevel(log_level_int)
        logging.getLogger("uvicorn").setLevel(max(log_level_int, logging.INFO))
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.INFO)

        # Log that workspace setup was successful
        logger.info(f"Effective server workspace root configured: {workspace_root}")

    except Exception as e:
        # Use basic print/stderr here as logging might not be fully set up
        print(f"FATAL: Failed to configure workspace path '{args.workspace}': {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    # Continue with logging now that it's configured
    logger.info(f"--- Lean MCP Server Starting ---")
    logger.info(f"Selected Transport Mode: {args.transport.upper()}")
    logger.info(f"Log level set to: {args.log_level}")
    logger.info(f"Allowed Resource Paths (relative to workspace): {args.allow_path or ['(root)']}")

    # --- Initialize Common Components ---
    server = MCPServer("MCP-Server", "1.1.0") # Updated version example
    try:
        # Tool loading now implicitly uses the workspace configured via set_tools_workspace
        load_default_tools(server.tool_registry)
        logger.info(f"Loaded {len(server.tool_registry.tools)} tools.")
    except Exception as tool_load_err:
        logger.error(f"Failed load tools: {tool_load_err}", exc_info=True)

    # --- Initialize Resources (Common - uses the same workspace_root) ---
    try:
        # workspace_root is already a resolved Path object and checked/created by set_tools_workspace

        if not args.allow_path:
             # Default to allowing the entire workspace root
             allowed_paths_abs_obj = [workspace_root] # List of Path objects
             logger.info("No specific --allow-path specified, allowing FileSystemProvider access to entire workspace root.")
        else:
             allowed_paths_abs_obj = []
             for rel_path in args.allow_path:
                 # Use pathlib for joining and resolving
                 abs_allowed = (workspace_root / rel_path).resolve()
                 # Check parent using pathlib properties
                 if workspace_root in abs_allowed.parents or abs_allowed == workspace_root:
                      allowed_paths_abs_obj.append(abs_allowed)
                      abs_allowed.mkdir(parents=True, exist_ok=True) # Ensure allowed paths exist
                 else:
                      logger.warning(f"Ignoring specified allowed path '{rel_path}' as it resolves to '{abs_allowed}' which is outside the workspace root '{workspace_root}'.")
             if not allowed_paths_abs_obj:
                 logger.error("No valid allowed paths remaining after validation. FileSystemProvider cannot be registered.")

        if allowed_paths_abs_obj:
             # Convert Path objects to strings for the provider's constructor
             allowed_paths_str = [str(p) for p in allowed_paths_abs_obj]
             fs_provider = FileSystemProvider(workspace_root=str(workspace_root), allowed_paths=allowed_paths_str)
             server.add_resource_provider(fs_provider)
             logger.info(f"Registered FileSystemProvider. Workspace: {workspace_root}, Allowed: {allowed_paths_str}")
        else:
             logger.warning("FileSystemProvider not registered due to lack of valid allowed paths.")

    except ValueError as provider_err:
         # Catch errors from FileSystemProvider init (like invalid workspace)
         logger.critical(f"Failed to initialize FileSystemProvider: {provider_err}. Exiting.", exc_info=True)
         sys.exit(1)
    except Exception as provider_err:
         logger.error(f"Unexpected error initializing FileSystemProvider: {provider_err}", exc_info=True)
         logger.warning("Continuing server startup without FileSystemProvider due to initialization error.")

    # --- Transport Setup (Common) ---
    transport: Optional[Transport] = None
    uvicorn_server: Optional[uvicorn.Server] = None

    try:
        # --- MODE-SPECIFIC SETUP AND EXECUTION ---
        if args.transport == 'stdio':
            # --- Stdio Mode ---
            logger.info("Mode: stdio - Initializing StdioTransport.")
            transport = StdioTransport()

            logger.info("Mode: stdio - Connecting transport (stdio streams)...")
            await transport.connect() # Sets up reader/writer

            logger.info("Mode: stdio - Connecting server to transport...")
            await server.connect(transport) # Connects protocol to stdio transport

            await asyncio.sleep(0.1) # Allow potential init messages time

            logger.info("Stdio mode ready. Waiting for JSON-RPC messages on stdin...")
            logger.info("Use Ctrl+C or send EOF to exit.")

            # Main Stdio processing loop
            while transport and not transport.closed:
                message: Optional[Dict[str, Any]] = None # Initialize message for error handling
                try:
                    message = await transport.receive()
                    if message is None:
                        logger.info("StdioTransport received EOF/None. Exiting loop.")
                        break

                    if server.protocol:
                        # Handle message (calls registered handlers like _handle_execute_tool)
                        response = await server.protocol.handle_message(message)
                        # Send response back if one was generated
                        if response:
                            await transport.send(response)
                    else:
                         logger.error("Cannot process message: server.protocol not available.")
                         # Attempt to send error back
                         err_resp = {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Internal server error: Protocol handler missing"},"id": message.get("id") if isinstance(message, dict) else None}
                         try: await transport.send(err_resp)
                         except Exception as send_err: logger.error(f"Failed to send protocol missing error: {send_err}")

                except asyncio.CancelledError:
                    logger.info("Stdio receive/process loop cancelled.")
                    break
                except Exception as loop_err:
                    logger.error(f"Error in stdio processing loop: {loop_err}", exc_info=True)
                    # Attempt to send error back
                    try:
                        msg_id = message.get("id") if isinstance(message, dict) else None
                        err_resp = {"jsonrpc": "2.0", "error": {"code": -32000, "message": f"Internal server error in processing loop: {loop_err}"},"id": msg_id}
                        await transport.send(err_resp)
                    except Exception as send_err: logger.error(f"Failed to send loop error message: {send_err}")
                    await asyncio.sleep(0.1) # Avoid tight loop on error

            logger.info("Stdio processing loop finished.")
            # End of Stdio Mode block

        elif args.transport == 'sse':
            # --- SSE Mode ---
            logger.info("Mode: sse - Initializing SSETransport and FastAPI.")
            transport = SSETransport(host=args.host, port=args.port)
            transport.app = app # Assign FastAPI app instance to transport
            await transport.connect() # Configures routes
            await server.connect(transport) # Connects protocol to SSE transport

            # Log ready state and available resources/tools
            logger.info(f"MCP Lean Server running on http://{args.host}:{args.port}")
            logger.info("Requests via HTTP POST /message, responses/notifications via GET /sse")
            logger.info("Available tools registered with the server (via API):")
            try:
                tools = server.tool_registry.tools
                if tools:
                    for t in tools:
                         func_info = t.get('function', {})
                         logger.info(f"  - {func_info.get('name','?')} ({func_info.get('description','N/A')})")
                else: logger.info("  (No tools found in registry)")
            except Exception as log_err: logger.error(f"Error logging tools: {log_err}")

            logger.info("Available resources registered with the server (via API):")
            try:
                # Assuming resources might be Path objects internally, convert to str for logging
                resources = server.resource_registry.get_resources()
                if resources:
                    for res in resources: logger.info(f"  - Resource: {res.name} ({res.mime_type or 'N/A'}) - URI: {res.uri}")
                else: logger.info("  (No resources found in registry)")
            except Exception as log_err: logger.error(f"Error logging registered resources: {log_err}")

            logger.info("Starting Uvicorn server...")
            config = uvicorn.Config(app=app, host=args.host, port=args.port, log_level=args.log_level.lower())
            uvicorn_server = uvicorn.Server(config)
            await uvicorn_server.serve()
            logger.info("Uvicorn server stopped.")
            # End of SSE Mode block

        else:
            # This case should be caught by argparse choices
            logger.critical(f"Invalid transport mode specified: {args.transport}")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Shutdown requested via KeyboardInterrupt.")
    except asyncio.CancelledError:
         logger.info("Main server task cancelled.")
    except Exception as e:
        logger.critical(f"Fatal error during server setup or run: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # --- Graceful Shutdown Sequence (Simplified) ---
        logger.info("Initiating shutdown sequence...")
        if uvicorn_server and hasattr(uvicorn_server, 'started') and uvicorn_server.started:
            logger.info("Signaling Uvicorn exit...")
            uvicorn_server.should_exit = True
            try:
                 # Check if shutdown method exists and is awaitable
                 if hasattr(uvicorn_server, 'shutdown') and inspect.iscoroutinefunction(uvicorn_server.shutdown):
                     await asyncio.wait_for(uvicorn_server.shutdown(), timeout=5.0)
                 else:
                      logger.warning("Uvicorn server instance doesn't have an awaitable shutdown method.")
            except asyncio.TimeoutError: logger.warning("Uvicorn shutdown timed out.")
            except Exception as uvi_err: logger.error(f"Error during Uvicorn shutdown: {uvi_err}")

        if transport:
            logger.info(f"Closing transport layer ({type(transport).__name__})...")
            try:
                await transport.close()
            except Exception as trans_err:
                 logger.error(f"Error closing transport: {trans_err}", exc_info=True)

        # Give tasks a moment to finish cleanup
        await asyncio.sleep(0.1)
        logger.info("=== Server shutdown sequence complete. ===")

# --- Main Entry Point ---
def main():
    """Main entry point for running the lean server."""
    try:
        asyncio.run(run_lean_server())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        # Log critical errors that happen outside the main async run loop
        print(f"\nFATAL ERROR in main execution: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("Server process finished.", file=sys.stderr)

if __name__ == "__main__":
    main()


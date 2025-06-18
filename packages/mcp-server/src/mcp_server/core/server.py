# packages/mcp-server/src/mcp_server/mcp/server.py
import asyncio
import inspect
import logging
import traceback # Keep for error logging if needed
import json
from typing import Dict, Any, Optional, Callable, Coroutine, Type, List # Added List
from pydantic import BaseModel, ValidationError # Keep for tool result handling
from fastapi import HTTPException # Keep if tools raise this

# Assuming these exist in the specified locations
from mcp_server.core.registry import ToolRegistry
# Import RequestHandlerExtra from protocol
from .protocol import MCPProtocol, RequestHandlerExtra
from .transport import Transport # Keep abstract Transport
from .resources import ResourceRegistry
from .prompts import PromptRegistry, Prompt

logger = logging.getLogger(__name__)

# Removed mcp_types import/check - simplify capabilities
MCP_TYPES_AVAILABLE = False


class MCPServer:
    """
    Core MCP server class. Manages protocol handling, tool/resource/prompt registries,
    and connection to a transport layer. Executes tools SYNCHRONOUSLY within handlers.
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.protocol = MCPProtocol()
        self.tool_registry = ToolRegistry()
        self.resource_registry = ResourceRegistry()
        self.prompt_registry = PromptRegistry()
        self.transport: Optional[Transport] = None
        logger.info(f"MCPServer '{name}' v{version} initialized (Synchronous Mode).")
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Registers the built-in MCP request handlers with the protocol."""
        handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_list_tools,
            "tools/call": self._handle_execute_tool, # Now fully synchronous behavior expected
            "resources/list": self._handle_list_resources,
            "resources/read": self._handle_read_resource,
            "prompts/list": self._handle_list_prompts,
            "prompts/get": self._handle_get_prompt,
            "completion/complete": self._handle_fill_prompt,
        }
        for method, handler in handlers.items():
            self.protocol.set_request_handler(method, handler)
        logger.debug(f"Registered {len(handlers)} default MCP handlers.")

    # --- Public Registration Methods (Unchanged) ---
    def tool(self) -> Callable[..., Any]:
        return self.tool_registry.tool()

    def add_resource_provider(self, provider: Any):
        self.resource_registry.add_provider(provider)
        logger.info(f"Added resource provider: {type(provider).__name__}")

    def register_prompt(self, prompt: Prompt):
        self.prompt_registry.register(prompt)
        logger.info(f"Registered prompt: {prompt.id}")

    # --- Default MCP Request Handlers ---

    async def _handle_initialize(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        """Handles 'initialize'. Returns simplified capabilities."""
        client_info = params.get("clientInfo", {})
        client_name = client_info.get('name', 'Unknown Client')
        client_version = client_info.get('version', 'N/A')
        req_id = extra.id if extra else 'N/A'
        logger.info(f"Handling 'initialize' request. ID={req_id}. Client: {client_name} v{client_version}")
        logger.debug(f"Initialize params received: {params}")

        # Simplified capabilities - no background tasks, etc.
        server_capabilities_dict = {
            "tools": {"dynamicRegistration": False},
            "resources": {"dynamicRegistration": False},
            "prompts": {"dynamicRegistration": False}
        }
        protocol_version_to_send = "2024-11-05"

        logger.debug(f"Announcing simplified server capabilities: {server_capabilities_dict}")

        response_payload = {
            "protocolVersion": protocol_version_to_send,
            "serverInfo": { "name": self.name, "version": self.version },
            "capabilities": server_capabilities_dict
        }
        logger.info(f"Responding to 'initialize' request ID={req_id}.")
        logger.debug(f"Initialize response payload: {response_payload}")
        return response_payload

    async def _handle_list_tools(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        logger.info(f"Handling 'tools/list' request, ID: {extra.id}")
        try:
            tool_schemas_from_registry = self.tool_registry.tools
            mcp_formatted_tools = []
            for tool_entry in tool_schemas_from_registry:
                 if isinstance(tool_entry, dict) and tool_entry.get("type") == "function":
                      schema = tool_entry.get("function")
                      if isinstance(schema, dict):
                           tool_definition_for_client = {
                                "name": schema.get("name"), "description": schema.get("description"),
                                "inputSchema": schema.get("parameters", {})
                           }
                           mcp_formatted_tools.append(tool_definition_for_client)
            logger.debug(f"Returning {len(mcp_formatted_tools)} tools in MCP format.")
            return {"tools": mcp_formatted_tools}
        except Exception as e:
             logger.error(f"Error listing tools: {e}", exc_info=True)
             return {"error": {"code": -32000, "message": f"Internal server error listing tools: {e}"}}

    async def _handle_execute_tool(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        """
        Handles 'tools/call' request SYNCHRONOUSLY within the handler.
        Executes the tool and returns the result payload dictionary.
        """
        tool_name = params.get("name"); tool_arguments = params.get("arguments", {})
        request_id = extra.id if extra else 'N/A'
        if not tool_name:
            error_text = "Missing required parameter: 'name' for tools/call"
            logger.error(f"Handling 'tools/call': ID={request_id} FAILED - {error_text}")
            return { "content": [{"type": "text", "text": error_text}], "isError": True }
        logger.info(f"Handling 'tools/call': ID={request_id}, Tool='{tool_name}' (Execution: Synchronous)")
        logger.debug(f"Arguments received for tool '{tool_name}': {tool_arguments}")
        tool_func = self.tool_registry.get_tool(tool_name)
        if not tool_func:
             error_text = f"Tool function not found in registry: '{tool_name}'"
             logger.error(f"Handling 'tools/call': ID={request_id} FAILED - {error_text}")
             return { "content": [{"type": "text", "text": error_text}], "isError": True }
        result_obj: Any = None; mcp_payload: Dict[str, Any] = {}
        try:
            call_kwargs = tool_arguments or {}
            if inspect.iscoroutinefunction(tool_func):
                logger.debug(f"TOOL HANDLER: Executing async tool synchronously: {tool_name}")
                result_obj = await tool_func(**call_kwargs)
            else:
                 logger.debug(f"TOOL HANDLER: Executing sync tool synchronously (via executor): {tool_name}")
                 loop = asyncio.get_running_loop()
                 result_obj = await loop.run_in_executor(None, lambda kw=call_kwargs: tool_func(**kw))
            logger.info(f"Tool '{tool_name}' executed successfully (raw result type: {type(result_obj).__name__}).")
            content_list: List[Dict[str, Any]] = []
            # --- START RESULT FORMATTING ---
            if result_obj is None: content_list = [{"type": "text", "text": ""}]
            elif isinstance(result_obj, str): content_list = [{"type": "text", "text": result_obj}]
            elif isinstance(result_obj, BaseModel):
                try: result_json_str = result_obj.model_dump_json(); content_list = [{"type": "text", "text": result_json_str}]
                except AttributeError:
                    try: result_json_str = result_obj.json(); content_list = [{"type": "text", "text": result_json_str}]
                    except Exception as json_err_v1: logger.warning(f"Could not JSON serialize Pydantic v1 model for '{tool_name}', using str(). Error: {json_err_v1}"); content_list = [{"type": "text", "text": str(result_obj)}]
                except Exception as json_err: logger.warning(f"Could not JSON serialize Pydantic model for '{tool_name}', using str(). Error: {json_err}"); content_list = [{"type": "text", "text": str(result_obj)}]
            elif isinstance(result_obj, dict):
                 try: result_str = json.dumps(result_obj, ensure_ascii=False); content_list = [{"type": "text", "text": result_str}]
                 except TypeError: result_str = str(result_obj); content_list = [{"type": "text", "text": result_str}]; logger.warning(f"Could not JSON serialize dict for '{tool_name}', using str().")
            else:
                result_str = str(result_obj); content_list = [{"type": "text", "text": result_str}]
                if not isinstance(result_obj, (int, float, bool, list)): logger.warning(f"Result type {type(result_obj).__name__} for '{tool_name}' has no specific handler, using str().")
            # --- END RESULT FORMATTING ---
            mcp_payload = { "content": content_list, "isError": False }
            logger.debug(f"Tool '{tool_name}' successful. Returning MCP payload: {str(mcp_payload)[:200]}...")
        except HTTPException as http_exc:
             error_text = f"Tool execution error: {http_exc.status_code} - {http_exc.detail}"
             logger.error(f"Tool '{tool_name}' failed with HTTPException: {error_text}", exc_info=False)
             mcp_payload = { "content": [{"type": "text", "text": error_text}], "isError": True }; logger.warning(f"Tool '{tool_name}' failed. Returning MCP error payload.")
        except Exception as e:
            error_text = f"Tool execution error: {type(e).__name__}: {str(e)}"
            logger.error(f"Tool '{tool_name}' execution failed unexpectedly: {error_text}", exc_info=True)
            mcp_payload = { "content": [{"type": "text", "text": error_text}], "isError": True }; logger.warning(f"Tool '{tool_name}' failed. Returning MCP error payload.")
        return mcp_payload

    # --- Resource and Prompt Handlers (Unchanged from previous) ---
    async def _handle_list_resources(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        logger.info(f"Handling 'resources/list' request, ID: {extra.id}")
        try: resources = self.resource_registry.get_resources(); return {"resources": [r.to_dict() for r in resources]}
        except Exception as e: logger.error(f"Error listing resources: {e}", exc_info=True); return {"error": {"code": -32000, "message": f"Internal error listing resources: {e}"}}
    async def _handle_read_resource(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        uri = params.get("uri"); req_id = extra.id if extra else 'N/A'; logger.info(f"Handling 'resources/read' for URI: {uri}, ID: {req_id}")
        if not uri: logger.warning(f"Request ID {req_id}: Missing 'uri'."); return {"contents": [{"type": "text", "text": "[Error: Missing required parameter: uri]", "mimeType": "text/plain", "uri": "error:///missing-uri"}]}
        try:
            provider_response = await self.resource_registry.get_resource_content(uri)
            if isinstance(provider_response, dict) and 'contents' in provider_response:
                for item in provider_response.get('contents', []):
                     if isinstance(item, dict) and 'uri' not in item: item['uri'] = uri
                return provider_response
            elif isinstance(provider_response, dict) and 'type' in provider_response:
                 if 'uri' not in provider_response: provider_response['uri'] = uri
                 return {"contents": [provider_response]}
            else: error_msg = f"Provider for '{uri}' returned unexpected: {type(provider_response)}"; logger.error(f"Req ID {req_id}: {error_msg}"); return {"contents": [{"type": "text", "text": f"[Error: {error_msg}]", "mimeType": "text/plain", "uri": uri}]}
        except ValueError as e: logger.warning(f"ValueError reading '{uri}' (Req {req_id}): {e}"); return {"contents": [{"type": "text", "text": f"[Error: {e}]", "mimeType": "text/plain", "uri": uri}]}
        except FileNotFoundError as e: logger.warning(f"Not Found/Access Denied '{uri}' (Req {req_id}): {e}"); return {"contents": [{"type": "text", "text": f"[Error: Resource not found or access denied - {uri}]", "mimeType": "text/plain", "uri": uri}]}
        except Exception as e: logger.error(f"Error reading '{uri}' (Req {req_id}): {e}", exc_info=True); return {"contents": [{"type": "text", "text": f"[Error reading resource: {type(e).__name__}]", "mimeType": "text/plain", "uri": uri}]}
    async def _handle_list_prompts(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        logger.info(f"Handling 'prompts/list' request, ID: {extra.id}");
        try: prompts = self.prompt_registry.list_prompts(); return {"prompts": [p.to_dict() for p in prompts]}
        except Exception as e: logger.error(f"Error listing prompts: {e}", exc_info=True); return {"error": {"code": -32000, "message": f"Internal error listing prompts: {e}"}}
    async def _handle_get_prompt(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        prompt_id = params.get("id"); logger.info(f"Handling 'prompts/get' for ID: {prompt_id}, ReqID: {extra.id}")
        if not prompt_id: return {"error": {"code": -32602, "message": "Missing required parameter: id"}}
        try: prompt = self.prompt_registry.get_prompt(prompt_id); return prompt.to_dict()
        except KeyError: return {"error": {"code": -32601, "message": f"Prompt not found: {prompt_id}"}}
        except Exception as e: logger.error(f"Error getting prompt '{prompt_id}': {e}", exc_info=True); return {"error": {"code": -32000, "message": f"Error getting prompt: {e}"}}
    async def _handle_fill_prompt(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        prompt_id = params.get("id"); parameters = params.get("parameters", {}); logger.info(f"Handling 'prompts/fill' for ID: {prompt_id}, ReqID: {extra.id}")
        if not prompt_id: return {"error": {"code": -32602, "message": "Missing required parameter: id"}}
        try: prompt = self.prompt_registry.get_prompt(prompt_id); filled_text = prompt.fill(parameters or {}); return {"text": filled_text}
        except KeyError: return {"error": {"code": -32601, "message": f"Prompt not found: {prompt_id}"}}
        except ValueError as e: return {"error": {"code": -32602, "message": str(e)}}
        except Exception as e: logger.error(f"Error filling prompt '{prompt_id}': {e}", exc_info=True); return {"error": {"code": -32000, "message": f"Error filling prompt: {e}"}}

    # --- Connection Logic (Unchanged from previous) ---
    async def connect(self, transport: Transport):
        if self.transport: logger.warning("MCPServer already connected. Overwriting.")
        if not transport: raise ValueError("Cannot connect MCPServer to a null transport.")
        self.transport = transport; logger.info(f"MCPServer associating with transport: {type(transport).__name__}")
        if hasattr(transport, 'set_message_handler') and callable(transport.set_message_handler): logger.debug("Setting protocol.handle_message as transport's message handler."); transport.set_message_handler(self.protocol.handle_message)
        else: logger.warning(f"Transport {type(transport).__name__} does not support 'set_message_handler'.")
        if not hasattr(transport, 'send') or not callable(transport.send): raise TypeError(f"Transport {type(transport).__name__} missing callable 'send' method.")
        if not inspect.iscoroutinefunction(transport.send): logger.warning(f"Transport's send method ({type(transport).__name__}) is not awaitable.")
        self.protocol._send_message_impl = transport.send; logger.info("MCPServer association with transport complete.")
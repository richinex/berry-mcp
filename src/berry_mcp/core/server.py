"""
MCP Server implementation for Berry MCP Server using proper protocol and transport layers
"""

import asyncio
import inspect
import logging
from typing import Dict, Any, Optional

from .registry import ToolRegistry
from .protocol import MCPProtocol, RequestHandlerExtra
from .transport import Transport, StdioTransport

logger = logging.getLogger(__name__)


class MCPServer:
    """
    Core MCP server that manages protocol handling, tool registry,
    and connection to a transport layer.
    """

    def __init__(self, name: str = "berry-mcp-server", version: str = "0.1.0"):
        self.name = name
        self.version = version
        self.protocol = MCPProtocol()
        self.tool_registry = ToolRegistry()
        self.transport: Optional[Transport] = None
        self.initialized = False
        
        logger.info(f"MCPServer '{name}' v{version} initialized")
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register the built-in MCP request handlers with the protocol"""
        handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_list_tools,
            "tools/call": self._handle_call_tool,
        }
        
        for method, handler in handlers.items():
            self.protocol.set_request_handler(method, handler)
        
        logger.debug(f"Registered {len(handlers)} default MCP handlers")

    # Tool registration methods
    def tool(self):
        """Get tool decorator from registry"""
        return self.tool_registry.tool()

    async def run(self, transport: Optional[Transport] = None):
        """Run the MCP server with specified transport"""
        if transport is None:
            transport = StdioTransport()
        
        await self.connect(transport)
        
        try:
            # Auto-discover tools from the tools package
            from .. import tools
            self.tool_registry.auto_discover_tools(tools)
            logger.info(f"Discovered {len(self.tool_registry.list_tools())} tools")
            
            # Main message processing loop
            while True:
                try:
                    message = await transport.receive()
                    if message is None:
                        logger.info("Transport closed, shutting down")
                        break
                    
                    response = await self.protocol.handle_message(message)
                    if response:
                        await transport.send(response)
                        
                except KeyboardInterrupt:
                    logger.info("Server stopped by user")
                    break
                except Exception as e:
                    logger.error(f"Error in message processing loop: {e}", exc_info=True)
                    
        finally:
            await transport.close()

    async def connect(self, transport: Transport):
        """Connect the server to a transport"""
        if self.transport:
            logger.warning("MCPServer already connected, overwriting")
        
        if not transport:
            raise ValueError("Cannot connect to null transport")
        
        self.transport = transport
        logger.info(f"Connecting to transport: {type(transport).__name__}")
        
        # Set up transport message handling
        if hasattr(transport, 'set_message_handler'):
            transport.set_message_handler(self.protocol.handle_message)
        
        # Connect the protocol's send implementation
        self.protocol.set_send_implementation(transport.send)
        
        # Establish transport connection
        await transport.connect()
        logger.info("MCPServer connected to transport")

    # Default MCP request handlers
    async def _handle_initialize(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        """Handle 'initialize' request"""
        client_info = params.get("clientInfo", {})
        client_name = client_info.get('name', 'Unknown Client')
        client_version = client_info.get('version', 'N/A')
        
        logger.info(f"Initialize request from {client_name} v{client_version} (ID: {extra.id})")
        
        self.initialized = True
        
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": self.name,
                "version": self.version
            },
            "capabilities": {
                "tools": {"dynamicRegistration": False}
            }
        }

    async def _handle_list_tools(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        """Handle 'tools/list' request"""
        logger.info(f"Tools list request (ID: {extra.id})")
        
        tools = []
        for tool_schema in self.tool_registry.tools:
            if tool_schema.get("type") == "function":
                func_info = tool_schema.get("function", {})
                tools.append({
                    "name": func_info.get("name"),
                    "description": func_info.get("description"),
                    "inputSchema": func_info.get("parameters", {})
                })
        
        logger.debug(f"Returning {len(tools)} tools")
        return {"tools": tools}

    async def _handle_call_tool(self, params: Dict[str, Any], extra: RequestHandlerExtra) -> Dict[str, Any]:
        """Handle 'tools/call' request"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            return {
                "content": [{"type": "text", "text": "Missing required parameter: 'name'"}],
                "isError": True
            }
        
        logger.info(f"Tool call: {tool_name} (ID: {extra.id})")
        
        tool_func = self.tool_registry.get_tool(tool_name)
        if not tool_func:
            return {
                "content": [{"type": "text", "text": f"Tool not found: {tool_name}"}],
                "isError": True
            }
        
        try:
            # Execute the tool
            if inspect.iscoroutinefunction(tool_func):
                result = await tool_func(**arguments)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: tool_func(**arguments))
            
            logger.info(f"Tool '{tool_name}' executed successfully")
            
            # Format result for MCP
            if isinstance(result, dict) and "error" in result:
                # Tool returned an error
                return {
                    "content": [{"type": "text", "text": result["error"]}],
                    "isError": True
                }
            else:
                # Successful result
                content_text = str(result) if not isinstance(result, str) else result
                return {
                    "content": [{"type": "text", "text": content_text}],
                    "isError": False
                }
                
        except Exception as e:
            logger.error(f"Tool '{tool_name}' execution failed: {e}", exc_info=True)
            return {
                "content": [{"type": "text", "text": f"Tool execution error: {str(e)}"}],
                "isError": True
            }


async def main():
    """Main entry point for the MCP server"""
    from ..utils.logging import setup_logging
    
    # Set up logging
    setup_logging(level="INFO")
    
    # Create and run server
    server = MCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
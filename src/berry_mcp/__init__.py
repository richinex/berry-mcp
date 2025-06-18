"""
Berry MCP Server - Universal MCP server bootstrapper
Create and deploy Model Context Protocol servers with any tools
"""

__version__ = "0.1.0"
__author__ = "Richard Chukwu"
__email__ = "richinex@gmail.com"

from .core.server import MCPServer
from .core.registry import ToolRegistry
from .core.transport import Transport, StdioTransport, SSETransport
from .core.protocol import MCPProtocol
from .tools.decorators import tool

__all__ = [
    "MCPServer", 
    "ToolRegistry", 
    "Transport", 
    "StdioTransport", 
    "SSETransport",
    "MCPProtocol",
    "tool"
]
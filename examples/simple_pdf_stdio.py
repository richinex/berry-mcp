#!/usr/bin/env python3
"""
Simple PDF MCP server using stdio transport (traditional MCP)
This is how most users would deploy - no authentication, direct process communication
"""

import asyncio
import sys

from berry_mcp import MCPServer
from berry_mcp.core.transport import StdioTransport


async def main():
    """Simple PDF server using stdio transport"""

    # Create MCP server
    server = MCPServer(name="pdf-processor")

    # PDF tools are automatically discovered from berry_mcp.tools.pdf_tools
    # because they're decorated with @tool

    # Use stdio transport (traditional MCP)
    transport = StdioTransport()
    server.connect_transport(transport)

    print("PDF MCP Server started (stdio mode)", file=sys.stderr)
    print(
        "Available tools: read_pdf_text, get_pdf_info, extract_pdf_pages",
        file=sys.stderr,
    )

    # Run the server
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())

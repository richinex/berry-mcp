# Berry PDF MCP Server Documentation

## Overview

Berry PDF MCP Server is a sophisticated, extensible Model Context Protocol (MCP) server featuring advanced transport and protocol handling capabilities. Built with a layered architecture that supports both stdio and HTTP/SSE communication methods while providing a clean decorator-based tool development experience.

## Architecture

### Core Components

The server is built with a layered architecture following SOLID principles:

1. **MCPServer** - Core server orchestrating protocol, tools, and transport
2. **MCPProtocol** - JSON-RPC 2.0 protocol handler with full MCP compliance
3. **Transport Layer** - Pluggable transport implementations (stdio, HTTP/SSE)
4. **ToolRegistry** - Advanced tool management with auto-discovery
5. **Tool Decorators** - Type-safe tool creation with automatic schema generation

### Transport Architecture

#### Transport Abstraction
```python
class Transport(ABC):
    @abstractmethod
    async def connect(self): pass
    
    @abstractmethod
    async def send(self, message: Dict[str, Any]) -> None: pass
    
    async def receive(self) -> Optional[Dict[str, Any]]: pass
    
    @abstractmethod
    async def close(self) -> None: pass
```

#### Stdio Transport
- **Use Case**: Standard MCP client integration (Claude Desktop, etc.)
- **Protocol**: JSON-RPC over stdin/stdout
- **Features**: Async message processing, JSON validation, error recovery

#### HTTP/SSE Transport
- **Use Case**: Web-based applications, REST API integration
- **Protocol**: HTTP POST for requests, Server-Sent Events for responses
- **Features**: Background task processing, concurrent client support, health monitoring

### Protocol Layer

#### MCP Protocol Handler
- **Compliance**: Full JSON-RPC 2.0 and MCP specification support
- **Features**: Method routing, error handling, notification support
- **Validation**: Request/response format validation
- **Extensibility**: Easy addition of new MCP methods

#### Message Flow
```
Client → Transport → Protocol → Server → Tool → Response → Transport → Client
```

### Design Principles

Advanced software engineering principles implemented:
- **Single Responsibility**: Each component has a focused purpose
- **Open/Closed**: Extensible without modification
- **Dependency Inversion**: Abstractions over concrete implementations  
- **Strategy Pattern**: Pluggable transport implementations
- **Decorator Pattern**: Simplified tool registration
- **Observer Pattern**: Event-driven message handling

## Tool Development

### Creating a New Tool

```python
from berry_pdf_mcp.tools.decorators import tool

@tool(description="Calculate the sum of two numbers")
def add_numbers(a: int, b: int) -> int:
    """Add two integers together"""
    return a + b

@tool()
def process_text(text: str, uppercase: bool = False) -> str:
    """Process text with optional uppercase conversion"""
    return text.upper() if uppercase else text.lower()
```

### Tool Registration

Tools are automatically discovered and registered:

```python
from berry_pdf_mcp import MCPServer, ToolRegistry

# Automatic discovery
server = MCPServer()
server.tool_registry.auto_discover_tools('my_tools_module')

# Manual registration
server.tool_registry.register_function(my_function, name="custom_name")
```

### Tool Types Supported

- **Async Tools**: Functions defined with `async def`
- **Sync Tools**: Regular functions (executed in thread pool)
- **Type Hints**: Automatic JSON schema generation from type annotations
- **Default Parameters**: Handled automatically in schema generation

## PDF Tools

### Available PDF Tools

1. **read_pdf_text** - Extract text as Markdown using PyMuPDF
2. **read_pdf_text_pypdf2** - Alternative extraction using PyPDF2

### Usage Examples

```python
# Using PyMuPDF (recommended)
result = await read_pdf_text("document.pdf", page_limit=10)

# Using PyPDF2 (fallback)
result = await read_pdf_text_pypdf2("document.pdf", max_chars=5000)
```

## Transport Configuration

### Stdio Transport (Default)

Standard MCP usage for integration with Claude Desktop and other MCP clients:

```bash
# Run with stdio transport (default)
berry-pdf-mcp

# Or explicitly
berry-pdf-mcp --transport stdio
```

```python
from berry_pdf_mcp import MCPServer, StdioTransport

async def run_stdio_server():
    server = MCPServer()
    transport = StdioTransport()
    await server.run(transport)
```

### HTTP/SSE Transport

For web applications and REST API integration:

```bash
# Run with HTTP transport
berry-pdf-mcp --transport http --host localhost --port 8000

# With custom configuration
berry-pdf-mcp --transport http --host 0.0.0.0 --port 3000
```

```python
from berry_pdf_mcp import MCPServer, SSETransport
from fastapi import FastAPI

async def run_http_server():
    app = FastAPI()
    server = MCPServer()
    transport = SSETransport("localhost", 8000)
    transport.app = app
    
    await server.connect(transport)
    # Start FastAPI server...
```

#### HTTP Endpoints

When using HTTP transport, the following endpoints are available:

- `GET /` - Server information and status
- `GET /ping` - Health check endpoint
- `GET /sse` - Server-Sent Events stream for responses
- `POST /message` - Send MCP JSON-RPC messages

### Custom Transport

Implement custom transport for specialized communication needs:

```python
from berry_pdf_mcp.core.transport import Transport

class CustomTransport(Transport):
    async def connect(self):
        # Custom connection logic
        pass
    
    async def send(self, message: Dict[str, Any]) -> None:
        # Custom message sending
        pass
    
    async def receive(self) -> Optional[Dict[str, Any]]:
        # Custom message receiving
        pass
    
    async def close(self) -> None:
        # Custom cleanup
        pass

# Use custom transport
server = MCPServer()
transport = CustomTransport()
await server.run(transport)
```

## Configuration

### Environment Variables

- `BERRY_PDF_WORKSPACE` - Default workspace directory
- `BERRY_PDF_LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)

### Workspace Management

```python
from berry_pdf_mcp.utils.validation import set_workspace, get_workspace

# Set workspace directory
set_workspace("/path/to/workspace")

# Get current workspace
current_workspace = get_workspace()
```

### Server Configuration

```python
from berry_pdf_mcp import MCPServer
from berry_pdf_mcp.utils.logging import setup_logging

# Configure logging
setup_logging(level="DEBUG", include_timestamp=True)

# Create server with custom settings
server = MCPServer(
    name="my-pdf-server",
    version="2.0.0"
)

# Auto-discover tools
from my_custom_tools import my_tools_module
server.tool_registry.auto_discover_tools(my_tools_module)

# Manual tool registration
@server.tool()
def my_custom_tool(input_text: str) -> str:
    return f"Processed: {input_text}"
```

## Error Handling

### Tool Error Patterns

```python
@tool()
def my_tool(param: str) -> Union[str, Dict[str, str]]:
    try:
        # Tool logic here
        return "success result"
    except Exception as e:
        return {"error": f"Tool failed: {str(e)}"}
```

### Server-Level Error Handling

- Validation errors return structured error responses
- Tool execution errors are caught and formatted
- Logging provides detailed error tracking

## Security

### Path Validation

All file paths are validated against the workspace:

```python
from berry_pdf_mcp.utils.validation import validate_path

# Safe path resolution
safe_path = validate_path("user/input/path.pdf")
if safe_path:
    # Path is safe to use
    pass
```

### Workspace Restrictions

- All file operations are restricted to the configured workspace
- Path traversal attacks are prevented
- Symbolic links outside workspace are blocked

## Performance

### Async Processing

- Tools can be async or sync
- Sync tools run in thread pool to avoid blocking
- Concurrent tool execution supported

### Memory Management

- PDF processing with configurable limits
- Text extraction size limits
- Proper resource cleanup

## Logging

### Setup

```python
from berry_pdf_mcp.utils.logging import setup_logging

setup_logging(level="DEBUG", include_timestamp=True)
```

### Logger Usage

```python
from berry_pdf_mcp.utils.logging import get_logger

logger = get_logger(__name__)
logger.info("Tool executed successfully")
```

## Testing

### Unit Tests

```python
import pytest
from berry_pdf_mcp.tools.pdf_tools import read_pdf_text

@pytest.mark.asyncio
async def test_pdf_reading():
    result = await read_pdf_text("test.pdf")
    assert isinstance(result, str)
```

### Integration Tests

```python
from berry_pdf_mcp import MCPServer

def test_server_initialization():
    server = MCPServer()
    assert server.name == "berry-pdf-mcp-server"
    assert len(server.tool_registry.list_tools()) > 0
```

## Deployment

### Standalone Executable

```bash
# Install with uv
uv pip install berry-pdf-mcp-server

# Run server
berry-pdf-mcp
```

### As Library

```python
from berry_pdf_mcp import MCPServer
import asyncio

async def main():
    server = MCPServer()
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
```

## Troubleshooting

### Common Issues

1. **PDF Library Not Found**
   - Install PyMuPDF: `uv pip install pymupdf4llm`
   - Install PyPDF2: `uv pip install PyPDF2`

2. **Permission Errors**
   - Check workspace permissions
   - Verify file paths are within workspace

3. **Tool Not Found**
   - Ensure tool is decorated with `@tool`
   - Check tool registration in registry

### Debug Mode

```bash
BERRY_PDF_LOG_LEVEL=DEBUG berry-pdf-mcp
```

## Extension Points

### Custom Tool Modules

```python
# my_tools.py
from berry_pdf_mcp.tools.decorators import tool

@tool()
def my_custom_tool(input_data: str) -> str:
    return f"Processed: {input_data}"

# Register with server
server.tool_registry.auto_discover_tools('my_tools')
```

### Custom Validators

```python
from berry_pdf_mcp.utils.validation import validate_path

def custom_validate_path(path: str) -> bool:
    # Custom validation logic
    return validate_path(path) is not None
```

## Best Practices

### Tool Design

1. Use clear, descriptive names
2. Provide comprehensive docstrings
3. Handle errors gracefully
4. Use type hints for automatic schema generation
5. Keep tools focused on single responsibilities

### Error Handling

1. Return structured error responses
2. Log errors with appropriate levels
3. Provide user-friendly error messages
4. Handle edge cases explicitly

### Performance

1. Use async for I/O bound operations
2. Implement proper resource cleanup
3. Set appropriate limits for processing
4. Monitor memory usage for large files
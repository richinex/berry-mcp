# MCP Transport Modes: stdio vs SSE

Berry MCP supports two different transport modes, each with different use cases and capabilities.

## stdio Transport (Traditional MCP)

### How it Works
- **Direct Process Communication**: VS Code launches your MCP server as a subprocess
- **stdin/stdout**: All communication happens via standard input/output
- **No Network**: No HTTP server, no ports, no authentication
- **Single Client**: One VS Code instance per server process

### Configuration
**.vscode/mcp.json**:
```json
{
  "servers": {
    "pdf-processor": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "berry_mcp.server"]
    }
  }
}
```

### Example Server
```python
# simple_pdf_stdio.py
from berry_mcp import MCPServer
from berry_mcp.core.transport import StdioTransport

server = MCPServer(name="pdf-processor")
transport = StdioTransport()
server.connect_transport(transport)
await server.run()
```

### Pros
- ✅ Simple setup - no configuration needed
- ✅ Secure - direct process communication
- ✅ No network dependencies
- ✅ Traditional MCP approach

### Cons
- ❌ No authentication possible
- ❌ No user interaction prompts
- ❌ Single client only
- ❌ No web access

---

## SSE Transport (Enhanced MCP)

### How it Works
- **HTTP Server**: Runs as a web service with REST endpoints
- **Server-Sent Events**: Real-time communication via SSE
- **Authentication**: OAuth2, API keys, etc.
- **Multi-Client**: Multiple VS Code instances can connect

### Configuration
**.vscode/mcp.json**:
```json
{
  "servers": {
    "secure-pdf-service": {
      "type": "sse",
      "url": "http://localhost:8080",
      "authorization_token": "your_token_here"
    }
  }
}
```

### Example Server
```python
# secure_pdf_sse.py
from berry_mcp import MCPServer
from berry_mcp.core import EnhancedSSETransport
from berry_mcp.auth import OAuth2Manager

server = MCPServer(name="secure-pdf-service")
transport = EnhancedSSETransport(
    host="localhost", 
    port=8080,
    oauth_manager=oauth_manager,
    require_auth=True
)
server.connect_transport(transport)
await server.run()
```

### Pros
- ✅ OAuth2 authentication
- ✅ User interaction prompts (elicitation)
- ✅ Multiple clients
- ✅ Web-based access
- ✅ Rate limiting, logging, monitoring

### Cons
- ❌ More complex setup
- ❌ Requires network configuration
- ❌ OAuth2 provider setup needed

---

## When to Use Which

### Use **stdio** when:
- Personal use on local machine
- Simple tool integration
- No authentication needed
- Traditional MCP workflow
- Quick prototyping

### Use **SSE** when:
- Multiple users need access
- Authentication required
- User approval workflows needed
- Production deployment
- Team/organization use

---

## Deployment Examples

### stdio Deployment (Simple)

**1. Create the server**:
```python
# my_pdf_server.py
from berry_mcp import MCPServer
from berry_mcp.core.transport import StdioTransport

async def main():
    server = MCPServer(name="pdf-tools")
    transport = StdioTransport()
    server.connect_transport(transport)
    await server.run()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

**2. VS Code config**:
```json
{
  "servers": {
    "pdf-tools": {
      "type": "stdio",
      "command": "python",
      "args": ["my_pdf_server.py"]
    }
  }
}
```

**3. Done!** No authentication, no setup - just works.

### SSE Deployment (Advanced)

**1. Setup OAuth2 provider** (Google, GitHub, etc.)

**2. Create authenticated server**:
```python
# secure_pdf_server.py
from berry_mcp import MCPServer
from berry_mcp.auth import OAuth2Config, OAuth2Manager
from berry_mcp.core import EnhancedSSETransport

# OAuth2 setup
oauth_config = OAuth2Config(
    client_id="your_client_id",
    client_secret="your_client_secret",
    authorization_url="https://accounts.google.com/o/oauth2/auth",
    token_url="https://oauth2.googleapis.com/token"
)
oauth_manager = OAuth2Manager(oauth_config)

# Server with authentication
server = MCPServer(name="secure-pdf-service")
transport = EnhancedSSETransport(
    host="localhost",
    port=8080, 
    oauth_manager=oauth_manager,
    require_auth=True
)
server.connect_transport(transport)
await server.run()
```

**3. User authentication flow**:
- User visits `http://localhost:8080/auth`
- Redirected to OAuth provider
- Gets access token

**4. VS Code config**:
```json
{
  "servers": {
    "secure-pdf": {
      "type": "sse",
      "url": "http://localhost:8080",
      "authorization_token": "user_access_token"
    }
  }
}
```

---

## Feature Comparison

| Feature | stdio | SSE |
|---------|-------|-----|
| Setup Complexity | Simple | Complex |
| Authentication | ❌ | ✅ OAuth2 |
| User Prompts | ❌ | ✅ Elicitation |
| Multiple Clients | ❌ | ✅ |
| Web Access | ❌ | ✅ |
| Production Ready | Personal | Enterprise |
| Network Required | ❌ | ✅ |
| Rate Limiting | ❌ | ✅ |
| Audit Logging | Basic | Advanced |

---

## Migration Path

You can start with **stdio** for simplicity and migrate to **SSE** when you need advanced features:

**Phase 1 - stdio (Personal Use)**:
```python
# Just the basics
server = MCPServer(name="pdf-tools")
server.connect_transport(StdioTransport())
```

**Phase 2 - SSE (Team Use)**:
```python
# Add HTTP server
server = MCPServer(name="pdf-tools") 
server.connect_transport(SSETransport(port=8080))
```

**Phase 3 - Authenticated SSE (Production)**:
```python
# Add authentication and user prompts
server = MCPServer(name="pdf-tools")
server.connect_transport(EnhancedSSETransport(
    port=8080,
    oauth_manager=oauth_manager,
    require_auth=True
))
```

The OAuth2 and elicitation features are **optional enhancements** for when you need them!
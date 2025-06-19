# Berry MCP - Two Ways to Deploy

Your Berry MCP framework supports **two different deployment modes** depending on your needs:

## 🚀 Quick Start (stdio) - Most Common

**Perfect for personal use and simple setups**

### 1. Create your server:
```python
# my_pdf_server.py
import asyncio
from berry_mcp import MCPServer
from berry_mcp.core.transport import StdioTransport

async def main():
    server = MCPServer(name="pdf-tools")
    transport = StdioTransport()
    server.connect_transport(transport)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Configure VS Code:
```json
// .vscode/mcp.json
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

### 3. Done! 
- No authentication setup needed
- No OAuth2 configuration required
- Just works immediately
- VS Code launches your server as needed

---

## 🔐 Advanced (SSE) - For Production

**Perfect for team use, authentication, and user interaction**

### 1. Setup OAuth2 (Google example):
- Go to [Google Cloud Console](https://console.cloud.google.com/)
- Create OAuth2 credentials
- Set redirect URI: `http://localhost:8080/oauth/callback`

### 2. Configure environment:
```bash
# .env
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
```

### 3. Run the enhanced server:
```bash
python examples/pdf_service_setup.py
```

### 4. Users authenticate:
- Visit `http://localhost:8080/auth`
- Login with Google/GitHub
- Get access token

### 5. Configure VS Code:
```json
// .vscode/mcp.json
{
  "servers": {
    "secure-pdf": {
      "type": "sse",
      "url": "http://localhost:8080", 
      "authorization_token": "user_access_token_here"
    }
  }
}
```

---

## Key Differences

| Feature | stdio (Simple) | SSE (Advanced) |
|---------|----------------|----------------|
| **Setup** | 2 minutes | 10 minutes |
| **Authentication** | None | OAuth2 |
| **User Prompts** | No | Yes |
| **Multiple Users** | No | Yes |
| **Use Case** | Personal | Production |

---

## Which Should You Use?

### Use **stdio** (Simple) if:
- ✅ Personal use only
- ✅ Want quick setup
- ✅ Don't need authentication
- ✅ Traditional MCP workflow

### Use **SSE** (Advanced) if:
- ✅ Multiple users need access
- ✅ Need authentication
- ✅ Want user approval workflows
- ✅ Production deployment
- ✅ Team/organization use

---

## Examples Included

1. **`examples/simple_pdf_stdio.py`** - Basic stdio server
2. **`examples/pdf_service_setup.py`** - Full SSE server with OAuth2
3. **`docs/transport_comparison.md`** - Detailed comparison
4. **`docs/deployment_guide.md`** - Production deployment guide

The **OAuth2 and elicitation features are completely optional** - most users will use the simple stdio mode, while organizations can use the advanced SSE mode for enhanced security and user interaction.

Both modes give users access to the same PDF processing tools - the difference is in how authentication and user interaction work!
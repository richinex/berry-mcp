# Enterprise MCP Deployment Guide

## How Organizations Deploy Authenticated MCP Servers

### Transport Protocol Stack

```
┌─────────────────────────────────────┐
│          VS Code Client             │
├─────────────────────────────────────┤
│    MCP Client (SSE Transport)       │
├─────────────────────────────────────┤
│         HTTPS / WSS                 │
├─────────────────────────────────────┤
│      Server-Sent Events             │
├─────────────────────────────────────┤
│       OAuth2 Middleware             │
├─────────────────────────────────────┤
│      Berry MCP Server               │
└─────────────────────────────────────┘
```

### Step-by-Step Organization Setup

## 1. **Server Deployment**

Organizations deploy the MCP server as a web service:

```python
# enterprise_pdf_server.py
from berry_mcp import MCPServer
from berry_mcp.auth import OAuth2Config, OAuth2Manager
from berry_mcp.core import EnhancedSSETransport

# Enterprise OAuth2 setup (using organization's SSO)
oauth_config = OAuth2Config(
    client_id="org_mcp_client_id",
    client_secret="org_mcp_client_secret",
    authorization_url="https://sso.company.com/oauth2/auth",
    token_url="https://sso.company.com/oauth2/token",
    redirect_uri="https://mcp.company.com/oauth/callback",
    scope="openid profile email groups"
)

oauth_manager = OAuth2Manager(oauth_config)

# Production server with HTTPS
server = MCPServer(name="enterprise-pdf-service")
transport = EnhancedSSETransport(
    host="0.0.0.0",
    port=443,  # HTTPS port
    oauth_manager=oauth_manager,
    require_auth=True,
    ssl_cert_path="/etc/ssl/certs/mcp.company.com.pem",
    ssl_key_path="/etc/ssl/private/mcp.company.com.key"
)

server.connect_transport(transport)
await server.run()
```

## 2. **DNS and Load Balancer**

```
Internet → Load Balancer → MCP Servers
   ↓           ↓              ↓
   └→ mcp.company.com:443 → [Server 1, Server 2, Server 3]
```

## 3. **User Connection Flow**

### **Initial Setup (One-time per user):**

1. **Admin provides server URL**: `https://mcp.company.com`
2. **User authenticates**: 
   ```bash
   curl https://mcp.company.com/auth
   # Redirects to company SSO
   ```
3. **User gets access token** after SSO login
4. **User configures VS Code**

### **VS Code Configuration:**

```json
// .vscode/mcp.json (User's local config)
{
  "servers": {
    "company-pdf-service": {
      "type": "sse",
      "url": "https://mcp.company.com",
      "authorization_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
      "timeout": 30000,
      "retry_attempts": 3
    }
  }
}
```

## 4. **Network Communication**

### **Connection Establishment:**
```
VS Code → HTTPS GET https://mcp.company.com/events
Headers:
  Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
  Accept: text/event-stream
  Cache-Control: no-cache
```

### **MCP Protocol over SSE:**
```
# Server sends (SSE format):
data: {"jsonrpc": "2.0", "method": "initialize", "params": {...}}

# Client responds (HTTP POST):
POST https://mcp.company.com/rpc
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Content-Type: application/json

{"jsonrpc": "2.0", "method": "tools/list", "id": 1}
```

## 5. **Enterprise Features**

### **User Authentication & Authorization:**
```python
# Role-based access control
@server.tool
async def sensitive_pdf_extract(file_path: str):
    user = get_current_user()  # From OAuth2 token
    
    if not user.has_role("pdf_processor"):
        raise PermissionError("Insufficient permissions")
    
    if not user.can_access_path(file_path):
        raise PermissionError("Path access denied")
    
    return await extract_pdf(file_path)
```

### **Audit Logging:**
```python
# Every action is logged
logger.info("pdf_extract_requested", 
    user_id=user.id, 
    user_email=user.email,
    file_path=file_path,
    timestamp=datetime.utcnow(),
    client_ip=request.client.host
)
```

### **Rate Limiting:**
```python
# Per-user rate limiting
@rate_limit(max_requests=100, window_minutes=60)
@server.tool
async def pdf_extract(file_path: str):
    # Implementation
```

## 6. **Production Deployment Options**

### **Option A: Kubernetes**
```yaml
# kubernetes/mcp-server.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-pdf-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mcp-pdf-service
  template:
    spec:
      containers:
      - name: mcp-server
        image: company/mcp-pdf-service:latest
        ports:
        - containerPort: 8080
        env:
        - name: OAUTH_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: oauth-secrets
              key: client-id
        - name: OAUTH_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: oauth-secrets
              key: client-secret
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-pdf-service
spec:
  selector:
    app: mcp-pdf-service
  ports:
  - port: 443
    targetPort: 8080
  type: LoadBalancer
```

### **Option B: Docker Swarm**
```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  mcp-server:
    image: company/mcp-pdf-service:latest
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 30s
      restart_policy:
        condition: on-failure
    ports:
      - "443:8080"
    environment:
      - OAUTH_PROVIDER=enterprise_sso
      - SSL_CERT_PATH=/certs/server.pem
      - SSL_KEY_PATH=/certs/server.key
    volumes:
      - ssl-certs:/certs:ro
      - pdf-storage:/app/storage
    networks:
      - mcp-network

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ssl-certs:/etc/ssl/certs:ro
```

### **Option C: Cloud Functions (Serverless)**
```python
# For lighter workloads
from berry_mcp.cloud import CloudFunctionAdapter

def gcp_function_handler(request):
    adapter = CloudFunctionAdapter(
        oauth_config=get_oauth_config(),
        allowed_origins=["https://company.com"]
    )
    return adapter.handle_request(request)
```

## 7. **User Experience**

### **For End Users:**
1. **One-time setup**: Admin provides server URL
2. **Authentication**: Login with company credentials (SSO)
3. **VS Code integration**: Configure MCP server
4. **Usage**: Same as local MCP - tools appear in VS Code

### **For Administrators:**
1. **Deploy server**: Kubernetes/Docker deployment
2. **Configure SSO**: Integrate with company OAuth2/SAML
3. **Set permissions**: Role-based access control
4. **Monitor usage**: Audit logs and metrics
5. **Scale as needed**: Add more server instances

## 8. **Security Features**

### **Transport Security:**
- ✅ TLS 1.3 encryption (HTTPS)
- ✅ Certificate pinning
- ✅ Perfect Forward Secrecy

### **Authentication:**
- ✅ OAuth2 with company SSO
- ✅ JWT token validation
- ✅ Token refresh handling
- ✅ Session management

### **Authorization:**
- ✅ Role-based access control
- ✅ Path-based permissions
- ✅ Resource quotas
- ✅ Rate limiting

### **Monitoring:**
- ✅ Audit logs for all actions
- ✅ Performance metrics
- ✅ Error tracking
- ✅ User activity monitoring

## 9. **Scaling Considerations**

### **Horizontal Scaling:**
```python
# Stateless server design
server = MCPServer(name="pdf-service")
server.connect_transport(EnhancedSSETransport(
    host="0.0.0.0",
    port=8080,
    oauth_manager=oauth_manager,
    session_store=RedisSessionStore(),  # Shared session storage
    rate_limiter=RedisRateLimiter()     # Shared rate limiting
))
```

### **Load Balancing:**
```nginx
# nginx.conf
upstream mcp_servers {
    server mcp-server-1:8080;
    server mcp-server-2:8080;
    server mcp-server-3:8080;
}

server {
    listen 443 ssl;
    server_name mcp.company.com;
    
    ssl_certificate /etc/ssl/certs/mcp.company.com.pem;
    ssl_certificate_key /etc/ssl/private/mcp.company.com.key;
    
    location / {
        proxy_pass http://mcp_servers;
        proxy_set_header Authorization $http_authorization;
        proxy_set_header X-Real-IP $remote_addr;
        
        # SSE specific headers
        proxy_set_header Cache-Control no-cache;
        proxy_buffering off;
        proxy_read_timeout 86400;
    }
}
```

This architecture allows organizations to provide secure, scalable MCP services to their users while maintaining proper authentication, authorization, and audit trails.
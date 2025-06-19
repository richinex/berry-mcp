# Berry MCP Deployment Guide

This guide shows how to deploy Berry MCP with OAuth2 authentication for production use, specifically for PDF processing services.

## Quick Setup for PDF Service

### 1. Prerequisites

```bash
# Install with PDF dependencies
uv pip install -e ".[dev]"
uv pip install pymupdf4llm PyPDF2

# Or using pip
pip install -e ".[dev]"
pip install pymupdf4llm PyPDF2
```

### 2. OAuth2 Provider Setup

#### Option A: Google OAuth2
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google+ API
4. Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client ID"
5. Set application type to "Web application"
6. Add authorized redirect URI: `http://localhost:8080/oauth/callback`
7. Save your Client ID and Client Secret

#### Option B: GitHub OAuth2
1. Go to GitHub → Settings → Developer settings → OAuth Apps
2. Click "New OAuth App"
3. Set Authorization callback URL: `http://localhost:8080/oauth/callback`
4. Save your Client ID and Client Secret

### 3. Environment Configuration

Create a `.env` file:

```bash
# OAuth2 Configuration
OAUTH_PROVIDER=google  # or github
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here

# Or for GitHub:
# GITHUB_CLIENT_ID=your_github_client_id_here
# GITHUB_CLIENT_SECRET=your_github_client_secret_here

# Service Configuration
SERVICE_HOST=localhost
SERVICE_PORT=8080

# Logging
BERRY_PDF_LOG_LEVEL=INFO
```

### 4. Run the Secure PDF Service

```bash
# Using the example service
python examples/pdf_service_setup.py

# Or using environment variables
OAUTH_PROVIDER=google SERVICE_PORT=8080 python examples/pdf_service_setup.py
```

### 5. User Authentication Flow

1. **Start Service**: Server starts at `http://localhost:8080`
2. **User Authentication**: 
   - Visit `http://localhost:8080/auth`
   - Redirected to OAuth provider (Google/GitHub)
   - Grant permissions
   - Redirected back with access token
3. **VS Code Integration**:
   - Add to `.vscode/mcp.json`:
   ```json
   {
     "servers": {
       "secure-pdf-service": {
         "type": "sse",
         "url": "http://localhost:8080",
         "authorization_token": "token_from_auth_flow"
       }
     }
   }
   ```

## Production Deployment

### 1. Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml .
COPY src/ src/
COPY examples/ examples/

# Install Python dependencies
RUN pip install -e ".[dev]" && \
    pip install pymupdf4llm PyPDF2

# Create non-root user
RUN useradd -m -u 1000 berry && \
    chown -R berry:berry /app
USER berry

# Expose port
EXPOSE 8080

# Run service
CMD ["python", "examples/pdf_service_setup.py"]
```

Build and run:

```bash
docker build -t secure-pdf-service .
docker run -p 8080:8080 \
  -e OAUTH_PROVIDER=google \
  -e GOOGLE_CLIENT_ID=your_client_id \
  -e GOOGLE_CLIENT_SECRET=your_client_secret \
  secure-pdf-service
```

### 2. Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  pdf-service:
    build: .
    ports:
      - "8080:8080"
    environment:
      - OAUTH_PROVIDER=google
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - SERVICE_HOST=0.0.0.0
      - SERVICE_PORT=8080
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    
  # Optional: Add Redis for token storage
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  redis_data:
```

Run with:
```bash
docker-compose up -d
```

### 3. Kubernetes Deployment

Create `k8s-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: secure-pdf-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: secure-pdf-service
  template:
    metadata:
      labels:
        app: secure-pdf-service
    spec:
      containers:
      - name: pdf-service
        image: secure-pdf-service:latest
        ports:
        - containerPort: 8080
        env:
        - name: OAUTH_PROVIDER
          value: "google"
        - name: GOOGLE_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: oauth-secrets
              key: client-id
        - name: GOOGLE_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: oauth-secrets
              key: client-secret
        - name: SERVICE_HOST
          value: "0.0.0.0"
        - name: SERVICE_PORT
          value: "8080"
---
apiVersion: v1
kind: Service
metadata:
  name: secure-pdf-service
spec:
  selector:
    app: secure-pdf-service
  ports:
  - port: 80
    targetPort: 8080
  type: LoadBalancer
```

## Security Considerations

### 1. Token Storage
- **Development**: File-based storage in `~/.berry_mcp/tokens.json`
- **Production**: Use Redis or database for token storage
- **Kubernetes**: Use secrets and persistent volumes

### 2. HTTPS in Production
```python
# For production, use HTTPS
transport = EnhancedSSETransport(
    host="0.0.0.0",
    port=443,
    oauth_manager=oauth_manager,
    require_auth=True,
    ssl_cert_path="/path/to/cert.pem",
    ssl_key_path="/path/to/key.pem"
)
```

### 3. File Access Controls
```python
# Restrict file access to user's directory
@server.tool
async def secure_pdf_extract(file_path: str):
    # Validate file is in allowed directory
    allowed_dirs = [
        str(Path.home() / "Documents"),
        str(Path.home() / "Downloads"),
        "/tmp/user_uploads"
    ]
    
    if not any(file_path.startswith(dir) for dir in allowed_dirs):
        return {"error": "Access denied: File outside allowed directories"}
```

### 4. Rate Limiting
```python
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self, max_requests=10, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
    
    def is_allowed(self, user_id: str) -> bool:
        now = time.time()
        user_requests = self.requests[user_id]
        
        # Remove old requests
        user_requests[:] = [req_time for req_time in user_requests 
                           if now - req_time < self.window_seconds]
        
        if len(user_requests) >= self.max_requests:
            return False
            
        user_requests.append(now)
        return True
```

## Monitoring and Logging

### 1. Structured Logging
```python
import structlog

logger = structlog.get_logger(__name__)

@server.tool
async def monitored_pdf_extract(file_path: str):
    logger.info("pdf_extract_started", 
                file_path=file_path, 
                user_id=get_current_user_id())
    
    try:
        result = await process_pdf(file_path)
        logger.info("pdf_extract_completed", 
                    file_path=file_path,
                    pages_processed=result.get('pages', 0))
        return result
    except Exception as e:
        logger.error("pdf_extract_failed", 
                     file_path=file_path,
                     error=str(e))
        raise
```

### 2. Health Checks
```python
@server.tool
async def health_check():
    """Health check endpoint for load balancers"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0",
        "dependencies": {
            "pymupdf": PYMUPDF_AVAILABLE,
            "pypdf2": PYPDF2_AVAILABLE
        }
    }
```

## VS Code Integration

### 1. User Setup Instructions

After authentication, users add to their `.vscode/mcp.json`:

```json
{
  "servers": {
    "secure-pdf-service": {
      "type": "sse", 
      "url": "https://your-domain.com",
      "authorization_token": "user_access_token_here"
    }
  }
}
```

### 2. Available Tools

Users will have access to:
- `secure_pdf_extract`: Extract text from PDF with confirmation
- `list_user_pdfs`: List available PDF files
- `pdf_batch_process`: Process multiple PDFs with approval

### 3. User Experience Flow

1. **Authentication**: User logs in via OAuth2
2. **Tool Discovery**: VS Code discovers available PDF tools
3. **Permission Prompts**: User gets confirmation dialogs for operations
4. **Secure Processing**: PDFs processed with user consent
5. **Results**: Extracted text returned to VS Code

This setup provides a secure, production-ready PDF processing service with proper authentication, user consent, and VS Code integration!
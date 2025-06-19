# OAuth2 Authentication & Elicitation Features

This document describes the new OAuth2 authentication and elicitation (human-in-the-loop) features added to Berry MCP Server, based on recent Anthropic MCP specification updates.

## OAuth2 Authentication

### Overview

OAuth2 authentication support allows MCP servers to securely authenticate with external services and provide token-based access control.

### Features

- **Standard OAuth2 flows** with PKCE support
- **Automatic token refresh** when tokens expire
- **Token storage** (memory and file-based)
- **Authentication middleware** for FastAPI routes
- **MCP connector compatibility** with authorization_token parameter

### Configuration

#### Basic OAuth2 Setup

```python
from berry_mcp.auth import OAuth2Manager, OAuth2Config

# Configure OAuth2
config = OAuth2Config(
    client_id="your_client_id",
    client_secret="your_client_secret", 
    authorization_url="https://provider.com/oauth/authorize",
    token_url="https://provider.com/oauth/token",
    redirect_uri="http://localhost:8080/oauth/callback",
    scope="read write",
    use_pkce=True
)

oauth_manager = OAuth2Manager(config)
```

#### Environment Variables

```bash
export OAUTH_CLIENT_ID="your_client_id"
export OAUTH_CLIENT_SECRET="your_client_secret"
export OAUTH_AUTH_URL="https://provider.com/oauth/authorize"
export OAUTH_TOKEN_URL="https://provider.com/oauth/token"
export OAUTH_REDIRECT_URI="http://localhost:8080/oauth/callback"
export OAUTH_SCOPE="read write"
export REQUIRE_AUTH="true"  # Require auth for all requests
```

#### MCP Configuration

Update your `.vscode/mcp.json` to include OAuth2 tokens:

```json
{
  "servers": {
    "berry-mcp-authenticated": {
      "type": "sse",
      "url": "http://localhost:8080",
      "authorization_token": "YOUR_ACCESS_TOKEN_HERE",
      "headers": {
        "Content-Type": "application/json"
      }
    }
  }
}
```

### OAuth2 Flow

1. **Authorization**: Generate authorization URL with PKCE
2. **User Consent**: User authenticates with provider
3. **Token Exchange**: Exchange authorization code for tokens
4. **Token Refresh**: Automatically refresh expired tokens
5. **Request Authentication**: Include Bearer token in requests

### API Endpoints

When OAuth2 is enabled, the following endpoints are available:

- `GET /oauth/authorize` - Start OAuth flow
- `POST /oauth/callback` - Handle OAuth callback
- `POST /oauth/refresh` - Refresh access token
- `GET /health` - Health check with auth status

### Example Usage

```python
from berry_mcp.core.enhanced_transport import EnhancedSSETransport

# Create enhanced transport with OAuth2
transport = EnhancedSSETransport(
    host="localhost",
    port=8080,
    oauth_manager=oauth_manager,
    require_auth=True  # Require authentication for all requests
)

# Tools can check authentication status
@tool(description="Secure operation requiring authentication")
async def secure_operation(data: str) -> dict:
    token_info = transport.get_token_info()
    if not token_info:
        return {"error": "Authentication required"}
    
    return {"success": True, "data": f"Processed: {data}"}
```

## Elicitation (Human-in-the-Loop)

### Overview

Elicitation enables MCP servers to request information from end users during tool execution, enabling sophisticated human-in-the-loop workflows.

### Features

- **Multiple prompt types**: Confirmation, input, choice, file selection
- **Async communication** between server and client
- **Timeout handling** for prompts
- **Validation** of user responses
- **Streaming support** for long-running operations
- **Enhanced tool schemas** with capability metadata

### Prompt Types

#### Confirmation Prompts

```python
from berry_mcp.elicitation import ElicitationManager, PromptBuilder

# Ask for yes/no confirmation
confirmed = await elicitation_manager.prompt_confirmation(
    title="Delete File",
    message="Are you sure you want to delete this file?",
    default=False,
    timeout=60
)
```

#### Input Prompts

```python
# Get text input from user
user_input = await elicitation_manager.prompt_input(
    title="Enter Name",
    message="Please enter your name:",
    placeholder="Your name here...",
    default="Anonymous",
    max_length=100,
    pattern=r"^[A-Za-z\s]+$",  # Only letters and spaces
    timeout=120
)
```

#### Choice Prompts

```python
# Single choice
choice = await elicitation_manager.prompt_choice(
    title="Select Mode",
    message="Choose processing mode:",
    choices=[
        ("fast", "Fast mode"),
        ("accurate", "Accurate mode"),
        ("balanced", "Balanced mode")
    ],
    timeout=60
)

# Multiple choice
choices = await elicitation_manager.prompt_choice(
    title="Select Options",
    message="Choose features to enable:",
    choices=[
        ("logging", "Enable logging"),
        ("cache", "Enable caching"),
        ("backup", "Enable backup")
    ],
    allow_multiple=True,
    min_selections=1,
    max_selections=3,
    timeout=120
)
```

#### File Selection Prompts

```python
# Single file selection
file_path = await elicitation_manager.prompt_file_selection(
    title="Select Input File",
    message="Choose a file to process:",
    file_types=[".txt", ".json", ".csv"],
    start_directory="/home/user/documents",
    timeout=180
)

# Multiple file selection
file_paths = await elicitation_manager.prompt_file_selection(
    title="Select Files",
    message="Choose files to process:",
    file_types=[".txt", ".md"],
    allow_multiple=True,
    timeout=300
)
```

### Tool Enhancement

#### Enhanced Tool Decorators

```python
from berry_mcp.elicitation import CapabilityBuilder

@tool(description="Interactive file processor")
async def process_file_interactive(file_path: str) -> dict:
    """Process a file with user confirmation"""
    
    # Register capability metadata
    capability = CapabilityBuilder.create_file_tool_capability(
        name="process_file_interactive",
        description="Process files with user confirmation",
        supports_streaming=True
    )
    elicitation_manager.register_capability(capability)
    
    # Get user confirmation
    confirmed = await elicitation_manager.prompt_confirmation(
        title="File Processing",
        message=f"Process file: {file_path}?",
        default=False
    )
    
    if not confirmed:
        return {"error": "Operation cancelled", "success": False}
    
    # Process the file
    return {"success": True, "file_path": file_path}
```

#### Tool Output Schemas

```python
from berry_mcp.elicitation.schemas import SchemaBuilder, ToolOutputSchema

# Create output schema for search results
search_schema = SchemaBuilder.create_search_result_schema()

# Custom schema
custom_schema = ToolOutputSchema(description="Custom operation result")
custom_schema.add_property("status", "string", "Operation status", required=True)
custom_schema.add_property("data", "object", "Result data")
custom_schema.add_property("timestamp", "string", "Operation timestamp", format="date-time")
```

### Handlers

#### Console Handler (Development)

```python
from berry_mcp.elicitation import ConsoleElicitationHandler

# Console-based handler for development/testing
handler = ConsoleElicitationHandler()
elicitation_manager = ElicitationManager(handler=handler)
```

#### SSE Handler (Production)

```python
from berry_mcp.elicitation import SSEElicitationHandler

# SSE-based handler for web clients
handler = SSEElicitationHandler(transport_manager)
elicitation_manager = ElicitationManager(handler=handler)
```

### Streaming Results

For long-running operations, you can stream partial results:

```python
from berry_mcp.elicitation.manager import StreamingResultManager

streaming_manager = StreamingResultManager(transport)

@tool(description="Long-running operation with streaming")
async def long_operation(data: str) -> dict:
    operation_id = "op_" + str(uuid.uuid4())
    
    # Start streaming
    await streaming_manager.start_stream(
        operation_id=operation_id,
        tool_name="long_operation",
        metadata={"input_size": len(data)}
    )
    
    try:
        # Send progress chunks
        for i in range(10):
            await asyncio.sleep(1)  # Simulate work
            await streaming_manager.send_chunk(
                operation_id=operation_id,
                chunk_data={"progress": (i + 1) * 10, "status": f"Processing step {i+1}"},
                chunk_type="progress"
            )
        
        # Send final result
        final_result = {"processed_data": f"Result for: {data}"}
        await streaming_manager.complete_stream(operation_id, final_result)
        
        return final_result
        
    except Exception as e:
        await streaming_manager.complete_stream(operation_id, error=str(e))
        raise
```

## Example Server

See `examples/enhanced_server.py` for a complete example demonstrating:

- OAuth2 authentication setup
- Interactive tools with elicitation
- Capability registration
- Enhanced transport configuration
- Streaming operations

## Running the Enhanced Server

```bash
# Install dependencies
pip install -e ".[http]"

# Set OAuth2 environment variables (optional)
export OAUTH_CLIENT_ID="your_client_id"
export OAUTH_CLIENT_SECRET="your_client_secret"
export REQUIRE_AUTH="false"  # Set to true to require auth

# Run the enhanced server
python examples/enhanced_server.py
```

The server will start with:
- OAuth2 endpoints (if configured)
- Elicitation support for human-in-the-loop
- Enhanced health and status endpoints
- Interactive tools that prompt for user input

## Integration with VS Code

The enhanced features work seamlessly with VS Code MCP integration:

1. **Authentication**: Use the `authorization_token` parameter in MCP configuration
2. **Elicitation**: User prompts appear as VS Code notifications/dialogs
3. **Streaming**: Partial results are displayed in real-time
4. **Capabilities**: Enhanced tool discovery with metadata

## Best Practices

### Security

- Store OAuth2 credentials securely (environment variables, key vault)
- Use HTTPS for production OAuth2 flows
- Implement proper token rotation and refresh
- Validate all user inputs from elicitation prompts

### User Experience

- Provide clear, concise prompt messages
- Set reasonable timeouts for prompts
- Offer sensible defaults for optional inputs
- Handle cancellation gracefully

### Performance

- Use streaming for long-running operations
- Cache frequently requested data
- Implement proper error handling and recovery
- Monitor token expiration and refresh proactively

### Development

- Use console handler for development and testing
- Mock elicitation responses in unit tests
- Test OAuth2 flows with development credentials
- Validate tool schemas and capability metadata
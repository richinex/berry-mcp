# Tool Development Guide for Berry MCP Server

This guide explains how to create custom tools for Berry MCP Server.

## Quick Start

1. Create a Python module with tool functions
2. Decorate functions with `@tool`
3. Configure Berry MCP to load your module

```python
# my_tools.py
from berry_mcp.tools.decorators import tool

@tool(description="Add two numbers")
def add(a: float, b: float) -> float:
    """Add two numbers together"""
    return a + b
```

Then run: `BERRY_MCP_TOOLS_PATH=my_tools python -m berry_mcp`

## Tool Decorator

The `@tool` decorator automatically generates JSON schema from your function signature:

```python
@tool(
    name="custom_name",           # Optional: defaults to function name
    description="What this does", # Optional: defaults to docstring
    examples=[                    # Optional: usage examples
        {"input": {"a": 1, "b": 2}, "output": 3}
    ]
)
def my_function(a: int, b: int = 5) -> int:
    """Function docstring used as description if not specified"""
    return a + b
```

## Type Annotations

Berry MCP supports Python type annotations and converts them to JSON schema:

| Python Type | JSON Schema |
|-------------|-------------|
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list` / `List[T]` | `{"type": "array"}` |
| `dict` / `Dict[K,V]` | `{"type": "object"}` |
| `Optional[T]` | Same as T, not required |

```python
from typing import List, Dict, Optional, Union

@tool()
def complex_function(
    name: str,
    age: int,
    scores: List[float],
    metadata: Dict[str, str],
    nickname: Optional[str] = None
) -> Dict[str, Union[str, int, List[float]]]:
    """Demonstrates complex type annotations"""
    return {
        "name": name,
        "age": age, 
        "scores": scores,
        "nickname": nickname or "No nickname"
    }
```

## Async Tools

Berry MCP supports both synchronous and asynchronous tools:

```python
import asyncio

@tool(description="Async processing example")
async def async_process(data: str, delay: float = 1.0) -> str:
    """Demonstrate async tool with delay"""
    await asyncio.sleep(delay)
    return f"Processed: {data.upper()}"
```

## Error Handling

### Method 1: Return Error Dictionary (Recommended)
```python
@tool()
def safe_divide(a: float, b: float) -> Union[float, Dict[str, str]]:
    """Divide two numbers safely"""
    if b == 0:
        return {"error": "Division by zero is not allowed"}
    return a / b
```

### Method 2: Raise Exceptions
```python
@tool()
def risky_operation(value: str) -> str:
    """Operation that might fail"""
    if not value.strip():
        raise ValueError("Value cannot be empty")
    return value.upper()
```

## File Operations

When working with files, consider workspace security:

```python
import os
from pathlib import Path

@tool()
def read_text_file(filepath: str, encoding: str = "utf-8") -> Union[str, Dict[str, str]]:
    """Read a text file safely"""
    try:
        # Resolve and validate path
        path = Path(filepath).resolve()
        
        # Basic security check (customize as needed)
        if not path.exists():
            return {"error": f"File not found: {filepath}"}
        
        if not path.is_file():
            return {"error": f"Path is not a file: {filepath}"}
        
        with open(path, 'r', encoding=encoding) as f:
            return f.read()
            
    except PermissionError:
        return {"error": f"Permission denied: {filepath}"}
    except UnicodeDecodeError:
        return {"error": f"Cannot decode file with {encoding} encoding"}
    except Exception as e:
        return {"error": f"Failed to read file: {str(e)}"}
```

## External APIs

For tools that call external APIs:

```python
import requests
from typing import Optional

@tool()
def fetch_weather(city: str, api_key: Optional[str] = None) -> Union[Dict, Dict[str, str]]:
    """Fetch weather data for a city"""
    try:
        # Use environment variable if no API key provided
        key = api_key or os.getenv("WEATHER_API_KEY")
        if not key:
            return {"error": "API key required (WEATHER_API_KEY env var or api_key param)"}
        
        url = f"https://api.weather.com/v1/current?city={city}&key={key}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        return response.json()
        
    except requests.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Weather fetch failed: {str(e)}"}
```

## Tool Organization

### Single Module
```python
# my_tools.py
from berry_mcp.tools.decorators import tool

@tool()
def tool1(): pass

@tool() 
def tool2(): pass
```

### Package Structure
```
my_tools/
├── __init__.py
├── text_tools.py
├── file_tools.py
└── api_tools.py
```

```python
# my_tools/__init__.py
"""My custom tool collection"""

# Import tool modules to register them
from . import text_tools
from . import file_tools  
from . import api_tools

__all__ = ["text_tools", "file_tools", "api_tools"]
```

## Best Practices

### 1. Clear Documentation
```python
@tool(
    description="Convert text between different cases",
    examples=[
        {"input": {"text": "hello world", "case": "upper"}, "output": "HELLO WORLD"},
        {"input": {"text": "Hello World", "case": "snake"}, "output": "hello_world"}
    ]
)
def convert_case(text: str, case: str = "upper") -> Union[str, Dict[str, str]]:
    """
    Convert text to different cases.
    
    Args:
        text: The text to convert
        case: Target case (upper, lower, title, snake, camel)
    
    Returns:
        Converted text or error dictionary
    """
    # Implementation here
```

### 2. Input Validation
```python
@tool()
def process_data(data: List[float], operation: str = "sum") -> Union[float, Dict[str, str]]:
    """Process numerical data"""
    if not data:
        return {"error": "Data list cannot be empty"}
    
    valid_operations = ["sum", "mean", "max", "min"]
    if operation not in valid_operations:
        return {"error": f"Invalid operation. Choose from: {valid_operations}"}
    
    # Process data...
```

### 3. Configuration via Environment
```python
import os

@tool()
def api_call(endpoint: str) -> Union[Dict, Dict[str, str]]:
    """Call API with configured base URL"""
    base_url = os.getenv("API_BASE_URL", "https://api.example.com")
    timeout = int(os.getenv("API_TIMEOUT", "30"))
    
    # Make request...
```

## Testing Your Tools

Create a test script:

```python
# test_my_tools.py
import asyncio
from my_tools import add, async_process

def test_sync_tool():
    result = add(2, 3)
    assert result == 5
    print("✓ Sync tool works")

async def test_async_tool():
    result = await async_process("test", 0.1)
    assert "TEST" in result
    print("✓ Async tool works")

if __name__ == "__main__":
    test_sync_tool()
    asyncio.run(test_async_tool())
    print("All tests passed!")
```

## Loading Tools in Berry MCP

### Environment Variable
```bash
export BERRY_MCP_TOOLS_PATH="my_tools,other_tools.submodule"
python -m berry_mcp
```

### Command Line
```bash
python -m berry_mcp --tools-path "my_tools,other_tools"
```

### VS Code Configuration
```json
{
  "mcp": {
    "mcpServers": {
      "my-server": {
        "type": "stdio",
        "command": "python",
        "args": ["-m", "berry_mcp"],
        "env": {
          "BERRY_MCP_TOOLS_PATH": "my_tools,other_tools"
        }
      }
    }
  }
}
```

The Berry MCP framework will automatically discover and register all `@tool` decorated functions from the specified modules.
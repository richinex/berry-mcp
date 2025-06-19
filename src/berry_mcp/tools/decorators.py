"""
Tool registration decorators for Berry MCP Server
"""

import inspect
import logging
from collections.abc import Callable
from typing import Any, get_type_hints

logger = logging.getLogger(__name__)


def tool(
    name: str | None = None,
    description: str | None = None,
    examples: list[dict[str, Any]] | None = None,
) -> Callable[[Callable], Callable]:
    """
    Decorator to register a function as an MCP tool.

    This decorator automatically generates JSON schema from function signatures
    and type hints, making it easy to add new tools to the MCP server.

    Args:
        name: Optional custom name for the tool. Defaults to function name.
        description: Optional description for the tool. Defaults to function docstring.

    Example:
        @tool(description="Calculate the sum of two numbers")
        def add_numbers(a: int, b: int) -> int:
            '''Add two integers together'''
            return a + b

        @tool()
        def read_file(path: str, encoding: str = "utf-8") -> str:
            '''Read content from a file'''
            with open(path, 'r', encoding=encoding) as f:
                return f.read()
    """

    def decorator(func: Callable) -> Callable:
        # Get function metadata
        tool_name = name or func.__name__
        tool_description = description or (func.__doc__ or "").strip()

        # Get type hints and signature
        type_hints = get_type_hints(func)
        signature = inspect.signature(func)

        # Generate JSON schema for parameters
        parameters_schema = _generate_parameters_schema(signature, type_hints)

        # Store tool metadata on the function
        func._mcp_tool_metadata = {
            "name": tool_name,
            "description": tool_description,
            "parameters": parameters_schema,
            "function": func,
            "examples": examples or [],
            "async": inspect.iscoroutinefunction(func),
        }

        logger.debug(
            f"Tool decorated: {tool_name} ({'async' if inspect.iscoroutinefunction(func) else 'sync'})"
        )

        return func

    return decorator


def _generate_parameters_schema(
    signature: inspect.Signature, type_hints: dict[str, Any]
) -> dict[str, Any]:
    """Generate JSON schema for function parameters"""
    properties = {}
    required = []

    for param_name, param in signature.parameters.items():
        if param_name == "self":
            continue

        param_type = type_hints.get(param_name, str)
        param_info = _type_to_json_schema(param_type)

        # Handle default values
        if param.default != inspect.Parameter.empty:
            param_info["default"] = param.default
        else:
            required.append(param_name)

        properties[param_name] = param_info

    schema = {"type": "object", "properties": properties}

    if required:
        schema["required"] = required

    return schema


def _type_to_json_schema(python_type: Any) -> dict[str, Any]:
    """Convert Python type to JSON schema"""
    if python_type == str:
        return {"type": "string"}
    elif python_type == int:
        return {"type": "integer"}
    elif python_type == float:
        return {"type": "number"}
    elif python_type == bool:
        return {"type": "boolean"}
    elif python_type == list:
        return {"type": "array"}
    elif python_type == dict:
        return {"type": "object"}
    elif hasattr(python_type, "__origin__"):
        # Handle generic types like List[str], Optional[int], etc.
        origin = python_type.__origin__
        if origin == list:
            return {"type": "array"}
        elif origin == dict:
            return {"type": "object"}
        elif origin == type(None) or str(python_type).startswith("typing.Union"):
            # Handle Optional types
            return {"type": "string"}

    # Default to string for unknown types
    return {"type": "string"}

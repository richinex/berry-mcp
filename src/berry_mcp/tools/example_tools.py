"""
Example tools for Berry MCP Server
These demonstrate how to create tools that users can easily add to their tools/ directory

This module provides comprehensive examples of:
- Simple synchronous tools
- Asynchronous tools
- Tools with complex parameters
- Error handling patterns
- Type validation
- Documentation best practices
"""

from .decorators import tool


@tool(
    description="Add two numbers together",
    examples=[
        {"input": {"a": 2.5, "b": 3.7}, "output": 6.2},
        {"input": {"a": -1, "b": 5}, "output": 4.0},
    ],
)
def add_numbers(a: float, b: float) -> float:
    """Simple addition tool demonstrating basic math operations"""
    return a + b


@tool(
    description="Get basic system information",
    examples=[
        {
            "input": {},
            "output": {
                "platform": "Linux",
                "platform_version": "5.15.0",
                "python_version": "3.11.0",
                "current_directory": "/home/user",
                "user": "username",
            },
        }
    ],
)
def get_system_info() -> dict[str, str]:
    """Get basic system information including platform, Python version, and user details"""
    import os
    import platform

    return {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "python_version": platform.python_version(),
        "current_directory": os.getcwd(),
        "user": os.getenv("USER", "unknown"),
    }


@tool(
    description="Generate a UUID",
    examples=[
        {"input": {"version": 4}, "output": "550e8400-e29b-41d4-a716-446655440000"},
        {"input": {"version": 1}, "output": "6ba7b810-9dad-11d1-80b4-00c04fd430c8"},
    ],
)
def generate_uuid(version: int = 4) -> str | dict[str, str]:
    """Generate a UUID (version 1 or 4)"""
    import uuid

    if version == 1:
        return str(uuid.uuid1())
    elif version == 4:
        return str(uuid.uuid4())
    else:
        return {"error": f"Unsupported UUID version: {version}. Use 1 or 4."}


@tool(description="Format text in various ways")
def format_text(
    text: str, operation: str = "upper", prefix: str = "", suffix: str = ""
) -> str | dict[str, str]:
    """
    Format text in various ways

    Args:
        text: The text to format
        operation: Operation to perform (upper, lower, title, reverse)
        prefix: Text to add before
        suffix: Text to add after
    """
    operations = {
        "upper": lambda t: t.upper(),
        "lower": lambda t: t.lower(),
        "title": lambda t: t.title(),
        "reverse": lambda t: t[::-1],
        "strip": lambda t: t.strip(),
    }

    if operation not in operations:
        return {
            "error": f"Unknown operation: {operation}. Available: {list(operations.keys())}"
        }

    formatted = operations[operation](text)
    return f"{prefix}{formatted}{suffix}"


@tool(description="Encode/decode text in various formats")
def encode_decode_text(
    text: str, operation: str = "base64_encode", encoding: str = "utf-8"
) -> str | dict[str, str]:
    """
    Encode or decode text in various formats

    Args:
        text: Text to encode/decode
        operation: Operation (base64_encode, base64_decode, url_encode, url_decode)
        encoding: Text encoding (default: utf-8)
    """
    try:
        if operation == "base64_encode":
            import base64

            return base64.b64encode(text.encode(encoding)).decode("ascii")

        elif operation == "base64_decode":
            import base64

            return base64.b64decode(text).decode(encoding)

        elif operation == "url_encode":
            import urllib.parse

            return urllib.parse.quote(text)

        elif operation == "url_decode":
            import urllib.parse

            return urllib.parse.unquote(text)

        else:
            return {"error": f"Unknown operation: {operation}"}

    except Exception as e:
        return {"error": f"Encoding/decoding failed: {str(e)}"}


@tool(description="Generate random data")
def generate_random(
    data_type: str = "string", length: int = 10, charset: str = "alphanumeric"
) -> str | int | float | list | dict[str, str]:
    """
    Generate random data of various types

    Args:
        data_type: Type of data (string, integer, float, list, password)
        length: Length/count for the data
        charset: For strings (alphanumeric, letters, digits, special)
    """
    import random
    import string

    try:
        if data_type == "string":
            charsets = {
                "alphanumeric": string.ascii_letters + string.digits,
                "letters": string.ascii_letters,
                "digits": string.digits,
                "special": string.punctuation,
                "all": string.ascii_letters + string.digits + string.punctuation,
            }

            if charset not in charsets:
                return {
                    "error": f"Unknown charset: {charset}. Available: {list(charsets.keys())}"
                }

            return "".join(random.choices(charsets[charset], k=length))

        elif data_type == "integer":
            return random.randint(1, 10**length)

        elif data_type == "float":
            return random.uniform(0, 10**length)

        elif data_type == "list":
            return [random.randint(1, 100) for _ in range(length)]

        elif data_type == "password":
            # Generate secure password
            chars = string.ascii_letters + string.digits + "!@#$%^&*"
            return "".join(random.choices(chars, k=length))

        else:
            return {"error": f"Unknown data type: {data_type}"}

    except Exception as e:
        return {"error": f"Random generation failed: {str(e)}"}


@tool(description="Hash text using various algorithms")
def hash_text(text: str, algorithm: str = "sha256") -> str | dict[str, str]:
    """
    Hash text using various algorithms

    Args:
        text: Text to hash
        algorithm: Hash algorithm (md5, sha1, sha256, sha512)
    """
    import hashlib

    algorithms = {
        "md5": hashlib.md5,
        "sha1": hashlib.sha1,
        "sha256": hashlib.sha256,
        "sha512": hashlib.sha512,
    }

    if algorithm not in algorithms:
        return {
            "error": f"Unknown algorithm: {algorithm}. Available: {list(algorithms.keys())}"
        }

    try:
        hasher = algorithms[algorithm]()
        hasher.update(text.encode("utf-8"))
        return hasher.hexdigest()
    except Exception as e:
        return {"error": f"Hashing failed: {str(e)}"}


# Async tool example
@tool(description="Simulate async processing with delay")
async def async_process_data(
    data: str, delay_seconds: float = 1.0, process_type: str = "uppercase"
) -> str:
    """
    Simulate async data processing with configurable delay

    Args:
        data: Data to process
        delay_seconds: Delay in seconds
        process_type: Type of processing (uppercase, lowercase, reverse)
    """
    import asyncio

    # Simulate async work
    await asyncio.sleep(delay_seconds)

    if process_type == "uppercase":
        result = data.upper()
    elif process_type == "lowercase":
        result = data.lower()
    elif process_type == "reverse":
        result = data[::-1]
    else:
        result = data

    return f"[ASYNC PROCESSED after {delay_seconds}s]: {result}"


# Error handling example
@tool(description="Demonstrate error handling patterns")
def error_demo(
    should_fail: bool = False, error_type: str = "value_error"
) -> str | dict[str, str]:
    """
    Demonstrate different error handling patterns

    Args:
        should_fail: Whether to trigger an error
        error_type: Type of error to demonstrate
    """
    if not should_fail:
        return "Success! No error triggered."

    # Demonstrate returning error dictionary (recommended)
    if error_type == "value_error":
        return {"error": "This is a controlled ValueError demonstration"}

    elif error_type == "type_error":
        return {"error": "This is a controlled TypeError demonstration"}

    elif error_type == "custom_error":
        return {"error": "This is a custom error message with additional context"}

    # Demonstrate raising exception (will be caught by server)
    elif error_type == "exception":
        raise ValueError("This exception will be caught by the MCP server")

    else:
        return {"error": f"Unknown error type: {error_type}"}

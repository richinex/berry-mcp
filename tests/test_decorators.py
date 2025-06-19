"""
Tests for tool decorators
"""

from berry_mcp.tools.decorators import tool


def test_basic_tool_decorator():
    """Test basic tool decorator functionality"""

    @tool(description="Test tool")
    def test_func(x: int, y: str = "default") -> str:
        """Test function"""
        return f"{x}: {y}"

    # Check that metadata was added
    assert hasattr(test_func, "_mcp_tool_metadata")

    metadata = test_func._mcp_tool_metadata
    assert metadata["name"] == "test_func"
    assert metadata["description"] == "Test tool"

    # Check parameters schema
    params = metadata["parameters"]
    assert params["type"] == "object"
    assert "x" in params["properties"]
    assert "y" in params["properties"]
    assert params["properties"]["x"]["type"] == "integer"
    assert params["properties"]["y"]["type"] == "string"
    assert params["properties"]["y"]["default"] == "default"
    assert params["required"] == ["x"]


def test_tool_decorator_with_custom_name():
    """Test tool decorator with custom name"""

    @tool(name="custom_name", description="Custom tool")
    def original_name(value: str) -> str:
        return value.upper()

    metadata = original_name._mcp_tool_metadata
    assert metadata["name"] == "custom_name"
    assert metadata["description"] == "Custom tool"


def test_tool_decorator_uses_docstring():
    """Test that decorator uses function docstring if no description provided"""

    @tool()
    def documented_func() -> str:
        """This is from the docstring"""
        return "test"

    metadata = documented_func._mcp_tool_metadata
    assert metadata["description"] == "This is from the docstring"


def test_tool_decorator_type_hints():
    """Test various type hint conversions"""

    @tool()
    def type_test(
        string_param: str,
        int_param: int,
        float_param: float,
        bool_param: bool,
        list_param: list,
        dict_param: dict,
    ) -> str:
        return "test"

    params = type_test._mcp_tool_metadata["parameters"]
    props = params["properties"]

    assert props["string_param"]["type"] == "string"
    assert props["int_param"]["type"] == "integer"
    assert props["float_param"]["type"] == "number"
    assert props["bool_param"]["type"] == "boolean"
    assert props["list_param"]["type"] == "array"
    assert props["dict_param"]["type"] == "object"


def test_tool_decorator_no_params():
    """Test tool with no parameters"""

    @tool()
    def no_params() -> str:
        return "no params"

    params = no_params._mcp_tool_metadata["parameters"]
    assert params["type"] == "object"
    assert params["properties"] == {}
    assert "required" not in params or params["required"] == []


def test_tool_function_still_callable():
    """Test that decorated function is still callable"""

    @tool()
    def callable_test(x: int, y: int = 5) -> int:
        return x + y

    # Function should still work normally
    result = callable_test(10, 15)
    assert result == 25

    # With default parameter
    result = callable_test(10)
    assert result == 15

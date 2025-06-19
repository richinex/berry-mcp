"""
Tests for tool registry
"""

from berry_mcp.core.registry import ToolRegistry
from berry_mcp.tools.decorators import tool


def test_registry_initialization():
    """Test registry initialization"""
    registry = ToolRegistry()
    assert len(registry.list_tools()) == 0
    assert len(registry.tools) == 0


def test_tool_registration_with_decorator():
    """Test tool registration using decorator"""
    registry = ToolRegistry()

    @tool(description="Test tool for registry")
    def test_tool(x: int) -> str:
        return str(x)

    # Register the tool
    registry.tool()(test_tool)

    # Check registration
    assert len(registry.list_tools()) == 1
    assert "test_tool" in registry.list_tools()
    assert registry.get_tool("test_tool") == test_tool


def test_manual_function_registration():
    """Test manual function registration"""
    registry = ToolRegistry()

    def manual_func(a: str, b: int = 5) -> str:
        """Manual function"""
        return f"{a}-{b}"

    registry.register_function(manual_func, description="Manually registered")

    assert len(registry.list_tools()) == 1
    assert "manual_func" in registry.list_tools()
    assert registry.get_tool("manual_func") == manual_func

    # Check schema was generated
    tools = registry.tools
    assert len(tools) == 1
    tool_schema = tools[0]
    assert tool_schema["type"] == "function"
    assert tool_schema["function"]["name"] == "manual_func"
    assert tool_schema["function"]["description"] == "Manually registered"


def test_tool_schema_format():
    """Test that tool schemas are in correct format"""
    registry = ToolRegistry()

    @tool(description="Schema test tool")
    def schema_test(param1: str, param2: int = 10) -> str:
        return f"{param1}: {param2}"

    registry.tool()(schema_test)

    tools = registry.tools
    assert len(tools) == 1

    tool_schema = tools[0]
    assert tool_schema["type"] == "function"

    func_info = tool_schema["function"]
    assert func_info["name"] == "schema_test"
    assert func_info["description"] == "Schema test tool"

    params = func_info["parameters"]
    assert params["type"] == "object"
    assert "param1" in params["properties"]
    assert "param2" in params["properties"]
    assert params["properties"]["param1"]["type"] == "string"
    assert params["properties"]["param2"]["type"] == "integer"
    assert params["properties"]["param2"]["default"] == 10
    assert params["required"] == ["param1"]


def test_get_nonexistent_tool():
    """Test getting a tool that doesn't exist"""
    registry = ToolRegistry()
    assert registry.get_tool("nonexistent") is None


def test_multiple_tool_registration():
    """Test registering multiple tools"""
    registry = ToolRegistry()

    @tool()
    def tool1() -> str:
        return "tool1"

    @tool()
    def tool2() -> str:
        return "tool2"

    registry.tool()(tool1)
    registry.tool()(tool2)

    assert len(registry.list_tools()) == 2
    assert "tool1" in registry.list_tools()
    assert "tool2" in registry.list_tools()
    assert registry.get_tool("tool1") == tool1
    assert registry.get_tool("tool2") == tool2


def test_auto_discover_tools():
    """Test auto-discovery of tools from module"""
    registry = ToolRegistry()

    # Create a mock module with tools
    class MockModule:
        @tool()
        def discovered_tool1(self) -> str:
            return "discovered1"

        @tool()
        def discovered_tool2(self) -> str:
            return "discovered2"

        def not_a_tool(self) -> str:
            return "not a tool"

    mock_module = MockModule()

    # Manually scan the module (simplified version of auto_discover)
    for name in dir(mock_module):
        obj = getattr(mock_module, name)
        if callable(obj) and hasattr(obj, "_mcp_tool_metadata"):
            registry.tool()(obj)

    assert len(registry.list_tools()) == 2
    assert "discovered_tool1" in registry.list_tools()
    assert "discovered_tool2" in registry.list_tools()


def test_registry_warning_for_undecorated_function():
    """Test that registry warns when trying to register undecorated function"""
    registry = ToolRegistry()

    def undecorated_func() -> str:
        return "no decorator"

    # This should work but log a warning
    result_func = registry.tool()(undecorated_func)

    # Function should be returned unchanged
    assert result_func == undecorated_func

    # But it shouldn't be registered since it lacks metadata
    assert len(registry.list_tools()) == 0

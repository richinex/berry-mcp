# src/ai_agent/core/registry.py
from typing import Dict, Any, Callable, List
from .schema import SchemaGenerator, SchemaType

class Tool:
    """Decorator for registering tools with auto-generated schemas"""
    def __init__(self, registry: 'ToolRegistry'):
        self.registry = registry

    def __call__(self, func: Callable):
        schema = SchemaGenerator.parse_function(func)
        self.registry.register_with_schema(func, schema)
        return func

class ToolRegistry:
    """Registry for tools and their schemas"""
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register_with_schema(self, func: Callable, schema: Dict[str, Any]):
        """Register a function with its pre-generated schema"""
        self._tools[func.__name__] = func
        self._schemas[func.__name__] = schema

    def tool(self):
        """Decorator for registering tools"""
        return Tool(self)

    def get_tool(self, name: str) -> Callable:
        """Get a tool by name"""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        return self._tools[name]

    def get_schema(self, name: str) -> Dict[str, Any]:
        """Get a tool's schema by name"""
        if name not in self._schemas:
            raise KeyError(f"Schema for tool '{name}' not found in registry")
        return self._schemas[name]

    def _serialize_schema_value(self, value: Any) -> Any:
        """Convert schema values to serializable format"""
        if isinstance(value, SchemaType):
            return value.value
        elif isinstance(value, dict):
            return {k: self._serialize_schema_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._serialize_schema_value(v) for v in value]
        return value

    @property
    def tools(self) -> List[Dict[str, Any]]:
        """Get all tools in the format expected by AI models"""
        return [
            {
                "type": "function",
                "function": self._serialize_schema_value(schema)
            }
            for schema in self._schemas.values()
        ]
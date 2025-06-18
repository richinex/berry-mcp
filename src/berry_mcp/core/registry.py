"""
Tool registry for managing MCP tools
"""

import logging
from typing import Dict, List, Any, Callable, Optional
import inspect

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing MCP tools with decorator-based registration
    """
    
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._tool_schemas: List[Dict[str, Any]] = []
    
    def tool(self) -> Callable[[Callable], Callable]:
        """
        Decorator to register a function as a tool.
        
        This method returns a decorator that can be used to register functions
        that have been decorated with the @tool decorator from tools.decorators.
        """
        def decorator(func: Callable) -> Callable:
            # Check if function has MCP tool metadata
            if hasattr(func, '_mcp_tool_metadata'):
                metadata = func._mcp_tool_metadata
                tool_name = metadata['name']
                
                # Register the tool
                self._tools[tool_name] = func
                
                # Create tool schema in OpenAI function format
                tool_schema = {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": metadata['description'],
                        "parameters": metadata['parameters']
                    }
                }
                
                self._tool_schemas.append(tool_schema)
                logger.info(f"Registered tool: {tool_name}")
            else:
                logger.warning(f"Function {func.__name__} does not have MCP tool metadata. Use @tool decorator first.")
            
            return func
        
        return decorator
    
    def register_function(self, func: Callable, name: Optional[str] = None, description: Optional[str] = None):
        """
        Manually register a function as a tool (alternative to decorator approach)
        
        Args:
            func: The function to register
            name: Optional name for the tool (defaults to function name)
            description: Optional description (defaults to function docstring)
        """
        tool_name = name or func.__name__
        tool_description = description or (func.__doc__ or "").strip()
        
        # Generate schema from function signature
        signature = inspect.signature(func)
        type_hints = {}
        try:
            type_hints = func.__annotations__
        except AttributeError:
            pass
        
        parameters_schema = self._generate_parameters_schema(signature, type_hints)
        
        # Register the tool
        self._tools[tool_name] = func
        
        # Create tool schema
        tool_schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_description,
                "parameters": parameters_schema
            }
        }
        
        self._tool_schemas.append(tool_schema)
        logger.info(f"Manually registered tool: {tool_name}")
    
    def _generate_parameters_schema(self, signature: inspect.Signature, type_hints: Dict[str, Any]) -> Dict[str, Any]:
        """Generate JSON schema for function parameters"""
        properties = {}
        required = []
        
        for param_name, param in signature.parameters.items():
            if param_name == 'self':
                continue
                
            param_type = type_hints.get(param_name, str)
            param_info = self._type_to_json_schema(param_type)
            
            # Handle default values
            if param.default != inspect.Parameter.empty:
                param_info["default"] = param.default
            else:
                required.append(param_name)
            
            properties[param_name] = param_info
        
        schema = {
            "type": "object",
            "properties": properties
        }
        
        if required:
            schema["required"] = required
        
        return schema
    
    def _type_to_json_schema(self, python_type: Any) -> Dict[str, Any]:
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
        elif hasattr(python_type, '__origin__'):
            # Handle generic types like List[str], Optional[int], etc.
            origin = python_type.__origin__
            if origin == list:
                return {"type": "array"}
            elif origin == dict:
                return {"type": "object"}
            elif origin == type(None) or str(python_type).startswith('typing.Union'):
                # Handle Optional types
                return {"type": "string"}
        
        # Default to string for unknown types
        return {"type": "string"}
    
    def get_tool(self, name: str) -> Optional[Callable]:
        """Get a registered tool by name"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all registered tool names"""
        return list(self._tools.keys())
    
    @property
    def tools(self) -> List[Dict[str, Any]]:
        """Get all tool schemas"""
        return self._tool_schemas.copy()
    
    def auto_discover_tools(self, module_or_package):
        """
        Automatically discover and register tools from a module or package.
        
        This method will scan the provided module/package for functions decorated
        with @tool and automatically register them.
        
        Args:
            module_or_package: The module or package to scan for tools
        """
        import importlib
        import pkgutil
        
        if isinstance(module_or_package, str):
            module_or_package = importlib.import_module(module_or_package)
        
        # If it's a package, scan all modules
        if hasattr(module_or_package, '__path__'):
            for importer, modname, ispkg in pkgutil.iter_modules(module_or_package.__path__, 
                                                                  module_or_package.__name__ + "."):
                try:
                    submodule = importlib.import_module(modname)
                    self._scan_module_for_tools(submodule)
                except ImportError as e:
                    logger.warning(f"Could not import {modname}: {e}")
        else:
            # Single module
            self._scan_module_for_tools(module_or_package)
    
    def _scan_module_for_tools(self, module):
        """Scan a module for functions decorated with @tool"""
        for name in dir(module):
            obj = getattr(module, name)
            if callable(obj) and hasattr(obj, '_mcp_tool_metadata'):
                # This is a tool, register it using the registry decorator
                self.tool()(obj)
                logger.info(f"Auto-discovered tool: {obj._mcp_tool_metadata['name']}")
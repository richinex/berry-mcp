# packages/mcp-server/src/mcp_server/core/schema.py
from typing import Dict, Any, Optional, List, get_type_hints, Union, Type
import inspect
from enum import Enum
from docstring_parser import parse as parse_docstring
from pydantic import BaseModel, create_model, Field
import logging # Optional: for logging skipped defaults

# --- ADD THIS IMPORT ---
# Import Depends from where it's defined in your project or FastAPI directly
try:
    # Standard location in newer FastAPI
    from fastapi.params import Depends
except ImportError:
    try:
        # Older location or direct import
        from fastapi import Depends
    except ImportError:
        # If FastAPI isn't installed or Depends isn't used, create a dummy class
        # so the 'isinstance' check doesn't fail, but this means the check won't work.
        # A better approach might be conditional import or making fastapi a dependency.
        logging.warning("FastAPI 'Depends' not found. Schema generation might include non-serializable defaults.")
        class Depends: pass
# --- END IMPORT ---

logger = logging.getLogger(__name__) # Optional logging

class SchemaType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"

class SchemaGenerator:
    """Handles automatic schema generation from Python functions"""

    TYPE_MAP = {
        str: {"type": SchemaType.STRING},
        int: {"type": SchemaType.INTEGER},
        float: {"type": SchemaType.NUMBER},
        bool: {"type": SchemaType.BOOLEAN},
        list: {"type": SchemaType.ARRAY},
        dict: {"type": SchemaType.OBJECT},
    }

    @classmethod
    def parse_function(cls, func: callable) -> Dict[str, Any]:
        """Generate a complete function schema from a Python function"""
        sig = inspect.signature(func)
        doc = parse_docstring(func.__doc__ or "")
        # Use eval_str=True for forward references if needed, handle errors
        try:
            type_hints = get_type_hints(func, include_extras=True) # include_extras might be useful
        except NameError as e:
            logger.warning(f"Could not evaluate type hints for {func.__name__}: {e}. Using basic inspection.")
            type_hints = {} # Fallback or handle differently

        parameters = {}
        required = []

        for name, param in sig.parameters.items():
            # --- MODIFICATION: Check for Depends before processing type hint ---
            # If the default value is Depends, treat the parameter differently.
            # We often don't want these exposed as regular tool parameters.
            # Alternatively, check the type annotation as well.
            is_dependency = isinstance(param.default, Depends)
            # You might also want to check if the type annotation itself is Depends, though less common
            # is_dependency = is_dependency or param.annotation is Depends

            if is_dependency:
                logger.debug(f"Skipping FastAPI dependency parameter '{name}' in schema generation for tool '{func.__name__}'.")
                continue # Skip this parameter entirely from the schema
            # --- END MODIFICATION ---


            param_type = type_hints.get(name, Any) # Use Any if hint missing
             # Handle cases where type hint evaluation failed but param has annotation
            if param_type is Any and param.annotation is not inspect.Parameter.empty:
                 param_type = param.annotation # Use raw annotation

            param_doc = next((p.description for p in doc.params if p.arg_name == name), "")

            param_schema = cls._create_parameter_schema(
                name=name,
                param_type=param_type,
                description=param_doc,
                default=param.default if param.default is not inspect.Parameter.empty else None
            )

            parameters[name] = param_schema
            if param.default is inspect.Parameter.empty:
                required.append(name)

        # Determine return type schema, handle potential errors
        return_type = Any # Default
        if 'return' in type_hints:
            return_type = type_hints['return']
        elif sig.return_annotation is not inspect.Signature.empty:
            return_type = sig.return_annotation

        return {
            "name": func.__name__,
            "description": doc.short_description or f"Executes the {func.__name__} tool.", # Add default description
            "parameters": {
                "type": SchemaType.OBJECT.value, # Use .value for Enum
                "properties": parameters,
                "required": required
            },
            # Optional: Add return schema if needed by your spec/LLM
            # "returns": cls._get_type_schema(return_type)
        }

    @classmethod
    def _create_parameter_schema(
        cls,
        name: str,
        param_type: Type,
        description: str = "",
        default: Any = None # Default is None if not provided or empty
    ) -> Dict[str, Any]:
        """Create schema for a single parameter"""
        schema = cls._get_type_schema(param_type)
        if description: # Only add description if not empty
             schema["description"] = description

        # --- FIX: Check default value before adding ---
        # Check if default is not None AND it's not a Depends object
        if default is not None and not isinstance(default, Depends):
            # Add default only if it's serializable (basic check, might need refinement)
            try:
                # Attempt a quick JSON check - might be too slow if defaults are complex
                # json.dumps(default) # Removed this check for performance, rely on caller
                schema["default"] = default
            except TypeError:
                 logger.warning(f"Default value for parameter '{name}' is not JSON serializable. Omitting default from schema.")
        # --- END FIX ---

        return schema

    @classmethod
    def _get_type_schema(cls, type_hint: Any) -> Dict[str, Any]:
        """Convert Python type hints to JSON schema types"""
        if type_hint is Any or type_hint is inspect.Parameter.empty:
             # Represent 'Any' as an object without specific properties, or adjust as needed
             # return {"description": "Any type is allowed."}
             # Or default to string if Any isn't well-supported
             return {"type": SchemaType.STRING.value, "description": "Type hint was 'Any' or missing."}

        origin = getattr(type_hint, "__origin__", None)
        args = getattr(type_hint, "__args__", ())

        # Direct type mapping
        if not origin and type_hint in cls.TYPE_MAP:
            # Return a copy and use .value for Enum
            return {k: v.value if isinstance(v, Enum) else v for k, v in cls.TYPE_MAP[type_hint].items()}

        # Handle generics
        if origin:
            if origin is Union: # Handles Optional[T] which is Union[T, NoneType]
                # Filter out NoneType for schema generation
                non_none_args = [arg for arg in args if arg is not type(None)]
                if len(non_none_args) == 1:
                    # If it was Optional[T], just use schema for T
                    schema = cls._get_type_schema(non_none_args[0])
                    # Optional: Add nullable=True or similar if your schema standard supports it
                    return schema
                else:
                    # For Union[A, B, ...], use anyOf
                    return {"anyOf": [cls._get_type_schema(arg) for arg in non_none_args]}
            elif origin is list or origin is List:
                 item_type = args[0] if args else Any
                 return {
                     "type": SchemaType.ARRAY.value,
                     "items": cls._get_type_schema(item_type)
                 }
            elif origin is dict or origin is Dict:
                # JSON schema usually assumes string keys
                # key_type = args[0] if args else Any
                value_type = args[1] if len(args) > 1 else Any
                return {
                    "type": SchemaType.OBJECT.value,
                    "additionalProperties": cls._get_type_schema(value_type)
                }
            # Add handling for other generics like Tuple, Set if needed

        # Handle specific classes (Enum, Pydantic)
        if isinstance(type_hint, type):
            if issubclass(type_hint, Enum):
                return cls._handle_enum_type(type_hint)
            if issubclass(type_hint, BaseModel):
                # Use Pydantic's built-in schema generation for robustness
                try:
                    # model_json_schema handles references, defaults, etc. better
                    pydantic_schema = type_hint.model_json_schema()
                    # Remove auxiliary fields often added by Pydantic if not needed
                    pydantic_schema.pop('title', None)
                    pydantic_schema.pop('$defs', None) # Or handle definitions properly
                    return pydantic_schema
                except Exception as e:
                     logger.error(f"Failed to generate Pydantic schema for {type_hint.__name__}: {e}")
                     # Fallback schema
                     return {"type": SchemaType.OBJECT.value, "description": f"Pydantic model {type_hint.__name__}"}


        # Fallback for unknown types
        logger.warning(f"Could not map type hint '{type_hint}' to JSON schema. Defaulting to string.")
        return {"type": SchemaType.STRING.value} # Default to string for unknown types


    # Keep _handle_enum_type, _handle_pydantic_type as they were, or integrate Pydantic schema gen above
    @classmethod
    def _handle_enum_type(cls, enum_class: Type[Enum]) -> Dict[str, Any]:
        """Handle Enum types"""
        # Assuming enum values are strings, adjust if they can be other types
        return {
            "type": SchemaType.STRING.value,
            "enum": [e.value for e in enum_class]
        }

    # This custom pydantic handler might be redundant if using model_json_schema() above
    # @classmethod
    # def _handle_pydantic_type(cls, model_class: Type[BaseModel]) -> Dict[str, Any]:
    #     """Handle Pydantic model types"""
    #     return {
    #         "type": SchemaType.OBJECT.value,
    #         "properties": {
    #             field_name: cls._get_type_schema(field.annotation)
    #             for field_name, field in model_class.model_fields.items()
    #         },
    #         "required": [
    #             field_name
    #             for field_name, field in model_class.model_fields.items()
    #             if field.is_required()
    #         ]
    #     }
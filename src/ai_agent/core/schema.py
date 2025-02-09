# src/ai_agent/core/schema.py
from typing import Dict, Any, Optional, List, get_type_hints, Union, Type
import inspect
from enum import Enum
from docstring_parser import parse as parse_docstring
from pydantic import BaseModel, create_model, Field

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
        type_hints = get_type_hints(func)

        parameters = {}
        required = []

        for name, param in sig.parameters.items():
            param_type = type_hints.get(name, str)
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

        return {
            "name": func.__name__,
            "description": doc.short_description or "",
            "parameters": {
                "type": SchemaType.OBJECT,
                "properties": parameters,
                "required": required
            },
            "returns": cls._get_type_schema(type_hints.get('return', Any))
        }

    @classmethod
    def _create_parameter_schema(
        cls,
        name: str,
        param_type: Type,
        description: str = "",
        default: Any = None
    ) -> Dict[str, Any]:
        """Create schema for a single parameter"""
        schema = cls._get_type_schema(param_type)
        schema["description"] = description

        if default is not None:
            schema["default"] = default

        return schema

    @classmethod
    def _get_type_schema(cls, type_hint: Any) -> Dict[str, Any]:
        """Convert Python type hints to JSON schema types"""
        if type_hint in cls.TYPE_MAP:
            return cls.TYPE_MAP[type_hint].copy()

        if hasattr(type_hint, "__origin__"):
            if type_hint.__origin__ is Union:
                return cls._handle_union_type(type_hint)
            elif type_hint.__origin__ is list:
                return cls._handle_list_type(type_hint)
            elif type_hint.__origin__ is dict:
                return cls._handle_dict_type(type_hint)

        if isinstance(type_hint, type) and issubclass(type_hint, Enum):
            return cls._handle_enum_type(type_hint)

        if isinstance(type_hint, type) and issubclass(type_hint, BaseModel):
            return cls._handle_pydantic_type(type_hint)

        return {"type": SchemaType.STRING}

    @classmethod
    def _handle_union_type(cls, type_hint: Any) -> Dict[str, Any]:
        """Handle Union types, including Optional"""
        types = [t for t in type_hint.__args__ if t is not type(None)]
        if len(types) == 1:
            return cls._get_type_schema(types[0])
        return {"anyOf": [cls._get_type_schema(t) for t in types]}

    @classmethod
    def _handle_list_type(cls, type_hint: Any) -> Dict[str, Any]:
        """Handle List types"""
        item_type = type_hint.__args__[0]
        return {
            "type": SchemaType.ARRAY,
            "items": cls._get_type_schema(item_type)
        }

    @classmethod
    def _handle_dict_type(cls, type_hint: Any) -> Dict[str, Any]:
        """Handle Dict types"""
        _, value_type = type_hint.__args__
        return {
            "type": SchemaType.OBJECT,
            "additionalProperties": cls._get_type_schema(value_type)
        }

    @classmethod
    def _handle_enum_type(cls, enum_class: Type[Enum]) -> Dict[str, Any]:
        """Handle Enum types"""
        return {
            "type": SchemaType.STRING,
            "enum": [e.value for e in enum_class]
        }

    @classmethod
    def _handle_pydantic_type(cls, model_class: Type[BaseModel]) -> Dict[str, Any]:
        """Handle Pydantic model types"""
        return {
            "type": SchemaType.OBJECT,
            "properties": {
                field_name: cls._get_type_schema(field.annotation)
                for field_name, field in model_class.model_fields.items()
            },
            "required": [
                field_name
                for field_name, field in model_class.model_fields.items()
                if field.is_required()
            ]
        }
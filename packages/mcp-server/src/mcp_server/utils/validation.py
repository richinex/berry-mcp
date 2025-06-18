# validation.py
from typing import Any, Dict
from pydantic import BaseModel, ValidationError

class ToolCallValidator(BaseModel):
    """Validate tool call arguments"""
    name: str
    arguments: Dict[str, Any]

def validate_tool_call(tool_call: Dict[str, Any]) -> bool:
    """Validate a tool call structure"""
    try:
        ToolCallValidator(**tool_call)
        return True
    except ValidationError:
        return False
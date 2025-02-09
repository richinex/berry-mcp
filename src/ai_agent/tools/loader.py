# src/ai_agent/tools/loader.py
from typing import Dict, Any
from ..core.registry import ToolRegistry
from .weather import get_weather
from .calculator import calculate
from .search import search

def load_default_tools(registry: ToolRegistry) -> None:
    """Register all default tools with the registry"""
    registry.tool()(get_weather)
    registry.tool()(calculate)
    registry.tool()(search)
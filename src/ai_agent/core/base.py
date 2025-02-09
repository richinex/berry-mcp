# src/ai_agent/core/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from ..core.registry import ToolRegistry

class Message(BaseModel):
    role: str
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

class AIAgent(ABC):
    """Abstract base class for AI agents"""
    def __init__(self, tools: ToolRegistry):
        self.tools = tools
        self.messages: List[Message] = []

    @abstractmethod
    async def process_message(self, message: str) -> str:
        """Process a message and return a response"""
        pass

    @abstractmethod
    async def handle_tool_call(self, tool_call: Dict[str, Any]) -> Any:
        """Handle a tool call and return the result"""
        pass
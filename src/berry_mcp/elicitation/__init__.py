"""
Elicitation module for Berry MCP Server
Enables human-in-the-loop interactions and enhanced tool capabilities
"""

from .handlers import ConsoleElicitationHandler, ElicitationHandler, SSEElicitationHandler
from .manager import ElicitationManager
from .prompts import (
    ChoicePrompt,
    ConfirmationPrompt,
    ElicitationPrompt,
    InputPrompt,
    PromptBuilder,
    PromptType,
)
from .schemas import CapabilityBuilder, CapabilityMetadata, ToolOutputSchema

__all__ = [
    "ElicitationManager",
    "PromptType",
    "ElicitationPrompt",
    "ConfirmationPrompt",
    "InputPrompt",
    "ChoicePrompt",
    "PromptBuilder",
    "ElicitationHandler",
    "ConsoleElicitationHandler",
    "SSEElicitationHandler",
    "ToolOutputSchema",
    "CapabilityMetadata",
    "CapabilityBuilder",
]

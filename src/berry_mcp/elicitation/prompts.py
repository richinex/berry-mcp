"""
Elicitation prompts for human-in-the-loop interactions
Based on AWS contributions to MCP specification
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union


class PromptType(Enum):
    """Types of elicitation prompts"""

    CONFIRMATION = "confirmation"
    INPUT = "input"
    CHOICE = "choice"
    FILE_SELECTION = "file_selection"
    CUSTOM = "custom"


@dataclass
class ElicitationPrompt(ABC):
    """Base class for elicitation prompts"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt_type: PromptType = PromptType.CUSTOM
    title: str = ""
    message: str = ""
    timeout_seconds: int | None = None
    priority: str = "normal"  # low, normal, high, urgent
    context: dict[str, Any] = field(default_factory=dict)

    @abstractmethod
    def to_mcp_message(self) -> dict[str, Any]:
        """Convert to MCP elicitation message format"""
        pass

    @abstractmethod
    def validate_response(self, response: Any) -> bool:
        """Validate user response"""
        pass

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": self.id,
            "type": self.prompt_type.value,
            "title": self.title,
            "message": self.message,
            "timeout_seconds": self.timeout_seconds,
            "priority": self.priority,
            "context": self.context,
        }


@dataclass
class ConfirmationPrompt(ElicitationPrompt):
    """Prompt for yes/no confirmation"""

    prompt_type: PromptType = PromptType.CONFIRMATION
    default_response: bool = False

    def to_mcp_message(self) -> dict[str, Any]:
        """Convert to MCP elicitation message"""
        return {
            "jsonrpc": "2.0",
            "method": "notifications/elicitation",
            "params": {
                "type": "confirmation",
                "id": self.id,
                "title": self.title,
                "message": self.message,
                "default": self.default_response,
                "timeout": self.timeout_seconds,
                "priority": self.priority,
                "context": self.context,
            },
        }

    def validate_response(self, response: Any) -> bool:
        """Validate boolean response"""
        return isinstance(response, bool)


@dataclass
class InputPrompt(ElicitationPrompt):
    """Prompt for text input"""

    prompt_type: PromptType = PromptType.INPUT
    placeholder: str = ""
    default_value: str = ""
    multiline: bool = False
    max_length: int | None = None
    pattern: str | None = None  # Regex pattern for validation

    def to_mcp_message(self) -> dict[str, Any]:
        """Convert to MCP elicitation message"""
        params = {
            "type": "input",
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "placeholder": self.placeholder,
            "default": self.default_value,
            "multiline": self.multiline,
            "timeout": self.timeout_seconds,
            "priority": self.priority,
            "context": self.context,
        }

        if self.max_length:
            params["max_length"] = self.max_length
        if self.pattern:
            params["pattern"] = self.pattern

        return {
            "jsonrpc": "2.0",
            "method": "notifications/elicitation",
            "params": params,
        }

    def validate_response(self, response: Any) -> bool:
        """Validate string response"""
        if not isinstance(response, str):
            return False

        if self.max_length and len(response) > self.max_length:
            return False

        if self.pattern:
            import re

            return bool(re.match(self.pattern, response))

        return True


@dataclass
class ChoicePrompt(ElicitationPrompt):
    """Prompt for selecting from multiple choices"""

    prompt_type: PromptType = PromptType.CHOICE
    choices: list[dict[str, Any]] = field(default_factory=list)
    allow_multiple: bool = False
    min_selections: int = 0
    max_selections: int | None = None

    def add_choice(self, value: str, label: str, description: str = "") -> None:
        """Add a choice option"""
        self.choices.append(
            {
                "value": value,
                "label": label,
                "description": description,
            }
        )

    def to_mcp_message(self) -> dict[str, Any]:
        """Convert to MCP elicitation message"""
        params = {
            "type": "choice",
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "choices": self.choices,
            "allow_multiple": self.allow_multiple,
            "min_selections": self.min_selections,
            "timeout": self.timeout_seconds,
            "priority": self.priority,
            "context": self.context,
        }

        if self.max_selections:
            params["max_selections"] = self.max_selections

        return {
            "jsonrpc": "2.0",
            "method": "notifications/elicitation",
            "params": params,
        }

    def validate_response(self, response: Any) -> bool:
        """Validate choice response"""
        if self.allow_multiple:
            if not isinstance(response, list):
                return False

            if len(response) < self.min_selections:
                return False

            if self.max_selections and len(response) > self.max_selections:
                return False

            # Check all values are valid choices
            valid_values = {choice["value"] for choice in self.choices}
            return all(value in valid_values for value in response)
        else:
            # Single choice
            if not isinstance(response, str):
                return False

            valid_values = {choice["value"] for choice in self.choices}
            return response in valid_values


@dataclass
class FileSelectionPrompt(ElicitationPrompt):
    """Prompt for file selection"""

    prompt_type: PromptType = PromptType.FILE_SELECTION
    file_types: list[str] = field(default_factory=list)  # e.g., [".txt", ".json"]
    allow_multiple: bool = False
    start_directory: str | None = None

    def to_mcp_message(self) -> dict[str, Any]:
        """Convert to MCP elicitation message"""
        params = {
            "type": "file_selection",
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "file_types": self.file_types,
            "allow_multiple": self.allow_multiple,
            "timeout": self.timeout_seconds,
            "priority": self.priority,
            "context": self.context,
        }

        if self.start_directory:
            params["start_directory"] = self.start_directory

        return {
            "jsonrpc": "2.0",
            "method": "notifications/elicitation",
            "params": params,
        }

    def validate_response(self, response: Any) -> bool:
        """Validate file path response"""
        if self.allow_multiple:
            if not isinstance(response, list):
                return False
            return all(isinstance(path, str) for path in response)
        else:
            return isinstance(response, str)


class PromptBuilder:
    """Builder class for creating elicitation prompts"""

    @staticmethod
    def confirmation(
        title: str, message: str, default: bool = False, timeout: int | None = None
    ) -> ConfirmationPrompt:
        """Create a confirmation prompt"""
        return ConfirmationPrompt(
            title=title,
            message=message,
            default_response=default,
            timeout_seconds=timeout,
        )

    @staticmethod
    def text_input(
        title: str,
        message: str,
        placeholder: str = "",
        default: str = "",
        multiline: bool = False,
        max_length: int | None = None,
        pattern: str | None = None,
        timeout: int | None = None,
    ) -> InputPrompt:
        """Create a text input prompt"""
        return InputPrompt(
            title=title,
            message=message,
            placeholder=placeholder,
            default_value=default,
            multiline=multiline,
            max_length=max_length,
            pattern=pattern,
            timeout_seconds=timeout,
        )

    @staticmethod
    def single_choice(
        title: str,
        message: str,
        choices: list[tuple[str, str]],  # (value, label) pairs
        timeout: int | None = None,
    ) -> ChoicePrompt:
        """Create a single choice prompt"""
        prompt = ChoicePrompt(
            title=title, message=message, allow_multiple=False, timeout_seconds=timeout
        )

        for value, label in choices:
            prompt.add_choice(value, label)

        return prompt

    @staticmethod
    def multiple_choice(
        title: str,
        message: str,
        choices: list[tuple[str, str]],  # (value, label) pairs
        min_selections: int = 0,
        max_selections: int | None = None,
        timeout: int | None = None,
    ) -> ChoicePrompt:
        """Create a multiple choice prompt"""
        prompt = ChoicePrompt(
            title=title,
            message=message,
            allow_multiple=True,
            min_selections=min_selections,
            max_selections=max_selections,
            timeout_seconds=timeout,
        )

        for value, label in choices:
            prompt.add_choice(value, label)

        return prompt

    @staticmethod
    def file_selection(
        title: str,
        message: str,
        file_types: list[str] | None = None,
        allow_multiple: bool = False,
        start_directory: str | None = None,
        timeout: int | None = None,
    ) -> FileSelectionPrompt:
        """Create a file selection prompt"""
        return FileSelectionPrompt(
            title=title,
            message=message,
            file_types=file_types or [],
            allow_multiple=allow_multiple,
            start_directory=start_directory,
            timeout_seconds=timeout,
        )

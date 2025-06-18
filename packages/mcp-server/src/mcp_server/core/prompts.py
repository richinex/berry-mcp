# packages/mcp-server/src/mcp_server/mcp/prompts.py
from typing import Dict, Any, Optional, List

class PromptParameter:
    """Parameter for a prompt template"""
    def __init__(self, name: str, description: str, required: bool = True, default: Optional[str] = None):
        self.name = name
        self.description = description
        self.required = required
        self.default = default

    def to_dict(self) -> Dict[str, Any]:
        """Convert parameter to a dictionary"""
        result = {
            "name": self.name,
            "description": self.description,
            "required": self.required
        }
        if self.default is not None:
            result["default"] = self.default
        return result

class Prompt:
    """Represents a prompt template that can be used by LLMs"""

    def __init__(self, id: str, name: str, description: str, template: str, parameters: List[PromptParameter] = None):
        self.id = id
        self.name = name
        self.description = description
        self.template = template
        self.parameters = parameters or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert prompt to a dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parameters": [param.to_dict() for param in self.parameters]
        }

    def fill(self, parameters: Dict[str, str]) -> str:
        """Fill the prompt template with parameters"""
        filled_template = self.template

        # Check for required parameters
        for param in self.parameters:
            if param.required and param.name not in parameters:
                if param.default is not None:
                    parameters[param.name] = param.default
                else:
                    raise ValueError(f"Required parameter missing: {param.name}")

        # Replace parameters in template
        for name, value in parameters.items():
            placeholder = f"{{{name}}}"
            filled_template = filled_template.replace(placeholder, value)

        return filled_template

class PromptRegistry:
    """Registry for prompt templates"""

    def __init__(self):
        self.prompts: Dict[str, Prompt] = {}

    def register(self, prompt: Prompt):
        """Register a prompt template"""
        self.prompts[prompt.id] = prompt

    def get_prompt(self, prompt_id: str) -> Prompt:
        """Get a prompt by ID"""
        if prompt_id not in self.prompts:
            raise KeyError(f"Prompt not found: {prompt_id}")
        return self.prompts[prompt_id]

    def list_prompts(self) -> List[Prompt]:
        """List all registered prompts"""
        return list(self.prompts.values())
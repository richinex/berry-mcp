"""
Elicitation handlers for processing human-in-the-loop interactions
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from .prompts import ElicitationPrompt, PromptType

logger = logging.getLogger(__name__)


class ElicitationHandler(ABC):
    """Abstract base class for elicitation handlers"""
    
    @abstractmethod
    async def handle_prompt(self, prompt: ElicitationPrompt) -> Any:
        """Handle an elicitation prompt and return the user response"""
        pass
    
    @abstractmethod
    async def handle_timeout(self, prompt: ElicitationPrompt) -> Any:
        """Handle timeout for a prompt"""
        pass
    
    @abstractmethod
    async def handle_error(self, prompt: ElicitationPrompt, error: Exception) -> Any:
        """Handle error during prompt processing"""
        pass


class ConsoleElicitationHandler(ElicitationHandler):
    """Console-based elicitation handler for development/testing"""
    
    def __init__(self, use_input: bool = True) -> None:
        self.use_input = use_input
    
    async def handle_prompt(self, prompt: ElicitationPrompt) -> Any:
        """Handle prompt via console input"""
        print(f"\n🤖 {prompt.title}")
        print(f"📝 {prompt.message}")
        
        if prompt.prompt_type == PromptType.CONFIRMATION:
            return await self._handle_confirmation(prompt)
        elif prompt.prompt_type == PromptType.INPUT:
            return await self._handle_input(prompt)
        elif prompt.prompt_type == PromptType.CHOICE:
            return await self._handle_choice(prompt)
        elif prompt.prompt_type == PromptType.FILE_SELECTION:
            return await self._handle_file_selection(prompt)
        else:
            print(f"⚠️  Unsupported prompt type: {prompt.prompt_type}")
            return None
    
    async def _handle_confirmation(self, prompt: ElicitationPrompt) -> bool:
        """Handle confirmation prompt"""
        from .prompts import ConfirmationPrompt
        
        if not isinstance(prompt, ConfirmationPrompt):
            return False
        
        default_text = "Y/n" if prompt.default_response else "y/N"
        
        while True:
            try:
                if self.use_input:
                    response = input(f"Confirm? ({default_text}): ").strip().lower()
                else:
                    # For testing, return default
                    return prompt.default_response
                
                if not response:
                    return prompt.default_response
                
                if response in ['y', 'yes', 'true', '1']:
                    return True
                elif response in ['n', 'no', 'false', '0']:
                    return False
                else:
                    print("Please enter 'y' for yes or 'n' for no")
                    
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled")
                return False
    
    async def _handle_input(self, prompt: ElicitationPrompt) -> str:
        """Handle input prompt"""
        from .prompts import InputPrompt
        
        if not isinstance(prompt, InputPrompt):
            return ""
        
        placeholder_text = f" ({prompt.placeholder})" if prompt.placeholder else ""
        default_text = f" [default: {prompt.default_value}]" if prompt.default_value else ""
        
        print(f"Enter text{placeholder_text}{default_text}:")
        
        if prompt.multiline:
            print("(Press Ctrl+D or Ctrl+Z to finish)")
            lines = []
            try:
                while True:
                    if self.use_input:
                        line = input()
                        lines.append(line)
                    else:
                        # For testing, return default
                        return prompt.default_value
            except (KeyboardInterrupt, EOFError):
                pass
            response = "\n".join(lines)
        else:
            try:
                if self.use_input:
                    response = input("> ").strip()
                else:
                    # For testing, return default
                    return prompt.default_value
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled")
                return prompt.default_value
        
        if not response and prompt.default_value:
            response = prompt.default_value
        
        # Validate response
        if prompt.validate_response(response):
            return response
        else:
            print("❌ Invalid input. Please try again.")
            return await self._handle_input(prompt)
    
    async def _handle_choice(self, prompt: ElicitationPrompt) -> Any:
        """Handle choice prompt"""
        from .prompts import ChoicePrompt
        
        if not isinstance(prompt, ChoicePrompt):
            return None
        
        print("Available choices:")
        for i, choice in enumerate(prompt.choices, 1):
            description = f" - {choice['description']}" if choice.get('description') else ""
            print(f"  {i}. {choice['label']}{description}")
        
        if prompt.allow_multiple:
            print("Enter choice numbers separated by commas (e.g., 1,3,5):")
        else:
            print("Enter choice number:")
        
        while True:
            try:
                if self.use_input:
                    response = input("> ").strip()
                else:
                    # For testing, return first choice
                    if prompt.choices:
                        return [prompt.choices[0]["value"]] if prompt.allow_multiple else prompt.choices[0]["value"]
                    return [] if prompt.allow_multiple else ""
                
                if not response:
                    continue
                
                try:
                    if prompt.allow_multiple:
                        indices = [int(x.strip()) for x in response.split(',')]
                        selected_values = []
                        for idx in indices:
                            if 1 <= idx <= len(prompt.choices):
                                selected_values.append(prompt.choices[idx - 1]["value"])
                            else:
                                print(f"❌ Invalid choice number: {idx}")
                                break
                        else:
                            if prompt.validate_response(selected_values):
                                return selected_values
                            else:
                                print("❌ Invalid selection. Please check the requirements.")
                    else:
                        idx = int(response)
                        if 1 <= idx <= len(prompt.choices):
                            value = prompt.choices[idx - 1]["value"]
                            if prompt.validate_response(value):
                                return value
                            else:
                                print("❌ Invalid selection.")
                        else:
                            print(f"❌ Invalid choice number. Please enter 1-{len(prompt.choices)}")
                
                except ValueError:
                    print("❌ Please enter valid numbers")
                    
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled")
                return [] if prompt.allow_multiple else ""
    
    async def _handle_file_selection(self, prompt: ElicitationPrompt) -> Any:
        """Handle file selection prompt"""
        from .prompts import FileSelectionPrompt
        
        if not isinstance(prompt, FileSelectionPrompt):
            return ""
        
        file_types_text = f" ({', '.join(prompt.file_types)})" if prompt.file_types else ""
        print(f"Enter file path{file_types_text}:")
        
        if prompt.start_directory:
            print(f"Starting directory: {prompt.start_directory}")
        
        if prompt.allow_multiple:
            print("Enter multiple paths separated by commas:")
        
        while True:
            try:
                if self.use_input:
                    response = input("> ").strip()
                else:
                    # For testing, return empty
                    return [] if prompt.allow_multiple else ""
                
                if not response:
                    continue
                
                if prompt.allow_multiple:
                    paths = [path.strip() for path in response.split(',')]
                    if prompt.validate_response(paths):
                        return paths
                    else:
                        print("❌ Invalid file paths")
                else:
                    if prompt.validate_response(response):
                        return response
                    else:
                        print("❌ Invalid file path")
                        
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled")
                return [] if prompt.allow_multiple else ""
    
    async def handle_timeout(self, prompt: ElicitationPrompt) -> Any:
        """Handle timeout"""
        print(f"⏰ Prompt '{prompt.title}' timed out")
        
        # Return appropriate default based on prompt type
        if prompt.prompt_type == PromptType.CONFIRMATION:
            from .prompts import ConfirmationPrompt
            if isinstance(prompt, ConfirmationPrompt):
                return prompt.default_response
            return False
        elif prompt.prompt_type == PromptType.INPUT:
            from .prompts import InputPrompt
            if isinstance(prompt, InputPrompt):
                return prompt.default_value
            return ""
        elif prompt.prompt_type == PromptType.CHOICE:
            from .prompts import ChoicePrompt
            if isinstance(prompt, ChoicePrompt):
                return [] if prompt.allow_multiple else ""
            return ""
        elif prompt.prompt_type == PromptType.FILE_SELECTION:
            from .prompts import FileSelectionPrompt
            if isinstance(prompt, FileSelectionPrompt):
                return [] if prompt.allow_multiple else ""
            return ""
        
        return None
    
    async def handle_error(self, prompt: ElicitationPrompt, error: Exception) -> Any:
        """Handle error"""
        print(f"❌ Error handling prompt '{prompt.title}': {error}")
        logger.error(f"Elicitation error: {error}", exc_info=True)
        
        # Return safe defaults
        return await self.handle_timeout(prompt)


class SSEElicitationHandler(ElicitationHandler):
    """SSE-based elicitation handler for web clients"""
    
    def __init__(self, transport_manager: Any) -> None:
        self.transport_manager = transport_manager
        self._pending_prompts: dict[str, asyncio.Future] = {}
    
    async def handle_prompt(self, prompt: ElicitationPrompt) -> Any:
        """Send prompt via SSE and wait for response"""
        # Create future to wait for response
        future: asyncio.Future = asyncio.Future()
        self._pending_prompts[prompt.id] = future
        
        try:
            # Send elicitation message via transport
            message = prompt.to_mcp_message()
            await self.transport_manager.send_notification(message)
            
            # Wait for response with timeout
            if prompt.timeout_seconds:
                response = await asyncio.wait_for(future, timeout=prompt.timeout_seconds)
            else:
                response = await future
            
            # Validate response
            if prompt.validate_response(response):
                return response
            else:
                raise ValueError(f"Invalid response: {response}")
                
        except asyncio.TimeoutError:
            return await self.handle_timeout(prompt)
        except Exception as e:
            return await self.handle_error(prompt, e)
        finally:
            # Clean up
            self._pending_prompts.pop(prompt.id, None)
    
    async def handle_response(self, prompt_id: str, response: Any) -> None:
        """Handle response from client"""
        future = self._pending_prompts.get(prompt_id)
        if future and not future.done():
            future.set_result(response)
    
    async def handle_timeout(self, prompt: ElicitationPrompt) -> Any:
        """Handle timeout"""
        logger.warning(f"Elicitation prompt '{prompt.title}' timed out")
        
        # Send timeout notification
        timeout_message = {
            "jsonrpc": "2.0",
            "method": "notifications/elicitation/timeout",
            "params": {
                "id": prompt.id,
                "title": prompt.title
            }
        }
        await self.transport_manager.send_notification(timeout_message)
        
        return None
    
    async def handle_error(self, prompt: ElicitationPrompt, error: Exception) -> Any:
        """Handle error"""
        logger.error(f"Elicitation error for '{prompt.title}': {error}")
        
        # Send error notification
        error_message = {
            "jsonrpc": "2.0",
            "method": "notifications/elicitation/error",
            "params": {
                "id": prompt.id,
                "title": prompt.title,
                "error": str(error)
            }
        }
        await self.transport_manager.send_notification(error_message)
        
        return None
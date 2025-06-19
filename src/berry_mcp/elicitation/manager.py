"""
Elicitation manager for coordinating human-in-the-loop interactions
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from .handlers import (
    ConsoleElicitationHandler,
    ElicitationHandler,
    SSEElicitationHandler,
)
from .prompts import ElicitationPrompt, PromptBuilder
from .schemas import CapabilityMetadata, ToolOutputSchema

logger = logging.getLogger(__name__)


class ElicitationManager:
    """Manages elicitation prompts and human-in-the-loop interactions"""

    def __init__(
        self,
        handler: ElicitationHandler | None = None,
        default_timeout: int = 300,  # 5 minutes
    ) -> None:
        self.handler = handler or ConsoleElicitationHandler()
        self.default_timeout = default_timeout
        self._active_prompts: dict[str, ElicitationPrompt] = {}
        self._capabilities: dict[str, CapabilityMetadata] = {}

    def set_handler(self, handler: ElicitationHandler) -> None:
        """Set the elicitation handler"""
        self.handler = handler
        logger.info(f"Elicitation handler set to {type(handler).__name__}")

    async def prompt_confirmation(
        self,
        title: str,
        message: str,
        default: bool = False,
        timeout: int | None = None,
    ) -> bool:
        """Prompt user for confirmation"""
        prompt = PromptBuilder.confirmation(
            title=title,
            message=message,
            default=default,
            timeout=timeout or self.default_timeout,
        )

        result = await self._execute_prompt(prompt)
        return bool(result) if result is not None else False

    async def prompt_input(
        self,
        title: str,
        message: str,
        placeholder: str = "",
        default: str = "",
        multiline: bool = False,
        max_length: int | None = None,
        pattern: str | None = None,
        timeout: int | None = None,
    ) -> str:
        """Prompt user for text input"""
        prompt = PromptBuilder.text_input(
            title=title,
            message=message,
            placeholder=placeholder,
            default=default,
            multiline=multiline,
            max_length=max_length,
            pattern=pattern,
            timeout=timeout or self.default_timeout,
        )

        result = await self._execute_prompt(prompt)
        return str(result) if result is not None else ""

    async def prompt_choice(
        self,
        title: str,
        message: str,
        choices: list[tuple[str, str]],  # (value, label) pairs
        allow_multiple: bool = False,
        min_selections: int = 0,
        max_selections: int | None = None,
        timeout: int | None = None,
    ) -> str | list[str]:
        """Prompt user for choice selection"""
        if allow_multiple:
            prompt = PromptBuilder.multiple_choice(
                title=title,
                message=message,
                choices=choices,
                min_selections=min_selections,
                max_selections=max_selections,
                timeout=timeout or self.default_timeout,
            )
        else:
            prompt = PromptBuilder.single_choice(
                title=title,
                message=message,
                choices=choices,
                timeout=timeout or self.default_timeout,
            )

        result = await self._execute_prompt(prompt)
        if allow_multiple:
            return list(result) if isinstance(result, (list, tuple)) else []
        else:
            return str(result) if result is not None else ""

    async def prompt_file_selection(
        self,
        title: str,
        message: str,
        file_types: list[str] | None = None,
        allow_multiple: bool = False,
        start_directory: str | None = None,
        timeout: int | None = None,
    ) -> str | list[str]:
        """Prompt user for file selection"""
        prompt = PromptBuilder.file_selection(
            title=title,
            message=message,
            file_types=file_types,
            allow_multiple=allow_multiple,
            start_directory=start_directory,
            timeout=timeout or self.default_timeout,
        )

        result = await self._execute_prompt(prompt)
        if allow_multiple:
            return list(result) if isinstance(result, (list, tuple)) else []
        else:
            return str(result) if result is not None else ""

    async def _execute_prompt(self, prompt: ElicitationPrompt) -> Any:
        """Execute an elicitation prompt"""
        self._active_prompts[prompt.id] = prompt

        try:
            logger.info(f"Executing elicitation prompt: {prompt.title}")
            result = await self.handler.handle_prompt(prompt)
            logger.info(f"Elicitation prompt completed: {prompt.title}")
            return result

        except Exception as e:
            logger.error(f"Elicitation prompt failed: {prompt.title} - {e}")
            return await self.handler.handle_error(prompt, e)
        finally:
            self._active_prompts.pop(prompt.id, None)

    def register_capability(self, capability: CapabilityMetadata) -> None:
        """Register a tool capability"""
        self._capabilities[capability.name] = capability
        logger.info(f"Registered capability: {capability.name}")

    def get_capability(self, name: str) -> CapabilityMetadata | None:
        """Get capability metadata by name"""
        return self._capabilities.get(name)

    def list_capabilities(self) -> list[CapabilityMetadata]:
        """List all registered capabilities"""
        return list(self._capabilities.values())

    def get_capabilities_by_category(self, category: str) -> list[CapabilityMetadata]:
        """Get capabilities by category"""
        return [cap for cap in self._capabilities.values() if cap.category == category]

    def get_capabilities_by_tag(self, tag: str) -> list[CapabilityMetadata]:
        """Get capabilities by tag"""
        return [cap for cap in self._capabilities.values() if tag in cap.tags]

    async def handle_response(self, prompt_id: str, response: Any) -> None:
        """Handle response from external source (e.g., SSE client)"""
        if isinstance(self.handler, SSEElicitationHandler):
            await self.handler.handle_response(prompt_id, response)
        else:
            logger.warning(
                f"Cannot handle response for prompt {prompt_id} - handler doesn't support it"
            )

    def get_active_prompts(self) -> list[ElicitationPrompt]:
        """Get list of active prompts"""
        return list(self._active_prompts.values())

    async def cancel_prompt(self, prompt_id: str) -> bool:
        """Cancel an active prompt"""
        if prompt_id in self._active_prompts:
            prompt = self._active_prompts[prompt_id]
            logger.info(f"Cancelling prompt: {prompt.title}")

            # If using SSE handler, it might have cancellation support
            if hasattr(self.handler, "cancel_prompt"):
                result = await self.handler.cancel_prompt(prompt_id)
                return bool(result) if result is not None else False

            # Otherwise, remove from active prompts
            self._active_prompts.pop(prompt_id, None)
            return True

        return False

    def create_enhanced_tool_info(
        self, tool_func: Callable, capability: CapabilityMetadata
    ) -> dict[str, Any]:
        """Create enhanced tool info with capability metadata"""
        # Get basic tool info (assuming it exists)
        tool_info: dict[str, Any] = {
            "name": capability.name,
            "description": capability.description,
        }

        # Add capability metadata
        tool_info["metadata"] = capability.to_dict()

        # Add output schema if available
        if capability.output_schema:
            tool_info["output_schema"] = capability.output_schema.to_json_schema()

        return tool_info


class StreamingResultManager:
    """Manager for streaming partial results from long-running operations"""

    def __init__(self, transport_manager: Any) -> None:
        self.transport_manager = transport_manager
        self._active_streams: dict[str, dict[str, Any]] = {}

    async def start_stream(
        self, operation_id: str, tool_name: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Start a streaming operation"""
        self._active_streams[operation_id] = {
            "tool_name": tool_name,
            "metadata": metadata or {},
            "start_time": asyncio.get_event_loop().time(),
            "chunks_sent": 0,
        }

        # Send stream start notification
        message = {
            "jsonrpc": "2.0",
            "method": "notifications/streaming/start",
            "params": {
                "operation_id": operation_id,
                "tool_name": tool_name,
                "metadata": metadata or {},
            },
        }

        await self.transport_manager.send_notification(message)
        logger.info(f"Started streaming operation: {operation_id}")

    async def send_chunk(
        self,
        operation_id: str,
        chunk_data: Any,
        chunk_type: str = "data",
        sequence: int | None = None,
    ) -> None:
        """Send a chunk of streaming data"""
        if operation_id not in self._active_streams:
            logger.warning(f"Streaming operation not found: {operation_id}")
            return

        stream_info = self._active_streams[operation_id]
        stream_info["chunks_sent"] += 1

        # Use sequence number or auto-increment
        if sequence is None:
            sequence = stream_info["chunks_sent"]

        message = {
            "jsonrpc": "2.0",
            "method": "notifications/streaming/chunk",
            "params": {
                "operation_id": operation_id,
                "sequence": sequence,
                "type": chunk_type,
                "data": chunk_data,
                "timestamp": asyncio.get_event_loop().time(),
            },
        }

        await self.transport_manager.send_notification(message)
        logger.debug(f"Sent streaming chunk {sequence} for operation: {operation_id}")

    async def complete_stream(
        self, operation_id: str, final_result: Any = None, error: str | None = None
    ) -> None:
        """Complete a streaming operation"""
        if operation_id not in self._active_streams:
            logger.warning(f"Streaming operation not found: {operation_id}")
            return

        stream_info = self._active_streams.pop(operation_id)
        end_time = asyncio.get_event_loop().time()
        duration = end_time - stream_info["start_time"]

        message = {
            "jsonrpc": "2.0",
            "method": "notifications/streaming/complete",
            "params": {
                "operation_id": operation_id,
                "final_result": final_result,
                "error": error,
                "duration": duration,
                "total_chunks": stream_info["chunks_sent"],
            },
        }

        await self.transport_manager.send_notification(message)

        if error:
            logger.error(f"Streaming operation failed: {operation_id} - {error}")
        else:
            logger.info(
                f"Completed streaming operation: {operation_id} ({duration:.2f}s, {stream_info['chunks_sent']} chunks)"
            )

    def get_active_streams(self) -> list[str]:
        """Get list of active stream operation IDs"""
        return list(self._active_streams.keys())

    async def cancel_stream(self, operation_id: str) -> bool:
        """Cancel a streaming operation"""
        if operation_id in self._active_streams:
            await self.complete_stream(operation_id, error="Operation cancelled")
            return True
        return False

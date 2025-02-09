# src/ai_agent/agents/deepseek.py
# src/ai_agent/agents/deepseek.py
import json
from typing import Dict, Any, List
from openai import AsyncOpenAI
from ..core.base import AIAgent, Message
from ..core.registry import ToolRegistry
from ..utils.logging import get_logger

logger = get_logger(__name__)

class DeepseekAgent(AIAgent):
    """Concrete implementation for Deepseek AI"""
    def __init__(
        self,
        api_key: str,
        tools: ToolRegistry,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com"
    ):
        super().__init__(tools)
        self.api_key = api_key
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        logger.info(f"Initialized DeepseekAgent with model {model}")

    # async def process_message(self, message: str) -> str:
    #     """Process a user message and handle any tool calls"""
    #     try:
    #         # Add user message to history
    #         self.messages.append(Message(role="user", content=message))
    #         logger.debug(f"Processing message: {message}")

    #         # Get initial response
    #         response = await self._get_completion()
    #         assistant_message = response.choices[0].message
    #         logger.debug(f"Received assistant message: {assistant_message}")

    #         message_dict = {
    #             "role": assistant_message.role,
    #             "content": assistant_message.content or "Let me check that for you."
    #         }

    #         if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
    #             tool_calls = []
    #             for tc in assistant_message.tool_calls:
    #                 tool_call = {
    #                     "id": tc.id,
    #                     "type": tc.type,
    #                     "function": {
    #                         "name": tc.function.name,
    #                         "arguments": tc.function.arguments
    #                     }
    #                 }
    #                 tool_calls.append(tool_call)
    #                 logger.debug(f"Added tool call: {tool_call}")
    #             message_dict["tool_calls"] = tool_calls

    #         self.messages.append(Message(**message_dict))

    #         if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
    #             results = await self._process_tool_calls(assistant_message.tool_calls)
    #             logger.debug(f"Tool call results: {results}")

    #             # Add system message to guide the response
    #             self.messages.append(Message(
    #                 role="system",
    #                 content="Please provide a natural language response describing the results of the tool calls."
    #             ))

    #             final_response = await self._get_completion()
    #             final_message = final_response.choices[0].message
    #             logger.debug(f"Final message: {final_message}")

    #             return final_message.content or f"Based on the data: {json.dumps(results[0], indent=2)}"

    #         return message_dict["content"]

    #     except Exception as e:
    #         logger.error(f"Error processing message: {str(e)}", exc_info=True)
    #         raise


    async def process_message(self, message: str) -> str:
        """Process a user message and handle any tool calls"""
        try:
            self.messages.append(Message(role="user", content=message))
            logger.debug(f"Processing message: {message}")

            # Add initial system guidance for complex queries
            self.messages.append(Message(
                role="system",
                content="You can use multiple tools to answer complex queries. Break down the request and use appropriate tools in sequence."
            ))

            response = await self._get_completion()
            assistant_message = response.choices[0].message
            logger.debug(f"Received assistant message: {assistant_message}")

            message_dict = {
                "role": assistant_message.role,
                "content": assistant_message.content or "Let me process that request for you."
            }

            # Process tool calls and collect all results
            all_results = []
            if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                tool_calls = []
                for tc in assistant_message.tool_calls:
                    tool_call = {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    tool_calls.append(tool_call)
                    logger.debug(f"Added tool call: {tool_call}")
                message_dict["tool_calls"] = tool_calls

                self.messages.append(Message(**message_dict))
                results = await self._process_tool_calls(assistant_message.tool_calls)
                all_results.extend(results)
                logger.debug(f"All tool results: {all_results}")

                # Guide final response formatting
                self.messages.append(Message(
                    role="system",
                    content="""Please provide a comprehensive response that:
                    1. Integrates all tool results clearly
                    2. Presents numerical data first if present
                    3. Follows with any search or informational results
                    4. Makes logical connections between different pieces of information"""
                ))

                final_response = await self._get_completion()
                final_message = final_response.choices[0].message
                logger.debug(f"Final message: {final_message}")

                return final_message.content or f"Results:\n" + "\n".join(
                    [f"- {json.dumps(result, indent=2)}" for result in all_results]
                )

            return message_dict["content"]

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            raise

    async def _get_completion(self) -> Any:
        """Get a completion from the model"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[m.dict(exclude_none=True) for m in self.messages],
                tools=self.tools.tools
            )
            logger.debug(f"Completion response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error getting completion: {str(e)}", exc_info=True)
            raise

    async def _process_tool_calls(self, tool_calls: List[Any]) -> List[Any]:
        """Process a list of tool calls and add results to message history"""
        results = []
        for tool_call in tool_calls:
            try:
                result = await self.handle_tool_call(tool_call)
                results.append(result)
                self.messages.append(Message(
                    role="tool",
                    tool_call_id=tool_call.id,
                    content=json.dumps(result)
                ))
                logger.debug(f"Tool call successful: {tool_call.function.name} -> {result}")
            except Exception as e:
                logger.error(f"Tool call failed: {str(e)}", exc_info=True)
                raise
        return results

    async def handle_tool_call(self, tool_call: Any) -> Any:
        """Execute a tool call and return the result"""
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)

        logger.debug(f"Executing tool: {function_name} with args: {function_args}")
        tool = self.tools.get_tool(function_name)
        return await tool(**function_args)
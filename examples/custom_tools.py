from ai_agent.core.registry import ToolRegistry
from ai_agent.core.agent import DeepseekAgent
import asyncio

# Create custom tools
tools = ToolRegistry()

@tools.tool()
async def custom_greeting(
    name: str,
    language: str = "English"
) -> str:
    """Generate a custom greeting.

    Args:
        name: Name of the person to greet
        language: Language for the greeting
    """
    greetings = {
        "English": f"Hello, {name}!",
        "Spanish": f"¡Hola, {name}!",
        "French": f"Bonjour, {name}!"
    }
    return greetings.get(language, greetings["English"])

async def main():
    agent = DeepseekAgent(api_key="your-api-key", tools=tools)
    response = await agent.process_message("Generate a greeting for Alice in Spanish")
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
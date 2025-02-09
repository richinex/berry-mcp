# src/ai_agent/cli/commands.py
from typing import Optional
import asyncio
import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.logging import RichHandler
from pathlib import Path

from ..agents import DeepseekAgent
from ..core.registry import ToolRegistry
from ..utils.logging import setup_logging
from ..tools import load_default_tools

console = Console()

def create_agent(api_key: str) -> DeepseekAgent:
    """Create and configure the AI agent"""
    tools = ToolRegistry()
    load_default_tools(tools)
    return DeepseekAgent(api_key=api_key, tools=tools)

def register_commands(app: typer.Typer):
    """Register all CLI commands"""

    @app.command()
    def chat(
        message: Optional[str] = typer.Argument(None, help="Message to send to the AI agent"),
        api_key: str = typer.Option(None, "--api-key", "-k", envvar="AI_API_KEY", help="API key for the AI service"),
        interactive: bool = typer.Option(False, "--interactive", "-i", help="Start an interactive chat session"),
    ):
        """Chat with the AI agent"""
        setup_logging()

        if not api_key:
            console.print("[red]Error: API key not provided. Set AI_API_KEY environment variable or use --api-key[/red]")
            raise typer.Exit(1)

        if not message and not interactive:
            console.print("[red]Error: Provide a message or use --interactive mode[/red]")
            raise typer.Exit(1)

        agent = create_agent(api_key)

        if interactive:
            _run_interactive_mode(agent)
        else:
            _run_single_message(agent, message)

    @app.command()
    def tools():
        """List available tools"""
        tools = ToolRegistry()
        load_default_tools(tools)
        _display_tools(tools)

def _run_interactive_mode(agent: DeepseekAgent):
    """Run the interactive chat mode"""
    console.print("[bold blue]Starting interactive chat session (type 'exit' to quit)[/bold blue]")

    while True:
        message = Prompt.ask("\n[bold green]You")
        if message.lower() == 'exit':
            break

        with console.status("[bold yellow]AI is thinking..."):
            try:
                response = asyncio.run(agent.process_message(message))
                console.print(f"\n[bold blue]AI:[/bold blue] {response}")
            except Exception as e:
                console.print(f"\n[bold red]Error:[/bold red] {str(e)}")

def _run_single_message(agent: DeepseekAgent, message: str):
    """Process a single message"""
    with console.status("[bold yellow]AI is thinking..."):
        try:
            response = asyncio.run(agent.process_message(message))
            console.print(f"\n[bold blue]AI:[/bold blue] {response}")
        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {str(e)}")

def _display_tools(tools: ToolRegistry):
    """Display available tools and their schemas"""
    console.print("\n[bold]Available Tools:[/bold]")

    for name, schema in tools._schemas.items():
        console.print(f"\n[bold blue]{name}[/bold blue]")
        console.print(f"Description: {schema['description']}")
        console.print("Parameters:")

        for param_name, param in schema['parameters']['properties'].items():
            required = param_name in schema['parameters'].get('required', [])
            required_str = '[red](required)[/red]' if required else '[green](optional)[/green]'
            console.print(f"  - {param_name}: {param['description']} {required_str}")
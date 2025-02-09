# src/ai_agent/cli/app.py
import typer
from rich.console import Console
from .commands import register_commands

app = typer.Typer(help="AI Agent CLI")
console = Console()

# Register all commands
register_commands(app)

def run():
    """Entry point for the CLI"""
    app()
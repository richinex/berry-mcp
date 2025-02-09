from rich.table import Table
from rich.console import Console
from typing import Dict, Any

console = Console()

def create_tool_table(tools: Dict[str, Any]) -> Table:
    """Create a rich table for displaying tools"""
    table = Table(show_header=True)
    table.add_column("Tool Name", style="bold blue")
    table.add_column("Description")
    table.add_column("Parameters", style="dim")

    for name, schema in tools.items():
        params = ", ".join(schema['parameters']['properties'].keys())
        table.add_row(name, schema['description'], params)

    return table

def format_error(error: Exception) -> str:
    """Format error messages for display"""
    return f"[bold red]Error:[/bold red] {str(error)}"
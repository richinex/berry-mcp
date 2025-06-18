"""
Entry point for running Berry MCP Server as a module
Enables running with: python -m berry_mcp
"""

from .server import cli_main

if __name__ == "__main__":
    cli_main()
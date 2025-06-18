# VS Code Configuration for Berry MCP Server

This guide shows how to configure Berry MCP Server for use with VS Code and Claude.

## Basic Configuration

Add this configuration to your VS Code `settings.json`:

```json
{
  "mcp": {
    "mcpServers": {
      "berry-mcp": {
        "type": "stdio",
        "command": "python",
        "args": ["-m", "berry_mcp"],
        "cwd": "/home/richard/Documents/python_projects/berry-mcp"
      }
    }
  }
}
```

## Advanced Configuration with Custom Tools

To use Berry MCP with your own tools:

```json
{
  "mcp": {
    "mcpServers": {
      "my-custom-server": {
        "type": "stdio", 
        "command": "python",
        "args": ["-m", "berry_mcp", "--server-name", "my-custom-server"],
        "env": {
          "BERRY_MCP_TOOLS_PATH": "my_tools,another_module.tools",
          "BERRY_MCP_LOG_LEVEL": "DEBUG"
        },
        "cwd": "/path/to/your/project"
      }
    }
  }
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BERRY_MCP_SERVER_NAME` | Server identifier | `"berry-mcp-server"` |
| `BERRY_MCP_LOG_LEVEL` | Logging level | `"INFO"` |
| `BERRY_MCP_TOOLS_PATH` | Comma-separated tool module paths | Uses built-in tools |
| `BERRY_MCP_TRANSPORT` | Transport type | `"stdio"` |
| `BERRY_MCP_HOST` | HTTP host (if using http transport) | `"localhost"` |
| `BERRY_MCP_PORT` | HTTP port (if using http transport) | `8000` |

## Example Configurations

### PDF Processing Server
```json
{
  "mcp": {
    "mcpServers": {
      "pdf-processor": {
        "type": "stdio",
        "command": "python", 
        "args": ["-m", "berry_mcp"],
        "env": {
          "BERRY_MCP_TOOLS_PATH": "berry_mcp.tools.pdf_tools",
          "BERRY_MCP_SERVER_NAME": "pdf-processor"
        }
      }
    }
  }
}
```

### Web Scraping Server
```json
{
  "mcp": {
    "mcpServers": {
      "web-scraper": {
        "type": "stdio",
        "command": "python",
        "args": ["-m", "berry_mcp"],
        "env": {
          "BERRY_MCP_TOOLS_PATH": "my_web_tools",
          "BERRY_MCP_SERVER_NAME": "web-scraper"
        }
      }
    }
  }
}
```

### Multiple Tool Sources
```json
{
  "mcp": {
    "mcpServers": {
      "multi-tool-server": {
        "type": "stdio",
        "command": "python",
        "args": ["-m", "berry_mcp"],
        "env": {
          "BERRY_MCP_TOOLS_PATH": "my_tools,web_tools,data_tools.processors",
          "BERRY_MCP_SERVER_NAME": "multi-tool-server",
          "BERRY_MCP_LOG_LEVEL": "DEBUG"
        }
      }
    }
  }
}
```

## Troubleshooting

### Server Not Starting
1. Check that Berry MCP is installed: `python -c "import berry_mcp"`
2. Test the command manually: `python -m berry_mcp --help`
3. Check the logs in VS Code's Output panel

### Tools Not Loading
1. Verify your tool modules are importable: `python -c "import your_tool_module"`
2. Check that tools are decorated with `@tool`
3. Enable debug logging: `"BERRY_MCP_LOG_LEVEL": "DEBUG"`

### Permission Issues
Make sure the working directory and Python environment are accessible to VS Code.

## Creating Custom Tools

See the [Tool Development Guide](TOOL_DEVELOPMENT.md) for creating your own tools.
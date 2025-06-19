"""
Custom tools for testing Berry MCP Server auto-discovery
"""
from berry_mcp.tools.decorators import tool
import datetime
import os
import json


@tool(description="Add two numbers together")
def add_numbers(a: float, b: float) -> float:
    """Add two numbers and return the result"""
    return a + b


@tool(description="Generate a greeting message")  
def greet(name: str, title: str = "friend") -> str:
    """Generate a personalized greeting"""
    return f"Hello {title} {name}!"


@tool(description="Get current date and time information")
def get_current_datetime() -> dict:
    """Get the current date and time with detailed information"""
    now = datetime.datetime.now()
    return {
        "current_time": now.isoformat(),
        "timestamp": now.timestamp(),
        "day_of_week": now.strftime("%A"),
        "month": now.strftime("%B"),
        "year": now.year,
        "formatted": now.strftime("%Y-%m-%d %H:%M:%S")
    }


@tool(description="List files in a directory")
def list_directory(path: str = ".") -> dict:
    """List files and directories in the specified path"""
    try:
        items = []
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            items.append({
                "name": item,
                "is_directory": os.path.isdir(item_path),
                "size": os.path.getsize(item_path) if os.path.isfile(item_path) else None
            })
        
        return {
            "path": path,
            "items": items,
            "total_items": len(items)
        }
    except Exception as e:
        return {"error": str(e)}


@tool(description="Create a simple JSON report")
def create_report(title: str, data: dict) -> str:
    """Create a formatted JSON report with title and data"""
    report = {
        "title": title,
        "created_at": datetime.datetime.now().isoformat(),
        "data": data,
        "summary": {
            "data_keys": list(data.keys()) if isinstance(data, dict) else None,
            "data_type": type(data).__name__
        }
    }
    return json.dumps(report, indent=2)
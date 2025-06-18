# # packages/mcp-server/src/mcp_server/tools/calculator.py
from typing import Union

async def calculate(expression: str) -> Union[int, float]:
    """Calculate the result of a mathematical expression.

    Args:
        expression: Mathematical expression to evaluate
    """
    # Safe evaluation implementation
    try:
        # Add safe evaluation logic here
        result = eval(expression)
        return float(result) if isinstance(result, float) else int(result)
    except Exception as e:
        raise ValueError(f"Invalid expression: {str(e)}")
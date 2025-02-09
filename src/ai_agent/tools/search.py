# src/ai_agent/tools/search.py
from typing import List, Dict

async def search(
    query: str,
    max_results: int = 5
) -> List[Dict[str, str]]:
    """Search for information on a topic.

    Args:
        query: Search query
        max_results: Maximum number of results to return
    """
    # Mock search results for now
    results = [
        {"title": "Result 1", "snippet": "Description 1"},
        {"title": "Result 2", "snippet": "Description 2"},
        {"title": "Result 3", "snippet": "Description 3"},
    ]
    return results[:max_results]
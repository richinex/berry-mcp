# packages/mcp-server/src/mcp_server/mcp/resources.py
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

class Resource:
    """Represents a resource that can be accessed by LLMs"""

    def __init__(self,
                 uri: str,
                 name: str,
                 description: str = "",
                 mime_type: Optional[str] = None):
        self.uri = uri
        self.name = name
        self.description = description
        self.mime_type = mime_type

    def to_dict(self) -> Dict[str, Any]:
        """Convert resource to a dictionary"""
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type
        }

class ResourceProvider(ABC):
    """Base class for resource providers"""

    @abstractmethod
    async def get_content(self, uri: str) -> Dict[str, Any]:
        """Get the content of a resource"""
        pass

    @abstractmethod
    def get_resources(self) -> List[Resource]:
        """Get a list of available resources"""
        pass

class ResourceRegistry:
    """Registry for resources that can be accessed by LLMs"""

    def __init__(self):
        self.providers: List[ResourceProvider] = []

    def add_provider(self, provider: ResourceProvider):
        """Add a resource provider"""
        self.providers.append(provider)

    def get_resources(self) -> List[Resource]:
        """Get a list of all available resources"""
        resources = []
        for provider in self.providers:
            resources.extend(provider.get_resources())
        return resources

    async def get_resource_content(self, uri: str) -> Dict[str, Any]:
        """Get the content of a resource by URI"""
        for provider in self.providers:
            try:
                return await provider.get_content(uri)
            except (ValueError, FileNotFoundError):
                continue

        raise ValueError(f"Resource not found: {uri}")
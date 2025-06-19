"""
Tool output schemas and capability metadata for enhanced MCP integration
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Union


@dataclass
class ToolOutputSchema:
    """Schema definition for tool output"""
    
    type: str = "object"  # JSON Schema type
    properties: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    description: str = ""
    examples: list[Any] = field(default_factory=list)
    
    def add_property(
        self, 
        name: str, 
        prop_type: str, 
        description: str = "",
        required: bool = False,
        enum: Optional[list[Any]] = None,
        format: Optional[str] = None
    ) -> None:
        """Add a property to the schema"""
        prop_def = {
            "type": prop_type,
            "description": description
        }
        
        if enum:
            prop_def["enum"] = enum
        if format:
            prop_def["format"] = format
        
        self.properties[name] = prop_def
        
        if required:
            self.required.append(name)
    
    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format"""
        schema = {
            "type": self.type,
            "properties": self.properties,
            "description": self.description
        }
        
        if self.required:
            schema["required"] = self.required
        
        if self.examples:
            schema["examples"] = self.examples
        
        return schema


@dataclass
class CapabilityMetadata:
    """Metadata for enhanced capability discovery"""
    
    name: str
    description: str
    version: str = "1.0.0"
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    output_schema: Optional[ToolOutputSchema] = None
    supports_streaming: bool = False
    supports_cancellation: bool = False
    requires_authentication: bool = False
    estimated_duration: Optional[str] = None  # "fast", "medium", "slow"
    resource_requirements: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation"""
        result = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "supports_streaming": self.supports_streaming,
            "supports_cancellation": self.supports_cancellation,
            "requires_authentication": self.requires_authentication,
        }
        
        if self.output_schema:
            result["output_schema"] = self.output_schema.to_json_schema()
        
        if self.estimated_duration:
            result["estimated_duration"] = self.estimated_duration
        
        if self.resource_requirements:
            result["resource_requirements"] = self.resource_requirements
        
        return result


class SchemaBuilder:
    """Builder class for creating tool output schemas"""
    
    @staticmethod
    def create_object_schema(description: str = "") -> ToolOutputSchema:
        """Create an object schema"""
        return ToolOutputSchema(type="object", description=description)
    
    @staticmethod
    def create_array_schema(item_type: str, description: str = "") -> ToolOutputSchema:
        """Create an array schema"""
        return ToolOutputSchema(
            type="array",
            description=description,
            properties={"items": {"type": item_type}}
        )
    
    @staticmethod
    def create_string_schema(description: str = "", enum: Optional[list[str]] = None) -> ToolOutputSchema:
        """Create a string schema"""
        schema = ToolOutputSchema(type="string", description=description)
        if enum:
            schema.properties = {"enum": enum}
        return schema
    
    @staticmethod
    def create_file_result_schema() -> ToolOutputSchema:
        """Create schema for file operation results"""
        schema = SchemaBuilder.create_object_schema("File operation result")
        schema.add_property("success", "boolean", "Whether the operation succeeded", required=True)
        schema.add_property("path", "string", "File path")
        schema.add_property("size", "integer", "File size in bytes")
        schema.add_property("modified", "string", "Last modified timestamp", format="date-time")
        schema.add_property("error", "string", "Error message if operation failed")
        return schema
    
    @staticmethod
    def create_search_result_schema() -> ToolOutputSchema:
        """Create schema for search results"""
        schema = SchemaBuilder.create_object_schema("Search results")
        schema.add_property("query", "string", "The search query", required=True)
        schema.add_property("total_results", "integer", "Total number of results", required=True)
        schema.add_property("results", "array", "Array of search results", required=True)
        schema.add_property("page", "integer", "Current page number")
        schema.add_property("per_page", "integer", "Results per page")
        return schema
    
    @staticmethod
    def create_api_response_schema() -> ToolOutputSchema:
        """Create schema for API responses"""
        schema = SchemaBuilder.create_object_schema("API response")
        schema.add_property("status_code", "integer", "HTTP status code", required=True)
        schema.add_property("data", "object", "Response data")
        schema.add_property("headers", "object", "Response headers")
        schema.add_property("error", "string", "Error message if request failed")
        return schema


class CapabilityBuilder:
    """Builder class for creating capability metadata"""
    
    @staticmethod
    def create_file_tool_capability(
        name: str,
        description: str,
        supports_streaming: bool = False
    ) -> CapabilityMetadata:
        """Create capability metadata for file tools"""
        return CapabilityMetadata(
            name=name,
            description=description,
            category="file_operations",
            tags=["files", "io"],
            output_schema=SchemaBuilder.create_file_result_schema(),
            supports_streaming=supports_streaming,
            supports_cancellation=True,
            estimated_duration="fast"
        )
    
    @staticmethod
    def create_search_tool_capability(
        name: str,
        description: str,
        requires_auth: bool = False
    ) -> CapabilityMetadata:
        """Create capability metadata for search tools"""
        return CapabilityMetadata(
            name=name,
            description=description,
            category="search",
            tags=["search", "query"],
            output_schema=SchemaBuilder.create_search_result_schema(),
            supports_streaming=True,
            supports_cancellation=True,
            requires_authentication=requires_auth,
            estimated_duration="medium"
        )
    
    @staticmethod
    def create_api_tool_capability(
        name: str,
        description: str,
        dependencies: Optional[list[str]] = None
    ) -> CapabilityMetadata:
        """Create capability metadata for API tools"""
        return CapabilityMetadata(
            name=name,
            description=description,
            category="api",
            tags=["api", "http"],
            dependencies=dependencies or [],
            output_schema=SchemaBuilder.create_api_response_schema(),
            supports_streaming=False,
            supports_cancellation=True,
            requires_authentication=True,
            estimated_duration="medium",
            resource_requirements={
                "network": True,
                "rate_limit": "standard"
            }
        )
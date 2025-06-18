# packages/mcp-server/src/mcp_server/mcp/providers.py
import asyncio
import json
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path
import mimetypes

from .resources import Resource, ResourceProvider

class FileResourceProvider(ResourceProvider):
    """Provider for file-based resources"""

    def __init__(self, directory: str, base_uri: str = "file://"):
        self.directory = Path(directory)
        self.base_uri = base_uri

    async def get_content(self, uri: str) -> Dict[str, Any]:
        """Get the content of a file resource"""
        if not uri.startswith(self.base_uri):
            raise ValueError(f"URI {uri} does not start with {self.base_uri}")

        # Remove the base URI prefix and normalize path
        relative_path = uri[len(self.base_uri):]
        file_path = (self.directory / relative_path).resolve()

        # Security check to prevent directory traversal
        if not str(file_path).startswith(str(self.directory.resolve())):
            raise ValueError(f"Path traversal attack detected: {relative_path}")

        if not file_path.exists():
            raise FileNotFoundError(f"Resource not found: {uri}")

        # Get MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))

        # Read file content
        loop = asyncio.get_event_loop()

        is_text = mime_type and (
            mime_type.startswith('text/') or
            mime_type in ['application/json', 'application/xml', 'application/javascript']
        )

        if is_text:
            # Text file
            content = await loop.run_in_executor(None, lambda: file_path.read_text())
            return {
                "uri": uri,
                "mimeType": mime_type,
                "text": content
            }
        else:
            # Binary file
            content = await loop.run_in_executor(None, lambda: file_path.read_bytes())
            return {
                "uri": uri,
                "mimeType": mime_type,
                "blob": base64.b64encode(content).decode('utf-8')
            }

    def get_resources(self) -> List[Resource]:
        """Get a list of all files in the directory"""
        resources = []

        for file_path in self.directory.glob("**/*"):
            if file_path.is_file():
                # Get relative path from base directory
                relative_path = file_path.relative_to(self.directory)
                uri = f"{self.base_uri}{relative_path}"

                # Guess content type
                mime_type, _ = mimetypes.guess_type(str(file_path))

                resources.append(Resource(
                    uri=uri,
                    name=file_path.name,
                    description=f"File: {relative_path}",
                    mime_type=mime_type
                ))

        return resources

class DatabaseResourceProvider(ResourceProvider):
    """Provider for database resources"""

    def __init__(self, connection_string: str, base_uri: str = "db://"):
        self.connection_string = connection_string
        self.base_uri = base_uri
        self.db_connection = None

    async def connect(self):
        """Connect to the database"""
        # This would be implemented with your database library of choice
        # For example, with asyncpg for PostgreSQL:
        # self.db_connection = await asyncpg.connect(self.connection_string)
        pass

    async def get_content(self, uri: str) -> Dict[str, Any]:
        """Get content from the database"""
        if not uri.startswith(self.base_uri):
            raise ValueError(f"URI {uri} does not start with {self.base_uri}")

        # Connect if not already connected
        if not self.db_connection:
            await self.connect()

        # Parse the URI to extract query path
        query_path = uri[len(self.base_uri):]

        # Execute query and get results
        # This is a placeholder - actual implementation depends on your DB
        results = await self._execute_query(query_path)

        return {
            "uri": uri,
            "mimeType": "application/json",
            "text": json.dumps(results)
        }

    async def _execute_query(self, query_path: str) -> List[Dict[str, Any]]:
        """Execute a database query based on the path"""
        # This would be implemented based on your database
        # Example with a SQL database:
        # return await self.db_connection.fetch(f"SELECT * FROM {query_path}")
        return []

    def get_resources(self) -> List[Resource]:
        """Get available database resources"""
        # This would list available tables, views, etc.
        # Example:
        # tables = await self.db_connection.fetch("SELECT table_name FROM information_schema.tables")
        tables = []

        return [
            Resource(
                uri=f"{self.base_uri}{table}",
                name=f"Table: {table}",
                description=f"Database table: {table}",
                mime_type="application/json"
            )
            for table in tables
        ]

class VectorDBResourceProvider(ResourceProvider):
    """Provider for vector database resources"""

    def __init__(self, vector_db_client, base_uri: str = "vector://"):
        self.vector_db = vector_db_client
        self.base_uri = base_uri

    async def get_content(self, uri: str) -> Dict[str, Any]:
        """Get content from the vector database"""
        if not uri.startswith(self.base_uri):
            raise ValueError(f"URI {uri} does not start with {self.base_uri}")

        # Parse URI to extract collection and query
        parts = uri[len(self.base_uri):].split('/')
        collection = parts[0]
        query = parts[1] if len(parts) > 1 else None

        # Execute similarity search
        results = await self._execute_search(collection, query)

        return {
            "uri": uri,
            "mimeType": "application/json",
            "text": json.dumps(results)
        }

    async def _execute_search(self, collection: str, query: Optional[str]) -> List[Dict[str, Any]]:
        """Execute a vector similarity search"""
        # This would be implemented with your vector DB of choice
        # Example:
        # return await self.vector_db.search(collection, query, top_k=10)
        return []

    def get_resources(self) -> List[Resource]:
        """Get available vector database collections"""
        # Example:
        # collections = self.vector_db.list_collections()
        collections = []

        return [
            Resource(
                uri=f"{self.base_uri}{collection}",
                name=f"Vector Collection: {collection}",
                description=f"Vector database collection for semantic search",
                mime_type="application/json"
            )
            for collection in collections
        ]
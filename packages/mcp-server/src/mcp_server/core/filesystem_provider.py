# packages/mcp-server/src/mcp_server/mcp/filesystem_provider.py
import os
import logging
import asyncio
import mimetypes
from typing import List, Dict, Any, Optional
from pydantic import BaseModel # Ensure BaseModel is imported for type checking

# Assuming resources.py is in the same directory or accessible via PYTHONPATH
from .resources import Resource, ResourceProvider
# Optionally import MCP types for type checking/conversion if needed
# (Not strictly needed for the current implementation logic but good for clarity)
# try:
#     from .models import TextResourceContents, BlobResourceContents
#     MCP_MODELS_AVAILABLE = True
# except ImportError:
#     MCP_MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

class FileSystemProvider(ResourceProvider):
    """
    Provides access to files within specified allowed paths under a workspace root
    as MCP resources.
    """
    def __init__(self, workspace_root: str, allowed_paths: List[str]):
        """
        Initializes the FileSystemProvider.

        Args:
            workspace_root: The absolute path to the root directory considered the workspace.
            allowed_paths: A list of absolute paths within the workspace root that
                           this provider is allowed to access and serve resources from.
        """
        self.workspace_root = os.path.abspath(workspace_root)
        self.allowed_paths = [os.path.abspath(p) for p in allowed_paths]

        logger.info(f"FileSystemProvider initialized. Workspace Root: {self.workspace_root}")

        # --- Validation and Security Checks ---
        if not os.path.isdir(self.workspace_root):
            logger.error(f"Workspace root '{self.workspace_root}' is not a valid directory.")
            # Ensure directory exists for agent operations
            try:
                os.makedirs(self.workspace_root, exist_ok=True)
                logger.info(f"Ensured agent workspace directory exists: {self.workspace_root}")
            except OSError as e:
                 logger.critical(f"Failed to create workspace root directory '{self.workspace_root}': {e}. FilesystemProvider cannot function.")
                 raise ValueError(f"Invalid or inaccessible workspace root directory: {self.workspace_root}") from e


        valid_allowed_paths = []
        for path in self.allowed_paths:
            # Resolve path relative to workspace root *before* checking if it starts with it
            # This handles cases like allowed_paths=["."] correctly
            resolved_path = os.path.abspath(os.path.join(self.workspace_root, path))

            if not resolved_path.startswith(self.workspace_root):
                logger.error(f"Security Error: Configured allowed path '{path}' resolves to '{resolved_path}', which is outside the workspace root '{self.workspace_root}'. Skipping this path.")
            elif not os.path.exists(resolved_path):
                 logger.warning(f"Allowed path '{path}' (resolves to '{resolved_path}') does not exist. Creating it.")
                 try:
                     os.makedirs(resolved_path, exist_ok=True)
                     valid_allowed_paths.append(resolved_path) # Add the resolved absolute path
                 except OSError as e:
                      logger.error(f"Failed to create allowed directory '{resolved_path}': {e}. Skipping this path.")
            elif not os.path.isdir(resolved_path):
                logger.error(f"Configured allowed path '{path}' (resolves to '{resolved_path}') exists but is not a directory. Skipping this path.")
            else:
                 valid_allowed_paths.append(resolved_path) # Add the resolved absolute path

        self.allowed_paths = valid_allowed_paths # Update with only valid, absolute paths
        if not self.allowed_paths:
             logger.warning(f"No valid allowed paths configured within workspace '{self.workspace_root}'. FileSystemProvider will serve no resources.")
        else:
            logger.info(f"FileSystemProvider serving resources from: {self.allowed_paths}")

        # Add common useful mime types if not present
        mimetypes.add_type("text/markdown", ".md")
        mimetypes.add_type("text/plain", ".log")
        mimetypes.add_type("application/json", ".json")
        mimetypes.add_type("application/x-python-code", ".py")
        mimetypes.add_type("text/x-dockerfile", "Dockerfile")

    def _is_safe_path(self, file_path: str) -> bool:
        """
        Security Check: Ensure the resolved absolute path is strictly within
        one of the configured allowed directories. Prevents path traversal.
        """
        try:
            # Ensure the input path is resolved absolutely first
            abs_path = os.path.abspath(file_path)

            # Basic check: Must be within the overall workspace root
            # Check both the path itself and its containing directory for robustness
            if not abs_path.startswith(self.workspace_root + os.sep) and abs_path != self.workspace_root:
                 logger.debug(f"Path '{abs_path}' rejected: Not within workspace root '{self.workspace_root}'")
                 return False

            # Granular check: Must be within one of the specifically allowed paths
            # Check starts with allowed path + separator OR is exactly the allowed path
            if not any(abs_path.startswith(allowed + os.sep) or abs_path == allowed for allowed in self.allowed_paths):
                logger.debug(f"Path '{abs_path}' rejected: Not within allowed paths: {self.allowed_paths}")
                return False

            logger.debug(f"Path '{abs_path}' is safe.")
            return True
        except Exception as e:
             # Catch potential errors during path manipulation (e.g., too long path)
             logger.error(f"Error during path safety check for '{file_path}': {e}")
             return False

    def get_resources(self) -> List[Resource]:
        """Scans allowed paths recursively and returns discovered files as Resource objects."""
        logger.info("--- FileSystemProvider: Executing get_resources ---")
        resources: List[Resource] = []
        if not self.allowed_paths:
             logger.warning("FileSystemProvider: No allowed paths configured, returning empty resource list.")
             return resources

        logger.info(f"FileSystemProvider: Scanning allowed paths: {self.allowed_paths}")
        scanned_paths = set() # Keep track of roots already scanned to avoid duplicates if allowed paths overlap

        for base_path in self.allowed_paths:
            abs_base_path = os.path.abspath(base_path) # Should already be absolute from __init__
            logger.info(f"FileSystemProvider: Processing base path: {abs_base_path}")
            if not os.path.isdir(abs_base_path):
                logger.warning(f"Allowed path is not a directory or doesn't exist anymore: {abs_base_path}. Skipping.")
                continue

            # Prevent scanning the same directory multiple times if allowed paths overlap
            if abs_base_path in scanned_paths:
                 logger.debug(f"Skipping already scanned path: {abs_base_path}")
                 continue
            scanned_paths.add(abs_base_path)

            logger.info(f"FileSystemProvider: Walking path: {abs_base_path}")
            try:
                for root, dirs, files in os.walk(abs_base_path, topdown=True):
                    logger.debug(f"  Walking root: {root}")
                    # logger.debug(f"    Dirs found: {dirs}")
                    # logger.debug(f"    Files found: {files}")

                    # Filter out commonly ignored directories
                    # Modify dirs[:] in-place to prevent walk from descending into them
                    dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'node_modules', '.mypy_cache', '.pytest_cache', '.ruff_cache', 'build', 'dist', '*.egg-info']]

                    for filename in files:
                        if filename.startswith('.'): # Skip hidden files
                            continue
                        full_path = os.path.join(root, filename)
                        logger.debug(f"      Checking file: {full_path}")
                        # Use the safety check method
                        if self._is_safe_path(full_path):
                            logger.debug(f"        File is safe, adding resource.")
                            self._add_file_resource(full_path, resources)
                        else:
                             # This case should ideally not happen if walk starts from allowed path,
                             # but keep as a safeguard against symlinks or other oddities.
                             logger.warning(f"        Skipping unsafe file found by os.walk (potential symlink?): {full_path}")

            except OSError as e:
                logger.error(f"OS error scanning directory {abs_base_path}: {e}")
            except Exception as e:
                 logger.error(f"Unexpected error scanning {abs_base_path}: {e}", exc_info=True)

        logger.info(f"FileSystemProvider finished scan. Discovered {len(resources)} resources.")
        return resources

    def _add_file_resource(self, full_path: str, resources_list: List[Resource]):
        """Helper to create and add a Resource object for a given file path."""
        if not self._is_safe_path(full_path): # Double-check safety before adding
             logger.warning(f"Skipping unsafe path during resource creation: {full_path}")
             return
        try:
            relative_path = os.path.relpath(full_path, self.workspace_root)
            # Create a file URI using forward slashes for cross-platform compatibility
            # Ensure no leading slash if relative_path starts at root
            uri_path = relative_path.replace(os.sep, '/')
            uri = f"file:///{uri_path}"
            filename = os.path.basename(full_path)
            mime_type = self._get_mime_type(filename)
            description = f"File: {relative_path}"
            try:
                size = os.path.getsize(full_path)
            except OSError:
                 size = None # Handle cases where size cannot be determined

            resource_instance = Resource(
                uri=uri,
                name=filename,
                description=description,
                mime_type=mime_type
                # Add size if Resource model supports it
                # size=size
            )
            resources_list.append(resource_instance)
            logger.debug(f"Added resource: Name={filename}, URI={uri}, Type={mime_type}")

        except Exception as e:
            logger.error(f"Error creating resource object for path {full_path}: {e}")


    async def get_content(self, uri: str) -> Dict[str, Any]:
        """
        Reads the content of a file resource specified by its 'file:///' URI.

        Returns:
            A dictionary conforming to the MCP ReadResourceResult structure,
            containing a list with a single content dictionary (e.g., TextContent)
            or an error message within the content dictionary.

        Raises:
            ValueError: If the URI scheme is not 'file:///'.
            FileNotFoundError: If the file is not found or access is denied (for security).
                               This exception is raised *only* if the path is deemed unsafe.
        """
        if not uri.startswith("file:///"):
            raise ValueError(f"URI scheme not supported by FileSystemProvider: {uri}")

        # Convert URI path segment back to OS-specific path relative to workspace root
        relative_path_from_uri = uri[len("file:///"):].replace('/', os.sep)
        full_path = os.path.abspath(os.path.join(self.workspace_root, relative_path_from_uri))

        logger.info(f"Attempting to read resource content for URI '{uri}' -> Path '{full_path}'")

        # --- CRITICAL SECURITY CHECK ---
        if not self._is_safe_path(full_path):
            logger.warning(f"Access denied for unsafe path derived from URI: {full_path} (URI: {uri})")
            # Raise FileNotFoundError which the registry handler expects for "not found" / access denied
            raise FileNotFoundError(f"Access denied or file not found in allowed paths: {uri}")

        content_dict = {}
        try:
            # Use run_in_executor for potentially blocking file I/O
            loop = asyncio.get_running_loop()
            content_bytes = await loop.run_in_executor(None, self._read_file_sync, full_path)

            # Attempt to decode as UTF-8 text content
            try:
                text_content = content_bytes.decode('utf-8')
                logger.debug(f"Read {len(text_content)} chars (UTF-8) from {uri}")
                content_dict = {
                    "type": "text", # Conforms to TextResourceContents structure implicitly
                    "text": text_content,
                    "mimeType": self._get_mime_type(full_path) or "text/plain"
                }

            except UnicodeDecodeError:
                logger.warning(f"File {uri} is not valid UTF-8. Treating as binary/unknown.")
                text_content_lossy = content_bytes.decode('utf-8', errors='replace')
                content_dict = {
                    "type": "text", # Still using text type, adjust if Blob is preferred/supported
                    "text": f"[Non-UTF8 Content]\n{text_content_lossy}",
                    "mimeType": self._get_mime_type(full_path) or "application/octet-stream"
                }

        except FileNotFoundError:
            logger.warning(f"File not found for URI: {uri} (Path: {full_path})")
            # Return structure indicating error/not found, protocol expects ReadResourceResult structure
            content_dict = {"type": "text", "text": f"[Error: File not found - {uri}]", "mimeType": "text/plain"}
        except IsADirectoryError:
             logger.warning(f"Attempted to read a directory as resource content: {uri} (Path: {full_path})")
             content_dict = {"type": "text", "text": f"[Error: Resource is a directory, not a file - {uri}]", "mimeType": "text/plain"}
        except OSError as e:
            logger.error(f"OS error reading file {full_path} for URI {uri}: {e}")
            content_dict = {"type": "text", "text": f"[Error: OS error reading file - {e}]", "mimeType": "text/plain"}
        except Exception as e:
            logger.error(f"Unexpected error reading file {full_path} for URI {uri}: {e}", exc_info=True)
            content_dict = {"type": "text", "text": f"[Error: Unexpected error reading file - {e}]", "mimeType": "text/plain"}

        # --- Ensure the inner content_dict is JSON serializable ---
        # If content_dict was created from a Pydantic model, dump it.
        # (Not strictly necessary here as it's built as a dict, but adds robustness)
        if isinstance(content_dict, BaseModel):
            try:
                content_dict = content_dict.model_dump(mode='json')
            except AttributeError:
                content_dict = content_dict.dict() # v1 fallback
            except Exception as dump_err:
                 logger.error(f"Failed to dump content_dict model: {dump_err}")
                 # Fallback to error representation if dumping fails
                 content_dict = {"type": "text", "text": f"[Error: Failed to serialize content - {dump_err}]", "mimeType": "text/plain"}


        # --- Return the structure required by ReadResourceResult ---
        result_structure = {"contents": [content_dict]}
        logger.info(f"FileSystemProvider returning structure for {uri}: {str(result_structure)[:200]}...") # Log truncated structure
        return result_structure


    def _read_file_sync(self, path: str) -> bytes:
        """Synchronous helper to read file bytes."""
        # Add size limit check if desired
        # MAX_FILE_SIZE = 10 * 1024 * 1024 # Example: 10MB
        # if os.path.getsize(path) > MAX_FILE_SIZE:
        #    raise OSError(f"File exceeds maximum allowed size ({MAX_FILE_SIZE} bytes)")
        with open(path, 'rb') as f:
            return f.read()

    def _get_mime_type(self, filename: str) -> Optional[str]:
        """Simple helper to guess mime type."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type
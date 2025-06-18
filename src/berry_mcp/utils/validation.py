"""
Path validation utilities for Berry PDF MCP Server
"""

import os
import pathlib
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Default workspace directory
DEFAULT_WORKSPACE = os.getcwd()


def validate_path(path: str, workspace: Optional[str] = None) -> Optional[pathlib.Path]:
    """
    Validate and resolve a file path within a workspace.
    
    Args:
        path: The file path to validate
        workspace: Optional workspace directory (defaults to current directory)
    
    Returns:
        Resolved Path object if valid, None if invalid
    """
    if not path:
        logger.warning("Empty path provided")
        return None
    
    workspace_root = pathlib.Path(workspace or DEFAULT_WORKSPACE).resolve()
    
    try:
        # Convert to Path and resolve
        file_path = pathlib.Path(path)
        
        # If relative path, make it relative to workspace
        if not file_path.is_absolute():
            file_path = workspace_root / file_path
        
        # Resolve the path
        resolved_path = file_path.resolve()
        
        # Security check: ensure path is within workspace
        try:
            resolved_path.relative_to(workspace_root)
        except ValueError:
            logger.warning(f"Path '{path}' is outside workspace '{workspace_root}'")
            return None
        
        return resolved_path
        
    except Exception as e:
        logger.warning(f"Invalid path '{path}': {e}")
        return None


def set_workspace(workspace_path: str) -> bool:
    """
    Set the default workspace directory.
    
    Args:
        workspace_path: Path to the workspace directory
    
    Returns:
        True if successful, False otherwise
    """
    global DEFAULT_WORKSPACE
    
    try:
        workspace = pathlib.Path(workspace_path).resolve()
        if not workspace.exists():
            logger.error(f"Workspace directory does not exist: {workspace}")
            return False
        
        if not workspace.is_dir():
            logger.error(f"Workspace path is not a directory: {workspace}")
            return False
        
        DEFAULT_WORKSPACE = str(workspace)
        logger.info(f"Workspace set to: {DEFAULT_WORKSPACE}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to set workspace '{workspace_path}': {e}")
        return False


def get_workspace() -> str:
    """Get the current workspace directory"""
    return DEFAULT_WORKSPACE
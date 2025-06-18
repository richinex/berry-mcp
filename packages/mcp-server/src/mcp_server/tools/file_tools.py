import os
import logging
import pathlib
import asyncio
import shutil # Needed for recursive delete
import json # NEW: Import for JSON parsing
from typing import Dict, Optional, Any, List, Union, Tuple

log = logging.getLogger(__name__)

# --- Centralized Config Holder ---
class ToolConfig:
    """Holds shared configuration, primarily the workspace root."""
    _workspace_root: Optional[pathlib.Path] = None

    @classmethod
    def set_workspace(cls, path: pathlib.Path):
        """Validates and sets the workspace root path."""
        if not path.is_absolute():
            log.error(f"Workspace path provided must be absolute: {path}")
            raise ValueError("Workspace path must be absolute.")
        if not path.exists():
            log.warning(f"Workspace path set does not exist: {path}. Attempting to create.")
            try:
                path.mkdir(parents=True, exist_ok=True)
                log.info(f"Successfully created tools workspace directory: {path}")
            except OSError as e:
                log.error(f"Failed to create tools workspace directory '{path}': {e}")
                raise ValueError(f"Failed to create tools workspace directory: {e}") from e
        elif not path.is_dir():
            log.error(f"Workspace path set is not a directory: {path}")
            raise ValueError("Workspace path must be a directory.")

        cls._workspace_root = path
        log.info(f"Tool workspace configured in ToolConfig to: {cls._workspace_root}")

    @classmethod
    def get_workspace(cls) -> Optional[pathlib.Path]:
        """Gets the configured workspace root path."""
        return cls._workspace_root

# --- Configuration Constants ---
MAX_FILE_SIZE_READ = 5 * 1024 * 1024 # Max 5MB read

# --- Wrapper Function for Server Startup ---
def set_tools_workspace(path: pathlib.Path):
    """
    Sets the absolute workspace path via the ToolConfig class.
    Should be called once during server startup.
    """
    try:
        ToolConfig.set_workspace(path)
        log.info(f"set_tools_workspace function finished successfully for path: {path}")
    except Exception as e:
         log.error(f"Error within set_tools_workspace function: {e}", exc_info=True)
         raise


# --- Security Helper ---
def validate_path(user_path: str, check_exists: bool = True) -> Optional[pathlib.Path]:
    """
    Validates a user-provided path to ensure it's relative and stays within
    the configured workspace obtained from ToolConfig.

    Args:
        user_path: The relative path string provided by the user/LLM.
        check_exists: If True (default), the validated path must exist.
                      If False, the path is validated for safety but may not exist
                      (useful for validating target paths for new files/dirs).

    Returns:
        A resolved, absolute pathlib.Path object if valid and within the workspace,
        otherwise None. Returns None if workspace hasn't been configured.
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        log.error("Tool workspace not configured (checked via ToolConfig). Cannot validate path.")
        return None

    target_path_str = user_path if user_path else "."

    # FIXED: Handle paths that might already contain the workspace root
    if target_path_str.startswith(str(workspace_root)):
        # Path already contains workspace root, make it relative
        try:
            relative_part = pathlib.Path(target_path_str).relative_to(workspace_root)
            target_path_str = str(relative_part)
        except ValueError:
            # If relative_to fails, the path isn't actually under workspace_root
            log.warning(f"Path appears to contain workspace root but isn't under it: '{target_path_str}'")
            return None

    # FIXED: More precise absolute path and traversal detection
    path_obj = pathlib.Path(target_path_str)

    # Check for directory traversal attempts
    if ".." in path_obj.parts:
        log.warning(f"Path validation failed: Directory traversal detected: '{target_path_str}'")
        return None

    # Check if it's an absolute path (but allow paths that were made relative above)
    if os.path.isabs(target_path_str) and not target_path_str.startswith(str(workspace_root)):
        log.warning(f"Path validation failed: Absolute path outside workspace: '{target_path_str}'")
        return None

    try:
        combined_path = workspace_root.joinpath(target_path_str).resolve()

        # FIXED: More robust workspace containment check
        try:
            combined_path.relative_to(workspace_root)
        except ValueError:
            log.warning(f"Path validation failed: Resolved path '{combined_path}' is outside workspace '{workspace_root}'. Original input: '{target_path_str}'")
            return None

        if check_exists and not combined_path.exists():
            log.warning(f"Path validation failed: Path '{combined_path}' (from input '{target_path_str}') does not exist and check_exists is True.")
            return None

        log.debug(f"Path validation success: '{target_path_str}' resolved to '{combined_path}' within workspace '{workspace_root}'. Exists check: {check_exists}, Actual exists: {combined_path.exists()}")
        return combined_path
    except Exception as e:
        log.error(f"Error validating path '{target_path_str}' relative to '{workspace_root}': {e}")
        return None

# --- Tool Implementations (Using ToolConfig) ---

async def list_files(path: Optional[str] = None) -> Dict[str, Optional[Union[List[str], str]]]:
    """
    Lists files and directories within the agent's secure workspace.
    Uses workspace configured via ToolConfig.

    Args:
        path: Optional relative path within the workspace. Defaults to the workspace root.

    Returns:
        A dictionary:
        - On success: {"data": ["file1", "dir1/"], "error": null}
        - On failure: {"data": null, "error": "Error description"}
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        return {"data": None, "error": "Workspace not configured"}

    log.info(f"Attempting to list files in path: '{path or '.'}' relative to workspace {workspace_root}.")
    target_dir_str = path if path else "."

    # For list_files, the directory must exist.
    validated_dir_path = validate_path(target_dir_str, check_exists=True)

    if not validated_dir_path:
        # validate_path logs details if workspace isn't set or path is invalid/outside workspace
        # If check_exists was the reason for failure, it means path doesn't exist
        # We need to check if the path was syntactically valid but just non-existent.
        temp_check_no_exist = validate_path(target_dir_str, check_exists=False)
        if temp_check_no_exist and not temp_check_no_exist.exists():
            return {"data": None, "error": f"Directory not found within workspace: '{path}'"}
        return {"data": None, "error": f"Invalid or disallowed path provided: '{path}'."}


    if not validated_dir_path.is_dir(): # Should be redundant if validate_path(check_exists=True) worked and it exists
        return {"data": None, "error": f"Path is not a directory within workspace: '{path}'"}

    try:
        items = []
        for item in validated_dir_path.iterdir():
            relative_item_path_display = item.relative_to(validated_dir_path)
            if item.is_dir():
                items.append(f"{relative_item_path_display}/")
            else:
                items.append(str(relative_item_path_display))
        log.info(f"Successfully listed {len(items)} items in validated path: {validated_dir_path}")
        return {"data": sorted(items), "error": None}
    except PermissionError:
        log.error(f"Permission denied listing directory: {validated_dir_path}")
        return {"data": None, "error": f"Permission denied listing directory '{path}'."}
    except Exception as e:
        log.error(f"Failed to list files in '{validated_dir_path}': {e}", exc_info=True)
        return {"data": None, "error": f"An unexpected error occurred while listing files: {e}"}


async def read_file(path: str) -> Dict[str, Optional[str]]:
    """
    Reads the content of a specified file within the agent's secure workspace.
    Uses workspace configured via ToolConfig.

    Args:
        path: The relative path to the file within the workspace.

    Returns:
        A dictionary:
        - On success: {"data": "file content", "error": null} (content might be truncated)
        - On failure: {"data": null, "error": "Error description"}
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        return {"data": None, "error": "Workspace not configured"}

    log.info(f"Attempting to read file: '{path}' relative to workspace {workspace_root}.")
    if not path:
        return {"data": None, "error": "File path cannot be empty."}

    validated_file_path = validate_path(path, check_exists=True)

    if not validated_file_path:
        temp_check_no_exist = validate_path(path, check_exists=False)
        if temp_check_no_exist and not temp_check_no_exist.exists():
            return {"data": None, "error": f"File not found within workspace: '{path}'"}
        return {"data": None, "error": f"Invalid or disallowed file path provided: '{path}'."}

    if not validated_file_path.is_file(): # Should be redundant
        return {"data": None, "error": f"Path is not a file within workspace: '{path}'"}

    try:
        file_size = validated_file_path.stat().st_size
        if file_size > MAX_FILE_SIZE_READ:
            log.warning(f"File '{validated_file_path}' exceeds size limit ({file_size} > {MAX_FILE_SIZE_READ}). Reading only the beginning.")
            content_bytes = await asyncio.to_thread(validated_file_path.read_bytes)
            content = content_bytes[:MAX_FILE_SIZE_READ].decode(encoding='utf-8', errors='ignore')
            content += f"\n\n[... File Truncated: Original size {file_size} bytes, Limit {MAX_FILE_SIZE_READ} bytes ...]"
        else:
            content = await asyncio.to_thread(validated_file_path.read_text, encoding='utf-8', errors='ignore')

        log.info(f"Successfully read file: {validated_file_path} (Size: {file_size} bytes)")
        return {"data": content, "error": None}
    except PermissionError:
        log.error(f"Permission denied reading file: {validated_file_path}")
        return {"data": None, "error": f"Permission denied reading file '{path}'."}
    except UnicodeDecodeError:
         log.error(f"Could not decode file as UTF-8: {validated_file_path}")
         return {"data": None, "error": f"Cannot read file '{path}'. It might not be a text file or uses an unsupported encoding."}
    except Exception as e:
        log.error(f"Failed to read file '{validated_file_path}': {e}", exc_info=True)
        return {"data": None, "error": f"An unexpected error occurred while reading file: {e}"}

# NEW TOOL: read_json_file
async def read_json_file(path: str) -> Dict[str, Any]:
    """
    Reads a specified JSON file within the agent's secure workspace and parses its content.

    Args:
        path: The relative path to the JSON file within the workspace.

    Returns:
        A dictionary:
        - On success: {"data": parsed_json_object, "error": null}
        - On failure: {"data": null, "error": "Error description"}
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        return {"data": None, "error": "Workspace not configured"}

    log.info(f"Attempting to read and parse JSON file: '{path}' relative to workspace {workspace_root}.")
    if not path:
        return {"data": None, "error": "File path cannot be empty."}

    validated_file_path = validate_path(path, check_exists=True)

    if not validated_file_path:
        temp_check_no_exist = validate_path(path, check_exists=False)
        if temp_check_no_exist and not temp_check_no_exist.exists():
            return {"data": None, "error": f"File not found within workspace: '{path}'"}
        return {"data": None, "error": f"Invalid or disallowed file path provided: '{path}'."}

    if not validated_file_path.is_file():
        return {"data": None, "error": f"Path is not a file within workspace: '{path}'"}

    try:
        file_content_str = await asyncio.to_thread(validated_file_path.read_text, encoding='utf-8', errors='strict')
        parsed_json = json.loads(file_content_str)
        log.info(f"Successfully read and parsed JSON from file: {validated_file_path}")
        return {"data": parsed_json, "error": None}
    except FileNotFoundError: # Should be caught by validate_path
        log.error(f"JSON file not found: {validated_file_path}")
        return {"data": None, "error": f"JSON file not found at '{path}'."}
    except PermissionError:
        log.error(f"Permission denied reading JSON file: {validated_file_path}")
        return {"data": None, "error": f"Permission denied reading JSON file '{path}'."}
    except UnicodeDecodeError:
        log.error(f"Could not decode JSON file as UTF-8: {validated_file_path}")
        return {"data": None, "error": f"Cannot read JSON file '{path}'. It might not be a valid text file or uses an unsupported encoding."}
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse JSON from file '{validated_file_path}': {e}", exc_info=True)
        return {"data": None, "error": f"Failed to parse JSON from file '{path}': {e}"}
    except Exception as e:
        log.error(f"An unexpected error occurred while reading JSON file '{validated_file_path}': {e}", exc_info=True)
        return {"data": None, "error": f"An unexpected error occurred while reading JSON file: {e}"}


async def write_file(path: str, content: str, append: bool = False) -> Dict[str, Optional[str]]:
    """
    Writes content to a specified file within the agent's secure workspace.
    Uses workspace configured via ToolConfig. Creates parent directories if needed.

    Args:
        path: The relative path to the file within the workspace.
        content: The string content to write to the file.
        append: If True, appends to existing file. If False (default), overwrites the file.

    Returns:
        A dictionary:
        - On success: {"data": "Success message", "error": null}
        - On failure: {"data": null, "error": "Error description"}
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        return {"data": None, "error": "Workspace not configured"}

    log.info(f"Attempting to {'append to' if append else 'write'} file: '{path}' relative to workspace {workspace_root}.")
    if not path:
        return {"data": None, "error": "File path cannot be empty."}

    validated_file_path = validate_path(path, check_exists=False)

    if not validated_file_path:
        return {"data": None, "error": f"Invalid or disallowed file path provided: '{path}'."}

    if validated_file_path.exists() and validated_file_path.is_dir():
         return {"data": None, "error": f"Path exists and is a directory, cannot overwrite with file: '{path}'"}

    try:
        parent_dir = validated_file_path.parent
        if workspace_root in parent_dir.parents or parent_dir == workspace_root:
            await asyncio.to_thread(parent_dir.mkdir, parents=True, exist_ok=True)
        else:
            log.error(f"Attempted to create parent directory outside configured workspace: {parent_dir}")
            return {"data": None, "error": f"Cannot create parent directory outside workspace for path '{path}'"}

        # ✅ SIMPLIFIED: Single approach for both append and write
        if append:
            def append_operation():
                with open(validated_file_path, 'a', encoding='utf-8') as f:
                    f.write(content)
            await asyncio.to_thread(append_operation)
            action = "appended to"
        else:
            def write_operation():
                with open(validated_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            await asyncio.to_thread(write_operation)
            action = "wrote"

        relative_path_for_msg = validated_file_path.relative_to(workspace_root)
        success_msg = f"Successfully {action} {len(content)} characters to file '{relative_path_for_msg}'."
        log.info(success_msg + f" (Absolute: {validated_file_path})")
        return {"data": success_msg, "error": None}

    except PermissionError:
        log.error(f"Permission denied writing file: {validated_file_path}")
        return {"data": None, "error": f"Permission denied writing to file '{path}'."}
    except IsADirectoryError:
         log.error(f"Attempted to write file content to an existing directory path: {validated_file_path}")
         return {"data": None, "error": f"Cannot write file content, path exists as a directory: '{path}'."}
    except Exception as e:
        log.error(f"Failed to write file '{validated_file_path}': {e}", exc_info=True)
        return {"data": None, "error": f"An unexpected error occurred while writing file: {e}"}


async def rename_path(old_path: str, new_path: str) -> Dict[str, Optional[str]]:
    """
    Renames or moves a file or directory within the agent's secure workspace.

    Args:
        old_path: The current relative path of the file/directory.
        new_path: The new relative path for the file/directory.

    Returns:
        A dictionary:
        - On success: {"data": "Success message", "error": null}
        - On failure: {"data": null, "error": "Error description"}
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        return {"data": None, "error": "Workspace not configured"}

    log.info(f"Attempting to rename path: '{old_path}' -> '{new_path}' relative to workspace {workspace_root}.")
    if not old_path or not new_path:
        return {"data": None, "error": "Both old and new paths must be provided."}

    validated_old_path = validate_path(old_path, check_exists=True)
    validated_new_path = validate_path(new_path, check_exists=False) # New path should not exist

    if not validated_old_path:
        temp_check_no_exist = validate_path(old_path, check_exists=False)
        if temp_check_no_exist and not temp_check_no_exist.exists():
            return {"data": None, "error": f"Source path does not exist within workspace: '{old_path}'"}
        return {"data": None, "error": f"Invalid or disallowed source path provided: '{old_path}'."}

    if not validated_new_path:
        return {"data": None, "error": f"Invalid or disallowed destination path provided: '{new_path}'."}

    if validated_new_path.exists(): # Check after validation
        return {"data": None, "error": f"Destination path already exists within workspace: '{new_path}'. Cannot overwrite."}

    try:
        new_parent_dir = validated_new_path.parent
        if workspace_root in new_parent_dir.parents or new_parent_dir == workspace_root:
            await asyncio.to_thread(new_parent_dir.mkdir, parents=True, exist_ok=True)
        else:
            log.error(f"Attempted to create parent directory outside configured workspace for rename destination: {new_parent_dir}")
            return {"data": None, "error": f"Cannot create parent directory outside workspace for destination path '{new_path}'"}

        await asyncio.to_thread(validated_old_path.rename, validated_new_path)

        relative_old = validated_old_path.relative_to(workspace_root)
        relative_new = validated_new_path.relative_to(workspace_root)
        success_msg = f"Successfully renamed '{relative_old}' to '{relative_new}'."
        log.info(success_msg + f" (Abs: {validated_old_path} -> {validated_new_path})")
        return {"data": success_msg, "error": None}
    except FileNotFoundError: # old_path disappeared
        log.error(f"Source path disappeared before rename: {validated_old_path}")
        return {"data": None, "error": f"Source path '{old_path}' disappeared before it could be renamed."}
    except FileExistsError: # new_path appeared
        log.error(f"Destination path appeared before rename could complete: {validated_new_path}")
        return {"data": None, "error": f"Destination path '{new_path}' created concurrently by another process."}
    except PermissionError:
        log.error(f"Permission denied renaming '{validated_old_path}' to '{validated_new_path}'")
        return {"data": None, "error": f"Permission denied renaming '{old_path}' to '{new_path}'."}
    except OSError as e:
         log.error(f"OS error renaming '{validated_old_path}' to '{validated_new_path}': {e}", exc_info=True)
         return {"data": None, "error": f"OS error during rename operation: {e}"}
    except Exception as e:
        log.error(f"Failed to rename '{validated_old_path}' to '{validated_new_path}': {e}", exc_info=True)
        return {"data": None, "error": f"An unexpected error occurred while renaming: {e}"}


async def delete_file(path: str) -> Dict[str, Optional[str]]:
    """
    Deletes a specific file within the agent's secure workspace.

    Args:
        path: The relative path to the file within the workspace.

    Returns:
        A dictionary:
        - On success: {"data": "Success message", "error": null}
        - On failure: {"data": null, "error": "Error description"}
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        return {"data": None, "error": "Workspace not configured"}

    log.info(f"Attempting to delete file: '{path}' relative to workspace {workspace_root}.")
    if not path:
        return {"data": None, "error": "File path cannot be empty."}

    validated_file_path = validate_path(path, check_exists=True)

    if not validated_file_path:
        temp_check_no_exist = validate_path(path, check_exists=False)
        if temp_check_no_exist and not temp_check_no_exist.exists():
            return {"data": None, "error": f"File not found within workspace: '{path}'"}
        return {"data": None, "error": f"Invalid or disallowed file path provided: '{path}'."}

    if not validated_file_path.is_file(): # Should be redundant
        return {"data": None, "error": f"Path is not a file, cannot delete using delete_file: '{path}'. Use delete_directory for directories."}

    if validated_file_path == workspace_root:
         log.warning(f"Attempted to delete the workspace root directory via delete_file: '{path}'")
         return {"data": None, "error": "Deleting the workspace root directory is not allowed."}

    try:
        await asyncio.to_thread(validated_file_path.unlink)
        relative_path_for_msg = validated_file_path.relative_to(workspace_root)
        success_msg = f"Successfully deleted file '{relative_path_for_msg}'."
        log.info(success_msg + f" (Absolute: {validated_file_path})")
        return {"data": success_msg, "error": None}
    except FileNotFoundError: # Should be caught by initial check_exists, but defensive
        log.warning(f"File disappeared before delete: {validated_file_path}")
        return {"data": None, "error": f"File '{path}' disappeared before it could be deleted."}
    except PermissionError:
        log.error(f"Permission denied deleting file: {validated_file_path}")
        return {"data": None, "error": f"Permission denied deleting file '{path}'."}
    except IsADirectoryError: # Should be caught by is_file check
         log.error(f"Attempted to delete a directory using delete_file: {validated_file_path}")
         return {"data": None, "error": f"Path is a directory, not a file: '{path}'."}
    except OSError as e:
         log.error(f"OS error deleting file '{validated_file_path}': {e}", exc_info=True)
         return {"data": None, "error": f"OS error deleting file: {e}"}
    except Exception as e:
        log.error(f"Failed to delete file '{validated_file_path}': {e}", exc_info=True)
        return {"data": None, "error": f"An unexpected error occurred while deleting file: {e}"}


async def delete_directory(path: str, recursive: bool = False) -> Dict[str, Optional[str]]:
    """
    Deletes a directory within the agent's secure workspace.

    Args:
        path: The relative path to the directory within the workspace.
        recursive: If True, deletes the directory and all its contents.
                   If False (default), only deletes empty directories.

    Returns:
        A dictionary:
        - On success: {"data": "Success message", "error": null}
        - On failure: {"data": null, "error": "Error description"}
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        return {"data": None, "error": "Workspace not configured"}

    log.info(f"Attempting to delete directory: '{path}' (Recursive: {recursive}) relative to workspace {workspace_root}.")
    if not path:
        return {"data": None, "error": "Directory path cannot be empty."}

    validated_dir_path = validate_path(path, check_exists=True)

    if not validated_dir_path:
        temp_check_no_exist = validate_path(path, check_exists=False)
        if temp_check_no_exist and not temp_check_no_exist.exists():
            return {"data": None, "error": f"Directory not found within workspace: '{path}'"}
        return {"data": None, "error": f"Invalid or disallowed directory path provided: '{path}'."}

    if validated_dir_path == workspace_root:
         log.warning(f"Attempted to delete the workspace root directory itself: '{path}' (Validated: {validated_dir_path})")
         return {"data": None, "error": "Deleting the workspace root directory is not allowed."}

    if not validated_dir_path.is_dir(): # Should be redundant
        return {"data": None, "error": f"Path is not a directory, cannot delete using delete_directory: '{path}'. Use delete_file for files."}

    try:
        if recursive:
            log.warning(f"Performing RECURSIVE delete of directory: {validated_dir_path}")
            await asyncio.to_thread(shutil.rmtree, validated_dir_path)
        else:
            await asyncio.to_thread(validated_dir_path.rmdir)

        relative_path_for_msg = validated_dir_path.relative_to(workspace_root)
        success_msg = f"Successfully deleted directory '{relative_path_for_msg}' (Recursive: {recursive})."
        log.info(success_msg + f" (Absolute: {validated_dir_path})")
        return {"data": success_msg, "error": None}
    except FileNotFoundError: # Should be caught by initial check, but defensive
        log.warning(f"Directory disappeared before delete: {validated_dir_path}")
        return {"data": None, "error": f"Directory '{path}' disappeared before it could be deleted."}
    except PermissionError:
        log.error(f"Permission denied deleting directory: {validated_dir_path}")
        return {"data": None, "error": f"Permission denied deleting directory '{path}'."}
    except NotADirectoryError: # Should be caught by is_dir check
         log.error(f"Attempted to delete a file using delete_directory: {validated_dir_path}")
         return {"data": None, "error": f"Path is a file, not a directory: '{path}'."}
    except OSError as e:
        if e.errno == 39 and not recursive: # ENOTEMPTY
            log.warning(f"Attempted non-recursive delete on non-empty directory: {validated_dir_path}")
            return {"data": None, "error": f"Directory '{path}' is not empty. Use recursive=True to delete non-empty directories."}
        log.error(f"OS error deleting directory '{validated_dir_path}': {e}", exc_info=True)
        return {"data": None, "error": f"OS error deleting directory: {e}"}
    except Exception as e:
        log.error(f"Failed to delete directory '{validated_dir_path}': {e}", exc_info=True)
        return {"data": None, "error": f"An unexpected error occurred while deleting directory: {e}"}


def _build_structure_recursive(
    current_path: pathlib.Path,
    start_path: pathlib.Path,
    current_depth: int,
    max_depth: Optional[int]
) -> List[str]:
    """Helper recursive function to build directory structure with pathlib."""
    structure_lines = []
    # Determine indent based on current_depth relative to the initial call's depth
    # The path relative to start_path gives us the correct "visual" depth.
    try:
        path_relative_to_start = current_path.relative_to(start_path)
        # Depth for indentation is number of parts in this relative path
        # (unless it's '.', then depth is 0)
        indent_depth = len(path_relative_to_start.parts) if str(path_relative_to_start) != "." else 0
    except ValueError: # Should not happen if current_path is always child of start_path
        indent_depth = current_depth

    indent = "  " * indent_depth
    sub_indent = "  " * (indent_depth + 1)

    # List and sort directories and files for consistent output
    try:
        entries = sorted(list(current_path.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        structure_lines.append(f"{indent}{current_path.name}/ [Permission Denied]")
        return structure_lines
    except FileNotFoundError:
        structure_lines.append(f"{indent}{current_path.name}/ [Not Found or Access Error]")
        return structure_lines


    for entry in entries:
        if entry.is_dir():
            structure_lines.append(f"{sub_indent}{entry.name}/")
            if max_depth is None or (current_depth + 1) < max_depth: # Depth check for recursion
                structure_lines.extend(
                    _build_structure_recursive(entry, start_path, current_depth + 1, max_depth)
                )
        elif entry.is_file():
            structure_lines.append(f"{sub_indent}{entry.name}")
    return structure_lines


async def get_workspace_structure(
    path: Optional[str] = None,
    max_depth: Optional[int] = 3 # Default to a sensible max_depth
) -> Dict[str, Optional[Union[List[str], str]]]:
    """
    Provides a tree-like listing of files and directories within the agent's secure workspace,
    up to a specified depth. Uses pathlib for traversal.

    Args:
        path: Optional relative path within the workspace to start listing from. Defaults to the workspace root.
        max_depth: Optional maximum depth of directories to explore relative to the starting path.
                   A value of 0 means only list the starting path's immediate contents (files and empty dirs).
                   A value of 1 means starting path + one level down. None means unlimited. Default is 3.

    Returns:
        A dictionary:
        - On success: {"data": ["./", "  file.txt", "  subdir/"], "error": null}
        - On failure: {"data": null, "error": "Error description"}
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        return {"data": None, "error": "Workspace not configured"}

    log.info(f"Attempting to get workspace structure for path: '{path or '.'}' relative to '{workspace_root}', max_depth: {max_depth}")
    target_dir_str = path if path else "."

    validated_start_path = validate_path(target_dir_str, check_exists=True)

    if not validated_start_path:
        temp_check_no_exist = validate_path(target_dir_str, check_exists=False)
        if temp_check_no_exist and not temp_check_no_exist.exists():
            return {"data": None, "error": f"Starting path not found within workspace: '{path}'"}
        return {"data": None, "error": f"Invalid or disallowed path provided: '{path}'."}

    if not validated_start_path.is_dir(): # Should be redundant
        return {"data": None, "error": f"Starting path is not a directory within workspace: '{path}'"}

    try:
        # The _build_structure_recursive helper needs to run in a thread
        # as iterdir() and stat() calls can be blocking.
        def build_structure_sync():
            structure = []
            # Display the root of the listing
            start_node_name = validated_start_path.name if str(validated_start_path) != str(workspace_root) or path else "."
            structure.append(f"{start_node_name}/")

            if max_depth == 0: # Only list immediate files if max_depth is 0
                entries = sorted(list(validated_start_path.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
                for entry in entries:
                    if entry.is_dir():
                        structure.append(f"  {entry.name}/")
                    else:
                        structure.append(f"  {entry.name}")
                if not entries and (start_node_name == "." or not path) :
                    structure = ["Your workspace is currently empty. No files or folders found."]
                elif not entries:
                    structure = [f"Directory '{start_node_name}' is empty."]

            elif max_depth is None or max_depth > 0 : # max_depth of None or >0 implies recursion
                structure.extend(
                    _build_structure_recursive(validated_start_path, validated_start_path, 0, max_depth)
                )

            # Check if workspace is empty after building structure
            if len(structure) == 1 and structure[0].endswith("/"):
                is_empty = not any(validated_start_path.iterdir())
                if is_empty:
                    if start_node_name == "." or not path:
                        structure = ["Your workspace is currently empty. No files or folders found."]
                    else:
                        structure = [f"Directory '{start_node_name}' is empty."]

            return structure if structure else ["Your workspace is currently empty. No files or folders found."]


        final_structure = await asyncio.to_thread(build_structure_sync)
        log.info(f"Successfully generated structure for: {validated_start_path}")
        return {"data": final_structure, "error": None}

    except PermissionError:
        log.error(f"Permission denied walking directory: {validated_start_path}")
        return {"data": None, "error": f"Permission denied accessing parts of the directory '{path}'."}
    except Exception as e:
        log.error(f"Failed to get workspace structure for '{validated_start_path}': {e}", exc_info=True)
        return {"data": None, "error": f"An unexpected error occurred while listing the structure: {e}"}
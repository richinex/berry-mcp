# # mcp-server/src/mcp_server/tools/code_analysis_tools.py
# import os
# import ast
# import logging
# import pathlib
# import asyncio
# from typing import Dict, Optional, Any, List, Union, Set

# # Assuming ToolConfig and validate_path are accessible
# from .file_tools import ToolConfig, validate_path

# log = logging.getLogger(__name__)

# DEFAULT_IGNORE_DIRS = ["__pycache__", ".venv", ".git", "node_modules", "build", "dist", "docs", "tests", "test"]
# MAX_FILE_SIZE_FOR_AST = 10 * 1024 * 1024 # 10 MB limit for AST parsing

# class ASTVisitor(ast.NodeVisitor):
#     """
#     A node visitor for AST trees that collects imports, and detailed information
#     (name and docstring) for top-level function and class definitions.
#     """
#     def __init__(self):
#         self.imports: Set[str] = set()
#         self.relative_imports: Set[str] = set()
#         # Store functions and classes as lists of dictionaries
#         self.functions: List[Dict[str, Any]] = []
#         self.classes: List[Dict[str, Any]] = []

#     def visit_Import(self, node: ast.Import):
#         for alias in node.names:
#             self.imports.add(alias.name)
#         # No self.generic_visit(node) needed typically for imports

#     def visit_ImportFrom(self, node: ast.ImportFrom):
#         module_name = node.module
#         if node.level > 0: # Relative import
#             prefix = "." * node.level
#             current_import = prefix + (module_name if module_name else "") # Handles "from . import X" vs "from .module import X"
#             self.relative_imports.add(current_import)
#             # Optionally, if you want to see the specific names from relative imports in the main 'imports' list
#             # for alias in node.names:
#             #    self.imports.add(f"{current_import}.{alias.name}")
#         elif module_name: # Absolute import
#             self.imports.add(module_name)
#         # No self.generic_visit(node) needed typically for imports

#     def visit_FunctionDef(self, node: ast.FunctionDef):
#         # Check if it's a top-level function (parent is ast.Module)
#         if hasattr(node, 'parent') and isinstance(node.parent, ast.Module): # type: ignore [attr-defined]
#             docstring = ast.get_docstring(node, clean=True)
#             self.functions.append({
#                 "name": node.name,
#                 "docstring": docstring if docstring else None
#                 # Could add more details here like args, return type from annotations
#             })
#         # Do not call self.generic_visit if you only want top-level elements
#         # and not functions defined inside other functions or methods inside classes.
#         # If you want methods, you'd call generic_visit on ClassDef and then
#         # this visit_FunctionDef would also capture methods if parent is ClassDef.

#     def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
#         if hasattr(node, 'parent') and isinstance(node.parent, ast.Module): # type: ignore [attr-defined]
#             docstring = ast.get_docstring(node, clean=True)
#             self.functions.append({ # Adding to the same 'functions' list
#                 "name": node.name,
#                 "docstring": docstring if docstring else None,
#                 "is_async": True
#             })

#     def visit_ClassDef(self, node: ast.ClassDef):
#         if hasattr(node, 'parent') and isinstance(node.parent, ast.Module): # type: ignore [attr-defined]
#             docstring = ast.get_docstring(node, clean=True)
#             self.classes.append({
#                 "name": node.name,
#                 "docstring": docstring if docstring else None
#                 # Could add base classes: [b.id for b in node.bases if isinstance(b, ast.Name)]
#             })
#         # If you want to find methods defined within this class and their docstrings,
#         # you would call self.generic_visit(node) here, and the visit_FunctionDef/AsyncFunctionDef
#         # would need to be adapted to handle being inside a ClassDef parent.
#         # For now, this focuses on the class's own docstring.

# def _add_parent_pointers(tree: ast.AST):
#     for node in ast.walk(tree):
#         for child in ast.iter_child_nodes(node):
#             child.parent = node # type: ignore [attr-defined]

# async def analyze_python_code_metadata(
#     path: Optional[str] = None,
#     recursive: bool = True,
#     max_depth: Optional[int] = None,
#     ignore_dirs: Optional[List[str]] = None
# ) -> Union[Dict[str, Any], Dict[str, str]]:
#     """
#     Recursively scans a directory for Python (.py) files and extracts metadata
#     (imports, module docstring, and details for top-level functions and classes
#     including their names and docstrings) using AST.
#     """
#     workspace_root = ToolConfig.get_workspace()
#     if workspace_root is None:
#         log.error("analyze_python_code_metadata: Workspace not configured.")
#         return {"error": "Workspace not configured"}

#     target_dir_str = path if path is not None and path.strip() != "" else "."
#     log.debug(f"Analyzing Python code metadata. Target: '{target_dir_str}', Recursive: {recursive}, Max Depth: {max_depth}")

#     validated_start_path = validate_path(target_dir_str)

#     if not validated_start_path:
#         log.warning(f"Invalid or disallowed path for analysis: '{target_dir_str}' relative to workspace '{workspace_root}'")
#         return {"error": f"Invalid or disallowed path provided: '{target_dir_str}'."}
#     if not validated_start_path.exists():
#         log.warning(f"Target path for analysis does not exist: '{validated_start_path}'")
#         return {"error": f"Target path does not exist: '{target_dir_str}'."}
#     if not validated_start_path.is_dir():
#         log.warning(f"Target path for analysis is not a directory: '{validated_start_path}'")
#         return {"error": f"Path is not a directory: '{target_dir_str}'."}

#     resolved_ignore_dirs = set(ignore_dirs if ignore_dirs is not None else DEFAULT_IGNORE_DIRS)
#     analyzed_files_data: Dict[str, Any] = {}
#     files_processed_count = 0
#     files_failed_count = 0
#     base_for_relative_paths = validated_start_path

#     for root_str, dirs, files in os.walk(str(validated_start_path), topdown=True):
#         current_path = pathlib.Path(root_str)
#         try:
#             relative_to_start = current_path.relative_to(validated_start_path)
#             current_depth = len(relative_to_start.parts) if str(relative_to_start) != "." else 0
#         except ValueError:
#             log.error(f"Could not make '{current_path}' relative to '{validated_start_path}'. Skipping.")
#             dirs[:] = []
#             continue

#         if not recursive and current_depth > 0:
#             dirs[:] = []
#         if max_depth is not None and current_depth >= max_depth:
#             dirs[:] = []

#         dirs[:] = [d_name for d_name in dirs if d_name not in resolved_ignore_dirs]

#         for filename in files:
#             if not filename.endswith(".py"):
#                 continue

#             file_path_abs = current_path / filename
#             relative_file_path_str = str(file_path_abs.relative_to(base_for_relative_paths))

#             try:
#                 file_stat = await asyncio.to_thread(file_path_abs.stat)
#                 file_size = file_stat.st_size
#                 if file_size > MAX_FILE_SIZE_FOR_AST:
#                     log.warning(f"Skipping AST for '{relative_file_path_str}', too large: {file_size} bytes.")
#                     analyzed_files_data[relative_file_path_str] = {
#                         "path": relative_file_path_str, "error": "File too large", "size_bytes": file_size}
#                     files_failed_count += 1
#                     continue

#                 content = await asyncio.to_thread(file_path_abs.read_text, encoding='utf-8', errors='ignore')
#                 tree = ast.parse(content, filename=str(file_path_abs))
#                 _add_parent_pointers(tree)

#                 visitor = ASTVisitor()
#                 visitor.visit(tree)

#                 module_docstring = ast.get_docstring(tree, clean=True)

#                 analyzed_files_data[relative_file_path_str] = {
#                     "path": relative_file_path_str,
#                     "imports": sorted(list(visitor.imports)),
#                     "relative_imports": sorted(list(visitor.relative_imports)),
#                     "module_docstring": module_docstring if module_docstring else None,
#                     "functions": sorted(visitor.functions, key=lambda x: x['name']), # List of {"name": ..., "docstring": ...}
#                     "classes": sorted(visitor.classes, key=lambda x: x['name'])      # List of {"name": ..., "docstring": ...}
#                 }
#                 files_processed_count += 1
#             except UnicodeDecodeError:
#                 log.warning(f"Unicode decode error for '{relative_file_path_str}'. Skipping.")
#                 analyzed_files_data[relative_file_path_str] = {"path": relative_file_path_str, "error": "Unicode decode error"}
#                 files_failed_count += 1
#             except SyntaxError as e:
#                 log.warning(f"Syntax error in '{relative_file_path_str}': {e.msg} (line {e.lineno}). Skipping.")
#                 analyzed_files_data[relative_file_path_str] = {
#                     "path": relative_file_path_str, "error": f"Syntax error: {e.msg}",
#                     "line": e.lineno, "offset": e.offset if e.offset is not None else -1}
#                 files_failed_count += 1
#             except FileNotFoundError:
#                 log.warning(f"File not found during processing: '{relative_file_path_str}'. Skipping.")
#                 analyzed_files_data[relative_file_path_str] = {"path": relative_file_path_str, "error": "File not found"}
#                 files_failed_count += 1
#             except Exception as e:
#                 log.error(f"Error analyzing '{relative_file_path_str}': {type(e).__name__} - {e}", exc_info=log.isEnabledFor(logging.DEBUG))
#                 analyzed_files_data[relative_file_path_str] = {
#                     "path": relative_file_path_str, "error": f"Unexpected error: {type(e).__name__} - {str(e)}"}
#                 files_failed_count += 1

#         if not recursive:
#             break

#     summary_base_path = str(base_for_relative_paths.relative_to(workspace_root)) if base_for_relative_paths != workspace_root else "."
#     log.info(
#         f"Python code metadata analysis for '{target_dir_str}' complete. "
#         f"Parsed: {files_processed_count}, Failed/Skipped: {files_failed_count}"
#     )

#     return {
#         "summary": {
#             "requested_path": target_dir_str,
#             "analyzed_base_path_relative_to_workspace": summary_base_path,
#             "recursive_scan": recursive,
#             "max_depth_applied": max_depth if recursive else 0,
#             "files_successfully_parsed": files_processed_count,
#             "files_failed_or_skipped": files_failed_count,
#             "total_python_files_considered": files_processed_count + files_failed_count,
#         },
#         "files_metadata": analyzed_files_data
#     }

# mcp-server/src/mcp_server/tools/code_analysis_tools.py
# mcp-server/src/mcp_server/tools/code_analysis_tools.py
import ast
import logging
import pathlib
import asyncio
from typing import Dict, Optional, Any, List, Union, Set

# Assuming ToolConfig and validate_path are accessible
from .file_tools import ToolConfig, validate_path

log = logging.getLogger(__name__)

DEFAULT_IGNORE_DIRS = ["__pycache__", ".venv", ".git", "node_modules", "build", "dist", "docs", "tests", "test"]
MAX_FILE_SIZE_FOR_AST = 10 * 1024 * 1024 # 10 MB limit for AST parsing

class ASTVisitor(ast.NodeVisitor):
    """
    A node visitor for AST trees that collects imports, and detailed information
    (name and docstring) for top-level function and class definitions.
    """
    def __init__(self):
        self.imports: Set[str] = set()
        self.relative_imports: Set[str] = set()
        # Store functions and classes as lists of dictionaries
        self.functions: List[Dict[str, Any]] = []
        self.classes: List[Dict[str, Any]] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.add(alias.name)
        # No self.generic_visit(node) needed typically for imports

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module_name = node.module
        if node.level > 0: # Relative import
            prefix = "." * node.level
            current_import = prefix + (module_name if module_name else "") # Handles "from . import X" vs "from .module import X"
            self.relative_imports.add(current_import)
        elif module_name: # Absolute import
            self.imports.add(module_name)
        # No self.generic_visit(node) needed typically for imports

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Check if it's a top-level function (parent is ast.Module)
        if hasattr(node, 'parent') and isinstance(node.parent, ast.Module): # type: ignore [attr-defined]
            docstring = ast.get_docstring(node, clean=True)
            self.functions.append({
                "name": node.name,
                "docstring": docstring if docstring else None,
                "is_async": False # Explicitly mark non-async
            })

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        if hasattr(node, 'parent') and isinstance(node.parent, ast.Module): # type: ignore [attr-defined]
            docstring = ast.get_docstring(node, clean=True)
            self.functions.append({ # Adding to the same 'functions' list
                "name": node.name,
                "docstring": docstring if docstring else None,
                "is_async": True
            })

    def visit_ClassDef(self, node: ast.ClassDef):
        if hasattr(node, 'parent') and isinstance(node.parent, ast.Module): # type: ignore [attr-defined]
            docstring = ast.get_docstring(node, clean=True)
            self.classes.append({
                "name": node.name,
                "docstring": docstring if docstring else None
            })

def _add_parent_pointers(tree: ast.AST):
    """
    Adds a 'parent' attribute to each node in the AST tree.
    This is useful for determining the context of a node (e.g., if it's top-level).
    """
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node # type: ignore [attr-defined]


async def _get_ast_metadata_for_file_content(
    file_content: str, file_path_for_ast_error_reporting: str
) -> Dict[str, Any]:
    """
    Parses Python code content and returns AST-derived metadata.
    Not a tool itself, but a helper for other tools.

    Args:
        file_content: The string content of the Python file.
        file_path_for_ast_error_reporting: The path string to use for error reporting in ast.parse.

    Returns:
        A dictionary containing imports, functions, classes, and module docstring.
    """
    tree = ast.parse(file_content, filename=file_path_for_ast_error_reporting)
    _add_parent_pointers(tree) # Add parent pointers before visiting

    visitor = ASTVisitor()
    visitor.visit(tree)

    module_docstring = ast.get_docstring(tree, clean=True) # Get module-level docstring

    return {
        "imports": sorted(list(visitor.imports)),
        "relative_imports": sorted(list(visitor.relative_imports)),
        "module_docstring": module_docstring if module_docstring else None,
        "functions": sorted(visitor.functions, key=lambda x: x['name']),
        "classes": sorted(visitor.classes, key=lambda x: x['name'])
    }


async def analyze_single_python_file_metadata(
    path: str  # Path is now mandatory and expected to be a file
) -> Union[Dict[str, Any], Dict[str, str]]:
    """
    Analyzes a single Python (.py) file and extracts metadata (imports, module docstring,
    and details for top-level functions and classes including their names and docstrings) using AST.

    Args:
        path: The relative path within the workspace to the Python file.

    Returns:
        A dictionary containing the extracted metadata for the file,
        or an error dictionary.
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        log.error("analyze_single_python_file_metadata: Workspace not configured.")
        return {"error": "Workspace not configured"}

    if not path or not path.strip():
        return {"error": "File path cannot be empty."}

    log.debug(f"Analyzing single Python file metadata. Target: '{path}'")
    validated_file_path = validate_path(path) # Returns pathlib.Path or None

    if not validated_file_path:
        log.warning(f"Invalid or disallowed file path for analysis: '{path}' relative to workspace '{workspace_root}'")
        return {"error": f"Invalid or disallowed file path provided: '{path}'."}
    if not validated_file_path.exists():
        log.warning(f"Target file for analysis does not exist: '{validated_file_path}'")
        return {"error": f"Target file does not exist: '{path}'."}
    if not validated_file_path.is_file():
        log.warning(f"Target path is not a file: '{validated_file_path}'")
        return {"error": f"Path is not a file: '{path}'. Use 'analyze_python_directory_metadata' for directories."}
    if validated_file_path.suffix != ".py":
        log.warning(f"Target file is not a Python file: '{validated_file_path}'")
        return {"error": f"Target is not a Python (.py) file: '{path}'."}

    relative_file_path_str = str(validated_file_path.relative_to(workspace_root))

    try:
        file_stat = await asyncio.to_thread(validated_file_path.stat)
        file_size = file_stat.st_size
        if file_size > MAX_FILE_SIZE_FOR_AST:
            log.warning(f"Skipping AST for '{relative_file_path_str}', file too large: {file_size} bytes (limit: {MAX_FILE_SIZE_FOR_AST}).")
            return {
                "path": relative_file_path_str,
                "error": "File too large for AST analysis",
                "size_bytes": file_size
            }

        log.debug(f"Reading content of '{relative_file_path_str}' for single file AST parsing.")
        content = await asyncio.to_thread(validated_file_path.read_text, encoding='utf-8', errors='ignore')

        # Use the helper to get metadata
        metadata = await _get_ast_metadata_for_file_content(content, str(validated_file_path))

        # Add path and other relevant top-level info for this file's result
        metadata["path"] = relative_file_path_str
        metadata["size_bytes"] = file_size

        log.info(f"Successfully analyzed single Python file: '{relative_file_path_str}'")
        return metadata

    except UnicodeDecodeError:
        log.warning(f"Unicode decode error for '{relative_file_path_str}'.")
        return {"path": relative_file_path_str, "error": "Unicode decode error"}
    except SyntaxError as e:
        log.warning(f"Syntax error parsing '{relative_file_path_str}' at line {e.lineno}, offset {e.offset}: {e.msg}.")
        return {
            "path": relative_file_path_str, "error": f"Syntax error: {e.msg}",
            "line": e.lineno, "offset": e.offset if e.offset is not None else -1
        }
    except FileNotFoundError: # Should be caught by exists() check earlier, but good for robustness
        log.warning(f"File '{relative_file_path_str}' not found during processing (race condition?).")
        return {"path": relative_file_path_str, "error": "File not found during processing"}
    except Exception as e:
        log.error(f"Unexpected error analyzing single file '{relative_file_path_str}': {type(e).__name__} - {e}", exc_info=log.isEnabledFor(logging.DEBUG))
        return {
            "path": relative_file_path_str,
            "error": f"Unexpected error processing file: {type(e).__name__} - {str(e)}"
        }


async def _process_directory_pathlib_for_metadata(
    current_dir_path: pathlib.Path,
    base_for_relative_paths: pathlib.Path, # The path the user initially requested to scan
    recursive: bool,
    current_depth: int,
    max_depth: Optional[int],
    resolved_ignore_dirs: Set[str],
    analyzed_files_data: Dict[str, Any], # Output dict for file metadata
    file_counters: Dict[str, int] # Mutable counters
):
    """
    Helper function to process a directory using pathlib, collecting metadata for Python files.
    Modifies analyzed_files_data and file_counters directly.
    """
    # Max depth check: if max_depth is defined and current_depth is already at or beyond it,
    # we don't recurse further into subdirectories. Files in *this* directory (at max_depth) are still processed.
    if max_depth is not None and current_depth >= max_depth:
        log.debug(f"Max depth {max_depth} reached at path {current_dir_path}. Not recursing into subdirectories.")
        # No return here, process files in current directory if current_depth == max_depth

    try:
        items_iterator = current_dir_path.iterdir()
    except PermissionError:
        log.warning(f"Permission denied to iterate directory: {current_dir_path}. Skipping.")
        file_counters['failed'] +=1 # Count the directory itself as a failed item to scan
        return
    except Exception as e:
        log.error(f"Error iterating directory {current_dir_path}: {e}. Skipping.")
        file_counters['failed'] +=1
        return

    for item_path in items_iterator:
        if item_path.is_dir():
            if item_path.name in resolved_ignore_dirs:
                log.debug(f"Ignoring directory by name: {item_path.name}")
                continue
            if recursive and (max_depth is None or current_depth < max_depth): # Recurse if allowed
                await _process_directory_pathlib_for_metadata(
                    item_path, base_for_relative_paths, recursive,
                    current_depth + 1, max_depth, resolved_ignore_dirs,
                    analyzed_files_data, file_counters
                )
        elif item_path.is_file() and item_path.suffix == ".py":
            # Path for the output should be relative to the initial directory scanned by the user
            relative_file_path_str = str(item_path.relative_to(base_for_relative_paths))
            try:
                file_stat = await asyncio.to_thread(item_path.stat)
                file_size = file_stat.st_size
                if file_size > MAX_FILE_SIZE_FOR_AST:
                    log.warning(f"Skipping AST for '{relative_file_path_str}', file too large: {file_size} bytes (limit: {MAX_FILE_SIZE_FOR_AST}).")
                    analyzed_files_data[relative_file_path_str] = {
                        "path": relative_file_path_str, "error": "File too large for AST analysis", "size_bytes": file_size}
                    file_counters['failed'] += 1
                    continue

                log.debug(f"Reading content of '{relative_file_path_str}' for directory scan AST parsing.")
                content = await asyncio.to_thread(item_path.read_text, encoding='utf-8', errors='ignore')

                metadata = await _get_ast_metadata_for_file_content(content, str(item_path))
                # Add path and other file-specific info to the metadata dict for this file
                metadata_for_output = {
                    "path": relative_file_path_str,
                    "size_bytes": file_size,
                    **metadata # Unpack the core AST metadata
                }
                analyzed_files_data[relative_file_path_str] = metadata_for_output
                file_counters['processed'] += 1
            except UnicodeDecodeError:
                log.warning(f"Unicode decode error for '{relative_file_path_str}'. Adding error entry.")
                analyzed_files_data[relative_file_path_str] = {"path": relative_file_path_str, "error": "Unicode decode error"}
                file_counters['failed'] += 1
            except SyntaxError as e:
                log.warning(f"Syntax error parsing '{relative_file_path_str}' at line {e.lineno}, offset {e.offset}: {e.msg}. Adding error entry.")
                analyzed_files_data[relative_file_path_str] = {
                    "path": relative_file_path_str, "error": f"Syntax error: {e.msg}",
                    "line": e.lineno, "offset": e.offset if e.offset is not None else -1}
                file_counters['failed'] += 1
            except FileNotFoundError:
                log.warning(f"File '{relative_file_path_str}' not found during processing (race condition?). Skipping.")
                analyzed_files_data[relative_file_path_str] = {"path": relative_file_path_str, "error": "File not found during processing"}
                file_counters['failed'] += 1
            except Exception as e:
                log.error(f"Unexpected error analyzing '{relative_file_path_str}' in directory scan: {type(e).__name__} - {e}", exc_info=log.isEnabledFor(logging.DEBUG))
                analyzed_files_data[relative_file_path_str] = {
                    "path": relative_file_path_str, "error": f"Unexpected error: {type(e).__name__} - {str(e)}"}
                file_counters['failed'] += 1


async def analyze_python_directory_metadata(
    path: Optional[str] = None, # Path is to a directory, or workspace root if None
    recursive: bool = True,
    max_depth: Optional[int] = None,
    ignore_dirs: Optional[List[str]] = None
) -> Union[Dict[str, Any], Dict[str, str]]:
    """
    Recursively scans a directory for Python (.py) files and extracts metadata
    (imports, module docstring, and details for top-level functions and classes
    including their names and docstrings) using AST for each file.

    Args:
        path: Optional relative path within the workspace to the directory. Defaults to workspace root.
        recursive: Whether to scan subdirectories. Defaults to True.
        max_depth: Max depth for recursion. None for unlimited if recursive is True.
        ignore_dirs: List of directory names to ignore. Defaults to common ones.

    Returns:
        A dictionary containing a summary and detailed metadata for each parsed file,
        or an error dictionary.
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        log.error("analyze_python_directory_metadata: Workspace not configured.")
        return {"error": "Workspace not configured"}

    target_dir_str = path if path is not None and path.strip() != "" else "."
    log.debug(f"Analyzing Python directory metadata. Target: '{target_dir_str}', Recursive: {recursive}, Max Depth: {max_depth}")

    validated_start_path = validate_path(target_dir_str) # Returns pathlib.Path or None

    if not validated_start_path:
        log.warning(f"Invalid or disallowed directory path for analysis: '{target_dir_str}' relative to workspace '{workspace_root}'")
        return {"error": f"Invalid or disallowed directory path provided: '{target_dir_str}'."}
    if not validated_start_path.exists():
        log.warning(f"Target directory for analysis does not exist: '{validated_start_path}'")
        return {"error": f"Target directory does not exist: '{target_dir_str}'."}
    if not validated_start_path.is_dir():
        log.warning(f"Target path is not a directory: '{validated_start_path}'")
        return {"error": f"Path is not a directory: '{target_dir_str}'. Use 'analyze_single_python_file_metadata' for single files."}

    resolved_ignore_dirs = set(ignore_dirs if ignore_dirs is not None else DEFAULT_IGNORE_DIRS)
    analyzed_files_data: Dict[str, Any] = {}
    file_counters = {'processed': 0, 'failed': 0} # Use a dict for mutable counter

    # For directory scan, base_for_relative_paths is the directory itself that was requested.
    base_for_relative_paths = validated_start_path

    await _process_directory_pathlib_for_metadata(
        current_dir_path=validated_start_path,
        base_for_relative_paths=base_for_relative_paths,
        recursive=recursive,
        current_depth=0, # Start scan at depth 0 relative to validated_start_path
        max_depth=max_depth,
        resolved_ignore_dirs=resolved_ignore_dirs,
        analyzed_files_data=analyzed_files_data,
        file_counters=file_counters
    )

    summary_base_path = str(base_for_relative_paths.relative_to(workspace_root)) if base_for_relative_paths != workspace_root else "."
    log.info(
        f"Python directory metadata analysis for '{target_dir_str}' (resolved to '{base_for_relative_paths}') complete. "
        f"Parsed: {file_counters['processed']}, Failed/Skipped: {file_counters['failed']}"
    )

    return {
        "summary": {
            "requested_path": target_dir_str,
            "analyzed_directory_relative_to_workspace": summary_base_path,
            "recursive_scan": recursive,
            "max_depth_applied": max_depth if recursive else 0, # Max depth is 0 if not recursive
            "files_successfully_parsed": file_counters['processed'],
            "files_failed_or_skipped": file_counters['failed'],
            "total_python_files_considered": file_counters['processed'] + file_counters['failed'],
        },
        "files_metadata": analyzed_files_data
    }

# --- End of code_analysis_tools.py ---
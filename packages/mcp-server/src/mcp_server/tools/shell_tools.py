# packages/mcp-server/src/mcp_server/tools/shell_tools.py

import asyncio
import logging
import subprocess
import pathlib
from typing import Dict, Any, Optional, List, Union

log = logging.getLogger(__name__)

# Ensure ToolConfig and validate_path are imported correctly.
# This assumes they are in a sibling module like file_tools.py
try:
    from .file_tools import ToolConfig, validate_path
except ImportError:
    log.critical("CRITICAL IMPORT ERROR: Could not import 'ToolConfig' or 'validate_path' from file_tools in shell_tools.py. Path validation for shell commands WILL NOT WORK and tools may be insecure.")
    # Fallback dummy implementations for critical failure, but warns about insecurity
    class ToolConfig:
        @staticmethod
        def get_workspace() -> Optional[pathlib.Path]: return None
    def validate_path(user_path: str) -> Optional[pathbi.Path]:
        log.error(f"DUMMY validate_path used for '{user_path}' - NO SECURITY!")
        return pathlib.Path(user_path) # DANGER: This is insecure if used in production!


async def execute_command(
    command: Union[str, List[str]],
    cwd: Optional[str] = None,
    timeout: int = 300
) -> Dict[str, Any]:
    """
    Executes a shell command.
    Uses workspace configured via ToolConfig for path validation of cwd.

    Args:
        command: The command to execute. Can be a string (e.g., "ls -la") which runs in a shell,
                 or a list of strings (e.g., ["ls", "-la"]) which runs directly.
                 For `docker compose` commands, a string is usually fine.
        cwd: The current working directory for the command. This path should be relative
             to the agent's secure workspace root. If None, the command runs in the
             agent's default workspace root.
        timeout: Maximum time in seconds to wait for the command to complete. Default is 300 seconds.

    Returns:
        A dictionary containing:
        - "status": "success" if the command exited with code 0, "failed" otherwise.
        - "exit_code": The return code of the command.
        - "stdout": Standard output as a string.
        - "stderr": Standard error as a string.
        - "error": An error message if an exception occurred (e.g., timeout, command not found).
    """
    log.info(f"Attempting to execute command: '{command}' (CWD: {cwd or 'default workspace'})")

    actual_cwd: Optional[pathlib.Path] = None
    workspace_root = ToolConfig.get_workspace()

    # Determine the effective current working directory
    if cwd:
        if not workspace_root:
            log.error("Workspace root not configured via ToolConfig. Cannot validate specified cwd for execute_command.")
            return {"status": "failed", "error": "Workspace root not configured, cannot validate cwd."}

        validated_cwd = validate_path(cwd)
        if not validated_cwd:
            # validate_path already logs the reason
            return {"status": "failed", "error": f"Invalid or disallowed current working directory: '{cwd}'."}
        if not validated_cwd.is_dir():
            log.error(f"Specified current working directory is not a directory: '{cwd}'.")
            return {"status": "failed", "error": f"Current working directory is not a directory: '{cwd}'."}
        actual_cwd = validated_cwd
    elif workspace_root:
        actual_cwd = workspace_root # Default to workspace root if no specific cwd provided
    else:
        # Fallback if no workspace and no cwd given (least secure option)
        log.warning("No workspace root or cwd specified, running command in system default location. This might be insecure.")
        actual_cwd = None # Let subprocess use its default cwd

    # Decide whether to use shell=True based on command type
    use_shell = isinstance(command, str) # Use shell=True for string commands (allows pipes, redirects)
    cmd_args = [command] if isinstance(command, str) else command # Convert to list for subprocess.Popen if string and shell=False

    proc = None # Initialize proc to None
    try:
        # Create the subprocess
        if use_shell:
            proc = await asyncio.create_subprocess_shell(
                cmd_args[0], # Pass the string command
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(actual_cwd) if actual_cwd else None
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args, # Pass list of args
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(actual_cwd) if actual_cwd else None
            )

        # Wait for command to complete with a timeout
        stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        stdout_str = stdout_data.decode(errors='ignore').strip()
        stderr_str = stderr_data.decode(errors='ignore').strip()

        if proc.returncode == 0:
            log.info(f"Command succeeded. Exit code: {proc.returncode}")
            return {
                "status": "success",
                "exit_code": proc.returncode,
                "stdout": stdout_str,
                "stderr": stderr_str,
            }
        else:
            log.warning(f"Command failed. Exit code: {proc.returncode}. Stderr: {stderr_str}")
            return {
                "status": "failed",
                "exit_code": proc.returncode,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "error": f"Command exited with non-zero status code {proc.returncode}"
            }
    except asyncio.TimeoutError:
        log.warning(f"Command timed out after {timeout} seconds.")
        if proc and proc.returncode is None: # If process is still running
            proc.terminate() # Send SIGTERM
            await asyncio.sleep(1) # Give it a moment
            if proc.returncode is None:
                proc.kill() # Send SIGKILL if still not terminated
            await proc.wait() # Wait for the process to exit after kill
        return {"status": "failed", "error": f"Command timed out after {timeout} seconds."}
    except FileNotFoundError:
        log.error(f"Command not found: '{command}'. Make sure the executable is in PATH.")
        return {"status": "failed", "error": f"Command not found: '{command}'"}
    except Exception as e:
        log.error(f"Error executing command: {e}", exc_info=True)
        return {"status": "failed", "error": f"Error executing command: {e}"}
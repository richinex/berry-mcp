# packages/mcp-server/src/mcp_server/tools/docker_compose_tools.py

import asyncio
import logging
import pathlib
from typing import Dict, Any, Optional, List, Union

log = logging.getLogger(__name__)

# Import the ToolConfig class and validate_path function
try:
    from .file_tools import ToolConfig, validate_path
    FILE_TOOLS_IMPORTED = True
except ImportError as e:
    log.critical("CRITICAL IMPORT ERROR: Could not import 'ToolConfig' or 'validate_path' from file_tools. Docker Compose path validation WILL NOT WORK and tools may fail.", exc_info=True)
    FILE_TOOLS_IMPORTED = False
    class ToolConfig:
        @staticmethod
        def get_workspace() -> Optional[pathlib.Path]:
            log.error("Using DUMMY ToolConfig - IMPORT FAILED")
            return None
    def validate_path(user_path: str) -> Optional[pathlib.Path]:
        log.error(f"Using DUMMY validate_path for '{user_path}' - IMPORT FAILED, NO SECURITY!")
        return None


async def docker_compose_up(
    compose_file: str = "compose.yml",
    project_directory: Optional[str] = None,
    detached: bool = True,
    build: bool = False,
    services: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Starts Docker Compose services using 'docker compose up'.

    Args:
        compose_file: Name of the compose file (e.g., 'compose.yml', 'docker-compose.dev.yml').
                     Must be relative to project_directory.
        project_directory: Directory containing the compose file, relative to workspace.
                          If None, uses workspace root.
        detached: Run services in the background (default: True).
        build: Force rebuild of images before starting (default: False).
        services: Optional list of specific services to start. If None, starts all services.

    Returns:
        Dictionary with status, output, and any error information.
    """
    log.info(f"Starting Docker Compose services from '{compose_file}' (detached: {detached})")

    # Validate and resolve paths
    workspace_root = ToolConfig.get_workspace()
    if not workspace_root:
        return {"status": "failed", "error": "Workspace root not configured via ToolConfig."}

    if project_directory:
        validated_project_dir = validate_path(project_directory)
        if not validated_project_dir:
            return {"status": "failed", "error": f"Invalid project directory: '{project_directory}'."}
        if not validated_project_dir.is_dir():
            return {"status": "failed", "error": f"Project directory is not a directory: '{project_directory}'."}
        working_dir = validated_project_dir
    else:
        working_dir = workspace_root

    # Validate compose file exists
    compose_file_path = working_dir / compose_file
    if not compose_file_path.is_file():
        return {"status": "failed", "error": f"Compose file not found: '{compose_file}' in '{working_dir}'."}

    # Build command
    command = ["docker", "compose", "-f", compose_file]
    if detached:
        command.extend(["up", "-d"])
    else:
        command.extend(["up"])

    if build:
        command.append("--build")

    if services:
        command.extend(services)

    return await _execute_compose_command(command, working_dir)


async def docker_compose_down(
    compose_file: str = "compose.yml",
    project_directory: Optional[str] = None,
    remove_volumes: bool = False,
    remove_images: Optional[str] = None
) -> Dict[str, Any]:
    """
    Stops and removes Docker Compose services using 'docker compose down'.

    Args:
        compose_file: Name of the compose file.
        project_directory: Directory containing the compose file, relative to workspace.
        remove_volumes: Remove named volumes declared in the `volumes` section (default: False).
        remove_images: Remove images. Options: 'all' (remove all), 'local' (remove only images that don't have a custom tag).

    Returns:
        Dictionary with status, output, and any error information.
    """
    log.info(f"Stopping Docker Compose services from '{compose_file}'")

    workspace_root = ToolConfig.get_workspace()
    if not workspace_root:
        return {"status": "failed", "error": "Workspace root not configured via ToolConfig."}

    if project_directory:
        validated_project_dir = validate_path(project_directory)
        if not validated_project_dir:
            return {"status": "failed", "error": f"Invalid project directory: '{project_directory}'."}
        working_dir = validated_project_dir
    else:
        working_dir = workspace_root

    # Build command
    command = ["docker", "compose", "-f", compose_file, "down"]

    if remove_volumes:
        command.append("--volumes")

    if remove_images in ["all", "local"]:
        command.extend(["--rmi", remove_images])

    return await _execute_compose_command(command, working_dir)


async def docker_compose_logs(
    compose_file: str = "compose.yml",
    project_directory: Optional[str] = None,
    services: Optional[List[str]] = None,
    follow: bool = False,
    tail: Union[int, str] = 100
) -> Dict[str, Any]:
    """
    View logs from Docker Compose services.

    Args:
        compose_file: Name of the compose file.
        project_directory: Directory containing the compose file, relative to workspace.
        services: Optional list of specific services to get logs from.
        follow: Follow log output (default: False).
        tail: Number of lines to show from end of logs, or 'all' (default: 100).

    Returns:
        Dictionary with status, output, and any error information.
    """
    log.info(f"Getting logs from Docker Compose services")

    workspace_root = ToolConfig.get_workspace()
    if not workspace_root:
        return {"status": "failed", "error": "Workspace root not configured via ToolConfig."}

    if project_directory:
        validated_project_dir = validate_path(project_directory)
        if not validated_project_dir:
            return {"status": "failed", "error": f"Invalid project directory: '{project_directory}'."}
        working_dir = validated_project_dir
    else:
        working_dir = workspace_root

    # Build command
    command = ["docker", "compose", "-f", compose_file, "logs"]

    # Add tail option
    if isinstance(tail, int) and tail > 0:
        command.extend(["--tail", str(tail)])
    elif tail == "all":
        command.extend(["--tail", "all"])

    if follow:
        command.append("--follow")

    if services:
        command.extend(services)

    # For follow mode, we need special handling with timeout
    if follow:
        return await _execute_compose_command(command, working_dir, timeout=30)
    else:
        return await _execute_compose_command(command, working_dir)


async def docker_compose_ps(
    compose_file: str = "compose.yml",
    project_directory: Optional[str] = None,
    all: bool = False
) -> Dict[str, Any]:
    """
    List Docker Compose services and their status.

    Args:
        compose_file: Name of the compose file.
        project_directory: Directory containing the compose file, relative to workspace.
        all: Show all containers including stopped ones (default: False).

    Returns:
        Dictionary with status, output, and any error information.
    """
    log.info(f"Listing Docker Compose services status")

    workspace_root = ToolConfig.get_workspace()
    if not workspace_root:
        return {"status": "failed", "error": "Workspace root not configured via ToolConfig."}

    if project_directory:
        validated_project_dir = validate_path(project_directory)
        if not validated_project_dir:
            return {"status": "failed", "error": f"Invalid project directory: '{project_directory}'."}
        working_dir = validated_project_dir
    else:
        working_dir = workspace_root

    # Build command
    command = ["docker", "compose", "-f", compose_file, "ps"]

    if all:
        command.append("--all")

    return await _execute_compose_command(command, working_dir)


async def docker_compose_exec(
    service_name: str,
    command_to_run: Union[str, List[str]],
    compose_file: str = "compose.yml",
    project_directory: Optional[str] = None,
    workdir: Optional[str] = None,
    user: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute a command in a running Docker Compose service container.

    Args:
        service_name: Name of the service to execute the command in.
        command_to_run: Command to execute (string or list of strings).
        compose_file: Name of the compose file.
        project_directory: Directory containing the compose file, relative to workspace.
        workdir: Working directory inside the container.
        user: User to run the command as.

    Returns:
        Dictionary with status, output, and any error information.
    """
    log.info(f"Executing command in Docker Compose service '{service_name}'")

    workspace_root = ToolConfig.get_workspace()
    if not workspace_root:
        return {"status": "failed", "error": "Workspace root not configured via ToolConfig."}

    if project_directory:
        validated_project_dir = validate_path(project_directory)
        if not validated_project_dir:
            return {"status": "failed", "error": f"Invalid project directory: '{project_directory}'."}
        working_dir = validated_project_dir
    else:
        working_dir = workspace_root

    # Build command
    command = ["docker", "compose", "-f", compose_file, "exec"]

    if workdir:
        command.extend(["--workdir", workdir])

    if user:
        command.extend(["--user", user])

    command.append(service_name)

    # Add the command to run
    if isinstance(command_to_run, str):
        # Split string command into parts for security
        command.extend(command_to_run.split())
    else:
        command.extend(command_to_run)

    return await _execute_compose_command(command, working_dir)


async def docker_compose_restart(
    compose_file: str = "compose.yml",
    project_directory: Optional[str] = None,
    services: Optional[List[str]] = None,
    timeout: int = 10
) -> Dict[str, Any]:
    """
    Restart Docker Compose services.

    Args:
        compose_file: Name of the compose file.
        project_directory: Directory containing the compose file, relative to workspace.
        services: Optional list of specific services to restart.
        timeout: Timeout in seconds for stopping containers (default: 10).

    Returns:
        Dictionary with status, output, and any error information.
    """
    log.info(f"Restarting Docker Compose services")

    workspace_root = ToolConfig.get_workspace()
    if not workspace_root:
        return {"status": "failed", "error": "Workspace root not configured via ToolConfig."}

    if project_directory:
        validated_project_dir = validate_path(project_directory)
        if not validated_project_dir:
            return {"status": "failed", "error": f"Invalid project directory: '{project_directory}'."}
        working_dir = validated_project_dir
    else:
        working_dir = workspace_root

    # Build command
    command = ["docker", "compose", "-f", compose_file, "restart"]

    if timeout != 10:  # Only add if different from default
        command.extend(["--timeout", str(timeout)])

    if services:
        command.extend(services)

    return await _execute_compose_command(command, working_dir)


# Helper function to execute Docker Compose commands
async def _execute_compose_command(
    command: List[str],
    working_dir: pathlib.Path,
    timeout: int = 300
) -> Dict[str, Any]:
    """
    Execute a Docker Compose command with proper error handling.

    Args:
        command: List of command parts to execute.
        working_dir: Directory to run the command in.
        timeout: Maximum time to wait for command completion.

    Returns:
        Dictionary with execution results.
    """
    log.debug(f"Executing command: {' '.join(command)} in {working_dir}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(working_dir)
        )

        stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        stdout_str = stdout_data.decode(errors='ignore').strip()
        stderr_str = stderr_data.decode(errors='ignore').strip()

        if proc.returncode == 0:
            log.info(f"Docker Compose command succeeded. Exit code: {proc.returncode}")
            return {
                "status": "success",
                "exit_code": proc.returncode,
                "stdout": stdout_str,
                "stderr": stderr_str,
            }
        else:
            log.warning(f"Docker Compose command failed. Exit code: {proc.returncode}. Stderr: {stderr_str}")
            return {
                "status": "failed",
                "exit_code": proc.returncode,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "error": f"Command exited with status code {proc.returncode}"
            }

    except asyncio.TimeoutError:
        log.warning(f"Docker Compose command timed out after {timeout} seconds.")
        if 'proc' in locals() and proc.returncode is None:
            proc.terminate()
            await asyncio.sleep(1)
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
        return {"status": "failed", "error": f"Command timed out after {timeout} seconds."}

    except FileNotFoundError:
        log.error(f"Docker Compose not found. Make sure 'docker' command is in PATH.")
        return {"status": "failed", "error": "Docker Compose not found. Make sure Docker is installed and 'docker' command is in PATH."}

    except Exception as e:
        log.error(f"Error executing Docker Compose command: {e}", exc_info=True)
        return {"status": "failed", "error": f"Error executing command: {e}"}
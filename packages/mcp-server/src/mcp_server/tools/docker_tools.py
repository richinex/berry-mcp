# # packages/mcp-server/src/mcp_server/tools/docker_tools.py

# import asyncio
# import logging
# import docker
# import docker.errors
# import docker.models.containers
# from docker.models.containers import Container # Explicit import for type hints
# import json
# import pathlib
# from typing import Dict, Optional, Any, List, Union

# log = logging.getLogger(__name__)

# # --- Corrected Import from file_tools ---
# # Import the ToolConfig class and the updated validate_path function
# try:
#     # Ensure this path is correct relative to mcp_server/tools/
#     from .file_tools import ToolConfig, validate_path
#     FILE_TOOLS_IMPORTED = True
#     # We don't need to check ToolConfig.get_workspace() at import time,
#     # validate_path and the tool functions will check it at runtime.
# except ImportError as e:
#     # Use critical level as this severely impacts tool functionality
#     log.critical("CRITICAL IMPORT ERROR: Could not import 'ToolConfig' or 'validate_path' from file_tools. Docker volume path validation WILL NOT WORK and tools may fail.", exc_info=True)
#     # Define dummy versions that clearly indicate failure and lack of security
#     FILE_TOOLS_IMPORTED = False
#     class ToolConfig: # Dummy class if import fails
#         @staticmethod
#         def get_workspace() -> Optional[pathlib.Path]:
#             log.error("Using DUMMY ToolConfig - IMPORT FAILED")
#             return None
#     def validate_path(user_path: str) -> Optional[pathlib.Path]:
#         log.error(f"Using DUMMY validate_path for '{user_path}' - IMPORT FAILED, NO SECURITY!")
#         return None # Always fail validation if import failed


# # --- Helper Function to Get Docker Client ---
# async def _get_docker_client() -> Optional[docker.DockerClient]:
#     """Gets and verifies connection to the Docker client."""
#     client = None
#     try:
#         # Use run_in_executor for the potentially blocking docker.from_env()
#         client = await asyncio.to_thread(docker.from_env)
#         # Use run_in_executor for the blocking ping()
#         await asyncio.to_thread(client.ping)
#         log.debug("Docker client initialized and connection verified.")
#         return client
#     except docker.errors.DockerException as e:
#         log.error(f"Failed to connect to Docker daemon: {e}")
#         log.error("Please ensure Docker is running and accessible.")
#         if client:
#             try: await asyncio.to_thread(client.close)
#             except Exception: pass
#         return None
#     except Exception as e:
#         log.error(f"Unexpected error initializing Docker client: {e}", exc_info=True)
#         if client:
#             try: await asyncio.to_thread(client.close)
#             except Exception: pass
#         return None

# # --- Helper Function to Get Container ---
# async def _get_container(client: docker.DockerClient, container_id_or_name: str) -> Optional[Container]:
#     """Safely gets a container object by ID or name."""
#     try:
#         # Use run_in_executor for the blocking containers.get()
#         container = await asyncio.to_thread(client.containers.get, container_id_or_name)
#         return container
#     except docker.errors.NotFound:
#         log.warning(f"Container '{container_id_or_name}' not found.")
#         return None
#     except docker.errors.APIError as e:
#         log.error(f"Docker API error getting container '{container_id_or_name}': {e}")
#         return None
#     except Exception as e:
#         log.error(f"Unexpected error getting container '{container_id_or_name}': {e}", exc_info=True)
#         return None

# # --- New Helper Function for Port Validation and Normalization ---
# def _validate_and_normalize_ports(ports: Optional[Dict[str, Optional[int]]]) -> Optional[Dict]:
#     """
#     Validates and normalizes port mappings for Docker SDK.

#     Accepts formats like:
#     - {'8080': 8080} -> maps container port 8080 to host port 8080
#     - {'80': 8080} -> maps container port 80 to host port 8080
#     - {'8080': None} -> maps container port 8080 to random host port
#     """
#     if not ports:
#         return None

#     normalized_ports = {}
#     for container_port_str, host_port in ports.items():
#         try:
#             # Ensure container_port is a valid integer
#             container_port_int = int(container_port_str)
#             if not (1 <= container_port_int <= 65535):
#                 raise ValueError(f"Invalid container port range: {container_port_str}. Must be between 1 and 65535.")

#             # Validate host_port if provided
#             if host_port is not None:
#                 host_port_int = int(host_port)
#                 if not (1 <= host_port_int <= 65535):
#                     raise ValueError(f"Invalid host port range: {host_port}. Must be between 1 and 65535.")
#                 normalized_ports[container_port_int] = host_port_int
#             else:
#                 normalized_ports[container_port_int] = None

#         except (ValueError, TypeError) as e:
#             log.error(f"Invalid port mapping provided: container_port='{container_port_str}', host_port='{host_port}'. Error: {e}")
#             return None

#     return normalized_ports

# # --- Tool Implementations (Updated to use new validate_path) ---

# async def build_docker_image(
#     context_path: str,
#     image_tag: str,
#     dockerfile: str = "Dockerfile",
#     build_args: Optional[Dict[str, str]] = None,
#     platform: Optional[str] = None,
# ) -> Dict[str, Any]:
#     """
#     Builds a Docker image using the host's Docker daemon.
#     Uses workspace configured via ToolConfig for path validation.

#     Args:
#         context_path: The relative path within the workspace to use as the build context.
#         image_tag: The tag to apply to the built image (e.g., 'my-app:latest').
#         dockerfile: The relative path to the Dockerfile *within* the context_path. Defaults to 'Dockerfile'.
#         build_args: Optional dictionary of build arguments.
#         platform: Optional target platform for the build (e.g., 'linux/amd64').

#     Returns:
#         A dictionary containing build status, logs, and image details on success,
#         or an error dictionary on failure.
#     """
#     log.info(f"Attempting to build Docker image '{image_tag}' from context '{context_path}'")

#     # Use the imported validate_path function (which now uses ToolConfig internally)
#     # Note: validate_path handles the case where ToolConfig hasn't been configured yet
#     validated_context_path = validate_path(context_path)

#     if not validated_context_path:
#         # validate_path logs details if it fails (including if workspace isn't configured)
#         return {"error": f"Invalid or disallowed context path: '{context_path}'."}
#     if not validated_context_path.is_dir():
#         return {"error": f"Context path is not a directory: '{context_path}'"}

#     # Validate dockerfile path *relative* to the context and ensure it stays within workspace
#     dockerfile_abs_path: Optional[pathlib.Path] = None
#     try:
#         # Resolve potential Dockerfile path relative to validated context
#         potential_dockerfile_abs_path = validated_context_path.joinpath(dockerfile).resolve()

#         # Now validate this potential absolute path using validate_path again.
#         # To do this robustly, we need the workspace root from ToolConfig.
#         workspace_root = ToolConfig.get_workspace()
#         if not workspace_root:
#              # This check is essential as validate_path needs it.
#              log.error("Workspace root not configured via ToolConfig. Cannot validate Dockerfile path.")
#              return {"error": "Workspace root not configured, cannot validate Dockerfile path."}

#         # Convert the absolute path back to a relative path string for validation
#         # This ensures it adheres to the same sandbox rules (no '..', etc.)
#         try:
#             relative_dockerfile_to_root = str(potential_dockerfile_abs_path.relative_to(workspace_root))
#             validated_dockerfile_path_obj = validate_path(relative_dockerfile_to_root) # Validate the relative path string

#             if not validated_dockerfile_path_obj:
#                 # validate_path already logged the reason
#                 log.warning(f"Resolved Dockerfile path '{potential_dockerfile_abs_path}' failed validation relative to workspace root.")
#                 return {"error": f"Dockerfile path '{dockerfile}' resolves outside the allowed workspace when combined with context '{context_path}'."}
#             else:
#                 # Use the validated absolute path object
#                 dockerfile_abs_path = validated_dockerfile_path_obj

#         except ValueError: # Could happen if paths are truly unrelated
#             log.warning(f"Could not make potential Dockerfile path '{potential_dockerfile_abs_path}' relative to workspace root '{workspace_root}'.")
#             return {"error": f"Dockerfile path '{dockerfile}' seems unrelated to workspace when combined with context '{context_path}'."}

#         # Final check: ensure the validated path points to an existing file
#         if not dockerfile_abs_path.is_file():
#             return {"error": f"Dockerfile not found at expected validated path: '{dockerfile_abs_path}'"}

#     except Exception as path_e:
#         log.error(f"Error resolving or validating dockerfile path: {path_e}", exc_info=True)
#         return {"error": f"Could not resolve or validate dockerfile path '{dockerfile}' relative to context '{context_path}'."}

#     # Docker build API expects the dockerfile path *relative* to the context root
#     dockerfile_rel_path = str(dockerfile_abs_path.relative_to(validated_context_path))

#     build_logs = []
#     image_id = None
#     error_detail = None
#     client: Optional[docker.DockerClient] = None # Explicitly define type

#     try:
#         client = await _get_docker_client()
#         if not client:
#             return {"error": "Docker connection failed. Is Docker running?"}

#         log.info(f"Starting Docker build: context='{validated_context_path}', tag='{image_tag}', dockerfile='{dockerfile_rel_path}'")

#         # Perform the build using asyncio.to_thread for the blocking call
#         response_stream = await asyncio.to_thread(
#             lambda: client.api.build(
#                 path=str(validated_context_path),
#                 dockerfile=dockerfile_rel_path,
#                 tag=image_tag,
#                 buildargs=build_args,
#                 rm=True,  # Remove intermediate containers
#                 decode=True, # Decode JSON stream objects
#                 platform=platform,
#             )
#         )

#         # Process the build log stream
#         for line in response_stream:
#             if isinstance(line, dict):
#                 log_entry = line.get("stream", "").strip()
#                 if log_entry:
#                     build_logs.append(log_entry)
#                     log.debug(f"Build log: {log_entry}")
#                 if "errorDetail" in line:
#                     error_detail = line["errorDetail"]["message"]
#                     log.error(f"Docker build error reported in stream: {error_detail}")
#                 # Extract image ID robustly
#                 if "aux" in line and "ID" in line["aux"]:
#                     possible_image_id = line["aux"]["ID"]
#                     if isinstance(possible_image_id, str) and possible_image_id.startswith("sha256:"):
#                          image_id = possible_image_id
#                          log.debug(f"Detected Image ID from aux: {image_id}")
#                 elif "Successfully built" in log_entry:
#                      parts = log_entry.split()
#                      if len(parts) >= 3:
#                          possible_image_id = parts[-1]
#                          # Basic check for potential ID format (could be short or long hash)
#                          if len(possible_image_id) >= 8:
#                              image_id = possible_image_id # Assume this is it
#                              log.debug(f"Detected Image ID from stream: {image_id}")

#         # FIX APPLIED HERE: Pass error_detail as positional argument
#         if error_detail:
#              raise docker.errors.BuildError(error_detail, build_log=build_logs)

#         # After successful build, get the image object to confirm ID and tags
#         try:
#              image = await asyncio.to_thread(lambda: client.images.get(image_tag))
#              final_image_id = image.id
#              tags = image.tags
#              log.info(f"Docker build successful. Image ID: {final_image_id}, Tags: {tags}")
#              return {
#                  "status": "success",
#                  "image_id": final_image_id, # Use ID from image object
#                  "tags": tags,
#                  "logs": build_logs,
#              }
#         except docker.errors.ImageNotFound:
#              log.error(f"Build stream finished without error, but image '{image_tag}' not found afterwards. Last detected potential ID: {image_id}")
#              return {"error": f"Build finished but image tag '{image_tag}' could not be found.", "logs": build_logs}
#         except Exception as img_get_err:
#              log.error(f"Build stream finished without error, but failed to get image details for '{image_tag}': {img_get_err}", exc_info=True)
#              return {"error": f"Build finished but failed to get image details for tag '{image_tag}'.", "logs": build_logs, "potential_image_id": image_id}

#     except docker.errors.BuildError as e:
#         # Use getattr to safely retrieve 'message' or fall back to e.args[0] or str(e)
#         error_message = getattr(e, 'message', e.args[0] if e.args else str(e))
#         # If the specific message is empty, try to get more from build_log
#         if not error_message and hasattr(e, 'build_log') and e.build_log:
#             error_message = "\n".join(e.build_log)

#         log.error(f"Docker build failed for tag '{image_tag}'. Error: {error_message}")
#         return {
#             "status": "failed",
#             "error": f"Build failed: {error_message}",
#             "logs": build_logs or getattr(e, 'build_log', []), # Ensure logs are captured
#         }
#     except docker.errors.APIError as e:
#         log.error(f"Docker API error during build: {e}", exc_info=True)
#         return {"error": f"Docker API error during build: {e}", "logs": build_logs}
#     except Exception as e:
#         log.error(f"Unexpected error during Docker build: {e}", exc_info=True)
#         return {"error": f"Unexpected error during build: {e}", "logs": build_logs}
#     finally:
#          if client:
#              try: await asyncio.to_thread(client.close)
#              except Exception: pass


# async def run_docker_container(
#     image_tag: str,
#     command: Optional[Union[str, List[str]]] = None,
#     ports: Optional[Dict[str, Optional[int]]] = None,  # Updated type hint
#     volumes: Optional[Dict[str, Dict[str, str]]] = None,
#     environment: Optional[Dict[str, str]] = None,
#     name: Optional[str] = None,
#     detach: bool = True,
#     remove: bool = False,
#     network_mode: str = "bridge",
# ) -> Dict[str, Any]:
#     """
#     Runs a Docker container using the host's Docker daemon.
#     Uses workspace configured via ToolConfig for volume path validation.

#     Args:
#         image_tag: The tag of the image to run.
#         command: Optional command to run in the container. This overrides the Dockerfile's CMD/ENTRYPOINT.
#         ports: Port mappings as {'container_port': host_port}.
#                Example: {'8080': 8080, '80': 8000, '3000': None}
#                Use None for host_port to let Docker assign a random port.
#         volumes: Optional volume mappings {'host_path_relative_to_workspace': {'bind': '/container/path', 'mode': 'rw'|'ro'}}.
#                  Host paths MUST be relative within the secure workspace.
#         environment: Optional dictionary of environment variables.
#         name: Optional name for the container.
#         detach: Run container in the background. Default: True. If False, the tool will return the container's log output immediately upon completion.
#         remove: Automatically remove the container when it exits. Default: False.
#         network_mode: Docker network mode ('bridge', 'host', 'none', etc.). Default: 'bridge'.

#     Returns:
#         A dictionary containing the container status, ID, etc., or an error dictionary.
#     """
#     log.info(f"Attempting to run Docker container from image '{image_tag}' with name '{name}'")

#     # Validate and normalize ports early as per advice
#     validated_ports = _validate_and_normalize_ports(ports)
#     # Only return an error if 'ports' was provided (i.e., not None) but the validation failed (returned None)
#     if ports is not None and validated_ports is None:
#         return {"error": "Invalid port configuration provided. Check logs for details."}


#     validated_volumes = {}
#     if volumes:
#         log.debug(f"Validating volume mappings: {volumes}")
#         for host_path_relative, bind_info in volumes.items():
#             # Use the imported validate_path function (now uses ToolConfig)
#             validated_host_path = validate_path(host_path_relative)

#             if not validated_host_path:
#                 # validate_path logs details if it fails (incl. if workspace isn't configured)
#                 error_msg = f"Invalid or disallowed host path in volume mapping: '{host_path_relative}'."
#                 return {"error": error_msg}

#             # Validate bind_info structure
#             if not isinstance(bind_info, dict) or 'bind' not in bind_info or 'mode' not in bind_info:
#                  error_msg = f"Invalid volume bind info for host path '{host_path_relative}'. Must be a dict including 'bind' and 'mode'."
#                  log.error(error_msg)
#                  return {"error": error_msg}
#             if bind_info['mode'] not in ['rw', 'ro']:
#                  error_msg = f"Invalid volume mode '{bind_info['mode']}' for host path '{host_path_relative}'. Must be 'rw' or 'ro'."
#                  log.error(error_msg)
#                  return {"error": error_msg}

#             # Use the absolute path returned by validate_path for the Docker API
#             validated_volumes[str(validated_host_path)] = bind_info
#             log.debug(f"Volume validated: Host '{validated_host_path}' -> Container '{bind_info['bind']}' ({bind_info['mode']})")
#         log.info("All volume paths validated successfully.")

#     client: Optional[docker.DockerClient] = None # Explicitly define type
#     container: Optional[Container] = None
#     try:
#         client = await _get_docker_client()
#         if not client:
#             return {"error": "Docker connection failed. Is Docker running?"}

#         log.info(f"Starting container '{name or 'unnamed'}' from image '{image_tag}'. Detach: {detach}, Remove: {remove}")

#         # Run the container using asyncio.to_thread
#         container_result = await asyncio.to_thread(
#             lambda: client.containers.run(
#                 image=image_tag,
#                 command=command, # <--- This argument already allows overriding CMD
#                 ports=validated_ports, # Use the validated and normalized ports here
#                 volumes=validated_volumes, # Use validated absolute host paths
#                 environment=environment,
#                 name=name,
#                 detach=detach,
#                 remove=remove,
#                 network_mode=network_mode,
#             )
#         )

#         if detach:
#             # If detached, 'container_result' is a Container object
#             container = container_result # Assign to container for potential reload/logging
#             container_id = container.id
#             # Need to reload to get updated status and ports after start
#             await asyncio.to_thread(container.reload)
#             status = container.status
#             # The 'ports' attribute on the container object might be a complex dict.
#             # It's returned as is, consistent with docker-py's internal representation.
#             assigned_ports = container.ports
#             log.info(f"Container '{container.name}' ({container_id[:12]}) started. Status: {status}")
#             return {
#                 "status": "success",
#                 "container_id": container_id,
#                 "container_name": container.name,
#                 "container_status": status,
#                 "ports": assigned_ports,
#             }
#         else:
#             # If not detached, 'container_result' is the log output (bytes)
#             logs = container_result.decode('utf-8', errors='ignore')
#             log.info(f"Container ran to completion (not detached).")
#             return {
#                 "status": "completed",
#                 "logs": logs,
#                 # Exit code is implicitly 0 if ContainerError wasn't raised by run()
#                 "exit_code": 0
#             }

#     except docker.errors.ContainerError as e:
#          container_name_for_log = getattr(e.container, 'name', name or "unknown") # Safer access
#          log_output = e.stderr.decode('utf-8', errors='ignore') if isinstance(e.stderr, bytes) else "N/A"
#          log.error(f"Container '{container_name_for_log}' failed. Exit code: {e.exit_status}. Stderr:\n{log_output}")
#          return {
#              "status": "failed",
#              "error": f"Container exited with non-zero status: {e.exit_status}",
#              "container_id": getattr(e.container, 'id', None), # Safer access
#              "container_name": container_name_for_log,
#              "exit_code": e.exit_status,
#              "logs": log_output,
#          }
#     except docker.errors.ImageNotFound:
#         log.error(f"Image not found: {image_tag}")
#         return {"error": f"Docker image '{image_tag}' not found."}
#     except docker.errors.APIError as e:
#         log.error(f"Docker API error during container run: {e}", exc_info=True)
#         error_str = str(e).lower()
#         if "port is already allocated" in error_str or "bind for" in error_str:
#             return {"error": f"Port conflict: A specified host port is likely already in use. Details: {e}"}
#         if "conflict: the container name" in error_str and name:
#              return {"error": f"Container name conflict: '{name}' is already in use. Details: {e}"}
#         return {"error": f"Docker API error: {e}"}
#     except Exception as e:
#         log.error(f"Unexpected error running container: {e}", exc_info=True)
#         return {"error": f"Unexpected error: {e}"}
#     finally:
#          if client:
#              try: await asyncio.to_thread(client.close)
#              except Exception: pass


# # --- Implemented Companion Tools ---
# # These tools do not interact with the workspace file system directly,
# # so they do not need changes related to ToolConfig or validate_path.

# async def list_running_containers(all: bool = False) -> Dict[str, Any]:
#     """
#     Lists Docker containers managed by the host daemon.

#     Args:
#        all (bool): If True, list all containers (including stopped). Default: False (only running).

#     Returns:
#         A dictionary containing a list of containers or an error.
#         Each container dict includes: id, name, image, status, ports.
#     """
#     log.info(f"Attempting to list {'all' if all else 'running'} Docker containers.")
#     client: Optional[docker.DockerClient] = None
#     try:
#         client = await _get_docker_client()
#         if not client:
#             return {"error": "Docker connection failed."}

#         containers: List[Container] = await asyncio.to_thread(client.containers.list, all=all)
#         container_list = []
#         for c in containers:
#             try: # Protect against errors fetching details for a single container
#                 await asyncio.to_thread(c.reload) # Ensure data is fresh
#                 container_list.append({
#                     "id": c.short_id,
#                     "name": c.name,
#                     "image": c.image.tags[0] if getattr(c, 'image', None) and getattr(c.image, 'tags', None) else str(getattr(c,'image', '?')), # Safer access
#                     "status": c.status,
#                     "ports": c.ports, # Dictionary of port mappings
#                 })
#             except Exception as detail_err:
#                 log.warning(f"Could not get full details for container {c.id[:12]}: {detail_err}")
#                 container_list.append({
#                     "id": c.short_id,
#                     "name": c.name or f"<{c.id[:12]}>",
#                     "image": "unknown",
#                     "status": "unknown",
#                     "ports": {},
#                     "error_fetching_details": str(detail_err),
#                 })

#         log.info(f"Found {len(container_list)} {'total' if all else 'running'} containers.")
#         return {"status": "success", "containers": container_list}

#     except docker.errors.APIError as e:
#        log.error(f"Docker API error listing containers: {e}", exc_info=True)
#        return {"error": f"Docker API error listing containers: {e}"}
#     except Exception as e:
#        log.error(f"Unexpected error listing containers: {e}", exc_info=True)
#        return {"error": f"Unexpected error listing containers: {e}"}
#     finally:
#          if client:
#             try: await asyncio.to_thread(client.close)
#             except Exception: pass


# async def get_container_logs(container_id_or_name: str, tail: Union[int, str] = 50) -> Dict[str, Any]:
#     """
#     Retrieves logs from a specific Docker container.

#     Args:
#         container_id_or_name: The ID (short or long) or name of the container.
#         tail: Number of lines to show from the end of the logs (int), or 'all' (str). Default: 50.

#     Returns:
#         A dictionary containing the logs or an.
#     """
#     log.info(f"Attempting to get logs for container '{container_id_or_name}', tail='{tail}'.")
#     client: Optional[docker.DockerClient] = None
#     try:
#         client = await _get_docker_client()
#         if not client:
#             return {"error": "Docker connection failed."}

#         container = await _get_container(client, container_id_or_name)
#         if not container:
#             return {"error": f"Container '{container_id_or_name}' not found."}

#         log.debug(f"Fetching logs for container '{container.name}' ({container.short_id}).")
#         # Validate tail parameter
#         valid_tail: Union[int, str] = 50 # Default to 50 if parsing fails
#         if isinstance(tail, str) and tail.lower() == 'all':
#             valid_tail = 'all'
#         elif isinstance(tail, int) and tail > 0:
#             valid_tail = tail
#         elif isinstance(tail, str) and tail.isdigit():
#             parsed_tail = int(tail)
#             if parsed_tail > 0:
#                 valid_tail = parsed_tail
#             else:
#                  log.warning(f"Invalid numeric tail value '{tail}', defaulting to 50.")
#                  # valid_tail remains 50
#         else:
#             log.warning(f"Invalid tail value '{tail}' (type: {type(tail)}), defaulting to 50.")
#             # valid_tail remains 50

#         logs_bytes: bytes = await asyncio.to_thread(
#             lambda: container.logs(
#                 tail=valid_tail,
#                 stdout=True,
#                 stderr=True,
#             )
#         )
#         logs_str = logs_bytes.decode('utf-8', errors='replace')

#         log.info(f"Successfully retrieved logs for '{container.name}'.")
#         return {
#             "status": "success",
#             "container_id": container.short_id,
#             "container_name": container.name,
#             "logs": logs_str
#         }

#     except docker.errors.APIError as e:
#        log.error(f"Docker API error getting logs for '{container_id_or_name}': {e}", exc_info=True)
#        return {"error": f"Docker API error getting logs: {e}"}
#     except Exception as e:
#        log.error(f"Unexpected error getting logs for '{container_id_or_name}': {e}", exc_info=True)
#        return {"error": f"Unexpected error getting logs: {e}"}
#     finally:
#          if client:
#             try: await asyncio.to_thread(client.close)
#             except Exception: pass


# async def stop_container(container_id_or_name: str, timeout: int = 10) -> Dict[str, Any]:
#     """
#     Stops a running Docker container gracefully (SIGTERM then SIGKILL after timeout).

#     Args:
#         container_id_or_name: The ID (short or long) or name of the container.
#         timeout: Seconds to wait for graceful shutdown before killing. Default: 10.

#     Returns:
#         A dictionary indicating success or failure.
#     """
#     log.info(f"Attempting to stop container '{container_id_or_name}' with timeout {timeout}s.")
#     client: Optional[docker.DockerClient] = None
#     try:
#         client = await _get_docker_client()
#         if not client:
#             return {"error": "Docker connection failed."}

#         container = await _get_container(client, container_id_or_name)
#         if not container:
#             return {"error": f"Container '{container_id_or_name}' not found."}

#         await asyncio.to_thread(container.reload)
#         current_status = container.status
#         log.debug(f"Container '{container.name}' current status: {current_status}")

#         if current_status == 'exited':
#              log.info(f"Container '{container.name}' is already stopped.")
#              return {"status": "success", "message": f"Container '{container.name}' was already stopped."}
#         if current_status not in ['running', 'restarting', 'paused']:
#             log.warning(f"Container '{container.name}' is not in a state that can be stopped (status: {current_status}).")
#             return {"error": f"Container '{container.name}' cannot be stopped (status: {current_status})."}

#         log.debug(f"Sending stop command to container '{container.name}' ({container.short_id}).")
#         await asyncio.to_thread(container.stop, timeout=timeout)

#         await asyncio.to_thread(container.reload)
#         final_status = container.status
#         log.info(f"Stop command finished. Container '{container.name}' final status: {final_status}.")

#         if final_status == 'exited':
#             return {"status": "success", "message": f"Container '{container.name}' stopped successfully."}
#         else:
#             log.warning(f"Container '{container.name}' status after stop command: {final_status}. Expected 'exited'.")
#             return {"status": "warning", "message": f"Stop command sent, but container final status is '{final_status}'. Manual check recommended."}

#     except docker.errors.APIError as e:
#        log.error(f"Docker API error stopping container '{container_id_or_name}': {e}", exc_info=True)
#        return {"error": f"Docker API error stopping container: {e}"}
#     except Exception as e:
#        log.error(f"Unexpected error stopping container '{container_id_or_name}': {e}", exc_info=True)
#        return {"error": f"Unexpected error stopping container: {e}"}
#     finally:
#          if client:
#             try: await asyncio.to_thread(client.close)
#             except Exception: pass


# async def remove_container(container_id_or_name: str, force: bool = False) -> Dict[str, Any]:
#    """
#    Removes a container (must be stopped unless force=True).

#    Args:
#        container_id_or_name: The ID (short or long) or name of the container.
#        force (bool): Force removal of a running container (SIGKILL). Default: False.

#    Returns:
#         A dictionary indicating success or failure.
#    """
#    log.info(f"Attempting to remove container '{container_id_or_name}', force={force}.")
#    client: Optional[docker.DockerClient] = None
#    try:
#        client = await _get_docker_client()
#        if not client:
#            return {"error": "Docker connection failed."}

#        container = await _get_container(client, container_id_or_name)
#        if not container:
#            log.info(f"Container '{container_id_or_name}' not found, considering it already removed.")
#            return {"status": "success", "message": f"Container '{container_id_or_name}' not found (already removed?)."}

#        if not force:
#            await asyncio.to_thread(container.reload)
#            current_status = container.status
#            if current_status not in ['created', 'exited', 'dead']:
#                 log.error(f"Cannot remove container '{container.name}' (status: {current_status}) without force=True.")
#                 return {"error": f"Container '{container.name}' is not stopped (status: {current_status}). Stop it first or use force=True."}

#        log.debug(f"Sending remove command for container '{container.name}' ({container.short_id}). Force: {force}")
#        await asyncio.to_thread(container.remove, force=force, v=True) # v=True removes associated anonymous volumes

#        # Verify removal
#        container_after_remove = await _get_container(client, container_id_or_name)
#        if container_after_remove is None:
#            log.info(f"Container '{container_id_or_name}' removed successfully.")
#            return {"status": "success", "message": f"Container '{container_id_or_name}' removed."}
#        else:
#             log.error(f"Remove command seemed successful, but container '{container_id_or_name}' still found.")
#             return {"error": "Container still exists after remove command executed without error."}

#    except docker.errors.APIError as e:
#        log.error(f"Docker API error removing container '{container_id_or_name}': {e}", exc_info=True)
#        if e.response.status_code == 404 or "no such container" in str(e).lower():
#             log.info(f"Container '{container_id_or_name}' not found during removal (API error 404), considering it removed.")
#             return {"status": "success", "message": f"Container '{container_id_or_name}' not found (already removed?)."}
#        if e.response.status_code == 409 or "conflict" in str(e).lower():
#            log.error(f"Conflict removing container '{container_id_or_name}'. It might be running or have dependencies. {e}")
#            return {"error": f"Conflict removing container: {e}. Check if it's stopped or has dependencies."}
#        return {"error": f"Docker API error removing container: {e}"}
#    except Exception as e:
#        log.error(f"Unexpected error removing container '{container_id_or_name}': {e}", exc_info=True)
#        return {"error": f"Unexpected error removing container: {e}"}
#    finally:
#          if client:
#             try: await asyncio.to_thread(client.close)
#             except Exception: pass

# # --- NEW TOOL: check_container_health ---
# async def check_container_health(container_id_or_name: str) -> Dict[str, Any]:
#     """
#     Checks the health status of a Docker container that has a HEALTHCHECK instruction.

#     Args:
#         container_id_or_name: The ID (short or long) or name of the container.

#     Returns:
#         A dictionary containing the container's health status, or an error.
#         If a health check is configured, it will return:
#         - status: 'healthy', 'unhealthy', 'starting', or 'no_healthcheck'
#         - log: A list of health check events, each with 'Start', 'End', 'ExitCode', 'Output'
#         - error: if any occurred during fetching
#     """
#     log.info(f"Attempting to check health for container '{container_id_or_name}'.")
#     client: Optional[docker.DockerClient] = None
#     try:
#         client = await _get_docker_client()
#         if not client:
#             return {"error": "Docker connection failed."}

#         container = await _get_container(client, container_id_or_name)
#         if not container:
#             return {"error": f"Container '{container_id_or_name}' not found."}

#         # Reload container to ensure latest state is fetched
#         await asyncio.to_thread(container.reload)

#         health_data = container.attrs.get('State', {}).get('Health')

#         if not health_data:
#             log.info(f"Container '{container.name}' does not have a HEALTHCHECK configured.")
#             return {
#                 "status": "no_healthcheck",
#                 "message": f"Container '{container.name}' does not have a HEALTHCHECK configured in its Dockerfile.",
#                 "container_id": container.short_id,
#                 "container_name": container.name
#             }

#         health_status = health_data.get('Status')
#         health_log = health_data.get('Log', [])

#         log.info(f"Health status for '{container.name}': {health_status}")
#         return {
#             "status": health_status,
#             "container_id": container.short_id,
#             "container_name": container.name,
#             "log": health_log
#         }

#     except docker.errors.APIError as e:
#         log.error(f"Docker API error checking health for '{container_id_or_name}': {e}", exc_info=True)
#         return {"error": f"Docker API error checking health: {e}"}
#     except Exception as e:
#         log.error(f"Unexpected error checking container health for '{container_id_or_name}': {e}", exc_info=True)
#         return {"error": f"Unexpected error checking health: {e}"}
#     finally:
#         if client:
#             try: await asyncio.to_thread(client.close)
#             except Exception: pass

# packages/mcp-server/src/mcp_server/tools/docker_tools.py

import asyncio
import logging
import docker
import docker.errors
import docker.models.containers
from docker.models.containers import Container # Explicit import for type hints
import json
import pathlib
from typing import Dict, Optional, Any, List, Union

log = logging.getLogger(__name__)

# --- Corrected Import from file_tools ---
# Import the ToolConfig class and the updated validate_path function
try:
    # Ensure this path is correct relative to mcp_server/tools/
    from .file_tools import ToolConfig, validate_path
    FILE_TOOLS_IMPORTED = True
    # We don't need to check ToolConfig.get_workspace() at import time,
    # validate_path and the tool functions will check it at runtime.
except ImportError as e:
    # Use critical level as this severely impacts tool functionality
    log.critical("CRITICAL IMPORT ERROR: Could not import 'ToolConfig' or 'validate_path' from file_tools. Docker volume path validation WILL NOT WORK and tools may fail.", exc_info=True)
    # Define dummy versions that clearly indicate failure and lack of security
    FILE_TOOLS_IMPORTED = False
    class ToolConfig: # Dummy class if import fails
        @staticmethod
        def get_workspace() -> Optional[pathlib.Path]:
            log.error("Using DUMMY ToolConfig - IMPORT FAILED")
            return None
    def validate_path(user_path: str) -> Optional[pathlib.Path]:
        log.error(f"Using DUMMY validate_path for '{user_path}' - IMPORT FAILED, NO SECURITY!")
        return None # Always fail validation if import failed


# --- Helper Function to Get Docker Client ---
async def _get_docker_client() -> Optional[docker.DockerClient]:
    """Gets and verifies connection to the Docker client."""
    client = None
    try:
        # Use run_in_executor for the potentially blocking docker.from_env()
        client = await asyncio.to_thread(docker.from_env)
        # Use run_in_executor for the blocking ping()
        await asyncio.to_thread(client.ping)
        log.debug("Docker client initialized and connection verified.")
        return client
    except docker.errors.DockerException as e:
        log.error(f"Failed to connect to Docker daemon: {e}")
        log.error("Please ensure Docker is running and accessible.")
        if client:
            try: await asyncio.to_thread(client.close)
            except Exception: pass
        return None
    except Exception as e:
        log.error(f"Unexpected error initializing Docker client: {e}", exc_info=True)
        if client:
            try: await asyncio.to_thread(client.close)
            except Exception: pass
        return None

# --- Helper Function to Get Container ---
async def _get_container(client: docker.DockerClient, container_id_or_name: str) -> Optional[Container]:
    """Safely gets a container object by ID or name."""
    try:
        # Use run_in_executor for the blocking containers.get()
        container = await asyncio.to_thread(client.containers.get, container_id_or_name)
        return container
    except docker.errors.NotFound:
        log.warning(f"Container '{container_id_or_name}' not found.")
        return None
    except docker.errors.APIError as e:
        log.error(f"Docker API error getting container '{container_id_or_name}': {e}")
        return None
    except Exception as e:
        log.error(f"Unexpected error getting container '{container_id_or_name}': {e}", exc_info=True)
        return None

# --- New Helper Function for Port Validation and Normalization ---
def _validate_and_normalize_ports(ports: Optional[Dict[str, Optional[int]]]) -> Optional[Dict]:
    """
    Validates and normalizes port mappings for Docker SDK.

    Accepts formats like:
    - {'8080': 8080} -> maps container port 8080 to host port 8080
    - {'80': 8080} -> maps container port 80 to host port 8080
    - {'8080': None} -> maps container port 8080 to random host port
    """
    if not ports:
        return None

    normalized_ports = {}
    for container_port_str, host_port in ports.items():
        try:
            # Ensure container_port is a valid integer
            container_port_int = int(container_port_str)
            if not (1 <= container_port_int <= 65535):
                raise ValueError(f"Invalid container port range: {container_port_str}. Must be between 1 and 65535.")

            # Validate host_port if provided
            if host_port is not None:
                host_port_int = int(host_port)
                if not (1 <= host_port_int <= 65535):
                    raise ValueError(f"Invalid host port range: {host_port}. Must be between 1 and 65535.")
                normalized_ports[container_port_int] = host_port_int
            else:
                normalized_ports[container_port_int] = None

        except (ValueError, TypeError) as e:
            log.error(f"Invalid port mapping provided: container_port='{container_port_str}', host_port='{host_port}'. Error: {e}")
            return None

    return normalized_ports

# --- Tool Implementations (Updated to use new validate_path) ---

async def build_docker_image(
    context_path: str,
    image_tag: str,
    dockerfile: str = "Dockerfile",
    build_args: Optional[Dict[str, str]] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Builds a Docker image using the host's Docker daemon.
    Uses workspace configured via ToolConfig for path validation.

    Args:
        context_path: The relative path within the workspace to use as the build context.
        image_tag: The tag to apply to the built image (e.g., 'my-app:latest').
        dockerfile: The relative path to the Dockerfile *within* the context_path. Defaults to 'Dockerfile'.
        build_args: Optional dictionary of build arguments.
        platform: Optional target platform for the build (e.g., 'linux/amd64').

    Returns:
        A dictionary containing build status, logs, and image details on success,
        or an error dictionary on failure.
    """
    log.info(f"Attempting to build Docker image '{image_tag}' from context '{context_path}'")

    # Use the imported validate_path function (which now uses ToolConfig internally)
    # Note: validate_path handles the case where ToolConfig hasn't been configured yet
    validated_context_path = validate_path(context_path)

    if not validated_context_path:
        # validate_path logs details if it fails (including if workspace isn't configured)
        return {"error": f"Invalid or disallowed context path: '{context_path}'."}
    if not validated_context_path.is_dir():
        return {"error": f"Context path is not a directory: '{context_path}'"}

    # Validate dockerfile path *relative* to the context and ensure it stays within workspace
    dockerfile_abs_path: Optional[pathlib.Path] = None
    try:
        # Resolve potential Dockerfile path relative to validated context
        potential_dockerfile_abs_path = validated_context_path.joinpath(dockerfile).resolve()

        # Now validate this potential absolute path using validate_path again.
        # To do this robustly, we need the workspace root from ToolConfig.
        workspace_root = ToolConfig.get_workspace()
        if not workspace_root:
             # This check is essential as validate_path needs it.
             log.error("Workspace root not configured via ToolConfig. Cannot validate Dockerfile path.")
             return {"error": "Workspace root not configured, cannot validate Dockerfile path."}

        # Convert the absolute path back to a relative path string for validation
        # This ensures it adheres to the same sandbox rules (no '..', etc.)
        try:
            relative_dockerfile_to_root = str(potential_dockerfile_abs_path.relative_to(workspace_root))
            validated_dockerfile_path_obj = validate_path(relative_dockerfile_to_root) # Validate the relative path string

            if not validated_dockerfile_path_obj:
                # validate_path already logged the reason
                log.warning(f"Resolved Dockerfile path '{potential_dockerfile_abs_path}' failed validation relative to workspace root.")
                return {"error": f"Dockerfile path '{dockerfile}' resolves outside the allowed workspace when combined with context '{context_path}'."}
            else:
                # Use the validated absolute path object
                dockerfile_abs_path = validated_dockerfile_path_obj

        except ValueError: # Could happen if paths are truly unrelated
            log.warning(f"Could not make potential Dockerfile path '{potential_dockerfile_abs_path}' relative to workspace root '{workspace_root}'.")
            return {"error": f"Dockerfile path '{dockerfile}' seems unrelated to workspace when combined with context '{context_path}'."}

        # Final check: ensure the validated path points to an existing file
        if not dockerfile_abs_path.is_file():
            return {"error": f"Dockerfile not found at expected validated path: '{dockerfile_abs_path}'"}

    except Exception as path_e:
        log.error(f"Error resolving or validating dockerfile path: {path_e}", exc_info=True)
        return {"error": f"Could not resolve or validate dockerfile path '{dockerfile}' relative to context '{context_path}'."}

    # Docker build API expects the dockerfile path *relative* to the context root
    dockerfile_rel_path = str(dockerfile_abs_path.relative_to(validated_context_path))

    build_logs = []
    image_id = None
    error_detail = None
    client: Optional[docker.DockerClient] = None # Explicitly define type

    try:
        client = await _get_docker_client()
        if not client:
            return {"error": "Docker connection failed. Is Docker running?"}

        log.info(f"Starting Docker build: context='{validated_context_path}', tag='{image_tag}', dockerfile='{dockerfile_rel_path}'")

        # Perform the build using asyncio.to_thread for the blocking call
        response_stream = await asyncio.to_thread(
            lambda: client.api.build(
                path=str(validated_context_path),
                dockerfile=dockerfile_rel_path,
                tag=image_tag,
                buildargs=build_args,
                rm=True,  # Remove intermediate containers
                decode=True, # Decode JSON stream objects
                platform=platform,
            )
        )

        # Process the build log stream
        for line in response_stream:
            if isinstance(line, dict):
                log_entry = line.get("stream", "").strip()
                if log_entry:
                    build_logs.append(log_entry)
                    log.debug(f"Build log: {log_entry}")
                if "errorDetail" in line:
                    error_detail = line["errorDetail"]["message"]
                    log.error(f"Docker build error reported in stream: {error_detail}")
                # Extract image ID robustly
                if "aux" in line and "ID" in line["aux"]:
                    possible_image_id = line["aux"]["ID"]
                    if isinstance(possible_image_id, str) and possible_image_id.startswith("sha256:"):
                         image_id = possible_image_id
                         log.debug(f"Detected Image ID from aux: {image_id}")
                elif "Successfully built" in log_entry:
                     parts = log_entry.split()
                     if len(parts) >= 3:
                         possible_image_id = parts[-1]
                         # Basic check for potential ID format (could be short or long hash)
                         if len(possible_image_id) >= 8:
                             image_id = possible_image_id # Assume this is it
                             log.debug(f"Detected Image ID from stream: {image_id}")

        # FIX APPLIED HERE: Pass error_detail as positional argument
        if error_detail:
             raise docker.errors.BuildError(error_detail, build_log=build_logs)

        # After successful build, get the image object to confirm ID and tags
        try:
             image = await asyncio.to_thread(lambda: client.images.get(image_tag))
             final_image_id = image.id
             tags = image.tags
             log.info(f"Docker build successful. Image ID: {final_image_id}, Tags: {tags}")
             return {
                 "status": "success",
                 "image_id": final_image_id, # Use ID from image object
                 "tags": tags,
                 "logs": build_logs,
             }
        except docker.errors.ImageNotFound:
             log.error(f"Build stream finished without error, but image '{image_tag}' not found afterwards. Last detected potential ID: {image_id}")
             return {"error": f"Build finished but image tag '{image_tag}' could not be found.", "logs": build_logs}
        except Exception as img_get_err:
             log.error(f"Build stream finished without error, but failed to get image details for '{image_tag}': {img_get_err}", exc_info=True)
             return {"error": f"Build finished but failed to get image details for tag '{image_tag}'.", "logs": build_logs, "potential_image_id": image_id}

    except docker.errors.BuildError as e:
        # Use getattr to safely retrieve 'message' or fall back to e.args[0] or str(e)
        error_message = getattr(e, 'message', e.args[0] if e.args else str(e))
        # If the specific message is empty, try to get more from build_log
        if not error_message and hasattr(e, 'build_log') and e.build_log:
            error_message = "\n".join(e.build_log)

        log.error(f"Docker build failed for tag '{image_tag}'. Error: {error_message}")
        return {
            "status": "failed",
            "error": f"Build failed: {error_message}",
            "logs": build_logs or getattr(e, 'build_log', []), # Ensure logs are captured
        }
    except docker.errors.APIError as e:
        log.error(f"Docker API error during build: {e}", exc_info=True)
        return {"error": f"Docker API error during build: {e}", "logs": build_logs}
    except Exception as e:
        log.error(f"Unexpected error during Docker build: {e}", exc_info=True)
        return {"error": f"Unexpected error during build: {e}", "logs": build_logs}
    finally:
         if client:
             try: await asyncio.to_thread(client.close)
             except Exception: pass


async def run_docker_container(
    image_tag: str,
    command: Optional[Union[str, List[str]]] = None,
    ports: Optional[Dict[str, Optional[int]]] = None,
    volumes: Optional[Dict[str, Dict[str, str]]] = None,
    environment: Optional[Dict[str, str]] = None,
    name: Optional[str] = None,
    detach: bool = True,
    remove: bool = False,
    network_mode: str = "bridge",
) -> Dict[str, Any]:
    """
    Runs a Docker container using the host's Docker daemon.
    Uses workspace configured via ToolConfig for volume path validation.

    Args:
        image_tag: The tag of the image to run.
        command: Optional command to run in the container. This overrides the Dockerfile's CMD/ENTRYPOINT.
        ports: Port mappings as {'container_port': host_port}.
               Example: {'8080': 8080, '80': 8000, '3000': None}
               Use None for host_port to let Docker assign a random port.
        volumes: Optional volume mappings {'host_path_relative_to_workspace': {'bind': '/container/path', 'mode': 'rw'|'ro'}}.
                 Host paths MUST be relative within the secure workspace.
        environment: Optional dictionary of environment variables.
        name: Optional name for the container.
        detach: Run container in the background. Default: True. If False, the tool will return the container's log output immediately upon completion.
        remove: Automatically remove the container when it exits. Default: False.
        network_mode: Docker network mode ('bridge', 'host', 'none', etc.). Default: 'bridge'.

    Returns:
        A dictionary containing the container status, ID, etc., or an error dictionary.
    """
    log.info(f"Attempting to run Docker container from image '{image_tag}' with name '{name}'")

    # Validate and normalize ports early as per advice
    validated_ports = _validate_and_normalize_ports(ports)
    # Only return an error if 'ports' was provided (i.e., not None) but the validation failed (returned None)
    if ports is not None and validated_ports is None:
        return {"error": "Invalid port configuration provided. Check logs for details."}

    validated_volumes = {}
    if volumes:
        log.debug(f"Validating volume mappings: {volumes}")
        for host_path_relative, bind_info in volumes.items():
            # Use the imported validate_path function (now uses ToolConfig)
            validated_host_path = validate_path(host_path_relative)

            if not validated_host_path:
                # validate_path logs details if it fails (incl. if workspace isn't configured)
                error_msg = f"Invalid or disallowed host path in volume mapping: '{host_path_relative}'."
                return {"error": error_msg}

            # Validate bind_info structure
            if not isinstance(bind_info, dict) or 'bind' not in bind_info or 'mode' not in bind_info:
                 error_msg = f"Invalid volume bind info for host path '{host_path_relative}'. Must be a dict including 'bind' and 'mode'."
                 log.error(error_msg)
                 return {"error": error_msg}
            if bind_info['mode'] not in ['rw', 'ro']:
                 error_msg = f"Invalid volume mode '{bind_info['mode']}' for host path '{host_path_relative}'. Must be 'rw' or 'ro'."
                 log.error(error_msg)
                 return {"error": error_msg}

            # Use the absolute path returned by validate_path for the Docker API
            validated_volumes[str(validated_host_path)] = bind_info
            log.debug(f"Volume validated: Host '{validated_host_path}' -> Container '{bind_info['bind']}' ({bind_info['mode']})")
        log.info("All volume paths validated successfully.")

    client: Optional[docker.DockerClient] = None
    container: Optional[Container] = None
    try:
        client = await _get_docker_client()
        if not client:
            return {"error": "Docker connection failed. Is Docker running?"}

        log.info(f"Starting container '{name or 'unnamed'}' from image '{image_tag}'")

        # Modified approach: Always run detached initially to avoid ContainerError
        container = await asyncio.to_thread(
            lambda: client.containers.run(
                image=image_tag,
                command=command,
                ports=validated_ports,
                volumes=validated_volumes,
                environment=environment,
                name=name,
                detach=True,  # Always detach initially
                remove=False,  # Don't auto-remove so we can get logs
                network_mode=network_mode,
            )
        )

        container_id = container.id
        container_name = container.name

        # If the original request was for detached mode, return immediately
        if detach:
            # Reload to get updated status and ports after start
            await asyncio.to_thread(container.reload)
            status = container.status
            assigned_ports = container.ports
            log.info(f"Container '{container_name}' ({container_id[:12]}) started. Status: {status}")

            # If remove was requested in detach mode, we can't remove it immediately
            if remove:
                log.warning(f"Container '{container_name}' was requested to be removed, but it's running in detached mode. Manual removal required.")

            return {
                "status": "success",
                "container_id": container_id,
                "container_name": container_name,
                "container_status": status,
                "ports": assigned_ports,
            }
        else:
            # For non-detached mode, wait for completion and get logs
            log.info(f"Waiting for container '{container_name}' to complete...")

            # Wait for the container to finish
            wait_result = await asyncio.to_thread(container.wait)
            exit_code = wait_result.get('StatusCode', -1)

            # Get logs (both stdout and stderr)
            logs_bytes = await asyncio.to_thread(
                lambda: container.logs(stdout=True, stderr=True)
            )
            logs = logs_bytes.decode('utf-8', errors='ignore')

            # Remove the container if requested
            if remove:
                try:
                    await asyncio.to_thread(container.remove)
                    log.info(f"Container '{container_name}' removed after completion.")
                except Exception as remove_err:
                    log.warning(f"Failed to remove container '{container_name}': {remove_err}")

            # Return appropriate response based on exit code
            if exit_code == 0:
                log.info(f"Container '{container_name}' completed successfully.")
                return {
                    "status": "completed",
                    "container_id": container_id,
                    "container_name": container_name,
                    "exit_code": exit_code,
                    "logs": logs,
                }
            else:
                log.error(f"Container '{container_name}' failed with exit code: {exit_code}")
                return {
                    "status": "failed",
                    "error": f"Container exited with non-zero status: {exit_code}",
                    "container_id": container_id,
                    "container_name": container_name,
                    "exit_code": exit_code,
                    "logs": logs,
                }

    except docker.errors.ImageNotFound:
        log.error(f"Image not found: {image_tag}")
        return {"error": f"Docker image '{image_tag}' not found."}
    except docker.errors.APIError as e:
        log.error(f"Docker API error during container run: {e}", exc_info=True)
        error_str = str(e).lower()
        if "port is already allocated" in error_str or "bind for" in error_str:
            return {"error": f"Port conflict: A specified host port is likely already in use. Details: {e}"}
        if "conflict: the container name" in error_str and name:
             return {"error": f"Container name conflict: '{name}' is already in use. Details: {e}"}
        return {"error": f"Docker API error: {e}"}
    except Exception as e:
        log.error(f"Unexpected error running container: {e}", exc_info=True)
        return {"error": f"Unexpected error: {e}"}
    finally:
        if client:
            try:
                await asyncio.to_thread(client.close)
            except Exception:
                pass


# --- Implemented Companion Tools ---
# These tools do not interact with the workspace file system directly,
# so they do not need changes related to ToolConfig or validate_path.

async def list_running_containers(all: bool = False) -> Dict[str, Any]:
    """
    Lists Docker containers managed by the host daemon.

    Args:
       all (bool): If True, list all containers (including stopped). Default: False (only running).

    Returns:
        A dictionary containing a list of containers or an error.
        Each container dict includes: id, name, image, status, ports.
    """
    log.info(f"Attempting to list {'all' if all else 'running'} Docker containers.")
    client: Optional[docker.DockerClient] = None
    try:
        client = await _get_docker_client()
        if not client:
            return {"error": "Docker connection failed."}

        containers: List[Container] = await asyncio.to_thread(client.containers.list, all=all)
        container_list = []
        for c in containers:
            try: # Protect against errors fetching details for a single container
                await asyncio.to_thread(c.reload) # Ensure data is fresh
                container_list.append({
                    "id": c.short_id,
                    "name": c.name,
                    "image": c.image.tags[0] if getattr(c, 'image', None) and getattr(c.image, 'tags', None) else str(getattr(c,'image', '?')), # Safer access
                    "status": c.status,
                    "ports": c.ports, # Dictionary of port mappings
                })
            except Exception as detail_err:
                log.warning(f"Could not get full details for container {c.id[:12]}: {detail_err}")
                container_list.append({
                    "id": c.short_id,
                    "name": c.name or f"<{c.id[:12]}>",
                    "image": "unknown",
                    "status": "unknown",
                    "ports": {},
                    "error_fetching_details": str(detail_err),
                })

        log.info(f"Found {len(container_list)} {'total' if all else 'running'} containers.")
        return {"status": "success", "containers": container_list}

    except docker.errors.APIError as e:
       log.error(f"Docker API error listing containers: {e}", exc_info=True)
       return {"error": f"Docker API error listing containers: {e}"}
    except Exception as e:
       log.error(f"Unexpected error listing containers: {e}", exc_info=True)
       return {"error": f"Unexpected error listing containers: {e}"}
    finally:
         if client:
            try: await asyncio.to_thread(client.close)
            except Exception: pass


async def get_container_logs(container_id_or_name: str, tail: Union[int, str] = 50) -> Dict[str, Any]:
    """
    Retrieves logs from a specific Docker container.

    Args:
        container_id_or_name: The ID (short or long) or name of the container.
        tail: Number of lines to show from the end of the logs (int), or 'all' (str). Default: 50.

    Returns:
        A dictionary containing the logs or an.
    """
    log.info(f"Attempting to get logs for container '{container_id_or_name}', tail='{tail}'.")
    client: Optional[docker.DockerClient] = None
    try:
        client = await _get_docker_client()
        if not client:
            return {"error": "Docker connection failed."}

        container = await _get_container(client, container_id_or_name)
        if not container:
            return {"error": f"Container '{container_id_or_name}' not found."}

        log.debug(f"Fetching logs for container '{container.name}' ({container.short_id}).")
        # Validate tail parameter
        valid_tail: Union[int, str] = 50 # Default to 50 if parsing fails
        if isinstance(tail, str) and tail.lower() == 'all':
            valid_tail = 'all'
        elif isinstance(tail, int) and tail > 0:
            valid_tail = tail
        elif isinstance(tail, str) and tail.isdigit():
            parsed_tail = int(tail)
            if parsed_tail > 0:
                valid_tail = parsed_tail
            else:
                 log.warning(f"Invalid numeric tail value '{tail}', defaulting to 50.")
                 # valid_tail remains 50
        else:
            log.warning(f"Invalid tail value '{tail}' (type: {type(tail)}), defaulting to 50.")
            # valid_tail remains 50

        logs_bytes: bytes = await asyncio.to_thread(
            lambda: container.logs(
                tail=valid_tail,
                stdout=True,
                stderr=True,
            )
        )
        logs_str = logs_bytes.decode('utf-8', errors='replace')

        log.info(f"Successfully retrieved logs for '{container.name}'.")
        return {
            "status": "success",
            "container_id": container.short_id,
            "container_name": container.name,
            "logs": logs_str
        }

    except docker.errors.APIError as e:
       log.error(f"Docker API error getting logs for '{container_id_or_name}': {e}", exc_info=True)
       return {"error": f"Docker API error getting logs: {e}"}
    except Exception as e:
       log.error(f"Unexpected error getting logs for '{container_id_or_name}': {e}", exc_info=True)
       return {"error": f"Unexpected error getting logs: {e}"}
    finally:
         if client:
            try: await asyncio.to_thread(client.close)
            except Exception: pass


async def stop_container(container_id_or_name: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Stops a running Docker container gracefully (SIGTERM then SIGKILL after timeout).

    Args:
        container_id_or_name: The ID (short or long) or name of the container.
        timeout: Seconds to wait for graceful shutdown before killing. Default: 10.

    Returns:
        A dictionary indicating success or failure.
    """
    log.info(f"Attempting to stop container '{container_id_or_name}' with timeout {timeout}s.")
    client: Optional[docker.DockerClient] = None
    try:
        client = await _get_docker_client()
        if not client:
            return {"error": "Docker connection failed."}

        container = await _get_container(client, container_id_or_name)
        if not container:
            return {"error": f"Container '{container_id_or_name}' not found."}

        await asyncio.to_thread(container.reload)
        current_status = container.status
        log.debug(f"Container '{container.name}' current status: {current_status}")

        if current_status == 'exited':
             log.info(f"Container '{container.name}' is already stopped.")
             return {"status": "success", "message": f"Container '{container.name}' was already stopped."}
        if current_status not in ['running', 'restarting', 'paused']:
            log.warning(f"Container '{container.name}' is not in a state that can be stopped (status: {current_status}).")
            return {"error": f"Container '{container.name}' cannot be stopped (status: {current_status})."}

        log.debug(f"Sending stop command to container '{container.name}' ({container.short_id}).")
        await asyncio.to_thread(container.stop, timeout=timeout)

        await asyncio.to_thread(container.reload)
        final_status = container.status
        log.info(f"Stop command finished. Container '{container.name}' final status: {final_status}.")

        if final_status == 'exited':
            return {"status": "success", "message": f"Container '{container.name}' stopped successfully."}
        else:
            log.warning(f"Container '{container.name}' status after stop command: {final_status}. Expected 'exited'.")
            return {"status": "warning", "message": f"Stop command sent, but container final status is '{final_status}'. Manual check recommended."}

    except docker.errors.APIError as e:
       log.error(f"Docker API error stopping container '{container_id_or_name}': {e}", exc_info=True)
       return {"error": f"Docker API error stopping container: {e}"}
    except Exception as e:
       log.error(f"Unexpected error stopping container '{container_id_or_name}': {e}", exc_info=True)
       return {"error": f"Unexpected error stopping container: {e}"}
    finally:
         if client:
            try: await asyncio.to_thread(client.close)
            except Exception: pass


async def remove_container(container_id_or_name: str, force: bool = False) -> Dict[str, Any]:
   """
   Removes a container (must be stopped unless force=True).

   Args:
       container_id_or_name: The ID (short or long) or name of the container.
       force (bool): Force removal of a running container (SIGKILL). Default: False.

   Returns:
        A dictionary indicating success or failure.
   """
   log.info(f"Attempting to remove container '{container_id_or_name}', force={force}.")
   client: Optional[docker.DockerClient] = None
   try:
       client = await _get_docker_client()
       if not client:
           return {"error": "Docker connection failed."}

       container = await _get_container(client, container_id_or_name)
       if not container:
           log.info(f"Container '{container_id_or_name}' not found, considering it already removed.")
           return {"status": "success", "message": f"Container '{container_id_or_name}' not found (already removed?)."}

       if not force:
           await asyncio.to_thread(container.reload)
           current_status = container.status
           if current_status not in ['created', 'exited', 'dead']:
                log.error(f"Cannot remove container '{container.name}' (status: {current_status}) without force=True.")
                return {"error": f"Container '{container.name}' is not stopped (status: {current_status}). Stop it first or use force=True."}

       log.debug(f"Sending remove command for container '{container.name}' ({container.short_id}). Force: {force}")
       await asyncio.to_thread(container.remove, force=force, v=True) # v=True removes associated anonymous volumes

       # Verify removal
       container_after_remove = await _get_container(client, container_id_or_name)
       if container_after_remove is None:
           log.info(f"Container '{container_id_or_name}' removed successfully.")
           return {"status": "success", "message": f"Container '{container_id_or_name}' removed."}
       else:
            log.error(f"Remove command seemed successful, but container '{container_id_or_name}' still found.")
            return {"error": "Container still exists after remove command executed without error."}

   except docker.errors.APIError as e:
       log.error(f"Docker API error removing container '{container_id_or_name}': {e}", exc_info=True)
       if e.response.status_code == 404 or "no such container" in str(e).lower():
            log.info(f"Container '{container_id_or_name}' not found during removal (API error 404), considering it removed.")
            return {"status": "success", "message": f"Container '{container_id_or_name}' not found (already removed?)."}
       if e.response.status_code == 409 or "conflict" in str(e).lower():
           log.error(f"Conflict removing container '{container_id_or_name}'. It might be running or have dependencies. {e}")
           return {"error": f"Conflict removing container: {e}. Check if it's stopped or has dependencies."}
       return {"error": f"Docker API error removing container: {e}"}
   except Exception as e:
       log.error(f"Unexpected error removing container '{container_id_or_name}': {e}", exc_info=True)
       return {"error": f"Unexpected error removing container: {e}"}
   finally:
         if client:
            try: await asyncio.to_thread(client.close)
            except Exception: pass

# --- NEW TOOL: check_container_health ---
async def check_container_health(container_id_or_name: str) -> Dict[str, Any]:
    """
    Checks the health status of a Docker container that has a HEALTHCHECK instruction.

    Args:
        container_id_or_name: The ID (short or long) or name of the container.

    Returns:
        A dictionary containing the container's health status, or an error.
        If a health check is configured, it will return:
        - status: 'healthy', 'unhealthy', 'starting', or 'no_healthcheck'
        - log: A list of health check events, each with 'Start', 'End', 'ExitCode', 'Output'
        - error: if any occurred during fetching
    """
    log.info(f"Attempting to check health for container '{container_id_or_name}'.")
    client: Optional[docker.DockerClient] = None
    try:
        client = await _get_docker_client()
        if not client:
            return {"error": "Docker connection failed."}

        container = await _get_container(client, container_id_or_name)
        if not container:
            return {"error": f"Container '{container_id_or_name}' not found."}

        # Reload container to ensure latest state is fetched
        await asyncio.to_thread(container.reload)

        health_data = container.attrs.get('State', {}).get('Health')

        if not health_data:
            log.info(f"Container '{container.name}' does not have a HEALTHCHECK configured.")
            return {
                "status": "no_healthcheck",
                "message": f"Container '{container.name}' does not have a HEALTHCHECK configured in its Dockerfile.",
                "container_id": container.short_id,
                "container_name": container.name
            }

        health_status = health_data.get('Status')
        health_log = health_data.get('Log', [])

        log.info(f"Health status for '{container.name}': {health_status}")
        return {
            "status": health_status,
            "container_id": container.short_id,
            "container_name": container.name,
            "log": health_log
        }

    except docker.errors.APIError as e:
        log.error(f"Docker API error checking health for '{container_id_or_name}': {e}", exc_info=True)
        return {"error": f"Docker API error checking health: {e}"}
    except Exception as e:
        log.error(f"Unexpected error checking container health for '{container_id_or_name}': {e}", exc_info=True)
        return {"error": f"Unexpected error checking health: {e}"}
    finally:
        if client:
            try: await asyncio.to_thread(client.close)
            except Exception: pass
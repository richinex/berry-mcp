import asyncio
import logging
import docker
import tempfile
import os
import time
import shlex
import re
import json # Import json for explicit serialization if needed
from typing import Dict, Optional, Any, List, Literal

log = logging.getLogger(__name__)

# --- Configuration ---

# Ensure DEBUG logging is set here during development for detailed sandbox output
# log.setLevel(logging.DEBUG) # <--- Keep this commented in final, uncomment for debugging


# --- NEW: Language Configuration Mapping ---
LANGUAGE_CONFIG = {
    "python": {
        "image": "python-sandbox-image:latest", # Your custom Python image
        "filename": "user_script.py",
        "command_template": "python /sandbox/{filename}", # Template using filename
        "allowed_libraries": { # Python specific library allowlist
            "flask", "numpy", "pandas", "scipy", "requests", "matplotlib", "scikit-learn"
        }
    },
    "golang": {
        "image": "go-sandbox-image:latest", # The Go image you just built
        "filename": "main.go", # Go convention
        # Command requires building THEN running the output binary
        "command_template": "go build -o /tmp/main_bin /sandbox/{filename} && /tmp/main_bin",
        "allowed_libraries": None # Go uses modules, validation is different (or skip for now)
    },
    "nodejs": { # NEW: Node.js configuration
        "image": "node-sandbox-image:latest", # Your custom Node.js image
        "filename": "user_script.js",
        "command_template": "node /sandbox/{filename}",
        "allowed_libraries": None # Can add an array of allowed npm packages if needed
    },
}
# --- End Language Configuration ---

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MEMORY_LIMIT = "256m"

# --- Helper Function (Now Language Aware) ---
async def _run_in_docker_sandbox(
    code: str,
    language: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    mem_limit: str = DEFAULT_MEMORY_LIMIT,
    network_mode: str = "none",
) -> Dict[str, Any]:
    """
    Internal function to execute code within a language-specific Docker sandbox.
    Handles build steps for compiled languages like Go.
    """
    internal_result: Dict[str, Any] = {
        "stdout": "", "stderr": "", "exit_code": None,
        "error": None, "duration_seconds": 0,
    }
    start_time = time.monotonic()
    lang_lower = language.lower()

    # --- Get Language Config ---
    config = LANGUAGE_CONFIG.get(lang_lower)
    if not config:
        internal_result["error"] = f"Unsupported language: {language}. Supported: {list(LANGUAGE_CONFIG.keys())}"
        internal_result["duration_seconds"] = round(time.monotonic() - start_time, 2)
        return internal_result

    docker_image = config["image"]
    script_filename = config["filename"]
    command_template = config["command_template"]

    # --- Prepare Execution ---
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path_host = os.path.join(tmpdir, script_filename)
        # Container path for the source file (always /sandbox)
        script_path_container = f"/sandbox/{script_filename}"

        try:
            with open(script_path_host, 'w', encoding='utf-8') as f: f.write(code)
            log.debug(f"Code written to {script_path_host}")
        except Exception as e:
            log.error(f"Failed to write code to temporary file: {e}", exc_info=True)
            internal_result["error"] = f"Internal error: Failed to prepare script file: {e}"
            internal_result["duration_seconds"] = round(time.monotonic() - start_time, 2)
            return internal_result

        # --- Construct Docker Command ---
        # The command needs to be run via shell for languages like Go (build && run)
        # For simple execution like Python or Node.js, `shlex.split` might be safer
        # but a general `sh -c` approach handles all cases robustly.
        full_cmd_str = command_template.format(filename=script_filename)
        docker_cmd_array = ["/bin/sh", "-c", full_cmd_str] # More robust for composite commands
        log.debug(f"Docker command array for {language}: {docker_cmd_array}")

        docker_client = None
        container_run_result = None
        try:
            docker_client = await asyncio.to_thread(docker.from_env)
            await asyncio.to_thread(docker_client.ping)
            log.info(f"Docker client initialized. Running {language} code in image '{docker_image}'...")

            # --- Docker Run ---
            # Mount source code read-only to /sandbox
            # Working directory should be /sandbox for script execution
            container_run_result = await asyncio.to_thread(
                lambda: docker_client.containers.run(
                    image=docker_image,
                    command=docker_cmd_array, # Pass as list for shell execution
                    volumes={tmpdir: {'bind': '/sandbox', 'mode': 'ro'}},
                    working_dir='/sandbox',
                    mem_limit=mem_limit,
                    network_mode=network_mode,
                    remove=True,
                    stdout=True, stderr=True, detach=False,
                )
            )
            # Docker SDK combines stdout and stderr into the returned bytes on success
            # If the command executes successfully, the output is stdout. stderr is captured by error.
            # If a ContainerError occurs, stderr might be populated.
            internal_result["stdout"] = container_run_result.decode('utf-8', errors='ignore')
            internal_result["stderr"] = "" # Assuming success means no stderr from the command itself
            internal_result["exit_code"] = 0
            log.info(f"{language} container execution successful (exit code 0).")

        except docker.errors.ContainerError as e:
            log.warning(f"{language} container execution failed with exit code {e.exit_status}")
            # docker-py's ContainerError captures stdout/stderr in e.stdout/e.stderr
            stdout_output = e.stdout.decode('utf-8', errors='ignore') if e.stdout else ""
            stderr_output = e.stderr.decode('utf-8', errors='ignore') if e.stderr else ""
            log.debug(f"ContainerError stdout: {stdout_output}")
            log.debug(f"ContainerError stderr: {stderr_output}")

            internal_result["stdout"] = stdout_output
            internal_result["stderr"] = stderr_output
            internal_result["exit_code"] = e.exit_status
            internal_result["error"] = f"Code execution failed inside container (Exit Code: {e.exit_status}). Check stderr for details."
        except docker.errors.ImageNotFound:
            log.error(f"Docker image not found: {docker_image}")
            internal_result["error"] = f"Required Docker image '{docker_image}' not found. Please build it."
        except docker.errors.APIError as e:
            log.error(f"Docker API error: {e}", exc_info=True)
            internal_result["error"] = f"Docker API error: {e}"
        except Exception as e:
            log.error(f"Unexpected error during Docker execution: {e}", exc_info=True)
            internal_result["error"] = f"Unexpected error during Docker execution: {e}"

    internal_result["duration_seconds"] = round(time.monotonic() - start_time, 2)
    log.info(f"Sandbox helper ({language}) finished in {internal_result['duration_seconds']:.2f}s. Exit code: {internal_result['exit_code']}")
    return internal_result


# --- Main Tool Function (Now Multi-Lingual) ---
async def execute_code_in_sandbox(
    code: str,
    language: str,
    timeout_override_seconds: Optional[int] = None,
    memory_limit_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes provided code in a specified language (e.g., python, golang, nodejs)
    within a secure, language-specific Docker sandbox using pre-built images.
    ALWAYS returns a dictionary containing execution results.

    **WARNING:** Executes arbitrary code. Security relies heavily on proper Docker
               image vetting, configuration, and resource limits.

    Args:
        code: The source code snippet to execute.
        language: The programming language (e.g., 'python', 'golang', 'nodejs'). Must match configured images.
        timeout_override_seconds: Optional: Informational timeout value.
        memory_limit_override: Optional: Override container memory limit (e.g., "512m").

    Returns:
        Dict[str, Any]: Execution status: {"stdout": ..., "stderr": ..., "exit_code": ..., "error": ...}
    """
    log.warning(f"Executing code in sandbox for language '{language}'. SECURITY RISK.")

    timeout = timeout_override_seconds if timeout_override_seconds and timeout_override_seconds > 0 else DEFAULT_TIMEOUT_SECONDS
    mem_limit = memory_limit_override if memory_limit_override else DEFAULT_MEMORY_LIMIT
    wrapper_timeout = timeout + 20 # Add more buffer for potential compile steps

    try:
         execution_result = await asyncio.wait_for(
             _run_in_docker_sandbox(
                 code=code, language=language,
                 timeout=timeout, mem_limit=mem_limit,
                 network_mode="none" # Keep this default unless specifically needed
             ),
             timeout=wrapper_timeout
         )
    except asyncio.TimeoutError:
         log.error(f"Overall sandbox operation timed out after {wrapper_timeout} seconds.")
         execution_result = {
             "stdout": "", "stderr": f"Operation timed out after {wrapper_timeout}s.",
             "exit_code": -1, "error": "Sandbox operation exceeded overall time limit.",
             "duration_seconds": wrapper_timeout, "llm_analysis": None
         }
    except Exception as e:
         log.error(f"Unexpected error calling _run_in_docker_sandbox wrapper: {e}", exc_info=True)
         execution_result = {
             "stdout": "", "stderr": str(e), "exit_code": -1,
             "error": f"Failed to initiate sandbox execution: {e}",
             "duration_seconds": 0, "llm_analysis": None
         }

    # Ensure essential keys exist (provide defaults if not set by _run_in_docker_sandbox)
    execution_result.setdefault("stdout", "")
    execution_result.setdefault("stderr", "")
    # Set exit_code to -1 if there's an error, otherwise default to 0
    execution_result.setdefault("exit_code", -1 if execution_result.get("error") else 0)
    execution_result.setdefault("error", None)
    execution_result.setdefault("duration_seconds", 0)
    # This 'llm_analysis' key is not something the tool generates, it's usually for the LLM itself to populate if it was doing analysis on code output
    execution_result.setdefault("llm_analysis", None)

    if execution_result["exit_code"] == 0 and execution_result["error"] is None:
        log.info(f"Sandbox execution successful ({language}). Returning result dictionary.")
    else:
        log.warning(f"Sandbox execution failed ({language}). Returning result dictionary with error details.")

    return execution_result

# --- Example usage (for testing) ---
async def main_test():
    # Setup logging for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    # If you want to see DEBUG logs from this module specifically:
    log.setLevel(logging.DEBUG)


    log.info("\n--- Test Python: Simple Print ---")
    python_code_print = """
print("Hello from Python sandbox!")
"""
    if "python" in LANGUAGE_CONFIG:
        result_py_print = await execute_code_in_sandbox(code=python_code_print, language="python")
        print(f"Python Print Result:\n---\n{json.dumps(result_py_print, indent=2)}\n---")
    else:
        log.warning("Skipping Python Print Test: 'python' not configured in LANGUAGE_CONFIG.")

    log.info("\n--- Test Python: Runtime Error ---")
    python_code_error = """
1/0 # Division by zero
"""
    if "python" in LANGUAGE_CONFIG:
        result_py_error = await execute_code_in_sandbox(code=python_code_error, language="python")
        print(f"Python Error Result:\n---\n{json.dumps(result_py_error, indent=2)}\n---")
    else:
        log.warning("Skipping Python Error Test: 'python' not configured.")


    log.info("\n--- Test Go: Simple Print ---")
    go_code_print = """
package main
import "fmt"
func main() {
    fmt.Println("Hello from Go sandbox!")
}
"""
    if "golang" in LANGUAGE_CONFIG:
        result_go_print = await execute_code_in_sandbox(code=go_code_print, language="golang")
        print(f"Go Print Result:\n---\n{json.dumps(result_go_print, indent=2)}\n---")
    else:
        log.warning("Skipping Go Print Test: 'golang' not configured in LANGUAGE_CONFIG.")

    log.info("\n--- Test Go: Compile Error ---")
    go_code_error = """
package main
import "fmt"
func main() {
    fmt.Println("Hello without quotes) // Syntax error
}
"""
    if "golang" in LANGUAGE_CONFIG:
        result_go_error = await execute_code_in_sandbox(code=go_code_error, language="golang")
        print(f"Go Error Result:\n---\n{json.dumps(result_go_error, indent=2)}\n---") # Should show stderr from 'go build'
    else:
         log.warning("Skipping Go Error Test: 'golang' not configured.")

    # --- NEW: Node.js Test ---
    log.info("\n--- Test Node.js: Simple Print ---")
    node_code_print = """
console.log("Hello from Node.js sandbox!");
"""
    if "nodejs" in LANGUAGE_CONFIG:
        result_node_print = await execute_code_in_sandbox(code=node_code_print, language="nodejs")
        print(f"Node.js Print Result:\n---\n{json.dumps(result_node_print, indent=2)}\n---")
    else:
        log.warning("Skipping Node.js Print Test: 'nodejs' not configured in LANGUAGE_CONFIG.")

    log.info("\n--- Test Node.js: Runtime Error ---")
    node_code_error = """
console.log("Hello from Node.js!");
throw new Error("Intentional Node.js runtime error");
"""
    if "nodejs" in LANGUAGE_CONFIG:
        result_node_error = await execute_code_in_sandbox(code=node_code_error, language="nodejs")
        print(f"Node.js Error Result:\n---\n{json.dumps(result_node_error, indent=2)}\n---")
    else:
        log.warning("Skipping Node.js Error Test: 'nodejs' not configured.")


    log.info("\n--- Code Execution Sandbox Test Complete ---")


if __name__ == "__main__":
    # Requires Docker running, permissions, and the necessary images built
    try:
        import docker
        import re
        import json
        asyncio.run(main_test())
    except ImportError as e:
        print(f"Import error: {e}. Please install required libraries (e.g., 'docker').")
    except Exception as main_err:
        print(f"An error occurred: {main_err}")
        print("Ensure Docker is installed, running, you have permissions,")
        print(f"AND the necessary images (e.g., '{LANGUAGE_CONFIG.get('python',{}).get('image','')}','{LANGUAGE_CONFIG.get('golang',{}).get('image','')}','{LANGUAGE_CONFIG.get('nodejs',{}).get('image','')}') are built.")
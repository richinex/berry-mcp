#!/usr/bin/env python
# packages/mcp-server/src/mcp_server/mcp/mcp_tasks.py

# --- START EVENTLET MONKEY PATCHING ---
# Optional: If you need eventlet for certain async libraries used by your tools.
# Uncomment if necessary, but be aware of potential compatibility issues with asyncio.
# try:
#     import eventlet
#     eventlet.monkey_patch()
#     import sys
#     print("Eventlet monkey patch applied successfully.", file=sys.stderr, flush=True)
# except ImportError:
#     import sys
#     print("Eventlet not found, monkey patch skipped.", file=sys.stderr, flush=True)
# --- END MONKEY PATCH ---

import time
import json
import logging
import os
import sys
import inspect
import traceback
from typing import Dict, Any, List, Optional, Union
import asyncio # Import asyncio for running async tools

# --- Setup Project Path ---
# Ensure the worker can find project modules (like ai_agent.mcp.models)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    print(f"Added project root to sys.path: {project_root}", file=sys.stderr, flush=True)

# --- Imports (after path setup) ---
try:
    import redis as sync_redis
    from celery import Celery
    from celery.exceptions import Ignore, Reject, SoftTimeLimitExceeded, TimeLimitExceeded
    from pydantic import BaseModel, ValidationError # Ensure Pydantic is imported

    # --- Import MCP Models (Corrected Import) ---
    from .models import TaskStatus # Use relative import

    # --- Import ToolRegistry (Corrected Import) ---
    from ..core.registry import ToolRegistry # Go up one level, then into core

    # --- Import Tools Loader (Corrected Import) ---
    from ..tools.loader import load_default_tools # Go up one level, then into tools

    # --- MCP Standard Types Import (Optional Check) ---
    # (Keep as is, relative imports not needed here)
    try:
        from mcp import types as mcp_types # Keep attempt for MCP_TYPES_AVAILABLE flag
        MCP_TYPES_AVAILABLE = True
        print("Successfully imported mcp types.", file=sys.stderr, flush=True)
    except ImportError:
        print("mcp library types not found in worker. Using fallback dicts for notifications.", file=sys.stderr, flush=True)
        mcp_types = None
        MCP_TYPES_AVAILABLE = False

except ImportError as e:
    # Log critical import errors and exit if essential modules are missing
    print(f"ERROR: Celery worker failed to import modules: {e}")
    print(f"Ensure the worker runs with the correct environment and paths.")
    print(f"Current sys.path: {sys.path}") # Keep this for debugging if errors persist
    traceback.print_exc()
    sys.exit(1)

# --- Constants ---
TASK_HASH_PREFIX = "mcp:task:"          # Prefix for Redis keys storing task details
NOTIFICATION_CHANNEL = "mcp:notifications" # Redis channel for publishing notifications

# --- Logging Setup for Celery Worker ---
# Configure logging level via environment variable, default to INFO
log_level_name = os.environ.get("MCP_WORKER_LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)

# Basic file and stream handler setup
log_file = "mcp_celery_worker.log"
log_dir = os.path.dirname(log_file)
if log_dir and not os.path.exists(log_dir):
     try: os.makedirs(log_dir)
     except OSError: pass # Ignore error if directory already exists

logging.basicConfig(
    level=log_level,
    format='[%(asctime)s] [%(process)d] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S %z',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stderr) # Also log to stdout/stderr for container/terminal visibility
    ],
    force=True # Override any root logger config potentially set by libraries
)
logger = logging.getLogger("mcp_celery_tasks") # Logger specific to this task module

# Set Celery's internal logger level if desired (can be noisy)
logging.getLogger('celery').setLevel(os.environ.get("CELERY_LOG_LEVEL", "WARNING").upper())
logging.getLogger('redis').setLevel(os.environ.get("REDIS_LOG_LEVEL", "WARNING").upper())

logger.info(f"Celery task module logger initialized. Level: {log_level_name}. Log file: {log_file}")

# --- Pydantic JSON Encoder ---
def pydantic_encoder(obj):
    """ Custom JSON encoder for Pydantic models (v1 and v2). """
    if isinstance(obj, BaseModel):
        try:
            # Try Pydantic v2+ .model_dump() method first
            return obj.model_dump(mode='json')
        except AttributeError:
            # Fallback to Pydantic v1 .dict() method
            return obj.dict()
    # Let the default encoder handle other types or raise TypeError if unhandled
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable by default")


# --- Celery Application Setup ---
# Use environment variable for Redis URL, default to standard localhost Redis
REDIS_URL = os.environ.get("MCP_REDIS_URL", "redis://localhost:6379/0")
if not REDIS_URL:
    logger.critical("FATAL: MCP_REDIS_URL environment variable not set. Celery cannot connect.")
    sys.exit(1)

logger.info(f"Celery using Redis backend/broker: {REDIS_URL}")

celery_app = Celery(
    'mcp_tasks', # Name of the celery application module
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['ai_agent.mcp.mcp_tasks'] # Module where tasks are defined (this file)
)

# Celery Configuration settings
celery_app.conf.update(
    task_serializer='json',          # Use JSON for task messages serialization
    accept_content=['json'],         # Accept only JSON formatted task content
    result_serializer='json',        # Use JSON for storing task results in the backend
    timezone='UTC',                  # Use UTC timezone consistently
    enable_utc=True,
    # Time limits (configurable via environment variables)
    task_time_limit=int(os.environ.get("CELERY_TASK_TIME_LIMIT", 3600)),      # Hard time limit (seconds) - task killed
    task_soft_time_limit=int(os.environ.get("CELERY_SOFT_TIME_LIMIT", 3500)), # Soft time limit (seconds) - raises exception
    # Worker configuration options
    worker_prefetch_multiplier=1,    # Process one task at a time per worker process (good for long tasks)
    worker_max_tasks_per_child=int(os.environ.get("CELERY_MAX_TASKS", 100)), # Restart worker process after N tasks (memory leak mitigation)
    task_acks_late=True,             # Acknowledge task AFTER it completes/fails (prevents task loss if worker crashes mid-execution)
    broker_connection_retry_on_startup=True, # Attempt to reconnect to broker if connection fails on startup
)
logger.info("Celery app configured.")

# --- Tool Loading ---
# Load tools into a global registry once when the worker process starts
GLOBAL_TOOL_REGISTRY = ToolRegistry()
try:
    # Assuming load_default_tools finds and registers all necessary tool functions
    load_default_tools(GLOBAL_TOOL_REGISTRY)
    logger.info(f"Celery worker loaded {len(GLOBAL_TOOL_REGISTRY.tools)} tools into its registry.")
except Exception as e:
    logger.error(f"Celery worker CRITICAL ERROR during tool loading on startup: {e}", exc_info=True)
    # Decide if this is fatal. If tools are essential, exit.
    # sys.exit(1)
    logger.warning("Continuing worker startup despite tool loading error. Tools may fail.")

# --- Helper Functions ---
def get_redis_connection(redis_url: str) -> sync_redis.Redis:
    """Establishes and verifies a synchronous Redis connection."""
    try:
        # decode_responses=True is important for getting strings back from Redis HGET/etc.
        conn = sync_redis.from_url(redis_url, decode_responses=True, health_check_interval=30)
        conn.ping() # Verify connection is alive
        logger.debug("Successfully connected to Redis.")
        return conn
    except sync_redis.RedisError as e:
        logger.error(f"Celery Task: Failed to connect to Redis at {redis_url}: {e}")
        # Raise a standard ConnectionError for Celery's autoretry mechanism
        raise ConnectionError(f"Redis connection failed: {e}") from e
    except Exception as e:
        # Catch other potential errors during connection setup
        logger.error(f"Celery Task: Unexpected error connecting to Redis: {e}", exc_info=True)
        raise ConnectionError(f"Unexpected Redis connection error: {e}") from e

def publish_notification_celery(redis_conn: sync_redis.Redis, mcp_method: str, mcp_params: Dict[str, Any]):
    """
    Publishes a notification message (as a dictionary) to the MCP notification channel via Redis Pub/Sub.
    Handles JSON serialization, including Pydantic models.
    """
    if not isinstance(redis_conn, sync_redis.Redis):
         # Prevent errors if connection object is invalid
         logger.error(f"Invalid Redis connection object provided to publish_notification_celery (method: {mcp_method}).")
         return
    if not mcp_method:
        logger.error("Attempted to publish notification with empty method name.")
        return

    try:
        # Construct the standard JSON-RPC notification structure
        notification_payload = {
            "jsonrpc": "2.0",
            "method": mcp_method,
            "params": mcp_params
        }
        # Serialize the payload to JSON, using the custom encoder for Pydantic models
        payload_json = json.dumps(notification_payload, default=pydantic_encoder)

        # Publish the JSON string to the dedicated channel
        published_count = redis_conn.publish(NOTIFICATION_CHANNEL, payload_json)
        # Log success only at debug level to reduce noise
        logger.debug(f"Celery Task published notification method='{mcp_method}' to '{NOTIFICATION_CHANNEL}' -> {published_count} subscribers.")

    except redis.RedisError as e:
        # Log specific Redis errors encountered during the publish operation
        logger.error(f"Celery Task: Redis error publishing notification '{mcp_method}': {e}")
    except TypeError as e:
        # Log errors during JSON serialization
        logger.error(f"Celery Task: Failed to JSON serialize notification message: {e} - Method: {mcp_method}", exc_info=True)
        # Log the parameters that caused the issue for easier debugging
        logger.error(f"Params causing serialization error: {mcp_params}")
    except Exception as e:
         # Log any other unexpected errors during the publishing process
         logger.error(f"Celery Task: Unexpected error publishing notification '{mcp_method}': {e}", exc_info=True)


def update_task_redis_celery(redis_conn: sync_redis.Redis, task_id: str, **kwargs):
    """
    Updates the task's hash key in Redis with the provided key-value pairs.
    Handles serialization of common types, including Pydantic models, for storage in Redis hash.
    """
    if not task_id:
        logger.error("update_task_redis_celery called with empty task_id.")
        return
    if not isinstance(redis_conn, sync_redis.Redis):
         # Prevent errors if connection object is invalid
         logger.error(f"Invalid Redis connection object provided to update_task_redis_celery for task {task_id}.")
         return

    task_key = f"{TASK_HASH_PREFIX}{task_id}" # Construct the Redis key for the task hash
    try:
        update_data = {} # Dictionary to hold fields to be updated
        for key, value in kwargs.items():
            # Skip None values, as HSET doesn't handle them well and we might not want to overwrite with None
            if value is not None:
                 # Attempt serialization for complex types (dicts, lists, Pydantic models) first
                 if isinstance(value, (dict, list, BaseModel)):
                     try:
                         # Serialize complex types to a JSON string
                         update_data[key] = json.dumps(value, default=pydantic_encoder)
                     except TypeError:
                         # Fallback for un-serializable complex types: store as string representation
                         update_data[key] = str(value)
                         logger.warning(f"Celery Task [{task_id}]: Could not JSON-serialize value for key '{key}', storing str(). Type: {type(value).__name__}")
                 # Handle basic types directly (strings, bytes, numbers)
                 elif isinstance(value, (str, bytes, int, float)):
                     update_data[key] = value
                 elif isinstance(value, bool):
                     # Store booleans explicitly as strings 'True'/'False' in Redis Hash
                     update_data[key] = str(value)
                 else:
                     # Fallback for any other unexpected types: store as string representation
                     update_data[key] = str(value)
                     logger.debug(f"Celery Task [{task_id}]: Storing value for key '{key}' as string (type: {type(value).__name__}).")

        # Perform the Redis HSET operation only if there is valid data to update
        if update_data:
            # HSET updates fields in the hash; returns number of fields added (not updated)
            result = redis_conn.hset(task_key, mapping=update_data)
            logger.debug(f"Celery Task [{task_id}]: Updated Redis HSET fields: {list(update_data.keys())}. Result (fields added): {result}")
        else:
            # Log if no updates were made (e.g., all kwargs were None)
            logger.debug(f"Celery Task [{task_id}]: No non-None fields provided to update in Redis.")

    except redis.RedisError as e:
         # Log specific Redis errors during the HSET operation
         logger.error(f"Celery Task [{task_id}]: Redis error updating hash '{task_key}': {e}")
    except Exception as e:
         # Log any other unexpected errors during the update process
         logger.error(f"Celery Task [{task_id}]: Unexpected error updating Redis hash '{task_key}': {e}", exc_info=True)

# --- Celery Task Definition ---
# --- Celery Task Definition ---
@celery_app.task(
    bind=True,                              # Makes `self` (task instance) available inside the function
    name='ai_agent.mcp.mcp_tasks.execute_tool_task', # Explicit, stable task name
    acks_late=True,                         # Acknowledge task *after* it runs (important for reliability)
    throws=(Reject, Ignore, SoftTimeLimitExceeded, TimeLimitExceeded), # Declare expected exceptions
    autoretry_for=(ConnectionError,),       # Automatically retry on connection errors (e.g., Redis down)
    retry_kwargs={'max_retries': 3, 'countdown': 5} # Retry 3 times, wait 5s between retries
)
def execute_tool_task(self, task_id: str, tool_name: str, parameters: Dict[str, Any], redis_url: str):
    """
    Celery task to execute a specific tool function identified by `tool_name`
    using parameters from the `parameters` dict.

    Handles:
    - Connecting to Redis.
    - Checking initial task status (expecting DEQUEUED).
    - Updating task status in Redis (RUNNING, COMPLETED, ERROR, CANCELLED) and progress.
    - Storing the final result or error message in Redis.
    - Publishing standard progress notifications (`notifications/progress`) via Redis Pub/Sub.
    - Executing synchronous or asynchronous tools.
    - Handling exceptions, including Celery time limits.

    NOTE: Does NOT publish a final result notification. The client/LLM must poll
          using a `check_task_status` tool (or similar) to retrieve results from Redis.
    """
    start_time = time.time()
    # Use Celery's request ID if available for logging, otherwise fall back to MCP task ID
    effective_task_id = self.request.id or task_id
    log_prefix = f"[TASK {effective_task_id}]" # Consistent prefix for log messages related to this task run
    task_key = f"{TASK_HASH_PREFIX}{task_id}" # Redis key uses the original MCP task ID for state

    logger.info(f"{log_prefix} Celery task received. Tool='{tool_name}'. MCP Task ID='{task_id}'")
    logger.debug(f"{log_prefix} Parameters: {json.dumps(parameters, default=str)}") # Log params safely

    redis_conn: Optional[sync_redis.Redis] = None       # Holds the Redis connection object
    final_status_for_reporting = TaskStatus.UNKNOWN # Track final status reliably for reporting

    try:
        # Establish Redis connection for this task instance
        # This might raise ConnectionError, triggering Celery's autoretry
        redis_conn = get_redis_connection(redis_url)

        # --- 1. Pre-execution Status Check ---
        # Verify the task hasn't been cancelled or put in an unexpected state
        try:
            current_status_str = redis_conn.hget(task_key, "status")
            # Handle case where hash or status field might be missing
            current_status = current_status_str if current_status_str else TaskStatus.UNKNOWN.value
        except redis.RedisError as e:
            logger.error(f"{log_prefix} Redis error checking initial status for key '{task_key}': {e}. Assuming UNKNOWN.")
            # If we can't check status, proceed cautiously, but log the error
            current_status = TaskStatus.UNKNOWN.value

        if current_status == TaskStatus.CANCELLED.value:
             logger.warning(f"{log_prefix} Task already marked CANCELLED in Redis before execution started. Ignoring.")
             raise Ignore() # Tell Celery to ignore this task, it's already handled

        elif current_status != TaskStatus.DEQUEUED.value:
             # This indicates a potential logic error in the bridge or a race condition
             logger.error(f"{log_prefix} CRITICAL STATE: Expected status DEQUEUED, found '{current_status}'. Rejecting task.")
             error_msg = f"Worker found unexpected status '{current_status}' on start (expected DEQUEUED)"
             # Attempt to mark as ERROR in Redis
             update_task_redis_celery(redis_conn, task_id, status=TaskStatus.ERROR.value, error=error_msg, end_time=str(time.time()))
             final_status_for_reporting = TaskStatus.ERROR # Track internal status

             # --- Publish TaskFinished Notification on REJECTION ---
             # Although we removed the normal finished notification, we SHOULD notify
             # if the task is immediately rejected due to bad state.
             mcp_finished_params = {
                 "taskId": task_id,
                 "status": TaskStatus.ERROR.value,
                 "result": { # Use result structure for consistency
                     "content": [{"type": "text", "text": error_msg}],
                     "isError": True
                 }
             }
             # Use the standard method name the client expects for completion/error
             publish_notification_celery(redis_conn, "tasks/finished", mcp_finished_params)
             # ----------------------------------------------------

             # Reject tells Celery this task failed permanently, do not requeue/retry
             raise Reject(error_msg, requeue=False)

        # --- 2. Mark as Running & Publish Initial Progress (Corrected) ---
        logger.info(f"{log_prefix} Setting status to RUNNING in Redis.")
        update_task_redis_celery(redis_conn, task_id, status=TaskStatus.RUNNING.value, progress=5) # Set initial progress

        # Construct and publish the initial progress notification
        initial_progress_percentage = 5.0 # Use float consistent with spec
        initial_progress_message = "Task execution started by worker"
        mcp_progress_params_dict = {
            "progressToken": task_id,           # ID for client to track
            "progress": initial_progress_percentage, # Send the numeric percentage (float)
            "message": initial_progress_message     # Optional descriptive message
        }
        # Use the correct MCP method name "notifications/progress"
        publish_notification_celery(redis_conn, "notifications/progress", mcp_progress_params_dict)

        # --- 3. Find and Execute the Tool ---
        tool_result = None      # Stores the successful result of the tool function
        tool_exception = None   # Stores any exception raised during tool execution
        is_cancelled = False    # Flag to track if cancellation was detected

        try:
            # Short sleep allows event loop tick, potentially processing cancellation signals sooner
            time.sleep(0.01)

            # Check for cancellation *before* starting potentially long execution
            if redis_conn.hget(task_key, "status") == TaskStatus.CANCELLED.value:
                 logger.warning(f"{log_prefix} Cancellation detected before tool execution started.")
                 is_cancelled = True
            else:
                 # Ensure the global tool registry is available
                 if GLOBAL_TOOL_REGISTRY is None:
                     raise RuntimeError("FATAL: Tool registry not loaded in worker.")

                 # Get the actual tool function callable from the registry
                 tool_func = GLOBAL_TOOL_REGISTRY.get_tool(tool_name)
                 if not tool_func:
                     # Tool requested by the bridge doesn't exist in the worker's registry
                     raise ValueError(f"Tool '{tool_name}' not found in Celery worker's tool registry.")

                 logger.info(f"{log_prefix} Executing tool '{tool_name}'...")
                 call_params = parameters or {} # Use provided parameters, default to empty dict if None

                 # --- Execute based on whether the tool is async or sync ---
                 if inspect.iscoroutinefunction(tool_func):
                     logger.debug(f"{log_prefix} Tool '{tool_name}' is async. Running via asyncio.")
                     try:
                         # Standard way to run an async function from a sync context
                         tool_result = asyncio.run(tool_func(**call_params))
                     except RuntimeError as e:
                         # Handle common "cannot run nested event loops" error, especially with eventlet/gevent
                          if "cannot run nested event loops" in str(e).lower():
                              logger.warning(f"{log_prefix} Nested event loop detected. Trying direct await via existing/new loop.")
                              # Attempt alternative ways to run the coroutine if asyncio.run fails
                              try:
                                  # Try getting the current running loop (might exist under eventlet/gevent)
                                  loop = asyncio.get_running_loop()
                                  logger.debug(f"{log_prefix} Using existing running loop.")
                              except RuntimeError:
                                  # If no loop is running, create a new one
                                  logger.debug(f"{log_prefix} No running loop, creating new one.")
                                  loop = asyncio.new_event_loop()
                                  asyncio.set_event_loop(loop)

                              try:
                                  # Run the coroutine until it completes on the obtained loop
                                  tool_result = loop.run_until_complete(tool_func(**call_params))
                              finally:
                                   # Close the loop only if we created it
                                   if not asyncio.get_event_loop().is_running():
                                       loop.close()
                                       logger.debug(f"{log_prefix} Closed newly created event loop.")
                                       asyncio.set_event_loop(None) # Clear the loop from the current context
                          else:
                             # Re-raise other RuntimeErrors
                             logger.error(f"{log_prefix} Unexpected RuntimeError running async tool: {e}", exc_info=True)
                             raise e
                 else:
                     # Execute synchronous tool function directly
                     logger.debug(f"{log_prefix} Tool '{tool_name}' is sync. Running directly.")
                     tool_result = tool_func(**call_params)

                 logger.info(f"{log_prefix} Tool '{tool_name}' execution finished successfully. Result type: {type(tool_result).__name__}")

                 # Check for cancellation *immediately after* execution finishes, before proceeding
                 if redis_conn.hget(task_key, "status") == TaskStatus.CANCELLED.value:
                      logger.warning(f"{log_prefix} Cancellation detected immediately after successful tool execution.")
                      is_cancelled = True # Mark as cancelled even though tool ran

        # --- Handle specific Celery exceptions related to time limits ---
        except SoftTimeLimitExceeded as soft_timeout:
             tool_exception = soft_timeout # Store the exception for reporting
             logger.warning(f"{log_prefix} Soft time limit ({celery_app.conf.task_soft_time_limit}s) exceeded during tool execution.")
             # Task execution stops here, proceeds to the finally block for cleanup/reporting
        except TimeLimitExceeded as hard_timeout:
             tool_exception = hard_timeout # Store the exception
             logger.error(f"{log_prefix} Hard time limit ({celery_app.conf.task_time_limit}s) exceeded. Task termination likely.")
             # The worker process might be killed abruptly after this. The finally block is not guaranteed to run fully.
        # --- Handle general exceptions during tool lookup or execution ---
        except Exception as e:
             tool_exception = e # Store the exception for reporting
             logger.error(f"{log_prefix} Tool execution failed with exception: {type(e).__name__}: {e}", exc_info=True)
             # Check if task was cancelled concurrently while handling the exception
             try:
                 if redis_conn.hget(task_key, "status") == TaskStatus.CANCELLED.value:
                     is_cancelled = True
                     logger.info(f"{log_prefix} Cancellation detected during exception handling for: {type(e).__name__}")
             except: pass # Ignore redis errors during this secondary check

        # --- 4. Post-execution Processing & Final Status Update (in finally block) ---
        finally:
            logger.debug(f"{log_prefix} Entering finally block for task cleanup and final status reporting.")
            # Ensure redis_conn is still valid before attempting final updates
            if not redis_conn:
                 logger.error(f"{log_prefix} Redis connection lost before final update phase. Cannot update status or notify.")
                 # If connection is lost, rely on Celery's retry or task failure mechanisms
                 return # Exit the task function if Redis is unavailable

            # Determine the final status based on execution outcome
            final_status_determined = TaskStatus.UNKNOWN
            # Prepare payload for final Redis update (always set end_time)
            update_payload_redis = {"end_time": str(time.time())}
            # Get latest progress value before finalizing (handle potential errors)
            current_progress = 5.0 # Default start progress
            try:
                prog_str = redis_conn.hget(task_key, "progress")
                # Use float for intermediate calculation, int for storage/notification if needed
                current_progress = float(prog_str) if prog_str else 5.0
            except (redis.RedisError, ValueError, TypeError) as prog_err:
                logger.warning(f"{log_prefix} Could not read/parse progress from Redis before final update: {prog_err}. Using default {current_progress}%.")

            error_for_reporting: Optional[str] = None # Holds formatted error message for Redis/notifications

            # --- Determine Final Status ---
            if is_cancelled:
                 final_status_determined = TaskStatus.CANCELLED
                 logger.warning(f"{log_prefix} Finalizing task status as CANCELLED.")
                 update_payload_redis["status"] = final_status_determined.value
                 update_payload_redis["progress"] = int(current_progress) # Keep progress where it was on cancel
                 error_for_reporting = "Task cancelled by request"
                 # Store cancellation reason in Redis error field if no other tool exception occurred
                 if not tool_exception:
                     update_payload_redis["error"] = error_for_reporting

            elif tool_exception is not None:
                 final_status_determined = TaskStatus.ERROR
                 logger.error(f"{log_prefix} Finalizing task status as ERROR due to exception: {type(tool_exception).__name__}")
                 update_payload_redis["status"] = final_status_determined.value
                 update_payload_redis["progress"] = int(current_progress) # Keep progress where it was on error
                 # Format the error message for storage and notification
                 error_for_reporting = f"{type(tool_exception).__name__}: {str(tool_exception)}"
                 # Store the detailed error message in Redis
                 update_payload_redis["error"] = error_for_reporting

            else: # Success path (no cancellation, no exception)
                 final_status_determined = TaskStatus.COMPLETED
                 logger.info(f"{log_prefix} Finalizing task status as COMPLETED.")
                 update_payload_redis["status"] = final_status_determined.value
                 update_payload_redis["progress"] = 100 # Mark 100% progress on successful completion
                 # Store the successful result (let helper handle serialization)
                 update_task_redis_celery(redis_conn, task_id, result=tool_result)
                 # Explicitly clear any potential previous error field in Redis on success
                 update_payload_redis["error"] = ""

            # --- Update Redis with final status, progress, end_time, error ---
            # This updates status, progress, end_time, and error fields based on the logic above
            # Note: 'result' is updated separately by the helper call above on success
            update_task_redis_celery(redis_conn, task_id, **update_payload_redis)
            final_status_for_reporting = final_status_determined # Update internal status tracker

            # --- Publish ONLY Final Progress Notification ---
            final_progress_percentage = float(update_payload_redis.get('progress', 0)) # Get final progress value
            final_progress_message = f"Task finished with status: {final_status_determined.value}"
            final_progress_params_dict = {
                "progressToken": task_id,
                "progress": final_progress_percentage, # Send the final numeric percentage (float)
                "message": final_progress_message       # Send the final status message
            }
            publish_notification_celery(redis_conn, "notifications/progress", final_progress_params_dict) # Use correct method

            # --- REMOVED tasks/finished PUBLISH CALL ---
            # The client is now responsible for calling check_task_status to get the final result.
            logger.debug(f"{log_prefix} Final result/error stored in Redis. No 'tasks/finished' notification published.")

            logger.info(f"{log_prefix} Celery task final processing completed. Duration: {time.time() - start_time:.2f}s. Final Status Reported (in Redis): {final_status_determined.value}")

    # --- Outer Exception Handling (Catches errors in setup, redis connection, etc.) ---
    except Ignore:
        # Task was ignored (e.g., already cancelled). Logged earlier.
        logger.warning(f"{log_prefix} Celery task processing ignored. No further action.")
    except Reject as e:
        # Task was rejected (e.g., invalid initial state). Logged earlier.
        logger.error(f"{log_prefix} Celery task processing rejected: {e}. No retry.")
        # Final notification for rejection was sent when Reject was raised.
    except ConnectionError as e:
        # Handle Redis connection errors specifically (might trigger retry)
        logger.error(f"{log_prefix} Redis Connection Error encountered: {e}. Allowing Celery to retry if configured.")
        # Re-raise the specific error to trigger Celery's autoretry mechanism
        # Ensure 'self' from bind=True is used to call retry
        raise self.retry(exc=e, countdown=5) # Example retry configuration
    except Exception as outer_exc:
        # Catch any other unexpected error during the task execution flow
        logger.critical(f"{log_prefix} Unhandled exception during Celery task execution: {outer_exc}", exc_info=True)
        final_status_for_reporting = TaskStatus.ERROR # Mark as error internally
        # Attempt to report this infrastructure/unexpected error back via Redis
        if redis_conn:
             try:
                  infra_err_msg = f"Celery worker infrastructure error: {type(outer_exc).__name__}: {outer_exc}"
                  # Update Redis status to ERROR
                  update_payload_infra_err = {
                      "status": TaskStatus.ERROR.value,
                      "error": infra_err_msg,
                      "end_time": str(time.time())
                      # Optionally keep existing progress on infra error, or set to 0/error value?
                  }
                  update_task_redis_celery(redis_conn, task_id, **update_payload_infra_err)

                  # --- Publish TaskFinished Notification on INFRASTRUCTURE ERROR ---
                  # It's crucial to notify the bridge/client that the task failed, even due to worker issues.
                  mcp_finished_params = {
                      "taskId": task_id,
                      "status": TaskStatus.ERROR.value,
                      "result": { # Use result field even for infra errors
                           "content": [{"type": "text", "text": infra_err_msg}],
                           "isError": True
                      }
                  }
                  publish_notification_celery(redis_conn, "tasks/finished", mcp_finished_params)
                  # -----------------------------------------------------------------
                  logger.info(f"{log_prefix} Successfully reported infrastructure error to Redis/PubSub.")

             except Exception as final_err:
                 # Log error during the final error reporting phase itself
                 logger.error(f"{log_prefix} CRITICAL: Worker failed to report infrastructure error status to Redis/PubSub after outer exception: {final_err}", exc_info=True)
        else:
             logger.error(f"{log_prefix} Cannot report infrastructure error status to Redis as connection is unavailable.")
        # Re-raise the original exception for Celery to record the task as failed
        raise outer_exc
    finally:
        # --- Final Cleanup ---
        # Ensure Redis connection is closed if it was successfully opened
        if redis_conn:
            try:
                redis_conn.close()
                logger.debug(f"{log_prefix} Redis connection closed.")
            except Exception as close_err:
                logger.warning(f"{log_prefix} Error closing Redis connection in finally block: {close_err}")


# --- Worker Entry Point ---
# This allows running the worker using `python # packages/mcp-server/src/mcp_server//mcp/mcp_tasks.py worker ...`
# or more commonly via `celery -A ai_agent.mcp.mcp_tasks worker ...`
if __name__ == '__main__':
    # This block is typically executed when the script is run directly.
    # Celery's command-line interface usually handles starting the worker.
    # However, this allows direct invocation for potential debugging or alternative setups.
    logger.info("Running Celery worker entry point from __main__...")
    # celery_app.start() is deprecated; use the CLI command instead.
    # Example: `celery -A ai_agent.mcp.mcp_tasks worker --loglevel=INFO`
    print("To start the worker, use the Celery CLI command:", file=sys.stderr)
    print("Example: celery -A ai_agent.mcp.mcp_tasks worker --loglevel=INFO", file=sys.stderr)
    # For demonstration if run directly:
    # argv = [
    #     'worker',
    #     '--loglevel=INFO',
    # ]
    # celery_app.worker_main(argv)
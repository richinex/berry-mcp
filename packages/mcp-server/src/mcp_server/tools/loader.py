# packages/mcp-server/src/mcp_server/tools/loader.py
from typing import Dict, Any
from ..core.registry import ToolRegistry
import logging
from typing import Dict, Any

# --- Import existing tools ---
from .weather import get_weather
from .calculator import calculate
from .search import search
from .search_pararius import search_pararius
from .safety_analyzer import analyze_area_safety
from .html_parser import parse_html
from .scientific_research import search_scientific_papers
from .docker_tools import (
    build_docker_image, run_docker_container, list_running_containers,
    get_container_logs, stop_container, remove_container,
    check_container_health # <--- NEW IMPORT
)
from .code_executor import execute_code_in_sandbox

# --- Import File Tools (Existing and New) ---
try:
    from .file_tools import (
        list_files,
        read_file,
        write_file,
        rename_path,
        delete_file,
        delete_directory,
        get_workspace_structure,
        read_json_file
    )
    FILE_TOOLS_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import File Tools: {e}")
    FILE_TOOLS_IMPORTED = False

# --- Import PDF Tools (NEW) ---
try:
    from . import pdf_tools
    PDF_TOOLS_READY = pdf_tools.PYMUPDF_AVAILABLE
    if not PDF_TOOLS_READY:
         print("Warning: pdf_tools imported, but required library (PyMuPDF) is missing. PDF tools disabled.")
except ImportError as e:
    print(f"Warning: Could not import PDF Tools module: {e}")
    pdf_tools = None
    PDF_TOOLS_READY = False
# --- End PDF Tools Import ---

# --- Import Code Analysis Tools (NEW) ---
try:
    from .code_analysis_tools import (
        analyze_single_python_file_metadata,
        analyze_python_directory_metadata
    )
    CODE_ANALYSIS_TOOLS_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import Code Analysis Tools: {e}")
    analyze_single_python_file_metadata = None
    analyze_python_directory_metadata = None
    CODE_ANALYSIS_TOOLS_IMPORTED = False
# --- End Code Analysis Tools Import ---

# --- Import Git Tools (NEW) ---
try:
    from .git_tools import (
        git_clone_repository,
        git_pull_latest,
        git_create_branch,
        git_checkout_branch,
        git_commit_changes,
        git_push_changes,
        git_get_status,
        git_get_commit_history
    )
    GIT_TOOLS_IMPORTED = True
    print("Successfully imported Git tools.")
except ImportError as e:
    print(f"Warning: Could not import Git Tools: {e}")
    GIT_TOOLS_IMPORTED = False
# --- End Git Tools Import ---

# # --- Import Shell Tools (NEW) ---
# try:
#     from .shell_tools import execute_command # <-- ADD THIS LINE
#     SHELL_TOOLS_IMPORTED = True
#     print("Successfully imported Shell tools.")
# except ImportError as e:
#     print(f"Warning: Could not import Shell Tools: {e}")
#     SHELL_TOOLS_IMPORTED = False
# --- End Shell Tools Import ---
from .docker_compose_tools import (
    docker_compose_up,
    docker_compose_down,
    docker_compose_logs,
    docker_compose_ps,
    docker_compose_exec,
    docker_compose_restart
)
# ... (Keep other imports like finance, ecommerce, market_analyzer) ...
try:
    from .finance import convert_currency
    FINANCE_TOOLS_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import finance tools: {e}")
    FINANCE_TOOLS_IMPORTED = False

try:
    from .ecommerce import compare_product_prices
    ECOMMERCE_TOOLS_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import e-commerce tools (compare_product_prices): {e}")
    ECOMMERCE_TOOLS_IMPORTED = False

try:
    from .market_analyzer import generate_rental_market_report
    MARKET_ANALYZER_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import market analyzer tool: {e}")
    MARKET_ANALYZED_IMPORTED = False

try:
    from .doc_search import find_documentation
    DOC_SEARCH_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import Documentation Search tool: {e}")
    DOC_SEARCH_IMPORTED = False

# --- Import Email Tool (NEW) ---
try:
    from .email_tools import (
        send_email,
        read_emails,
        delete_email,
        mark_email_read,
        mark_email_unread
    )
    EMAIL_TOOLS_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import Email Tools: {e}")
    EMAIL_TOOLS_IMPORTED = False

# --- Import Calendar Tool (NEW) ---
try:
    from .calendar_tools import (
        list_calendar_events,
        create_calendar_event,
        delete_calendar_event
    )
    CALENDAR_TOOLS_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import Calendar Tools: {e}")
    CALENDAR_TOOLS_IMPORTED = False


log = logging.getLogger(__name__)


def load_default_tools(registry: ToolRegistry) -> None:
    """Register all default tools with the registry"""
    print("Loading default tools into registry...")

    # Basic tools
    registry.tool()(get_weather)
    registry.tool()(calculate)
    registry.tool()(search)
    registry.tool()(search_pararius)
    registry.tool()(parse_html)
    registry.tool()(search_scientific_papers)
    registry.tool()(analyze_area_safety)



    # Register Documentation Search if imported
    if DOC_SEARCH_IMPORTED:
        try:
            registry.tool()(find_documentation)
            print("Registered Documentation Search tool.")
        except Exception as e: print(f"Error registering Documentation Search tool: {e}")

    # Register Email Tools if imported (USE WITH EXTREME CAUTION)
    if EMAIL_TOOLS_IMPORTED:
        try:
            registry.tool()(send_email)
            registry.tool()(read_emails)
            registry.tool()(delete_email)
            registry.tool()(mark_email_read)
            registry.tool()(mark_email_unread)
            print("Registered Email tools (send, read, delete, mark read/unread).")
        except NameError as ne: print(f"Warning: NameError registering email tools: {ne}")
        except Exception as e: print(f"Error registering email tools: {e}")

    # --- Register Calendar Tools (NEW) ---
    if CALENDAR_TOOLS_IMPORTED:
        try:
            registry.tool()(list_calendar_events)
            registry.tool()(create_calendar_event)
            registry.tool()(delete_calendar_event)
            print("Registered Calendar tools (list, create, delete events).")
        except NameError as ne: print(f"Warning: NameError registering calendar tools: {ne}")
        except Exception as e: print(f"Error registering calendar tools: {e}")
    else:
        print("Skipping registration of calendar tools due to import errors.")


    # Register finance tools if imported
    if FINANCE_TOOLS_IMPORTED:
        try:
            registry.tool()(convert_currency)
            print("Registered finance tools.")
        except Exception as e: print(f"Error registering finance tools: {e}")

    # Register E-commerce tools if imported
    if ECOMMERCE_TOOLS_IMPORTED:
        try:
            registry.tool()(compare_product_prices)
            print("Registered E-commerce tools.")
        except Exception as e: print(f"Error registering e-commerce tool: {e}")

    # Register Code Executor if imported (USE WITH EXTREME CAUTION)
    try:
        registry.tool()(execute_code_in_sandbox)
        print("Registered Code Execution Sandbox tool. USE WITH EXTREME CAUTION.")
    except Exception as e: print(f"Error registering code executor tool: {e}")

    # Register Docker Tools (USE WITH CAUTION)
    try:
        registry.tool()(build_docker_image)
        registry.tool()(run_docker_container)
        registry.tool()(list_running_containers)
        registry.tool()(get_container_logs)
        registry.tool()(stop_container)
        registry.tool()(remove_container)
        registry.tool()(check_container_health) # <--- NEW REGISTRATION
        print("Registered Docker interaction tools, including health check. USE WITH CAUTION.")
    except Exception as e: print(f"Error registering Docker tools: {e}")

    # # --- Register Shell Tools (NEW) ---
    # if SHELL_TOOLS_IMPORTED:
    #     try:
    #         registry.tool()(execute_command)
    #         print("Registered Shell command execution tool (execute_command). USE WITH EXTREME CAUTION.")
    #     except AttributeError:
    #         print("Error: Could not find 'execute_command' function in shell_tools module during registration.")
    #     except Exception as e:
    #         print(f"Error registering shell command execution tool: {e}")
    # else:
    #     print("Skipping registration of shell tools due to import errors.")
    # --- End Shell Tools Registration ---

    # --- Register Docker Compose Tools (NEW) ---
    try:
        registry.tool()(docker_compose_up)
        registry.tool()(docker_compose_down)
        registry.tool()(docker_compose_logs)
        registry.tool()(docker_compose_ps)
        registry.tool()(docker_compose_exec)
        registry.tool()(docker_compose_restart)
        print("Registered Docker Compose tools (up, down, logs, ps, exec, restart). USE WITH CAUTION.")
    except Exception as e:
        print(f"Error registering Docker Compose tools: {e}")

    # Register File Tools (Operate within workspace)
    if FILE_TOOLS_IMPORTED:
        try:
            if 'list_files' in globals() or 'list_files' in locals(): registry.tool()(list_files)
            if 'read_file' in globals() or 'read_file' in locals(): registry.tool()(read_file)
            if 'write_file' in globals() or 'write_file' in locals(): registry.tool()(write_file)
            if 'rename_path' in globals() or 'rename_path' in locals(): registry.tool()(rename_path)
            if 'delete_file' in globals() or 'delete_file' in locals(): registry.tool()(delete_file)
            if 'delete_directory' in globals() or 'delete_directory' in locals(): registry.tool()(delete_directory)
            if 'get_workspace_structure' in globals() or 'get_workspace_structure' in locals(): registry.tool()(get_workspace_structure)
            if 'read_json_file' in globals() or 'read_json_file' in locals(): registry.tool()(read_json_file)
            print("Registered File Manipulation tools (list, read, write, rename, delete, read_json_file).")
        except NameError as ne: print(f"Warning: NameError registering file tools: {ne}")
        except Exception as e: print(f"Error registering file tools: {e}")
    else:
        print("Skipping registration of file tools due to import errors.")

    # --- Register PDF Tools (NEW) ---
    if PDF_TOOLS_READY: # Check if module imported AND library is available
        try:
            # Access the function via the imported module name
            registry.tool()(pdf_tools.read_pdf_text)
            print("Registered PDF Text Extraction tool (read_pdf_text).")
        except AttributeError: # If pdf_tools is None or function missing
             print("Error: Could not find 'read_pdf_text' function in pdf_tools module during registration.")
        except Exception as e:
             print(f"Error registering PDF tool: {e}")
    else:
        pass # Already logged during import check
    # --- End PDF Tools Registration ---

    # Register Market Analyzer if imported
    if MARKET_ANALYZER_IMPORTED:
        try:
            registry.tool()(generate_rental_market_report)
            print("Registered Rental Market Report tool.")
        except Exception as e: print(f"Error registering market analyzer tool: {e}")

    # --- Register Git Tools (NEW) ---
    if GIT_TOOLS_IMPORTED:
        try:
            registry.tool()(git_clone_repository)
            registry.tool()(git_pull_latest)
            registry.tool()(git_create_branch)
            registry.tool()(git_checkout_branch)
            registry.tool()(git_commit_changes)
            registry.tool()(git_push_changes)
            registry.tool()(git_get_status)
            registry.tool()(git_get_commit_history)
            print("Registered Git interaction tools. USE WITH CAUTION, especially push.")
        except Exception as e:
            print(f"Error registering Git tools: {e}")
    else:
        print("Skipping registration of Git tools due to import errors.")
    # --- End Git Tools Registration ---

    # --- Register Code Analysis Tools (NEW) ---
    if CODE_ANALYSIS_TOOLS_IMPORTED:
        if analyze_single_python_file_metadata and callable(analyze_single_python_file_metadata):
            try:
                registry.tool()(analyze_single_python_file_metadata)
                print("Registered Single Python File Metadata Analysis tool.")
            except Exception as e:
                print(f"Error registering Single Python File Metadata Analysis tool: {e}")
        else:
            if not analyze_single_python_file_metadata: print("analyze_single_python_file_metadata not imported.")

        if analyze_python_directory_metadata and callable(analyze_python_directory_metadata):
            try:
                registry.tool()(analyze_python_directory_metadata)
                print("Registered Python Directory Metadata Analysis tool.")
            except Exception as e:
                print(f"Error registering Python Directory Metadata Analysis tool: {e}")
        else:
             if not analyze_python_directory_metadata: print("analyze_python_directory_metadata not imported.")
    else:
        print("Skipping registration of Code Analysis tools due to import error.")
    # --- End Code Analysis Tools Registration ---

    print("Default tool loading complete.")
# # packages/mcp-server/src/mcp_server/tools/pdf_tools.py

# import logging
# import pathlib
# import asyncio
# from typing import Dict, Union, Optional

# # --- Dependency on file_tools for ToolConfig class and validation ---
# # This creates a coupling, but avoids duplicating the core security logic.
# # Ensure file_tools.set_tools_workspace() is called during server startup.
# from .file_tools import ToolConfig, validate_path, MAX_FILE_SIZE_READ # <-- Import ToolConfig

# # --- PDF Library Import ---
# try:
#     import PyPDF2
#     PDF_LIB_AVAILABLE = True
# except ImportError:
#     PDF_LIB_AVAILABLE = False
#     PyPDF2 = None # type: ignore

# log = logging.getLogger(__name__)

# # --- Configuration ---
# MAX_PDF_TEXT_CHARS = 50 * 1024 # Limit extracted text size (e.g., 50k chars)


# # --- PDF Tool Implementations ---

# async def read_pdf_text(path: str) -> Union[str, Dict[str, str]]:
#     """
#     Reads and extracts text content from a specified PDF file within the agent's
#     secure workspace using standard text extraction (NOT Vision API).
#     Requires the 'PyPDF2' library to be installed on the server.
#     Uses workspace configured via ToolConfig.

#     Args:
#         path: The relative path to the PDF file within the workspace.

#     Returns:
#         The extracted text content of the PDF as a string on success,
#         or a dictionary {'error': 'description'} on failure.
#         Extracted text might be truncated if it exceeds MAX_PDF_TEXT_CHARS.
#         Returns an error if the PDF library is not available or the file is not a PDF.
#     """
#     if not PDF_LIB_AVAILABLE:
#         log.error("read_pdf_text tool called, but PyPDF2 library is not installed.")
#         return {"error": "PDF processing library (PyPDF2) not available on the server."}

#     # --- Use ToolConfig class to get workspace ---
#     workspace_root = ToolConfig.get_workspace() # Get path via class method
#     log.debug(f"read_pdf_text: Checking workspace via ToolConfig.get_workspace(). Value = {workspace_root}") # Added Debug Log

#     if workspace_root is None:
#         log.error("Workspace not configured (checked via ToolConfig). Cannot execute read_pdf_text.")
#         return {"error": "Workspace not configured"}

#     log.info(f"Attempting to read PDF text from file: '{path}' relative to workspace {workspace_root}.") # Log the retrieved path
#     if not path:
#         return {"error": "File path cannot be empty."}

#     # validate_path now uses ToolConfig internally
#     validated_file_path = validate_path(path)

#     if not validated_file_path:
#         # validate_path logs details
#         return {"error": f"Invalid or disallowed file path provided: '{path}'."}

#     # Check existence and type *after* validation
#     if not validated_file_path.exists():
#         return {"error": f"File not found within workspace: '{path}'"}
#     if not validated_file_path.is_file():
#         return {"error": f"Path is not a file within workspace: '{path}'"}
#     if validated_file_path.suffix.lower() != ".pdf":
#          return {"error": f"File is not a PDF: '{path}'. Use 'read_file' for other types."}

#     # Check file size before trying to open/read
#     try:
#         file_size = validated_file_path.stat().st_size
#         if file_size > MAX_FILE_SIZE_READ * 5: # Allow 5MB PDFs
#              log.warning(f"PDF file '{validated_file_path}' is large ({file_size} bytes). Text extraction might be slow or truncated.")
#     except Exception as stat_err:
#          log.error(f"Could not get file size for '{validated_file_path}': {stat_err}")
#          return {"error": f"Failed to get file stats for '{path}': {stat_err}"}

#     extracted_text = ""
#     file_obj: Optional[object] = None # Define file_obj here for finally block

#     try:
#         pdf_reader: Optional[PyPDF2.PdfReader] = None # type: ignore

#         def _read_pdf():
#             f_obj = None
#             try:
#                 f_obj = validated_file_path.open('rb')
#                 reader = PyPDF2.PdfReader(f_obj)
#                 return reader, f_obj
#             except PyPDF2.errors.PdfReadError as pdf_err:
#                  log.error(f"PyPDF2 error reading PDF structure '{validated_file_path}': {pdf_err}")
#                  if f_obj: f_obj.close()
#                  raise pdf_err
#             except Exception as open_err:
#                 log.error(f"Failed to open or init PdfReader for '{validated_file_path}': {open_err}", exc_info=True)
#                 if f_obj: f_obj.close()
#                 raise open_err

#         pdf_reader, file_obj = await asyncio.to_thread(_read_pdf)

#         if pdf_reader.is_encrypted:
#              try:
#                  decrypt_result = pdf_reader.decrypt('')
#                  if decrypt_result == PyPDF2.PasswordType.OWNER_PASSWORD: # type: ignore
#                       log.warning(f"PDF '{validated_file_path}' has an owner password but content extraction might be restricted.")
#                  elif decrypt_result == PyPDF2.PasswordType.USER_PASSWORD: # type: ignore
#                       log.warning(f"PDF '{validated_file_path}' is encrypted with a user password.")
#                       return {"error": f"PDF file '{path}' is encrypted with a password and cannot be read."}
#              except NotImplementedError:
#                   log.warning(f"PDF '{validated_file_path}' uses an unsupported encryption algorithm.")
#                   return {"error": f"PDF file '{path}' uses unsupported encryption."}
#              except Exception as decrypt_err:
#                  log.error(f"Error during PDF decryption check for '{validated_file_path}': {decrypt_err}")
#                  return {"error": f"Failed to check encryption for PDF '{path}': {decrypt_err}"}

#         num_pages = len(pdf_reader.pages)
#         log.info(f"Reading {num_pages} pages from PDF: {validated_file_path}")

#         def _extract_pages_text():
#             texts = []
#             current_char_count = 0
#             for page_num, page in enumerate(pdf_reader.pages):
#                 try:
#                     page_text = page.extract_text()
#                     if page_text:
#                          clean_page_text = page_text.strip()
#                          if clean_page_text:
#                              texts.append(clean_page_text)
#                              current_char_count += len(clean_page_text)
#                              if current_char_count > MAX_PDF_TEXT_CHARS:
#                                  log.warning(f"PDF text extraction truncated at page {page_num+1} due to character limit ({MAX_PDF_TEXT_CHARS}).")
#                                  break
#                 except Exception as page_err:
#                     log.warning(f"Error extracting text from page {page_num + 1} of '{validated_file_path}': {page_err}")
#             return "\n\n".join(texts)

#         extracted_text = await asyncio.to_thread(_extract_pages_text)

#         if len(extracted_text) > MAX_PDF_TEXT_CHARS:
#             limit_pos = extracted_text.rfind('\n', 0, MAX_PDF_TEXT_CHARS)
#             if limit_pos == -1: limit_pos = MAX_PDF_TEXT_CHARS
#             extracted_text = extracted_text[:limit_pos] + "\n\n[... PDF Text Truncated due to size limit ...]"

#         log.info(f"Successfully extracted ~{len(extracted_text)} characters from PDF: {validated_file_path}")
#         return extracted_text if extracted_text else "[PDF contained no extractable text]"

#     except PyPDF2.errors.PdfReadError as pdf_err:
#          log.error(f"Invalid or corrupted PDF file '{validated_file_path}': {pdf_err}")
#          return {"error": f"Cannot read PDF '{path}'. File might be corrupted or invalid: {pdf_err}"}
#     except PermissionError:
#         log.error(f"Permission denied reading PDF file: {validated_file_path}")
#         return {"error": f"Permission denied reading file '{path}'."}
#     except Exception as e:
#         log.error(f"Failed to read PDF text from '{validated_file_path}': {e}", exc_info=True)
#         return {"error": f"An unexpected error occurred while reading PDF text: {e}"}
#     finally:
#         if file_obj and hasattr(file_obj, 'close') and callable(file_obj.close):
#              try:
#                  await asyncio.to_thread(file_obj.close) # type: ignore
#              except Exception as close_err:
#                  log.warning(f"Error closing PDF file object for '{validated_file_path}': {close_err}")

# # --- End of pdf_tools.py ---

# packages/mcp-server/src/mcp_server/tools/pdf_tools.py

import logging
import pathlib
import asyncio
from typing import Dict, Union, Optional

# --- Dependency on file_tools for ToolConfig class and validation ---
from .file_tools import ToolConfig, validate_path, MAX_FILE_SIZE_READ # Keep ToolConfig dependency

# --- NEW: PyMuPDF Library Import ---
try:
    # Import the high-level wrapper
    import pymupdf4llm
    # Import the core library for potential error types or advanced use
    import pymupdf # Keep this import for pymupdf.open used for page count
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    pymupdf4llm = None # type: ignore
    pymupdf = None # type: ignore

log = logging.getLogger(__name__)

# --- Configuration ---
# Default page limit if not specified in the tool call.
# Note: This limit is now primarily for notification, as `to_markdown` processes all pages.
DEFAULT_PDF_PAGE_LIMIT = 20

# --- PDF Tool Implementations ---

async def read_pdf_text(path: str, page_limit: int = DEFAULT_PDF_PAGE_LIMIT) -> Union[str, Dict[str, str]]:
    """
    Reads and extracts text content from a specified PDF file within the agent's
    secure workspace, outputting GitHub-flavored Markdown.
    Uses the PyMuPDF library (via pymupdf4llm) which must be installed.

    NOTE: Due to library limitations, this function currently extracts content
    from ALL pages of the PDF. The `page_limit` argument is used to notify
    the user if the total page count exceeds this limit.

    Args:
        path: The relative path to the PDF file within the workspace.
        page_limit: The page count threshold for notification purposes.

    Returns:
        The extracted content as a Markdown string on success,
        or a dictionary {'error': 'description'} on failure.
        Returns an error if the PyMuPDF library or its dependencies are not available,
        or if the file is not a valid PDF.
    """
    if not PYMUPDF_AVAILABLE:
        log.error("read_pdf_text tool called, but PyMuPDF/pymupdf4llm library is not installed or import failed.")
        return {"error": "PDF processing library (PyMuPDF/pymupdf4llm) not available on the server."}

    # --- Use ToolConfig class to get workspace ---
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        log.error("Workspace not configured (checked via ToolConfig). Cannot execute read_pdf_text.")
        return {"error": "Workspace not configured"}

    log.info(f"Attempting to read PDF Markdown from file: '{path}' relative to workspace {workspace_root}.")
    if not path:
        return {"error": "File path cannot be empty."}

    # validate_path now uses ToolConfig internally
    validated_file_path = validate_path(path)

    if not validated_file_path:
        # validate_path logs details
        return {"error": f"Invalid or disallowed file path provided: '{path}'."}

    # Check existence and type *after* validation
    if not validated_file_path.exists():
        return {"error": f"File not found within workspace: '{path}'"}
    if not validated_file_path.is_file():
        return {"error": f"Path is not a file within workspace: '{path}'"}
    # Simple check, PyMuPDF will give a better error if it's not really a PDF
    if validated_file_path.suffix.lower() != ".pdf":
         log.warning(f"File suffix is not .pdf for '{path}', attempting read anyway.")
         # Allow attempt, PyMuPDF might handle it or raise an error

    # Consider a size check, although PyMuPDF might be more efficient
    try:
        file_size = validated_file_path.stat().st_size
        # Example: Warn for files larger than 50MB
        if file_size > 50 * 1024 * 1024:
             log.warning(f"PDF file '{validated_file_path}' is very large ({file_size / (1024*1024):.1f} MB). Processing might take time.")
        # Check against a general max read size if defined elsewhere
        if MAX_FILE_SIZE_READ is not None and file_size > MAX_FILE_SIZE_READ:
            log.error(f"PDF file '{validated_file_path}' exceeds maximum allowed size ({MAX_FILE_SIZE_READ} bytes).")
            return {"error": f"File '{path}' exceeds maximum allowed size."}
    except Exception as stat_err:
         log.warning(f"Could not get file size for '{validated_file_path}': {stat_err}")
         # Continue anyway

    extracted_markdown = ""
    try:
        # PyMuPDF functions can be blocking, run them in a thread executor
        def _extract_markdown_sync():
            # This inner function runs in a separate thread
            try:
                log.debug(f"Calling pymupdf4llm.to_markdown for '{validated_file_path}' (processing all pages).")

                # Ensure path is passed as string
                # REMOVED `page_numbers` argument as it's not supported
                md_text = pymupdf4llm.to_markdown(str(validated_file_path))

                # Check total page count to potentially add a notification
                try:
                    # Use pymupdf directly to efficiently get page count
                    doc = pymupdf.open(str(validated_file_path))
                    total_pages = doc.page_count
                    doc.close()
                    # Check if the total pages exceed the *requested* limit for notification
                    if total_pages > page_limit:
                         # Append a message indicating the document exceeded the requested limit
                         md_text += f"\n\n[... Note: PDF has {total_pages} pages, exceeding the requested processing limit of {page_limit} pages. Full content extracted. ...]"
                         log.warning(f"PDF '{validated_file_path}' has {total_pages} pages, exceeding requested limit of {page_limit}. Full content was extracted.")

                except Exception as count_err:
                    # Catch potential errors opening just for page count (e.g., password error here)
                    err_str = str(count_err).lower()
                    if "password" in err_str or "owner permission" in err_str:
                        log.warning(f"Could not get total page count for '{validated_file_path}' due to encryption: {count_err}")
                        # Re-raise as ValueError for consistent handling.
                        raise ValueError(f"PDF file '{path}' appears to be password protected (detected during page count).") from count_err
                    else:
                        log.warning(f"Could not get total page count to check against limit for '{validated_file_path}': {count_err}")
                        # Continue without notification if page count fails for other reasons

                return md_text

            # --- Exception Handling for PyMuPDF/pymupdf4llm ---
            except RuntimeError as run_err:
                 err_str = str(run_err).lower()
                 if "password" in err_str or "owner permission" in err_str:
                    log.warning(f"PDF file '{validated_file_path}' seems to be encrypted: {run_err}")
                    raise ValueError(f"PDF file '{path}' appears to be password protected.") from run_err
                 else:
                    log.error(f"PyMuPDF runtime error processing '{validated_file_path}': {run_err}")
                    raise ValueError(f"Failed to process PDF '{path}' due to a runtime error: {run_err}") from run_err
            except ValueError as val_err:
                log.error(f"ValueError during PyMuPDF processing for '{validated_file_path}': {val_err}")
                raise # Re-raise to be caught by the outer block
            except TypeError as type_err:
                 # Catch potential TypeErrors from the library call itself (like the one observed)
                 log.error(f"TypeError during PyMuPDF markdown extraction for '{validated_file_path}': {type_err}", exc_info=True)
                 raise ValueError(f"Failed to process PDF '{path}' due to a library interface error (TypeError): {type_err}") from type_err
            except Exception as e:
                log.error(f"Unexpected error during PyMuPDF markdown extraction for '{validated_file_path}': {e}", exc_info=True)
                raise # Re-raise to be caught below

        # Run the synchronous extraction function in a thread
        extracted_markdown = await asyncio.to_thread(_extract_markdown_sync)

        log.info(f"Successfully extracted Markdown (length ~{len(extracted_markdown)}) from PDF: {validated_file_path}")
        # Handle case where PDF might be valid but contain no actual text
        return extracted_markdown if extracted_markdown.strip() else "[PDF contained no extractable text content]"

    # --- Outer Exception Handling ---
    except (ValueError, RuntimeError) as pdf_err: # Catch errors propagated from _extract_markdown_sync
         log.error(f"Failed to process PDF file '{validated_file_path}': {pdf_err}")
         error_msg = f"Cannot read PDF '{path}'. "
         err_str = str(pdf_err).lower()
         if "password protected" in err_str:
              error_msg += "File appears to be password protected."
         elif "typeerror" in err_str: # Check if it was the TypeError we added handling for
             error_msg += f"There was a library compatibility issue: {pdf_err}"
         elif isinstance(pdf_err, RuntimeError):
              error_msg += f"A processing error occurred (RuntimeError): {pdf_err}"
         elif isinstance(pdf_err, ValueError):
              error_msg += f"File might be invalid, corrupted, or processing failed: {pdf_err}"
         else:
              error_msg += f"File might be corrupted, invalid, or processing failed: {pdf_err}"
         return {"error": error_msg}
    except PermissionError:
        log.error(f"Permission denied accessing PDF file: {validated_file_path}")
        return {"error": f"Permission denied accessing file '{path}'."}
    except FileNotFoundError:
        log.error(f"File not found error for PDF: {validated_file_path}")
        return {"error": f"File not found: '{path}'."}
    except Exception as e: # Catch-all for unexpected errors in the async part
        log.error(f"Unexpected error reading PDF markdown from '{validated_file_path}': {e}", exc_info=True)
        # Make the error message slightly more specific about where the unexpected error occurred
        return {"error": f"An unexpected error occurred in the PDF reading process: {e}"}
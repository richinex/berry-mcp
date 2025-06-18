"""
PDF processing tools for Berry PDF MCP Server
"""

import logging
import pathlib
import asyncio
from typing import Dict, Union, Optional

from .decorators import tool
from ..utils.validation import validate_path

# PDF Library imports
try:
    import pymupdf4llm
    import pymupdf
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    pymupdf4llm = None
    pymupdf = None

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    PyPDF2 = None

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_PDF_PAGE_LIMIT = 20
MAX_PDF_TEXT_CHARS = 50 * 1024  # 50k characters limit


@tool(description="Extract text content from a PDF file as Markdown using PyMuPDF")
async def read_pdf_text(
    path: str, 
    page_limit: int = DEFAULT_PDF_PAGE_LIMIT
) -> Union[str, Dict[str, str]]:
    """
    Reads and extracts text content from a specified PDF file, outputting GitHub-flavored Markdown.
    Uses the PyMuPDF library (via pymupdf4llm) for high-quality text extraction.

    Args:
        path: The path to the PDF file
        page_limit: The page count threshold for notification purposes

    Returns:
        The extracted content as a Markdown string on success,
        or a dictionary {'error': 'description'} on failure.
    """
    if not PYMUPDF_AVAILABLE:
        logger.error("PyMuPDF/pymupdf4llm library is not installed")
        return {"error": "PDF processing library (PyMuPDF/pymupdf4llm) not available"}

    logger.info(f"Attempting to read PDF Markdown from file: '{path}'")
    if not path:
        return {"error": "File path cannot be empty"}

    # Validate file path
    validated_file_path = validate_path(path)
    if not validated_file_path:
        return {"error": f"Invalid or disallowed file path provided: '{path}'"}

    # Check file existence and type
    if not validated_file_path.exists():
        return {"error": f"File not found: '{path}'"}
    if not validated_file_path.is_file():
        return {"error": f"Path is not a file: '{path}'"}
    if validated_file_path.suffix.lower() != ".pdf":
        logger.warning(f"File suffix is not .pdf for '{path}', attempting read anyway")

    # Check file size
    try:
        file_size = validated_file_path.stat().st_size
        if file_size > 50 * 1024 * 1024:  # 50MB
            logger.warning(f"PDF file '{validated_file_path}' is very large ({file_size / (1024*1024):.1f} MB)")
    except Exception as stat_err:
        logger.warning(f"Could not get file size for '{validated_file_path}': {stat_err}")

    try:
        def _extract_markdown_sync():
            try:
                logger.debug(f"Calling pymupdf4llm.to_markdown for '{validated_file_path}'")
                md_text = pymupdf4llm.to_markdown(str(validated_file_path))

                # Check total page count
                try:
                    doc = pymupdf.open(str(validated_file_path))
                    total_pages = doc.page_count
                    doc.close()
                    
                    if total_pages > page_limit:
                        md_text += f"\n\n[Note: PDF has {total_pages} pages, exceeding the requested processing limit of {page_limit} pages. Full content extracted.]"
                        logger.warning(f"PDF '{validated_file_path}' has {total_pages} pages, exceeding requested limit of {page_limit}")
                        
                except Exception as count_err:
                    err_str = str(count_err).lower()
                    if "password" in err_str or "owner permission" in err_str:
                        logger.warning(f"Could not get page count due to encryption: {count_err}")
                        raise ValueError(f"PDF file '{path}' appears to be password protected")
                    else:
                        logger.warning(f"Could not get page count: {count_err}")

                return md_text

            except RuntimeError as run_err:
                err_str = str(run_err).lower()
                if "password" in err_str or "owner permission" in err_str:
                    logger.warning(f"PDF file appears to be encrypted: {run_err}")
                    raise ValueError(f"PDF file '{path}' appears to be password protected")
                else:
                    logger.error(f"PyMuPDF runtime error: {run_err}")
                    raise ValueError(f"Failed to process PDF '{path}': {run_err}")
            
            except Exception as e:
                logger.error(f"Unexpected error during PDF processing: {e}", exc_info=True)
                raise

        # Run extraction in thread
        extracted_markdown = await asyncio.to_thread(_extract_markdown_sync)
        
        logger.info(f"Successfully extracted Markdown (length ~{len(extracted_markdown)}) from PDF: {validated_file_path}")
        return extracted_markdown if extracted_markdown.strip() else "[PDF contained no extractable text content]"

    except ValueError as pdf_err:
        logger.error(f"Failed to process PDF file '{validated_file_path}': {pdf_err}")
        error_msg = f"Cannot read PDF '{path}'. "
        if "password protected" in str(pdf_err).lower():
            error_msg += "File appears to be password protected."
        else:
            error_msg += f"File might be invalid, corrupted, or processing failed: {pdf_err}"
        return {"error": error_msg}
    
    except PermissionError:
        logger.error(f"Permission denied accessing PDF file: {validated_file_path}")
        return {"error": f"Permission denied accessing file '{path}'"}
    
    except FileNotFoundError:
        logger.error(f"File not found: {validated_file_path}")
        return {"error": f"File not found: '{path}'"}
    
    except Exception as e:
        logger.error(f"Unexpected error reading PDF: {e}", exc_info=True)
        return {"error": f"An unexpected error occurred: {e}"}


@tool(description="Extract text content from a PDF file using PyPDF2 (alternative method)")
async def read_pdf_text_pypdf2(
    path: str,
    max_chars: int = MAX_PDF_TEXT_CHARS
) -> Union[str, Dict[str, str]]:
    """
    Reads and extracts text content from a PDF file using PyPDF2.
    This is an alternative method that may work better for some PDF files.

    Args:
        path: The path to the PDF file
        max_chars: Maximum number of characters to extract

    Returns:
        The extracted text content as a string on success,
        or a dictionary {'error': 'description'} on failure.
    """
    if not PYPDF2_AVAILABLE:
        logger.error("PyPDF2 library is not installed")
        return {"error": "PDF processing library (PyPDF2) not available"}

    logger.info(f"Attempting to read PDF text using PyPDF2 from file: '{path}'")
    if not path:
        return {"error": "File path cannot be empty"}

    # Validate file path
    validated_file_path = validate_path(path)
    if not validated_file_path:
        return {"error": f"Invalid or disallowed file path provided: '{path}'"}

    # Check file existence and type
    if not validated_file_path.exists():
        return {"error": f"File not found: '{path}'"}
    if not validated_file_path.is_file():
        return {"error": f"Path is not a file: '{path}'"}
    if validated_file_path.suffix.lower() != ".pdf":
        return {"error": f"File is not a PDF: '{path}'"}

    file_obj = None
    try:
        def _read_pdf():
            nonlocal file_obj
            file_obj = validated_file_path.open('rb')
            reader = PyPDF2.PdfReader(file_obj)
            
            if reader.is_encrypted:
                try:
                    decrypt_result = reader.decrypt('')
                    if decrypt_result == 0:  # Failed to decrypt
                        raise ValueError(f"PDF file '{path}' is encrypted with a password")
                except Exception:
                    raise ValueError(f"PDF file '{path}' is encrypted and cannot be read")

            num_pages = len(reader.pages)
            logger.info(f"Reading {num_pages} pages from PDF: {validated_file_path}")

            texts = []
            current_char_count = 0
            
            for page_num, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        clean_page_text = page_text.strip()
                        if clean_page_text:
                            texts.append(clean_page_text)
                            current_char_count += len(clean_page_text)
                            
                            if current_char_count > max_chars:
                                logger.warning(f"PDF text extraction truncated at page {page_num+1} due to character limit")
                                break
                                
                except Exception as page_err:
                    logger.warning(f"Error extracting text from page {page_num + 1}: {page_err}")

            return "\n\n".join(texts)

        # Run PDF reading in thread
        extracted_text = await asyncio.to_thread(_read_pdf)

        # Truncate if necessary
        if len(extracted_text) > max_chars:
            limit_pos = extracted_text.rfind('\n', 0, max_chars)
            if limit_pos == -1:
                limit_pos = max_chars
            extracted_text = extracted_text[:limit_pos] + "\n\n[... PDF Text Truncated due to size limit ...]"

        logger.info(f"Successfully extracted ~{len(extracted_text)} characters from PDF: {validated_file_path}")
        return extracted_text if extracted_text else "[PDF contained no extractable text]"

    except PyPDF2.errors.PdfReadError as pdf_err:
        logger.error(f"Invalid or corrupted PDF file: {pdf_err}")
        return {"error": f"Cannot read PDF '{path}'. File might be corrupted or invalid: {pdf_err}"}
    
    except ValueError as val_err:
        logger.error(f"PDF processing error: {val_err}")
        return {"error": str(val_err)}
    
    except PermissionError:
        logger.error(f"Permission denied reading PDF file: {validated_file_path}")
        return {"error": f"Permission denied reading file '{path}'"}
    
    except Exception as e:
        logger.error(f"Failed to read PDF text: {e}", exc_info=True)
        return {"error": f"An unexpected error occurred while reading PDF text: {e}"}
    
    finally:
        if file_obj and hasattr(file_obj, 'close'):
            try:
                await asyncio.to_thread(file_obj.close)
            except Exception as close_err:
                logger.warning(f"Error closing PDF file: {close_err}")
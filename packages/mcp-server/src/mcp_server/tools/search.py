# # src/ai_agent/tools/search.py
# import logging
# import os
# import httpx
# import json
# import time
# import asyncio
# import urllib.parse
# from dotenv import load_dotenv
# from typing import List, Dict, Any

# # Import trafilatura for content extraction
# import trafilatura

# # Import Selenium components
# try:
#     from selenium import webdriver
#     from selenium.webdriver.common.by import By
#     from selenium.webdriver.chrome.options import Options
#     from selenium.webdriver.support.ui import WebDriverWait
#     from selenium.webdriver.support import expected_conditions as EC
#     from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
#     SELENIUM_AVAILABLE = True
# except ImportError:
#     SELENIUM_AVAILABLE = False
#     Options = None
#     WebDriverException = Exception
#     TimeoutException = asyncio.TimeoutError

# # Import networkx for deduplication
# import networkx as nx

# log = logging.getLogger(__name__)

# load_dotenv()

# # --- Configuration ---
# GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
# SEARCH_API_URL = "https://www.googleapis.com/customsearch/v1"

# # Selenium constants
# USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
# SELENIUM_GENERAL_WAIT = 10
# SELENIUM_PAGE_LOAD_TIMEOUT = 60
# SELENIUM_RENDER_WAIT = 4

# def normalize_url(url: str) -> str:
#     """
#     Normalize a URL by lowercasing the scheme and netloc, stripping trailing slashes,
#     and removing query parameters and fragments.
#     """
#     try:
#         parsed = urllib.parse.urlparse(url)
#         scheme = parsed.scheme.lower()
#         netloc = parsed.netloc.lower()
#         path = parsed.path.rstrip("/")
#         normalized_url = urllib.parse.urlunparse((scheme, netloc, path, '', '', ''))
#         return normalized_url
#     except Exception as e:
#         log.warning(f"Failed to normalize URL '{url}': {e}", exc_info=True)
#         return url

# async def call_google_cse_api(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
#     """
#     Calls the Google Custom Search Engine API to get search results.
#     This is the working implementation from doc_search_v2.py
#     """
#     if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
#         log.error("Google API Key or CSE ID not configured in environment variables.")
#         return []

#     params = {
#         "key": GOOGLE_API_KEY,
#         "cx": GOOGLE_CSE_ID,
#         "q": query,
#         "num": max(1, min(num_results, 10))
#     }

#     results = []
#     try:
#         async with httpx.AsyncClient(timeout=10.0) as client:
#             log.debug(f"Calling Google CSE API with query: '{query}'")
#             response = await client.get(SEARCH_API_URL, params=params)
#             response.raise_for_status()
#             data = response.json()

#             if "items" in data:
#                 for item in data["items"]:
#                     if item.get("link") and item.get("title"):
#                         results.append({
#                             "title": item.get("title"),
#                             "link": item.get("link"),
#                             "snippet": item.get("snippet", "")
#                         })
#             else:
#                 log.warning(f"Google CSE returned no 'items' for query: '{query}'")

#     except httpx.HTTPStatusError as e:
#         log.error(f"Google CSE API HTTP error ({e.response.status_code}) for query '{query}': {e.response.text}")
#     except httpx.RequestError as e:
#         log.error(f"Google CSE API request error for query '{query}': {e}")
#     except json.JSONDecodeError as e:
#         log.error(f"Failed to decode JSON response from Google CSE API for query '{query}': {e}")
#     except Exception as e:
#         log.error(f"Unexpected error calling Google CSE API for query '{query}': {e}", exc_info=True)

#     log.debug(f"Google CSE API returned {len(results)} results for query: '{query}'")
#     return results

# def get_selenium_driver() -> webdriver.Chrome:
#     """Configures and returns a Selenium WebDriver instance."""
#     if not SELENIUM_AVAILABLE or not Options:
#         log.error("Selenium library not available. Cannot create driver.")
#         raise RuntimeError("Selenium library (selenium) is required for this operation.")

#     chrome_options = Options()
#     chrome_options.add_argument("--headless")
#     chrome_options.add_argument("--disable-gpu")
#     chrome_options.add_argument("--no-sandbox")
#     chrome_options.add_argument("--disable-dev-shm-usage")
#     chrome_options.add_argument("--window-size=1920,1080")
#     chrome_options.add_argument("--disable-blink-features=AutomationControlled")
#     chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
#     chrome_options.add_argument(f"user-agent={USER_AGENT}")
#     chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
#     chrome_options.add_argument('--log-level=3')
#     chrome_options.add_argument('--disable-infobars')
#     chrome_options.add_argument('--disable-extensions')
#     chrome_options.add_experimental_option("prefs", {"profile.default_content_setting_values.notifications": 2})

#     try:
#         driver = webdriver.Chrome(options=chrome_options)
#         log.debug("Selenium WebDriver initialized successfully.")
#         return driver
#     except WebDriverException as e:
#         log.error(f"Failed to initialize Selenium WebDriver: {e.msg}")
#         log.error("Ensure ChromeDriver is installed, updated, and accessible in your PATH.")
#         raise

# async def scrape_content_with_selenium(url: str) -> Dict[str, Any]:
#     """
#     Scrapes content from a URL using Selenium and extracts text with Trafilatura.
#     Returns a dictionary with extracted content and metadata.
#     """
#     if not SELENIUM_AVAILABLE:
#         return {"error": "Selenium is not available on the server"}

#     def _scrape_sync(url_to_scrape: str) -> Dict[str, Any]:
#         driver = None
#         start_time = time.time()

#         try:
#             log.debug(f"Selenium: Initializing driver for {url_to_scrape}")
#             driver = get_selenium_driver()
#             driver.set_page_load_timeout(SELENIUM_PAGE_LOAD_TIMEOUT)

#             log.info(f"Selenium: Navigating to {url_to_scrape}")
#             driver.get(url_to_scrape)

#             log.debug(f"Selenium: Waiting {SELENIUM_RENDER_WAIT}s for JS rendering...")
#             time.sleep(SELENIUM_RENDER_WAIT)

#             # Get the rendered HTML
#             html_content = driver.page_source
#             log.debug(f"Selenium: Got {len(html_content)} bytes of rendered page source")

#             # Extract main content using Trafilatura
#             extracted_text = trafilatura.extract(
#                 html_content,
#                 include_comments=False,
#                 include_tables=True,
#                 no_fallback=True
#             )

#             if not extracted_text:
#                 log.warning(f"Trafilatura (strict) extracted no content from {url_to_scrape}. Trying fallback.")
#                 extracted_text = trafilatura.extract(
#                     html_content,
#                     include_comments=False,
#                     include_tables=True,
#                     no_fallback=False
#                 )

#             if not extracted_text:
#                 log.warning(f"Trafilatura fallback failed. Using body text for {url_to_scrape}")
#                 try:
#                     body_element = driver.find_element(By.TAG_NAME, 'body')
#                     extracted_text = body_element.text
#                 except Exception as body_err:
#                     log.error(f"Failed to get body text: {body_err}")
#                     return {"error": "Failed to extract any content from page"}

#             # Get page title
#             try:
#                 page_title = driver.title
#             except Exception:
#                 page_title = "Unknown"

#             # Truncate content if too long
#             MAX_CONTENT_CHARS = 15000
#             if extracted_text and len(extracted_text) > MAX_CONTENT_CHARS:
#                 log.warning(f"Content from {url_to_scrape} truncated from {len(extracted_text)} to {MAX_CONTENT_CHARS} chars")
#                 extracted_text = extracted_text[:MAX_CONTENT_CHARS] + "\n\n[... CONTENT TRUNCATED ...]"

#             duration = time.time() - start_time
#             log.info(f"Successfully scraped {url_to_scrape} in {duration:.2f}s - extracted ~{len(extracted_text or '')} chars")

#             return {
#                 "text": extracted_text,
#                 "title": page_title,
#                 "url": url_to_scrape,
#                 "scraped_at": time.time(),
#                 "scrape_duration": duration
#             }

#         except TimeoutException:
#             error_msg = f"Selenium timeout ({SELENIUM_PAGE_LOAD_TIMEOUT}s) loading page"
#             log.warning(f"{error_msg}: {url_to_scrape}")
#             return {"error": error_msg}
#         except WebDriverException as e:
#             error_msg = f"Selenium WebDriver error: {e.msg}"
#             log.error(f"{error_msg} for {url_to_scrape}")
#             return {"error": error_msg}
#         except Exception as e:
#             error_msg = f"Unexpected error during scraping: {str(e)}"
#             log.error(f"{error_msg} for {url_to_scrape}", exc_info=True)
#             return {"error": error_msg}
#         finally:
#             if driver:
#                 try:
#                     driver.quit()
#                     log.debug(f"Selenium: Driver quit for {url_to_scrape}")
#                 except Exception as quit_err:
#                     log.error(f"Error quitting driver: {quit_err}")

#     # Run the synchronous scraping function in a thread
#     try:
#         result = await asyncio.to_thread(_scrape_sync, url)
#         return result
#     except Exception as e:
#         log.error(f"Error running scrape task in thread for {url}: {e}")
#         return {"error": f"Server error running scrape task: {str(e)}"}

# async def search_basic(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
#     """
#     Performs a basic search using the Google CSE API.
#     This now uses the working implementation from doc_search_v2.py
#     """
#     if not query or not query.strip():
#         log.warning("Search_basic called with an empty or whitespace-only query.")
#         return []

#     return await call_google_cse_api(query, max_results)

# async def robust_search(query: str, max_results: int = 5, detail_count: int = 3) -> List[Dict[str, Any]]:
#     """
#     Enriches the basic search results by scraping detailed content from the top `detail_count` results.
#     Uses NetworkX to ensure each unique URL is scraped only once.
#     """
#     basic_results = await search_basic(query, max_results)

#     if not basic_results:
#         log.info(f"Robust_search: No basic results found for query '{query}'. Returning empty list.")
#         return []

#     # Cap detail_count to the number of results obtained
#     actual_detail_count = min(detail_count, len(basic_results))

#     # Graph to track processed URLs and avoid redundant scraping
#     processed_urls_graph = nx.DiGraph()
#     enriched_items_count = 0

#     # Enrich top results with scraped content
#     for i in range(actual_detail_count):
#         result_item = basic_results[i]
#         link = result_item.get("link")

#         if not link:
#             log.warning(f"Skipping scraping for result without link: {result_item.get('title')}")
#             result_item["scraped_content"] = {"error": "Result item had no link for scraping"}
#             continue

#         normalized_link = normalize_url(link)

#         if not processed_urls_graph.has_node(normalized_link):
#             processed_urls_graph.add_node(normalized_link)
#             try:
#                 log.info(f"Scraping content for URL ({i+1}/{actual_detail_count}): {link}")
#                 scraped_data = await scrape_content_with_selenium(link)
#                 processed_urls_graph.nodes[normalized_link]["scraped_content"] = scraped_data
#                 enriched_items_count += 1
#             except Exception as e:
#                 log.error(f"Error during content scraping for URL '{link}': {e}", exc_info=True)
#                 processed_urls_graph.nodes[normalized_link]["scraped_content"] = {
#                     "error": f"Failed to scrape content: {str(e)}"
#                 }

#         # Assign the scraped content to the result item
#         if processed_urls_graph.has_node(normalized_link) and "scraped_content" in processed_urls_graph.nodes[normalized_link]:
#             result_item["scraped_content"] = processed_urls_graph.nodes[normalized_link]["scraped_content"]
#         else:
#             log.error(f"Scraped content missing in graph for URL: {normalized_link}")
#             result_item["scraped_content"] = {"error": "Internal error: Scraped content not found"}

#     # For remaining results, propagate cached scraped content if available
#     for i in range(actual_detail_count, len(basic_results)):
#         result_item = basic_results[i]
#         if "scraped_content" in result_item:
#             continue

#         link = result_item.get("link")
#         if link:
#             normalized_link = normalize_url(link)
#             if processed_urls_graph.has_node(normalized_link) and "scraped_content" in processed_urls_graph.nodes[normalized_link]:
#                 log.debug(f"Propagating cached scraped content to result: {link}")
#                 result_item["scraped_content"] = processed_urls_graph.nodes[normalized_link]["scraped_content"]

#     log.info(f"Robust search for '{query}' completed. "
#              f"Scraped content from {enriched_items_count}/{actual_detail_count} top results. "
#              f"Returning {len(basic_results)} results overall.")
#     return basic_results

# async def search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
#     """
#     Public search tool function. Uses Google CSE API + Selenium scraping for comprehensive results.

#     Args:
#         query (str): The search query.
#         max_results (int): Maximum number of search results to return.

#     Returns:
#         List[Dict[str, Any]]: Search results with scraped content. Each item contains:
#             - title: Page title
#             - link: URL
#             - snippet: Search result snippet
#             - scraped_content: Full scraped content (for top 3 results)
#     """
#     if not isinstance(query, str) or not query.strip():
#         log.error("Search tool called with invalid or empty query.")
#         return [{"error": "Query must be a non-empty string and cannot be null."}]

#     log.info(f"Starting comprehensive search for: '{query}' (max_results: {max_results})")

#     # Check dependencies
#     if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
#         log.error("Google CSE API not configured")
#         return [{"error": "Search service not available: Google CSE API not configured"}]

#     if not SELENIUM_AVAILABLE:
#         log.warning("Selenium not available - will return basic search results without content scraping")
#         # Fall back to basic search only
#         return await search_basic(query, max_results)

#     # Use robust search with scraping (default scrapes top 3 results)
#     return await robust_search(query, max_results=max_results, detail_count=3)

# src/ai_agent/tools/search.py
import logging
import os
import httpx
import json
import time
import asyncio
import urllib.parse
from dotenv import load_dotenv
from typing import List, Dict, Any, Tuple
from urllib.parse import urlparse

# Import trafilatura for content extraction
import trafilatura

# Import Selenium components
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    Options = None
    WebDriverException = Exception
    TimeoutException = asyncio.TimeoutError

# Import networkx for deduplication
import networkx as nx

log = logging.getLogger(__name__)

load_dotenv()

# --- Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
SEARCH_API_URL = "https://www.googleapis.com/customsearch/v1"

# Optimized Selenium constants for speed
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
SELENIUM_GENERAL_WAIT = 5      # Reduced from 10
SELENIUM_PAGE_LOAD_TIMEOUT = 15 # Reduced from 60
SELENIUM_RENDER_WAIT = 1       # Reduced from 4

def normalize_url(url: str) -> str:
    """
    Normalize a URL by lowercasing the scheme and netloc, stripping trailing slashes,
    and removing query parameters and fragments.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        normalized_url = urllib.parse.urlunparse((scheme, netloc, path, '', '', ''))
        return normalized_url
    except Exception as e:
        log.warning(f"Failed to normalize URL '{url}': {e}", exc_info=True)
        return url

def should_scrape_url(url: str) -> bool:
    """Determine if a URL is worth scraping based on domain and content type."""
    try:
        parsed = urlparse(url.lower())
        domain = parsed.netloc
        path = parsed.path

        # Skip these domains (not usually useful for general search)
        skip_domains = [
            'youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com', 'twitter.com', 'x.com',
            'facebook.com', 'linkedin.com', 'pinterest.com', 'reddit.com', 'discord.com',
            'snapchat.com', 'whatsapp.com', 'telegram.org'
        ]

        # Skip file downloads
        skip_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                          '.zip', '.rar', '.tar', '.gz', '.mp4', '.mp3', '.avi', '.mov']

        if any(skip_domain in domain for skip_domain in skip_domains):
            log.debug(f"Skipping social media/video site: {domain}")
            return False

        if any(path.endswith(ext) for ext in skip_extensions):
            log.debug(f"Skipping file download: {path}")
            return False

        return True
    except Exception as e:
        log.warning(f"Error checking if should scrape {url}: {e}")
        return True  # When in doubt, scrape

async def call_google_cse_api(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """
    Calls the Google Custom Search Engine API to get search results.
    Optimized version with better error handling.
    """
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        log.error("Google API Key or CSE ID not configured in environment variables.")
        return []

    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": max(1, min(num_results, 10))
    }

    results = []
    try:
        # Reduced timeout for faster response
        async with httpx.AsyncClient(timeout=8.0) as client:
            log.debug(f"Calling Google CSE API with query: '{query}'")
            response = await client.get(SEARCH_API_URL, params=params)
            response.raise_for_status()
            data = response.json()

            if "items" in data:
                for item in data["items"]:
                    if item.get("link") and item.get("title"):
                        results.append({
                            "title": item.get("title"),
                            "link": item.get("link"),
                            "snippet": item.get("snippet", "")
                        })
            else:
                log.warning(f"Google CSE returned no 'items' for query: '{query}'")

    except httpx.HTTPStatusError as e:
        log.error(f"Google CSE API HTTP error ({e.response.status_code}) for query '{query}': {e.response.text}")
    except httpx.RequestError as e:
        log.error(f"Google CSE API request error for query '{query}': {e}")
    except json.JSONDecodeError as e:
        log.error(f"Failed to decode JSON response from Google CSE API for query '{query}': {e}")
    except Exception as e:
        log.error(f"Unexpected error calling Google CSE API for query '{query}': {e}", exc_info=True)

    log.debug(f"Google CSE API returned {len(results)} results for query: '{query}'")
    return results

def get_selenium_driver() -> webdriver.Chrome:
    """Configures and returns an optimized Selenium WebDriver instance for speed."""
    if not SELENIUM_AVAILABLE or not Options:
        log.error("Selenium library not available. Cannot create driver.")
        raise RuntimeError("Selenium library (selenium) is required for this operation.")

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")

    # Speed optimizations
    chrome_options.add_argument("--disable-images")  # Don't load images
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-sync")

    # Memory and performance optimizations
    chrome_options.add_argument("--memory-pressure-off")
    chrome_options.add_argument("--max_old_space_size=4096")
    chrome_options.add_argument("--aggressive-cache-discard")
    chrome_options.add_argument("--window-size=1280,720")  # Smaller window

    # Network optimizations
    chrome_options.add_argument("--aggressive")
    chrome_options.add_argument("--disable-background-networking")

    # Disable unnecessary features
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument(f"user-agent={USER_AGENT}")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        "profile.managed_default_content_settings.images": 2  # Block images
    })

    try:
        driver = webdriver.Chrome(options=chrome_options)
        log.debug("Optimized Selenium WebDriver initialized successfully.")
        return driver
    except WebDriverException as e:
        log.error(f"Failed to initialize Selenium WebDriver: {e.msg}")
        log.error("Ensure ChromeDriver is installed, updated, and accessible in your PATH.")
        raise

async def scrape_content_with_selenium(url: str) -> Dict[str, Any]:
    """
    Scrapes content from a URL using optimized Selenium and extracts text with Trafilatura.
    Returns a dictionary with extracted content and metadata.
    """
    if not SELENIUM_AVAILABLE:
        return {"error": "Selenium is not available on the server"}

    def _scrape_sync(url_to_scrape: str) -> Dict[str, Any]:
        driver = None
        start_time = time.time()

        try:
            log.debug(f"Selenium: Initializing optimized driver for {url_to_scrape}")
            driver = get_selenium_driver()
            driver.set_page_load_timeout(SELENIUM_PAGE_LOAD_TIMEOUT)

            log.info(f"Selenium: Navigating to {url_to_scrape}")
            driver.get(url_to_scrape)

            # Minimal wait for essential content loading
            log.debug(f"Selenium: Waiting {SELENIUM_RENDER_WAIT}s for essential content...")
            time.sleep(SELENIUM_RENDER_WAIT)

            # Get the rendered HTML
            html_content = driver.page_source
            log.debug(f"Selenium: Got {len(html_content)} bytes of rendered page source")

            # Extract main content using Trafilatura (fast extraction)
            extracted_text = trafilatura.extract(
                html_content,
                include_comments=False,
                include_tables=True,
                no_fallback=True,
                favor_precision=True  # Faster extraction
            )

            if not extracted_text:
                log.debug(f"Trafilatura (strict) extracted no content from {url_to_scrape}. Trying fallback.")
                extracted_text = trafilatura.extract(
                    html_content,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False
                )

            if not extracted_text:
                log.debug(f"Trafilatura fallback failed. Using body text for {url_to_scrape}")
                try:
                    body_element = driver.find_element(By.TAG_NAME, 'body')
                    extracted_text = body_element.text
                    if len(extracted_text) < 100:  # If body text is too short, it might be an error page
                        extracted_text = None
                except Exception as body_err:
                    log.warning(f"Failed to get body text: {body_err}")

            # If still no content, return minimal info
            if not extracted_text:
                return {"error": "Failed to extract meaningful content from page", "url": url_to_scrape}

            # Get page title quickly
            try:
                page_title = driver.title or "Unknown"
            except Exception:
                page_title = "Unknown"

            # Optimized content truncation
            MAX_CONTENT_CHARS = 6000  # Reduced from 15000 for faster processing
            if len(extracted_text) > MAX_CONTENT_CHARS:
                log.debug(f"Content from {url_to_scrape} truncated from {len(extracted_text)} to {MAX_CONTENT_CHARS} chars")
                extracted_text = extracted_text[:MAX_CONTENT_CHARS] + "\n\n[... CONTENT TRUNCATED ...]"

            duration = time.time() - start_time
            log.info(f"Successfully scraped {url_to_scrape} in {duration:.2f}s - extracted ~{len(extracted_text)} chars")

            return {
                "text": extracted_text,
                "title": page_title,
                "url": url_to_scrape,
                "scraped_at": time.time(),
                "scrape_duration": round(duration, 2),
                "content_length": len(extracted_text)
            }

        except TimeoutException:
            error_msg = f"Selenium timeout ({SELENIUM_PAGE_LOAD_TIMEOUT}s) loading page"
            log.warning(f"{error_msg}: {url_to_scrape}")
            return {"error": error_msg, "url": url_to_scrape}
        except WebDriverException as e:
            error_msg = f"Selenium WebDriver error: {e.msg}"
            log.warning(f"{error_msg} for {url_to_scrape}")
            return {"error": error_msg, "url": url_to_scrape}
        except Exception as e:
            error_msg = f"Unexpected error during scraping: {str(e)}"
            log.warning(f"{error_msg} for {url_to_scrape}")
            return {"error": error_msg, "url": url_to_scrape}
        finally:
            if driver:
                try:
                    driver.quit()
                    log.debug(f"Selenium: Driver quit for {url_to_scrape}")
                except Exception as quit_err:
                    log.warning(f"Error quitting driver: {quit_err}")

    # Run the synchronous scraping function in a thread
    try:
        result = await asyncio.to_thread(_scrape_sync, url)
        return result
    except Exception as e:
        log.error(f"Error running scrape task in thread for {url}: {e}")
        return {"error": f"Server error running scrape task: {str(e)}", "url": url}

async def search_basic(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Performs a basic search using the Google CSE API.
    Fast mode without content scraping.
    """
    if not query or not query.strip():
        log.warning("Search_basic called with an empty or whitespace-only query.")
        return []

    return await call_google_cse_api(query, max_results)

async def robust_search(query: str, max_results: int = 5, detail_count: int = 2) -> List[Dict[str, Any]]:
    """
    Enriched search with parallel content scraping for optimal performance.
    Uses parallel processing and smart URL filtering.
    """
    basic_results = await search_basic(query, max_results)

    if not basic_results:
        log.info(f"Robust_search: No basic results found for query '{query}'. Returning empty list.")
        return []

    actual_detail_count = min(detail_count, len(basic_results))

    # Collect URLs to scrape with filtering
    urls_to_scrape = []
    url_to_result_map = {}

    scraped_count = 0
    for i, result_item in enumerate(basic_results[:max_results]):
        link = result_item.get("link")

        if not link:
            result_item["scraped_content"] = {"error": "No link available for scraping"}
            continue

        # Check if we should scrape this URL
        if scraped_count < actual_detail_count and should_scrape_url(link):
            normalized_link = normalize_url(link)
            urls_to_scrape.append((link, normalized_link, i))
            url_to_result_map[normalized_link] = result_item
            scraped_count += 1
        else:
            if scraped_count >= actual_detail_count:
                result_item["scraped_content"] = {"skipped": "Content scraping limit reached"}
            else:
                result_item["scraped_content"] = {"skipped": "URL not suitable for scraping"}

    if not urls_to_scrape:
        log.info(f"No URLs suitable for scraping in results for query: '{query}'")
        return basic_results

    # Parallel scraping with concurrency control
    semaphore = asyncio.Semaphore(2)  # Max 2 concurrent scrapes to be respectful

    async def scrape_with_semaphore(url_data):
        link, normalized_link, index = url_data
        async with semaphore:
            log.info(f"Scraping content for URL ({index + 1}): {link}")
            start_time = time.time()
            result = await scrape_content_with_selenium(link)
            duration = time.time() - start_time
            log.debug(f"Scraping completed for {link} in {duration:.2f}s")
            return normalized_link, result

    # Execute parallel scraping
    log.info(f"Starting parallel scraping of {len(urls_to_scrape)} URLs for query: '{query}'")
    scrape_start_time = time.time()

    try:
        scrape_tasks = [scrape_with_semaphore(url_data) for url_data in urls_to_scrape]
        scrape_results = await asyncio.gather(*scrape_tasks, return_exceptions=True)

        scrape_duration = time.time() - scrape_start_time
        log.info(f"Parallel scraping completed in {scrape_duration:.2f}s")

        # Assign scraped content to results
        successful_scrapes = 0
        for result in scrape_results:
            if isinstance(result, Exception):
                log.error(f"Scraping task failed: {result}")
                continue

            normalized_link, scraped_data = result
            if normalized_link in url_to_result_map:
                url_to_result_map[normalized_link]["scraped_content"] = scraped_data
                if "error" not in scraped_data:
                    successful_scrapes += 1

        log.info(f"Robust search for '{query}' completed. "
                 f"Successfully scraped {successful_scrapes}/{len(urls_to_scrape)} URLs. "
                 f"Total time: {scrape_duration:.2f}s")

    except Exception as e:
        log.error(f"Error during parallel scraping for query '{query}': {e}")
        # Fallback: mark all as failed
        for _, normalized_link, _ in urls_to_scrape:
            if normalized_link in url_to_result_map:
                url_to_result_map[normalized_link]["scraped_content"] = {
                    "error": f"Parallel scraping failed: {str(e)}"
                }

    return basic_results

async def search(query: str, max_results: int = 5, quick_mode: bool = False) -> List[Dict[str, Any]]:
    """
    Optimized search tool with quick mode option.

    Args:
        query (str): The search query.
        max_results (int): Maximum number of search results to return.
        quick_mode (bool): If True, returns basic results without scraping for speed.

    Returns:
        List[Dict[str, Any]]: Search results with optional scraped content.
    """
    if not isinstance(query, str) or not query.strip():
        log.error("Search tool called with invalid or empty query.")
        return [{"error": "Query must be a non-empty string and cannot be null."}]

    search_start_time = time.time()
    search_type = "quick" if quick_mode else "comprehensive"
    log.info(f"Starting {search_type} search for: '{query}' (max_results: {max_results})")

    # Check dependencies
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        log.error("Google CSE API not configured")
        return [{"error": "Search service not available: Google CSE API not configured"}]

    try:
        if quick_mode or not SELENIUM_AVAILABLE:
            if not SELENIUM_AVAILABLE and not quick_mode:
                log.warning("Selenium not available - falling back to quick mode")
            # Fast mode: just return Google results
            results = await search_basic(query, max_results)
        else:
            # Full mode: scrape content from top 2 results (reduced from 3 for speed)
            results = await robust_search(query, max_results=max_results, detail_count=2)

        search_duration = time.time() - search_start_time
        log.info(f"Search for '{query}' completed in {search_duration:.2f}s. "
                 f"Returned {len(results)} results. Mode: {search_type}")

        # Add metadata to results
        for result in results:
            result["search_metadata"] = {
                "query": query,
                "search_type": search_type,
                "search_duration": round(search_duration, 2),
                "timestamp": time.time()
            }

        return results

    except Exception as e:
        log.error(f"Unexpected error during search for '{query}': {e}", exc_info=True)
        return [{"error": f"Search failed: {str(e)}"}]

# Convenience function for quick searches
async def search_quick(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Quick search without content scraping for fastest results."""
    return await search(query, max_results, quick_mode=True)
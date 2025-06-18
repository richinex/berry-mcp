# # # packages/mcp-server/src/mcp_server/tools/doc_search_v2.py

# # import asyncio
# # import logging
# # import re
# # import json
# # import os # <-- Added for environment variables
# # from typing import Dict, Optional, Any, List, Union, Tuple
# # from urllib.parse import urlparse, urlunparse

# # import httpx # For reliable async HTTP requests
# # import trafilatura # For extracting main content from HTML

# # log = logging.getLogger(__name__)

# # # --- Configuration ---
# # KNOWN_DOC_SITES = {
# #     # Using netloc (domain) as the key, value can be priority or just True
# #     "docs.python.org": True,
# #     "requests.readthedocs.io": True,
# #     "numpy.org": True, # Main site often includes /doc/
# #     "pandas.pydata.org": True,
# #     "fastapi.tiangolo.com": True,
# #     "docs.djangoproject.com": True,
# #     "flask.palletsprojects.com": True,
# #     "docs.sqlalchemy.org": True,
# #     "docs.pydantic.dev": True,
# #     "www.python-httpx.org": True,
# #     "docs.aiohttp.org": True,
# #     "beautiful-soup-4.readthedocs.io": True,
# #     "www.selenium.dev": True,
# #     # Add more official documentation domains...
# # }

# # # Patterns to identify likely documentation URLs during ranking
# # DOC_URL_PATTERNS = [
# #     re.compile(r"readthedocs\.io", re.I),
# #     re.compile(r"docs\.[\w-]+\.\w+", re.I),
# #     re.compile(r"[\w-]+\.pydata\.org", re.I),
# #     re.compile(r"[\w-]+\.palletsprojects\.com", re.I),
# #     re.compile(r"[\w-]+\.tiangolo\.com", re.I),
# #     re.compile(r"www\.python-[\w-]+\.org", re.I),
# #     re.compile(r"numpy\.org/doc", re.I),
# #     re.compile(r"selenium\.dev/documentation", re.I),
# #     re.compile(r"pydantic\.dev", re.I),
# #     re.compile(r"/api/", re.I), # Common path segments
# #     re.compile(r"/reference/", re.I),
# #     re.compile(r"/guide/", re.I),
# #     re.compile(r"/tutorial/", re.I),
# # ]

# # # Penalty sites
# # NON_DOC_SITES = [
# #     "stackoverflow.com", "github.com", "youtube.com", "reddit.com",
# #     "geeksforgeeks.org", "medium.com", "w3schools.com",
# #     # Allow github only if it's not clearly code/issues
# # ]

# # # --- Google CSE API Configuration ---
# # GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# # GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
# # SEARCH_API_URL = "https://www.googleapis.com/customsearch/v1"

# # # --- Helper Functions ---

# # def normalize_url(url: str) -> str:
# #     """Normalize URL for deduplication and comparison."""
# #     try:
# #         parsed = urlparse(url)
# #         scheme = parsed.scheme.lower()
# #         netloc = parsed.netloc.lower().replace("www.", "")
# #         path = parsed.path.rstrip('/')
# #         normalized = urlunparse((scheme, netloc, path, '', '', ''))
# #         return normalized
# #     except Exception:
# #         return url # Fallback

# # async def call_google_cse_api(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
# #     """Calls the Google Custom Search Engine API."""
# #     if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
# #         log.error("Google API Key or CSE ID not configured in environment variables.")
# #         # Return empty list as the search cannot be performed
# #         return []

# #     params = {
# #         "key": GOOGLE_API_KEY,
# #         "cx": GOOGLE_CSE_ID,
# #         "q": query,
# #         "num": max(1, min(num_results, 10)) # API allows 1-10 results per page
# #     }
# #     results = []
# #     try:
# #         async with httpx.AsyncClient(timeout=10.0) as client:
# #             log.debug(f"Calling Google CSE API with query: '{query}'")
# #             response = await client.get(SEARCH_API_URL, params=params)
# #             response.raise_for_status() # Raise exceptions for 4xx/5xx errors
# #             data = response.json()

# #             if "items" in data:
# #                 for item in data["items"]:
# #                     results.append({
# #                         "title": item.get("title"),
# #                         "link": item.get("link"),
# #                         "snippet": item.get("snippet"),
# #                         # Google often includes pagemap data, useful for thumbnails etc.
# #                         # "pagemap": item.get("pagemap")
# #                     })
# #             else:
# #                 log.warning(f"Google CSE returned no 'items' for query: '{query}'")

# #     except httpx.HTTPStatusError as e:
# #         log.error(f"Google CSE API HTTP error ({e.response.status_code}) for query '{query}': {e.response.text}")
# #     except httpx.RequestError as e:
# #          log.error(f"Google CSE API request error for query '{query}': {e}")
# #     except Exception as e:
# #         log.error(f"Unexpected error calling Google CSE API for query '{query}': {e}", exc_info=True)

# #     log.debug(f"Google CSE API returned {len(results)} results for query: '{query}'")
# #     return results


# # async def _fetch_and_extract_content(url: str, timeout: int = 15) -> Tuple[Optional[str], Optional[str]]:
# #     """
# #     Fetches URL content and extracts main text using Trafilatura.
# #     Returns (extracted_text, error_message).
# #     """
# #     try:
# #         # Added headers to mimic a browser slightly better
# #         headers = {
# #             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36',
# #             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
# #             'Accept-Language': 'en-US,en;q=0.9',
# #             'Accept-Encoding': 'gzip, deflate, br',
# #             'Connection': 'keep-alive',
# #             'Upgrade-Insecure-Requests': '1',
# #         }
# #         async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, verify=False, headers=headers) as client:
# #             log.debug(f"Fetching URL for content extraction: {url}")
# #             response = await client.get(url)
# #             response.raise_for_status()
# #             html_content = response.text
# #             log.debug(f"Fetched {len(html_content)} bytes from {url}")

# #             # Trafilatura extract runs synchronously, wrap in to_thread
# #             extracted_text = await asyncio.to_thread(
# #                 trafilatura.extract,
# #                 html_content,
# #                 include_comments=False,
# #                 include_tables=True,
# #                 no_fallback=True # Avoid bare text extraction initially
# #             )
# #             if not extracted_text:
# #                  log.warning(f"Trafilatura extracted no main content from {url}. Attempting fallback.")
# #                  # Optional: fallback to less strict extraction
# #                  extracted_text = await asyncio.to_thread(
# #                      trafilatura.extract,
# #                      html_content,
# #                      include_comments=False,
# #                      include_tables=True,
# #                      no_fallback=False # Allow bare extraction
# #                  )
# #                  if not extracted_text:
# #                       log.error(f"Fallback extraction also failed for {url}")


# #             log.info(f"Extracted ~{len(extracted_text or '')} chars of content from {url}")
# #             return extracted_text, None

# #     except httpx.TimeoutException:
# #         log.warning(f"Timeout fetching content from {url}")
# #         return None, "Timeout fetching page content."
# #     except httpx.RequestError as e:
# #         log.warning(f"HTTP request error fetching content from {url}: {e}")
# #         return None, f"HTTP error fetching page: {e}"
# #     except httpx.HTTPStatusError as e:
# #          log.warning(f"HTTP status error {e.response.status_code} fetching content from {url}")
# #          return None, f"HTTP error {e.response.status_code} fetching page."
# #     except ImportError as e:
# #          # Specifically catch potential errors if lxml-html-clean is missing
# #          if 'lxml.html.clean' in str(e):
# #               log.error("Trafilatura dependency missing: 'lxml-html-clean'. Please install it.", exc_info=True)
# #               return None, "Server configuration error: Missing content extraction dependency."
# #          else:
# #               log.error(f"Import error during content extraction from {url}: {e}", exc_info=True)
# #               return None, f"Server configuration error during content extraction: {e}"
# #     except Exception as e:
# #         log.error(f"Error extracting content from {url}: {e}", exc_info=True)
# #         return None, f"Error processing page content: {e}"

# # # --- Main Tool Implementation ---

# # async def find_documentation(
# #     query: str,
# #     library_name: Optional[str] = None,
# #     version: Optional[str] = None,
# #     search_strategy: str = 'best_available', # Placeholder
# #     max_results: int = 5,
# #     fetch_content_level: str = 'snippet' # 'none', 'snippet', 'full_raw'
# # ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
# #     """
# #     Performs a documentation search using web search APIs (Google CSE) and ranks results.
# #     Optionally fetches full content for the top-ranked result.

# #     Args:
# #         query: The search query (keywords, function name, concept).
# #         library_name: Optional specific library to focus the search.
# #         version: Optional specific version string.
# #         search_strategy: Currently unused hint ('best_available').
# #         max_results: Maximum number of final results to return.
# #         fetch_content_level: 'none', 'snippet', or 'full_raw'.

# #     Returns:
# #         List of ranked results (title, link, snippet, Optional[content]), or error dict.
# #     """
# #     if not query:
# #         return {"error": "'query' argument is required."}
# #     if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
# #          log.error("Google CSE API Key/ID not configured on server. Documentation search unavailable.")
# #          return {"error": "Documentation search is not available due to server configuration."}

# #     log.info(f"Starting documentation search: query='{query}', library='{library_name or 'any'}', version='{version or 'any'}'")

# #     # --- Construct Queries ---
# #     queries_to_try = []
# #     norm_lib_name = library_name.lower().strip() if library_name else None
# #     version_str = f" {version}" if version else ""
# #     official_domain = None

# #     # 1. Site-specific query (if library and known domain)
# #     if norm_lib_name:
# #         for name, domain in KNOWN_DOC_SITES.items():
# #              if name in norm_lib_name.replace('-', ''):
# #                   official_domain = domain
# #                   # Use siteRestrict for better targeting if API supports it, or site: in query
# #                   # Google CSE API uses 'siteSearch' parameter or 'site:' in 'q'
# #                   queries_to_try.append(f"site:{official_domain} {query}{version_str}")
# #                   break

# #     # 2. General documentation query
# #     lib_prefix = f"\"{library_name}\"" if library_name else ""
# #     queries_to_try.append(f"{lib_prefix}{version_str} documentation {query}".strip())

# #     # --- Execute Searches (Using Google CSE API) ---
# #     all_results_raw: List[Dict[str, Any]] = []
# #     processed_norm_urls = set()

# #     search_provider = call_google_cse_api # Use the real API call function

# #     for search_query in queries_to_try:
# #         try:
# #             # Fetch a few extra in case some are duplicates or low quality
# #             basic_results = await search_provider(search_query, num_results=max_results + 3)
# #             for res in basic_results:
# #                 link = res.get("link")
# #                 if link:
# #                     norm_link = normalize_url(link)
# #                     if norm_link not in processed_norm_urls:
# #                         res['normalized_link'] = norm_link
# #                         res['search_type'] = 'google_cse' # Mark source
# #                         all_results_raw.append(res)
# #                         processed_norm_urls.add(norm_link)
# #         except Exception as e:
# #             log.warning(f"Search provider failed for query '{search_query}': {e}")
# #             continue # Try next query

# #     if not all_results_raw:
# #         log.warning(f"No results found from Google CSE for: query='{query}', library='{library_name}'")
# #         return [] # Return empty list

# #     # --- Rank Results ---
# #     def rank_result(result: Dict[str, Any]) -> float:
# #         score = 0.0
# #         link = result.get("link", "")
# #         title = result.get("title", "").lower()
# #         snippet = result.get("snippet", "").lower()
# #         combined_text = title + " " + snippet
# #         norm_link = result.get("normalized_link", "")

# #         parsed_url = urlparse(norm_link)
# #         netloc = parsed_url.netloc # Already normalized

# #         # 1. Source Priority
# #         if official_domain and official_domain == netloc: score += 100.0
# #         elif netloc in KNOWN_DOC_SITES: score += 70.0
# #         elif any(pattern.search(norm_link) for pattern in DOC_URL_PATTERNS): score += 40.0

# #         # 2. Keyword Relevance (Simple)
# #         query_words = set(re.findall(r'\b\w+\b', query.lower())) # More robust split
# #         title_words = set(re.findall(r'\b\w+\b', title))
# #         snippet_words = set(re.findall(r'\b\w+\b', snippet))
# #         if query_words.intersection(title_words): score += 15.0
# #         if query_words.intersection(snippet_words): score += 5.0

# #         # 3. Doc Keywords Bonus
# #         if any(k in combined_text for k in ["documentation", "api", "reference", "guide", "manual"]): score += 10.0
# #         if any(k in combined_text for k in ["tutorial", "example", "how-to", "usage"]): score += 5.0

# #         # 4. Penalties
# #         if parsed_url.scheme != "https": score -= 10.0
# #         is_likely_non_doc = any(site in netloc for site in NON_DOC_SITES)
# #         if "github.com" in netloc and ("/blob/" in parsed_url.path or "/issues/" in parsed_url.path or "/pull/" in parsed_url.path):
# #              is_likely_non_doc = True
# #         elif "github.com" in netloc: # Allow non-code github pages
# #              is_likely_non_doc = False
# #         if is_likely_non_doc: score -= 50.0

# #         result['relevance_score'] = round(score, 1)
# #         return score

# #     ranked_results = sorted(all_results_raw, key=rank_result, reverse=True)
# #     final_results = ranked_results[:max_results]

# #     # --- Fetch Content (if requested) ---
# #     if fetch_content_level in ['full_raw'] and final_results:
# #         # Fetch for the top result only for now (can be expanded)
# #         top_result = final_results[0]
# #         link_to_fetch = top_result.get("link")

# #         if link_to_fetch:
# #             extracted_text, error_msg = await _fetch_and_extract_content(link_to_fetch)
# #             top_result['content'] = {
# #                 "level": fetch_content_level,
# #                 "data": extracted_text if extracted_text else None,
# #                 "error": error_msg
# #             }
# #             if error_msg:
# #                  log.warning(f"Failed to get content for top result '{link_to_fetch}': {error_msg}")
# #                  # Keep the result, but note the content error
# #             elif not extracted_text:
# #                  log.warning(f"Extracted empty content for top result '{link_to_fetch}'")
# #                  # Keep the result, content.data will be None

# #     # Clean up temporary keys before returning
# #     for res in final_results:
# #         res.pop('normalized_link', None)

# #     log.info(f"Returning {len(final_results)} ranked documentation results using Google CSE.")
# #     return final_results

# # packages/mcp-server/src/mcp_server/tools/doc_search_v2.py

# import asyncio
# import logging
# import re
# import json
# import os
# from typing import Dict, Optional, Any, List, Union, Tuple
# from urllib.parse import urlparse, urlunparse

# import httpx # For reliable async HTTP requests
# import trafilatura # For extracting main content from HTML

# log = logging.getLogger(__name__)

# # --- Configuration ---
# KNOWN_DOC_SITES = {
#     # Using netloc (domain) as the key, value can be priority or just True
#     # Add more library domains here for better prioritization
#     "docs.python.org": True,
#     "requests.readthedocs.io": True,
#     "numpy.org": True,
#     "pandas.pydata.org": True,
#     "fastapi.tiangolo.com": True,
#     "docs.djangoproject.com": True,
#     "flask.palletsprojects.com": True,
#     "docs.sqlalchemy.org": True,
#     "docs.pydantic.dev": True,
#     "www.python-httpx.org": True,
#     "docs.aiohttp.org": True,
#     "beautiful-soup-4.readthedocs.io": True,
#     "www.selenium.dev": True,
#     "jax.readthedocs.io": True, # Added JAX
#     # Add more...
# }

# # Patterns to identify likely documentation URLs during ranking
# DOC_URL_PATTERNS = [
#     re.compile(r"readthedocs\.io", re.I),
#     re.compile(r"docs\.[\w-]+\.\w+", re.I), # docs.python.org, docs.djangoproject.com
#     re.compile(r"[\w-]+\.pydata\.org", re.I), # pandas.pydata.org
#     re.compile(r"[\w-]+\.palletsprojects\.com", re.I), # flask...
#     re.compile(r"[\w-]+\.tiangolo\.com", re.I), # fastapi
#     re.compile(r"www\.python-[\w-]+\.org", re.I), # httpx
#     re.compile(r"numpy\.org/doc", re.I),
#     re.compile(r"selenium\.dev/documentation", re.I),
#     re.compile(r"pydantic\.dev", re.I),
#     re.compile(r"/api/", re.I), # Common path segments
#     re.compile(r"/reference/", re.I),
#     re.compile(r"/guide/", re.I),
#     re.compile(r"/tutorial/", re.I),
# ]

# # Penalty sites (adjust as needed)
# NON_DOC_SITES = [
#     "stackoverflow.com", "github.com", "youtube.com", "reddit.com",
#     "geeksforgeeks.org", "medium.com", "w3schools.com",
#     # Allow github only if it's not clearly code/issues
# ]

# # --- Google CSE API Configuration ---
# GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
# SEARCH_API_URL = "https://www.googleapis.com/customsearch/v1"

# # --- Helper Functions ---

# def normalize_url(url: str) -> str:
#     """Normalize URL for deduplication and comparison."""
#     try:
#         parsed = urlparse(url)
#         scheme = parsed.scheme.lower()
#         netloc = parsed.netloc.lower().replace("www.", "")
#         path = parsed.path.rstrip('/')
#         # Keep only scheme, netloc, path (drop params, query, fragment)
#         normalized = urlunparse((scheme, netloc, path, '', '', ''))
#         return normalized
#     except Exception:
#         log.warning(f"Failed to normalize URL: {url}", exc_info=True)
#         return url # Fallback to original if parsing fails

# async def call_google_cse_api(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
#     """Calls the Google Custom Search Engine API."""
#     if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
#         log.error("Google API Key or CSE ID not configured in environment variables.")
#         # Return empty list as the search cannot be performed
#         return []

#     params = {
#         "key": GOOGLE_API_KEY,
#         "cx": GOOGLE_CSE_ID,
#         "q": query,
#         "num": max(1, min(num_results, 10)) # API allows 1-10 results per page
#     }
#     results = []
#     try:
#         async with httpx.AsyncClient(timeout=10.0) as client:
#             log.debug(f"Calling Google CSE API with query: '{query}'")
#             response = await client.get(SEARCH_API_URL, params=params)
#             response.raise_for_status() # Raise exceptions for 4xx/5xx errors
#             data = response.json()

#             if "items" in data:
#                 for item in data["items"]:
#                     # Ensure basic fields exist
#                     if item.get("link") and item.get("title"):
#                         results.append({
#                             "title": item.get("title"),
#                             "link": item.get("link"),
#                             "snippet": item.get("snippet", ""), # Use empty string if snippet missing
#                         })
#             else:
#                 log.warning(f"Google CSE returned no 'items' for query: '{query}'")

#     except httpx.HTTPStatusError as e:
#         log.error(f"Google CSE API HTTP error ({e.response.status_code}) for query '{query}': {e.response.text}")
#     except httpx.RequestError as e:
#          log.error(f"Google CSE API request error for query '{query}': {e}")
#     except json.JSONDecodeError as e:
#          log.error(f"Failed to decode JSON response from Google CSE API for query '{query}': {e}")
#     except Exception as e:
#         log.error(f"Unexpected error calling Google CSE API for query '{query}': {e}", exc_info=True)

#     log.debug(f"Google CSE API returned {len(results)} results for query: '{query}'")
#     return results


# async def _fetch_and_extract_content(url: str, timeout: int = 20) -> Tuple[Optional[str], Optional[str]]:
#     """
#     Fetches URL content and extracts main text using Trafilatura.
#     Returns (extracted_text, error_message). Increased timeout slightly.
#     """
#     try:
#         headers = {
#             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36', # Slightly newer UA
#             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
#             'Accept-Language': 'en-US,en;q=0.9',
#             'Accept-Encoding': 'gzip, deflate, br',
#             'Connection': 'keep-alive',
#             'Upgrade-Insecure-Requests': '1',
#         }
#         # Increased timeout, disable HTTP/2 for potential compatibility, disable SSL verification (use with caution!)
#         async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, verify=False, http2=False, headers=headers) as client:
#             log.debug(f"Fetching URL for content extraction: {url}")
#             response = await client.get(url)
#             response.raise_for_status()
#             html_content = response.text
#             log.debug(f"Fetched {len(html_content)} bytes from {url}. Status: {response.status_code}")

#             # Check content type if possible
#             content_type = response.headers.get('content-type', '').lower()
#             if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
#                  log.warning(f"Content type for {url} is '{content_type}', not HTML. Skipping Trafilatura.")
#                  return f"[Non-HTML Content Type: {content_type}]", None # Return info instead of None

#             # Trafilatura extract runs synchronously, wrap in to_thread
#             extracted_text = await asyncio.to_thread(
#                 trafilatura.extract,
#                 html_content,
#                 include_comments=False,
#                 include_tables=True,
#                 no_fallback=True # Avoid bare text extraction initially
#             )
#             if not extracted_text:
#                  log.warning(f"Trafilatura extracted no main content from {url}. Attempting fallback extraction.")
#                  extracted_text = await asyncio.to_thread(
#                      trafilatura.extract,
#                      html_content,
#                      include_comments=False,
#                      include_tables=True,
#                      no_fallback=False # Allow bare extraction
#                  )
#                  if not extracted_text:
#                       log.error(f"Fallback extraction also failed for {url}. Page might be JavaScript-heavy or have unusual structure.")
#                       return None, "Failed to extract main content from page."


#             log.info(f"Extracted ~{len(extracted_text or '')} chars of content from {url}")
#             # Limit extracted text size to avoid excessive token usage (e.g., 15k chars)
#             MAX_CONTENT_CHARS = 15000
#             if extracted_text and len(extracted_text) > MAX_CONTENT_CHARS:
#                  log.warning(f"Extracted content from {url} truncated from {len(extracted_text)} to {MAX_CONTENT_CHARS} chars.")
#                  extracted_text = extracted_text[:MAX_CONTENT_CHARS] + "\n\n[... CONTENT TRUNCATED ...]"

#             return extracted_text, None

#     except httpx.TimeoutException:
#         log.warning(f"Timeout ({timeout}s) fetching content from {url}")
#         return None, "Timeout fetching page content."
#     except httpx.RequestError as e:
#         log.warning(f"HTTP request error fetching content from {url}: {e}")
#         return None, f"HTTP error fetching page: {e}"
#     except httpx.HTTPStatusError as e:
#          log.warning(f"HTTP status error {e.response.status_code} fetching content from {url}")
#          return None, f"HTTP error {e.response.status_code} fetching page."
#     except ImportError as e:
#          if 'lxml.html.clean' in str(e):
#               log.error("Trafilatura dependency missing: 'lxml-html-clean'. Please install it.", exc_info=True)
#               return None, "Server configuration error: Missing content extraction dependency."
#          else:
#               log.error(f"Import error during content extraction from {url}: {e}", exc_info=True)
#               return None, f"Server configuration error during content extraction: {e}"
#     except Exception as e:
#         log.error(f"Error extracting content from {url}: {e}", exc_info=True)
#         return None, f"Error processing page content: {e}"

# # --- Main Tool Implementation ---

# async def find_documentation(
#     query: str,
#     library_name: Optional[str] = None,
#     version: Optional[str] = None,
#     search_strategy: str = 'best_available', # Placeholder
#     max_results: int = 5,
#     fetch_content_level: str = 'full_raw' # Default changed to 'full_raw'
# ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
#     """
#     Performs a documentation search using web search APIs (Google CSE) and ranks results.
#     Optionally fetches full content for the top-ranked result(s).

#     Args:
#         query: The search query (keywords, function name, concept).
#         library_name: Optional specific library to focus the search.
#         version: Optional specific version string.
#         search_strategy: Currently unused hint ('best_available').
#         max_results: Maximum number of final results to return.
#         fetch_content_level: 'none', 'snippet', or 'full_raw'.

#     Returns:
#         List of ranked results (title, link, snippet, Optional[content]), or error dict.
#     """
#     if not query:
#         return {"error": "'query' argument is required."}
#     if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
#          log.error("Google CSE API Key/ID not configured on server. Documentation search unavailable.")
#          return {"error": "Documentation search is not available due to server configuration."}

#     log.info(f"Starting documentation search: query='{query}', library='{library_name or 'any'}', version='{version or 'any'}', fetch_level='{fetch_content_level}'")

#     # --- Construct Queries ---
#     queries_to_try = []
#     norm_lib_name = library_name.lower().strip() if library_name else None
#     version_str = f" {version}" if version else ""
#     official_domain = None

#     # 1. Site-specific query (if library and known domain)
#     if norm_lib_name:
#         # Try finding a matching domain from known sites
#         for name, domain in KNOWN_DOC_SITES.items():
#              # Check if library name is in the key OR the domain itself
#              # Allows 'numpy' to match numpy.org, 'requests' matches requests.readthedocs.io
#              if name in norm_lib_name.replace('-', '') or norm_lib_name.replace('-', '') in name:
#                   official_domain = domain
#                   queries_to_try.append(f"site:{official_domain} {query}{version_str}")
#                   log.debug(f"Found known domain '{official_domain}' for library '{library_name}'.")
#                   break # Use first match

#     # 2. General documentation query (always include as fallback or primary)
#     lib_prefix = f"\"{library_name}\"" if library_name else ""
#     queries_to_try.append(f"{lib_prefix}{version_str} documentation {query}".strip())

#     # --- Execute Searches (Using Google CSE API) ---
#     all_results_raw: List[Dict[str, Any]] = []
#     processed_norm_urls = set()
#     search_provider = call_google_cse_api

#     for search_query in queries_to_try:
#         try:
#             # Fetch more results initially to allow for better ranking/filtering
#             basic_results = await search_provider(search_query, num_results=max_results + 5)
#             for res in basic_results:
#                 link = res.get("link")
#                 if link:
#                     norm_link = normalize_url(link)
#                     # Basic filter: skip if clearly not a doc link based on domain
#                     parsed_for_filter = urlparse(norm_link)
#                     if any(site in parsed_for_filter.netloc for site in NON_DOC_SITES):
#                          # Allow GitHub only if path doesn't look like code/issues
#                          if "github.com" in parsed_for_filter.netloc and \
#                             ("/blob/" in parsed_for_filter.path or \
#                              "/issues/" in parsed_for_filter.path or \
#                              "/pull/" in parsed_for_filter.path):
#                               log.debug(f"Skipping likely non-doc GitHub URL: {link}")
#                               continue
#                          elif "github.com" not in parsed_for_filter.netloc: # Skip other non-doc sites
#                               log.debug(f"Skipping likely non-doc URL: {link}")
#                               continue
#                          # Keep non-code GitHub links for now, ranking will handle later

#                     if norm_link not in processed_norm_urls:
#                         res['normalized_link'] = norm_link
#                         res['search_type'] = 'google_cse'
#                         all_results_raw.append(res)
#                         processed_norm_urls.add(norm_link)
#         except Exception as e:
#             log.warning(f"Search provider failed for query '{search_query}': {e}", exc_info=True)
#             continue # Try next query

#     if not all_results_raw:
#         log.warning(f"No results found from Google CSE for: query='{query}', library='{library_name}'")
#         return []

#     # --- Rank Results ---
#     def rank_result(result: Dict[str, Any]) -> float:
#         # (Ranking logic remains the same as previous version)
#         score = 0.0
#         link = result.get("link", "")
#         title = result.get("title", "").lower()
#         snippet = result.get("snippet", "").lower()
#         combined_text = title + " " + snippet
#         norm_link = result.get("normalized_link", "")
#         parsed_url = urlparse(norm_link)
#         netloc = parsed_url.netloc

#         if official_domain and official_domain == netloc: score += 100.0
#         elif netloc in KNOWN_DOC_SITES: score += 70.0
#         elif any(pattern.search(norm_link) for pattern in DOC_URL_PATTERNS): score += 40.0

#         query_words = set(re.findall(r'\b\w+\b', query.lower()))
#         title_words = set(re.findall(r'\b\w+\b', title))
#         snippet_words = set(re.findall(r'\b\w+\b', snippet))
#         common_title = query_words.intersection(title_words)
#         common_snippet = query_words.intersection(snippet_words)
#         if common_title: score += 15.0 * len(common_title) # Weight by number of common words
#         if common_snippet: score += 5.0 * len(common_snippet)

#         if any(k in combined_text for k in ["documentation", "api", "reference", "guide", "manual"]): score += 10.0
#         if any(k in combined_text for k in ["tutorial", "example", "how-to", "usage"]): score += 5.0
#         if parsed_url.scheme != "https": score -= 10.0

#         # Penalty logic refined slightly during aggregation/filtering phase now
#         result['relevance_score'] = round(score, 1)
#         return score

#     ranked_results = sorted(all_results_raw, key=rank_result, reverse=True)
#     final_results = ranked_results[:max_results]

#     # --- Fetch Content (if requested) ---
#     if fetch_content_level in ['full_raw'] and final_results:
#         # Fetch for the top result only
#         top_result = final_results[0]
#         link_to_fetch = top_result.get("link")

#         if link_to_fetch:
#             log.info(f"Fetching content for top ranked result ({top_result.get('relevance_score', 0):.1f}): {link_to_fetch}")
#             extracted_text, error_msg = await _fetch_and_extract_content(link_to_fetch)
#             top_result['content'] = {
#                 "level": fetch_content_level,
#                 "data": extracted_text if extracted_text else None,
#                 "error": error_msg
#             }
#             if error_msg:
#                  log.warning(f"Failed to get content for top result '{link_to_fetch}': {error_msg}")
#             elif not extracted_text:
#                  log.warning(f"Extracted empty content for top result '{link_to_fetch}'")

#     # Clean up temporary keys before returning
#     for res in final_results:
#         res.pop('normalized_link', None)

#     log.info(f"Returning {len(final_results)} ranked documentation results (content fetched: {fetch_content_level == 'full_raw' and 'content' in final_results[0] if final_results else False}).")
#     return final_results

# # packages/mcp-server/src/mcp_server/tools/doc_search_v2.py

# import asyncio
# import logging
# import re
# import json
# import os
# from typing import Dict, Optional, Any, List, Union, Tuple
# from urllib.parse import urlparse, urlunparse

# import httpx # For reliable async HTTP requests
# import trafilatura # For extracting main content from HTML

# log = logging.getLogger(__name__)

# # --- Configuration ---
# KNOWN_DOC_SITES = {
#     # Using netloc (domain) as the key, value can be priority or just True
#     # Add more library domains here for better prioritization

#     # --- Python Libs ---
#     "docs.python.org": True,
#     "requests.readthedocs.io": True,
#     "numpy.org": True,
#     "pandas.pydata.org": True,
#     "fastapi.tiangolo.com": True,
#     "docs.djangoproject.com": True,
#     "flask.palletsprojects.com": True,
#     "docs.sqlalchemy.org": True,
#     "docs.pydantic.dev": True,
#     "www.python-httpx.org": True,
#     "docs.aiohttp.org": True,
#     "beautiful-soup-4.readthedocs.io": True,
#     "www.selenium.dev": True,
#     "jax.readthedocs.io": True, # Added JAX

#     # --- Golang ---
#     "go.dev": True,             # Primary Go site
#     "pkg.go.dev": True,         # Go package documentation

#     # --- Other Potential Languages/Frameworks ---
#     # "doc.rust-lang.org": True,
#     # "developer.mozilla.org": True, # MDN (JS, Web APIs)
#     # ... add more as needed
# }

# # Patterns to identify likely documentation URLs during ranking
# DOC_URL_PATTERNS = [
#     # General Patterns
#     re.compile(r"readthedocs\.io", re.I),
#     re.compile(r"docs\.[\w-]+\.\w+", re.I), # docs.python.org, docs.djangoproject.com
#     re.compile(r"[\w-]+\.pydata\.org", re.I), # pandas.pydata.org
#     re.compile(r"[\w-]+\.palletsprojects\.com", re.I), # flask...
#     re.compile(r"[\w-]+\.tiangolo\.com", re.I), # fastapi
#     re.compile(r"www\.python-[\w-]+\.org", re.I), # httpx
#     re.compile(r"selenium\.dev/documentation", re.I),
#     re.compile(r"pydantic\.dev", re.I),
#     re.compile(r"/api/", re.I), # Common path segments
#     re.compile(r"/reference/", re.I),
#     re.compile(r"/guide/", re.I),
#     re.compile(r"/tutorial/", re.I),
#     re.compile(r"/docs?(?:umentation)?/", re.I), # /doc/, /docs/, /documentation/

#     # Go Specific Patterns
#     re.compile(r"go\.dev/doc", re.I),          # Go doc sections
#     re.compile(r"go\.dev/ref", re.I),          # Go reference sections (like spec)
#     re.compile(r"go\.dev/blog", re.I),         # Go blog often has deep dives
#     re.compile(r"go\.dev/tour", re.I),         # Go tour
#     re.compile(r"pkg\.go\.dev/[\w/.-]+", re.I), # Go package site

#     # Other Language/Framework Patterns (Examples)
#     # re.compile(r"doc\.rust-lang\.org", re.I),
#     # re.compile(r"developer\.mozilla\.org", re.I), # MDN
# ]

# # Penalty sites (adjust as needed)
# NON_DOC_SITES = [
#     "stackoverflow.com", "github.com", "youtube.com", "reddit.com",
#     "geeksforgeeks.org", "medium.com", "w3schools.com",
#     "tutorialspoint.com", # Added another common low-quality source
#     # Allow github only if it's not clearly code/issues/discussions/actions
# ]

# # --- Google CSE API Configuration ---
# GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
# SEARCH_API_URL = "https://www.googleapis.com/customsearch/v1"

# # --- Helper Functions ---

# def normalize_url(url: str) -> str:
#     """Normalize URL for deduplication and comparison."""
#     try:
#         parsed = urlparse(url)
#         # Use lower() for scheme and netloc for case-insensitivity
#         scheme = parsed.scheme.lower()
#         # Remove 'www.' prefix more reliably
#         netloc_parts = parsed.netloc.lower().split('.')
#         if len(netloc_parts) > 1 and netloc_parts[0] == 'www':
#             netloc = '.'.join(netloc_parts[1:])
#         else:
#             netloc = parsed.netloc.lower()

#         path = parsed.path.rstrip('/') or '/' # Ensure path is at least '/'
#         # Keep only scheme, netloc, path (drop params, query, fragment)
#         normalized = urlunparse((scheme, netloc, path, '', '', ''))
#         return normalized
#     except Exception:
#         log.warning(f"Failed to normalize URL: {url}", exc_info=True)
#         return url # Fallback to original if parsing fails

# async def call_google_cse_api(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
#     """Calls the Google Custom Search Engine API."""
#     if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
#         log.error("Google API Key or CSE ID not configured in environment variables.")
#         # Return empty list as the search cannot be performed
#         return []

#     params = {
#         "key": GOOGLE_API_KEY,
#         "cx": GOOGLE_CSE_ID,
#         "q": query,
#         "num": max(1, min(num_results, 10)) # API allows 1-10 results per page
#     }
#     results = []
#     try:
#         # Increase default timeout slightly, standard practice for external APIs
#         async with httpx.AsyncClient(timeout=15.0) as client:
#             log.debug(f"Calling Google CSE API with query: '{query}'")
#             response = await client.get(SEARCH_API_URL, params=params)
#             response.raise_for_status() # Raise exceptions for 4xx/5xx errors
#             data = response.json()

#             if "items" in data:
#                 for item in data["items"]:
#                     # Ensure basic fields exist
#                     if item.get("link") and item.get("title"):
#                         results.append({
#                             "title": item.get("title"),
#                             "link": item.get("link"),
#                             "snippet": item.get("snippet", ""), # Use empty string if snippet missing
#                         })
#             else:
#                 log.warning(f"Google CSE returned no 'items' for query: '{query}'. Response: {data}")

#     except httpx.HTTPStatusError as e:
#         log.error(f"Google CSE API HTTP error ({e.response.status_code}) for query '{query}': {e.response.text}")
#     except httpx.RequestError as e:
#          log.error(f"Google CSE API request error for query '{query}': {e}")
#     except json.JSONDecodeError as e:
#          log.error(f"Failed to decode JSON response from Google CSE API for query '{query}': {e}")
#     except Exception as e:
#         log.error(f"Unexpected error calling Google CSE API for query '{query}': {e}", exc_info=True)

#     log.debug(f"Google CSE API returned {len(results)} results for query: '{query}'")
#     return results


# async def _fetch_and_extract_content(url: str, timeout: int = 20) -> Tuple[Optional[str], Optional[str]]:
#     """
#     Fetches URL content and extracts main text using Trafilatura.
#     Returns (extracted_text, error_message). Increased timeout slightly.
#     """
#     try:
#         # Standard User-Agent often works better than overly specific ones
#         headers = {
#             'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)', # Pretend to be Googlebot (use responsibly)
#             # 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
#             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
#             'Accept-Language': 'en-US,en;q=0.9',
#             'Accept-Encoding': 'gzip, deflate, br',
#             'Connection': 'keep-alive',
#             'Upgrade-Insecure-Requests': '1',
#         }
#         # Keep verify=False ONLY if encountering frequent SSL issues, otherwise set to True.
#         # http2=False can sometimes help with compatibility.
#         async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, verify=True, http2=False, headers=headers) as client:
#             log.debug(f"Fetching URL for content extraction: {url}")
#             response = await client.get(url)
#             response.raise_for_status()
#             html_content = response.text
#             log.debug(f"Fetched {len(html_content)} bytes from {url}. Status: {response.status_code}")

#             # Check content type if possible
#             content_type = response.headers.get('content-type', '').lower()
#             if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
#                  log.warning(f"Content type for {url} is '{content_type}', not HTML. Skipping Trafilatura.")
#                  return f"[Non-HTML Content Type: {content_type}]", None # Return info instead of None

#             # Trafilatura extract runs synchronously, wrap in to_thread
#             # Use favor_precision=True for documentation sites which often have clearer structure
#             extracted_text = await asyncio.to_thread(
#                 trafilatura.extract,
#                 html_content,
#                 include_comments=False,
#                 include_tables=True,
#                 favor_precision=True, # Try precision mode first
#                 no_fallback=True
#             )
#             if not extracted_text:
#                  log.warning(f"Trafilatura (precision) extracted no main content from {url}. Attempting fallback extraction.")
#                  extracted_text = await asyncio.to_thread(
#                      trafilatura.extract,
#                      html_content,
#                      include_comments=False,
#                      include_tables=True,
#                      no_fallback=False # Allow bare extraction (less precise)
#                  )
#                  if not extracted_text:
#                       log.error(f"Fallback extraction also failed for {url}. Page might be JavaScript-heavy or have unusual structure.")
#                       return None, "Failed to extract main content from page."


#             log.info(f"Extracted ~{len(extracted_text or '')} chars of content from {url}")
#             # Limit extracted text size to avoid excessive token usage (e.g., 20k chars)
#             MAX_CONTENT_CHARS = 20000
#             if extracted_text and len(extracted_text) > MAX_CONTENT_CHARS:
#                  log.warning(f"Extracted content from {url} truncated from {len(extracted_text)} to {MAX_CONTENT_CHARS} chars.")
#                  extracted_text = extracted_text[:MAX_CONTENT_CHARS] + "\n\n[... CONTENT TRUNCATED ...]"

#             return extracted_text, None

#     except httpx.TimeoutException:
#         log.warning(f"Timeout ({timeout}s) fetching content from {url}")
#         return None, "Timeout fetching page content."
#     except httpx.RequestError as e:
#         # Log the specific URL causing the error
#         log.warning(f"HTTP request error fetching content from {url}: {type(e).__name__} - {e}")
#         return None, f"HTTP error fetching page: {type(e).__name__}"
#     except httpx.HTTPStatusError as e:
#          log.warning(f"HTTP status error {e.response.status_code} fetching content from {url}")
#          return None, f"HTTP error {e.response.status_code} fetching page."
#     except ImportError as e:
#          if 'lxml.html.clean' in str(e):
#               log.error("Trafilatura dependency missing: 'lxml-html-clean'. Please install it.", exc_info=True)
#               return None, "Server configuration error: Missing content extraction dependency."
#          else:
#               log.error(f"Import error during content extraction from {url}: {e}", exc_info=True)
#               return None, f"Server configuration error during content extraction: {e}"
#     except Exception as e:
#         log.error(f"Error extracting content from {url}: {e}", exc_info=True)
#         return None, f"Error processing page content: {e}"

# # --- Main Tool Implementation ---

# async def find_documentation(
#     query: str,
#     library_name: Optional[str] = None,
#     version: Optional[str] = None,
#     search_strategy: str = 'best_available', # Placeholder
#     max_results: int = 5,
#     fetch_content_level: str = 'full_raw' # Default changed to 'full_raw'
# ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
#     """
#     Performs a documentation search using web search APIs (Google CSE) and ranks results.
#     Optionally fetches full content for the top-ranked result(s).

#     Args:
#         query: The search query (keywords, function name, concept).
#         library_name: Optional specific library to focus the search (e.g., "requests", "golang").
#         version: Optional specific version string.
#         search_strategy: Currently unused hint ('best_available').
#         max_results: Maximum number of final results to return.
#         fetch_content_level: 'none', 'snippet', or 'full_raw'.

#     Returns:
#         List of ranked results (title, link, snippet, Optional[content]), or error dict.
#     """
#     if not query:
#         return {"error": "'query' argument is required."}
#     if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
#          log.error("Google CSE API Key/ID not configured on server. Documentation search unavailable.")
#          return {"error": "Documentation search is not available due to server configuration."}

#     log.info(f"Starting documentation search: query='{query}', library='{library_name or 'any'}', version='{version or 'any'}', fetch_level='{fetch_content_level}'")

#     # --- Construct Queries ---
#     queries_to_try = []
#     norm_lib_name = library_name.lower().strip() if library_name else None
#     # Special handling for 'go' / 'golang'
#     is_golang_query = norm_lib_name in ["go", "golang"]
#     if is_golang_query:
#         norm_lib_name = "golang" # Standardize

#     version_str = f" {version}" if version else ""
#     official_domain_found = None # Store the matched domain netloc

#     # 1. Site-specific query (if library and known domain)
#     if norm_lib_name:
#         # Try finding a matching domain from known sites
#         # Normalize netlocs from KNOWN_DOC_SITES for matching
#         known_netlocs = {urlparse(f"https://{d}").netloc.replace("www.", ""): d for d in KNOWN_DOC_SITES}

#         # More robust matching for library name -> domain
#         lib_name_variations = {norm_lib_name, norm_lib_name.replace('-', ''), norm_lib_name.replace('_', '')}
#         if is_golang_query:
#             lib_name_variations.add("go") # Add "go" specifically for golang queries

#         matched_domain_key = None
#         for variation in lib_name_variations:
#             # Check if variation matches a key directly (like 'numpy.org')
#             if variation in known_netlocs:
#                  matched_domain_key = variation
#                  break
#             # Check if variation is *part* of a key (like 'requests' in 'requests.readthedocs.io')
#             for key_netloc in known_netlocs:
#                  if variation in key_netloc.split('.'):
#                       matched_domain_key = key_netloc
#                       break
#             if matched_domain_key:
#                  break

#         if matched_domain_key:
#              official_domain_for_query = KNOWN_DOC_SITES.get(matched_domain_key) or known_netlocs.get(matched_domain_key) # Get original key/netloc
#              if official_domain_for_query: # Ensure we got a value
#                 # Use the original domain string from KNOWN_DOC_SITES for the site: search
#                 queries_to_try.append(f"site:{official_domain_for_query} {query}{version_str}")
#                 log.debug(f"Found known domain '{official_domain_for_query}' for library '{library_name}'. Adding site-specific query.")
#                 # Store the normalized netloc for ranking later
#                 official_domain_found = urlparse(f"https://{official_domain_for_query}").netloc.replace("www.", "")


#     # 2. General documentation query (always include as fallback or primary)
#     lib_prefix = f"\"{library_name}\"" if library_name and not is_golang_query else "golang" if is_golang_query else ""
#     # Refine general query: For Go, maybe prioritize "spec", "effective go", "tour" over generic "documentation" for core concepts?
#     # This is harder to generalize. Let's stick with "documentation" for now, but add a slightly broader one.
#     queries_to_try.append(f"{lib_prefix}{version_str} documentation {query}".strip())
#     # Maybe a slightly broader query without "documentation" if lib name is present
#     if lib_prefix:
#         queries_to_try.append(f"{lib_prefix}{version_str} {query}".strip())


#     # --- Execute Searches (Using Google CSE API) ---
#     all_results_raw: List[Dict[str, Any]] = []
#     processed_norm_urls = set()
#     search_provider = call_google_cse_api

#     # Remove duplicate queries before running
#     unique_queries = []
#     for q in queries_to_try:
#         if q not in unique_queries:
#             unique_queries.append(q)

#     for search_query in unique_queries:
#         try:
#             # Fetch more results initially to allow for better ranking/filtering
#             basic_results = await search_provider(search_query, num_results=max_results + 5)
#             for res in basic_results:
#                 link = res.get("link")
#                 if link:
#                     try:
#                         norm_link = normalize_url(link)
#                         parsed_for_filter = urlparse(norm_link)
#                         netloc_for_filter = parsed_for_filter.netloc

#                         # Filter NON_DOC_SITES, refining GitHub logic
#                         is_non_doc = False
#                         for site in NON_DOC_SITES:
#                              if site in netloc_for_filter:
#                                   if site == "github.com":
#                                        # Allow github.io, but filter code/issues/etc. on github.com
#                                        if not netloc_for_filter.endswith(".github.io") and \
#                                           ("/blob/" in parsed_for_filter.path or \
#                                            "/issues/" in parsed_for_filter.path or \
#                                            "/pull/" in parsed_for_filter.path or \
#                                            "/discussions/" in parsed_for_filter.path or \
#                                            "/actions/" in parsed_for_filter.path or \
#                                            parsed_for_filter.path == '/' or # Root of repo
#                                            len(parsed_for_filter.path.split('/')) <= 2): # e.g. /user/repo
#                                                log.debug(f"Skipping likely non-doc GitHub URL: {link}")
#                                                is_non_doc = True
#                                                break
#                                   else:
#                                        log.debug(f"Skipping non-doc site URL: {link}")
#                                        is_non_doc = True
#                                        break
#                         if is_non_doc:
#                              continue

#                         if norm_link not in processed_norm_urls:
#                             res['normalized_link'] = norm_link
#                             res['search_type'] = 'google_cse'
#                             all_results_raw.append(res)
#                             processed_norm_urls.add(norm_link)
#                     except Exception as norm_err:
#                          log.warning(f"Error processing link {link} during filtering: {norm_err}", exc_info=True)
#                          continue # Skip result if processing fails
#         except Exception as e:
#             log.warning(f"Search provider failed for query '{search_query}': {e}", exc_info=True)
#             continue # Try next query

#     if not all_results_raw:
#         log.warning(f"No results found from Google CSE for: query='{query}', library='{library_name}'")
#         # Provide a more informative empty state if possible
#         # E.g., return {"message": "No documentation found via search.", "results": []}
#         return []

#     # --- Rank Results ---
#     def rank_result(result: Dict[str, Any]) -> float:
#         score = 0.0
#         link = result.get("link", "")
#         title = result.get("title", "").lower()
#         snippet = result.get("snippet", "").lower()
#         combined_text = title + " " + snippet
#         norm_link = result.get("normalized_link", "")
#         try:
#             parsed_url = urlparse(norm_link)
#             netloc = parsed_url.netloc # Already normalized (www removed, lowercased)
#         except Exception:
#              log.warning(f"Could not parse normalized URL for ranking: {norm_link}")
#              return -1000 # Heavily penalize unparseable URLs

#         # --- Major Boosts ---
#         # Use official_domain_found (normalized netloc) captured during query building
#         if official_domain_found and official_domain_found == netloc:
#             score += 100.0
#             log.debug(f"Rank: +100 (Official domain match: {netloc}) for {link}")
#         # Check against normalized known_netlocs
#         elif netloc in KNOWN_DOC_SITES: # Check direct key match (already normalized)
#             score += 75.0 # Slightly lower boost than specific match from query phase
#             log.debug(f"Rank: +75 (Known doc site match: {netloc}) for {link}")
#         elif any(pattern.search(norm_link) for pattern in DOC_URL_PATTERNS):
#             score += 40.0
#             log.debug(f"Rank: +40 (Doc URL pattern match) for {link}")


#         # --- Keyword Boosts ---
#         query_words = set(re.findall(r'\b\w{3,}\b', query.lower())) # Ignore very short words
#         title_words = set(re.findall(r'\b\w+\b', title))
#         snippet_words = set(re.findall(r'\b\w+\b', snippet))

#         # Boost more if query words appear early in the title
#         try:
#             first_title_match_pos = min(title.find(qw) for qw in query_words if qw in title)
#             if first_title_match_pos < 20: # Arbitrary threshold for "early"
#                 score += 10.0
#                 log.debug(f"Rank: +10 (Query match early in title) for {link}")
#         except (ValueError, TypeError): # Handle cases where no words match or errors occur
#              pass

#         common_title = query_words.intersection(title_words)
#         common_snippet = query_words.intersection(snippet_words)
#         if common_title:
#              title_boost = 15.0 * len(common_title)
#              score += title_boost
#              log.debug(f"Rank: +{title_boost:.1f} (Query/Title overlap: {len(common_title)} words) for {link}")
#         if common_snippet:
#              snippet_boost = 5.0 * len(common_snippet)
#              score += snippet_boost
#              log.debug(f"Rank: +{snippet_boost:.1f} (Query/Snippet overlap: {len(common_snippet)} words) for {link}")


#         # --- Documentation Keyword Boosts ---
#         doc_keywords = ["documentation", "api", "reference", "guide", "manual", "spec", "specification", "effective go", "tour"]
#         tutorial_keywords = ["tutorial", "example", "how-to", "usage", "getting started", "quickstart"]
#         if any(k in combined_text for k in doc_keywords):
#              score += 15.0 # Increased boost
#              log.debug(f"Rank: +15 (Doc keyword match) for {link}")

#         if any(k in combined_text for k in tutorial_keywords):
#              score += 8.0 # Slightly increased boost
#              log.debug(f"Rank: +8 (Tutorial keyword match) for {link}")


#         # --- Penalties ---
#         if parsed_url.scheme != "https":
#             score -= 20.0 # Stronger penalty for non-HTTPS
#             log.debug(f"Rank: -20 (Non-HTTPS) for {link}")

#         # Penalize short paths (less likely to be specific doc pages) - adjust threshold as needed
#         path_depth = len(list(filter(None, parsed_url.path.split('/'))))
#         if path_depth <= 1 and parsed_url.path not in ['/', '/doc/', '/docs/']: # Allow root or common doc roots
#             score -= 5.0
#             log.debug(f"Rank: -5 (Shallow path depth: {path_depth}) for {link}")

#         # Optional: Penalize if the domain is just the library name (e.g., numpy.org/ - less specific)
#         # This is tricky, skip for now.

#         result['relevance_score'] = round(score, 1)
#         return score

#     ranked_results = sorted(all_results_raw, key=rank_result, reverse=True)
#     final_results = ranked_results[:max_results]

#     # --- Fetch Content (if requested) ---
#     if fetch_content_level in ['full_raw'] and final_results:
#         top_result = final_results[0]
#         link_to_fetch = top_result.get("link")

#         if link_to_fetch:
#             log.info(f"Fetching content for top ranked result ({top_result.get('relevance_score', 0):.1f}): {link_to_fetch}")
#             extracted_text, error_msg = await _fetch_and_extract_content(link_to_fetch)

#             # Store structured content info
#             content_info = {
#                 "level": fetch_content_level,
#                 "data": extracted_text if extracted_text else None,
#                 "error": error_msg,
#                 "source_url": link_to_fetch # Add source URL for clarity
#             }
#             # Only add 'data' key if extraction was successful and non-empty
#             if not extracted_text:
#                  content_info.pop("data", None)

#             top_result['content'] = content_info

#             if error_msg:
#                  log.warning(f"Failed to get content for top result '{link_to_fetch}': {error_msg}")
#             elif not extracted_text:
#                  log.warning(f"Extracted empty content for top result '{link_to_fetch}'")

#     # Clean up temporary keys before returning
#     for res in final_results:
#         res.pop('normalized_link', None)
#         res.pop('search_type', None) # Remove internal keys


#     log.info(f"Returning {len(final_results)} ranked documentation results (content fetched: {fetch_content_level == 'full_raw' and 'content' in final_results[0] if final_results else False}). Top score: {final_results[0]['relevance_score'] if final_results else 'N/A'}")
#     # Return the list directly, even if empty (consistent return type)
#     return final_results

# # --- Example Usage (for testing) ---
# async def main_test():
#     # Test Case 1: Golang Channels
#     print("--- Testing: Golang Channels ---")
#     results_go = await find_documentation(query="channels", library_name="golang", fetch_content_level='full_raw')
#     if isinstance(results_go, list):
#         for i, r in enumerate(results_go):
#             print(f"{i+1}. {r.get('title')} ({r.get('relevance_score')}) - {r.get('link')}")
#             if 'content' in r:
#                 print(f"  Content Status: {'OK' if r['content'].get('data') else 'Empty/Failed'}{' | Error: ' + r['content']['error'] if r['content'].get('error') else ''}")
#                 # print(f"  Content Data: {r['content'].get('data', '')[:200]}...") # Uncomment to see content snippet
#     else:
#         print(f"Error: {results_go}")

#     # Test Case 2: Python Requests Timeout
#     print("\n--- Testing: Python Requests Timeout ---")
#     results_py = await find_documentation(query="timeout parameter", library_name="requests", fetch_content_level='snippet')
#     if isinstance(results_py, list):
#         for i, r in enumerate(results_py):
#             print(f"{i+1}. {r.get('title')} ({r.get('relevance_score')}) - {r.get('link')}")
#             print(f"  Snippet: {r.get('snippet')}")
#     else:
#         print(f"Error: {results_py}")

# if __name__ == "__main__":
#     logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
#     # Ensure environment variables are set for testing
#     if not os.getenv("GOOGLE_API_KEY") or not os.getenv("GOOGLE_CSE_ID"):
#          print("Error: GOOGLE_API_KEY and GOOGLE_CSE_ID environment variables must be set to run tests.")
#     else:
#          asyncio.run(main_test())

# # packages/mcp-server/src/mcp_server/tools/doc_search_v2.py

# import asyncio
# import logging
# import re
# import json
# import os
# from typing import Dict, Optional, Any, List, Union, Tuple
# from urllib.parse import urlparse, urlunparse

# import httpx # For reliable async HTTP requests
# import trafilatura # For extracting main content from HTML

# log = logging.getLogger(__name__)

# # --- Configuration ---
# KNOWN_DOC_SITES = {
#     # Library Name (lowercase, common alias) -> Official Domain (netloc, no www)
#     # Use common variations people might type
#     "python": "docs.python.org",
#     "python3": "docs.python.org",
#     "requests": "requests.readthedocs.io",
#     "numpy": "numpy.org",
#     "np": "numpy.org", # Alias
#     "pandas": "pandas.pydata.org",
#     "pd": "pandas.pydata.org", # Alias
#     "fastapi": "fastapi.tiangolo.com",
#     "django": "docs.djangoproject.com",
#     "flask": "flask.palletsprojects.com",
#     "sqlalchemy": "docs.sqlalchemy.org",
#     "pydantic": "docs.pydantic.dev",
#     "httpx": "python-httpx.org", # Domain is www.python-httpx.org, normalize removes www
#     "aiohttp": "docs.aiohttp.org",
#     "beautifulsoup": "beautiful-soup-4.readthedocs.io",
#     "bs4": "beautiful-soup-4.readthedocs.io", # Alias
#     "selenium": "selenium.dev", # Domain is www.selenium.dev
#     "jax": "jax.readthedocs.io",
#     "go": "go.dev",             # Map 'go' to go.dev
#     "golang": "go.dev",         # Map 'golang' to go.dev
#     # Add more... e.g., 'pytorch': 'pytorch.org'
# }

# # Patterns to identify likely documentation URLs during ranking
# DOC_URL_PATTERNS = [
#     re.compile(r"readthedocs\.io", re.I),
#     re.compile(r"docs\.[\w-]+\.\w+", re.I), # docs.python.org, docs.djangoproject.com
#     re.compile(r"[\w-]+\.pydata\.org", re.I), # pandas.pydata.org
#     re.compile(r"[\w-]+\.palletsprojects\.com", re.I), # flask...
#     re.compile(r"[\w-]+\.tiangolo\.com", re.I), # fastapi
#     re.compile(r"python-[\w-]+\.org", re.I), # httpx (handle www removal)
#     re.compile(r"numpy\.org/doc", re.I),
#     re.compile(r"selenium\.dev/documentation", re.I),
#     re.compile(r"pydantic\.dev", re.I),
#     re.compile(r"go\.dev/(?:doc|ref|tour|pkg)/", re.I), # Added Go paths
#     re.compile(r"pkg\.go\.dev/", re.I), # Added Go package site
#     re.compile(r"/api/", re.I), # Common path segments
#     re.compile(r"/reference/", re.I),
#     re.compile(r"/guide/", re.I),
#     re.compile(r"/tutorial/", re.I),
#     re.compile(r"/docs/", re.I), # Common path segment
# ]

# # Penalty sites (adjust as needed)
# NON_DOC_SITES = [
#     "stackoverflow.com", "github.com", "youtube.com", "reddit.com",
#     "geeksforgeeks.org", "medium.com", "w3schools.com", "tutorialspoint.com",
#     # Allow github only if it's not clearly code/issues/PRs
# ]

# # --- Google CSE API Configuration ---
# GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
# SEARCH_API_URL = "https://www.googleapis.com/customsearch/v1"

# # --- Helper Functions ---

# def normalize_url(url: str) -> str:
#     """Normalize URL for deduplication and comparison."""
#     try:
#         parsed = urlparse(url)
#         scheme = parsed.scheme.lower()
#         # Handle cases where netloc might be empty (e.g., mailto: links)
#         netloc = parsed.netloc.lower().replace("www.", "") if parsed.netloc else ""
#         path = parsed.path.rstrip('/') if parsed.path else ""
#         # Reconstruct, ensuring components are strings
#         normalized = urlunparse((str(scheme), str(netloc), str(path), '', '', ''))
#         return normalized
#     except Exception:
#         log.warning(f"Failed to normalize URL: {url}", exc_info=True)
#         return url # Fallback

# async def call_google_cse_api(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
#     """Calls the Google Custom Search Engine API."""
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
#                             "snippet": item.get("snippet", ""),
#                         })
#             else:
#                 log.warning(f"Google CSE returned no 'items' for query: '{query}'")

#     except httpx.HTTPStatusError as e:
#         log.error(f"Google CSE API HTTP error ({e.response.status_code}) for query '{query}': {e.response.text}")
#     except httpx.RequestError as e:
#          log.error(f"Google CSE API request error for query '{query}': {e}")
#     except json.JSONDecodeError as e:
#          log.error(f"Failed to decode JSON response from Google CSE API for query '{query}': {e}")
#     except Exception as e:
#         log.error(f"Unexpected error calling Google CSE API for query '{query}': {e}", exc_info=True)

#     log.debug(f"Google CSE API returned {len(results)} results for query: '{query}'")
#     return results


# async def _fetch_and_extract_content(url: str, timeout: int = 20) -> Tuple[Optional[str], Optional[str]]:
#     """
#     Fetches URL content and extracts main text using Trafilatura.
#     Returns (extracted_text, error_message).
#     """
#     extracted_text: Optional[str] = None
#     error_msg: Optional[str] = None
#     try:
#         headers = {
#             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
#             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
#             'Accept-Language': 'en-US,en;q=0.9',
#             'Accept-Encoding': 'gzip, deflate, br',
#             'Connection': 'keep-alive',
#             'Upgrade-Insecure-Requests': '1',
#         }
#         # Note: verify=False disables SSL certificate verification - use cautiously.
#         # http2=False can sometimes help with compatibility.
#         async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, verify=False, http2=False, headers=headers) as client:
#             log.debug(f"Fetching URL for content extraction: {url}")
#             response = await client.get(url)
#             response.raise_for_status() # Check for 4xx/5xx errors immediately
#             html_content = response.text
#             log.debug(f"Fetched {len(html_content)} bytes from {url}. Status: {response.status_code}")

#             content_type = response.headers.get('content-type', '').lower()
#             if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
#                  log.warning(f"Content type for {url} is '{content_type}', not HTML. Skipping Trafilatura.")
#                  extracted_text = f"[Non-HTML Content Type: {content_type}]" # Return info instead of None
#             else:
#                 # Run Trafilatura in a separate thread
#                 extracted_text = await asyncio.to_thread(
#                     trafilatura.extract,
#                     html_content,
#                     include_comments=False,
#                     include_tables=True,
#                     no_fallback=True # Try strict extraction first
#                 )
#                 if not extracted_text:
#                      log.warning(f"Trafilatura (strict) extracted no main content from {url}. Attempting fallback.")
#                      extracted_text = await asyncio.to_thread(
#                          trafilatura.extract,
#                          html_content,
#                          include_comments=False,
#                          include_tables=True,
#                          no_fallback=False # Allow bare extraction as fallback
#                      )
#                      if not extracted_text:
#                           log.error(f"Fallback extraction also failed for {url}. Page might be JS-heavy or have unusual structure.")
#                           error_msg = "Failed to extract main content from page."

#             if extracted_text:
#                 log.info(f"Extracted ~{len(extracted_text)} chars of content from {url}")
#                 # Limit extracted text size
#                 MAX_CONTENT_CHARS = 15000
#                 if len(extracted_text) > MAX_CONTENT_CHARS:
#                      log.warning(f"Extracted content from {url} truncated from {len(extracted_text)} to {MAX_CONTENT_CHARS} chars.")
#                      extracted_text = extracted_text[:MAX_CONTENT_CHARS] + "\n\n[... CONTENT TRUNCATED ...]"

#     except httpx.TimeoutException:
#         error_msg = f"Timeout ({timeout}s) fetching page content."
#         log.warning(f"{error_msg} URL: {url}")
#     except httpx.RequestError as e:
#         error_msg = f"HTTP request error fetching page: {e}"
#         log.warning(f"{error_msg} URL: {url}")
#     except httpx.HTTPStatusError as e:
#          error_msg = f"HTTP error {e.response.status_code} fetching page."
#          log.warning(f"{error_msg} URL: {url}")
#     except ImportError as e:
#          # Handle potential missing optional dependency for trafilatura
#          if 'lxml.html.clean' in str(e):
#               error_msg = "Server configuration error: Missing 'lxml-html-clean' dependency."
#               log.error(error_msg, exc_info=True)
#          else:
#               error_msg = f"Server configuration error during content extraction: {e}"
#               log.error(f"Import error during content extraction from {url}: {e}", exc_info=True)
#     except Exception as e:
#         error_msg = f"Error processing page content: {e}"
#         log.error(f"Unexpected error extracting content from {url}: {e}", exc_info=True)

#     # Return tuple (text, error)
#     return extracted_text, error_msg

# # --- Main Tool Implementation ---

# async def find_documentation(
#     query: str,
#     library_name: Optional[str] = None,
#     version: Optional[str] = None,
#     search_strategy: str = 'best_available', # Placeholder
#     max_results: int = 5,
#     fetch_content_level: str = 'full_raw' # Default set to fetch full content
# ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
#     """
#     Performs a documentation search using web search APIs (Google CSE) and ranks results.
#     Optionally fetches full content for the top-ranked result(s).

#     Args:
#         query: The search query (keywords, function name, concept).
#         library_name: Optional specific library to focus the search.
#         version: Optional specific version string.
#         search_strategy: Currently unused hint ('best_available').
#         max_results: Maximum number of final results to return.
#         fetch_content_level: 'none', 'snippet', or 'full_raw'.

#     Returns:
#         List of ranked results (title, link, snippet, Optional[content]), or error dict.
#     """
#     if not query:
#         return {"error": "'query' argument is required."}
#     if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
#          log.error("Google CSE API Key/ID not configured on server. Documentation search unavailable.")
#          return {"error": "Documentation search is not available due to server configuration."}

#     log.info(f"Starting documentation search: query='{query}', library='{library_name or 'any'}', version='{version or 'any'}', fetch_level='{fetch_content_level}'")

#     # --- Construct Queries ---
#     queries_to_try = []
#     norm_lib_name = library_name.lower().strip().replace('-', '') if library_name else None # Normalize for lookup
#     version_str = f" {version}" if version else ""
#     official_domain = None

#     # 1. Site-specific query (if library and known domain)
#     if norm_lib_name:
#         official_domain = KNOWN_DOC_SITES.get(norm_lib_name) # Direct lookup using normalized name
#         if official_domain:
#              # Google CSE API uses 'siteSearch' parameter or 'site:' in 'q'
#              queries_to_try.append(f"site:{official_domain} {query}{version_str}")
#              log.debug(f"Found known domain '{official_domain}' for library '{library_name}'. Adding site-specific query.")
#         else:
#              log.debug(f"No pre-configured domain found for library '{library_name}' in KNOWN_DOC_SITES.")

#     # 2. General documentation query (always include)
#     # Use original library name if available for potentially better search results
#     lib_prefix = f"\"{library_name}\"" if library_name else ""
#     queries_to_try.append(f"{lib_prefix}{version_str} documentation {query}".strip())

#     # --- Execute Searches (Using Google CSE API) ---
#     all_results_raw: List[Dict[str, Any]] = []
#     processed_norm_urls = set()
#     search_provider = call_google_cse_api

#     for search_query in queries_to_try:
#         try:
#             # Fetch more results initially to allow for better ranking/filtering
#             basic_results = await search_provider(search_query, num_results=max_results + 5)
#             for res in basic_results:
#                 link = res.get("link")
#                 title = res.get("title")
#                 if link and title: # Basic check for usable result
#                     norm_link = normalize_url(link)
#                     if norm_link not in processed_norm_urls:
#                         # Filter clearly non-doc sites early if possible
#                         parsed_for_filter = urlparse(norm_link)
#                         is_likely_non_doc_site = False
#                         if any(site in parsed_for_filter.netloc for site in NON_DOC_SITES):
#                              # Special check for GitHub
#                              if "github.com" in parsed_for_filter.netloc and \
#                                 ("/blob/" in parsed_for_filter.path or \
#                                  "/issues/" in parsed_for_filter.path or \
#                                  "/pull/" in parsed_for_filter.path):
#                                   is_likely_non_doc_site = True
#                              elif "github.com" not in parsed_for_filter.netloc:
#                                   is_likely_non_doc_site = True

#                         if is_likely_non_doc_site:
#                               log.debug(f"Filtering out likely non-doc URL during aggregation: {link}")
#                               continue

#                         # Store result if it passed initial filter and is unique
#                         res['normalized_link'] = norm_link
#                         res['search_type'] = 'google_cse' # Mark source
#                         all_results_raw.append(res)
#                         processed_norm_urls.add(norm_link)
#         except Exception as e:
#             # Log specific error from search_provider if it raises one
#             log.warning(f"Search provider failed for query '{search_query}': {e}", exc_info=True)
#             continue # Try next query

#     if not all_results_raw:
#         log.warning(f"No usable results found from Google CSE for: query='{query}', library='{library_name}'")
#         return []

#     # --- Rank Results ---
#     # Define rank_result inner function here
#     def rank_result(result: Dict[str, Any]) -> float:
#         score = 0.0
#         title = result.get("title", "").lower()
#         snippet = result.get("snippet", "").lower()
#         combined_text = title + " " + snippet
#         norm_link = result.get("normalized_link", "") # Use pre-normalized

#         parsed_url = urlparse(norm_link)
#         netloc = parsed_url.netloc # Already normalized (lowercase, no www)

#         # 1. Source Priority (Boosts)
#         # Highest boost if library was specified AND domain matches the *found* official domain
#         if official_domain and official_domain == netloc:
#             score += 100.0
#         # High boost if domain matches *any* known official site domain (value from dict)
#         elif netloc in KNOWN_DOC_SITES.values():
#              score += 70.0
#         # Medium boost if URL matches common documentation patterns
#         elif any(pattern.search(norm_link) for pattern in DOC_URL_PATTERNS):
#              score += 40.0

#         # 2. Keyword Relevance (Simple word overlap scoring)
#         query_words = set(re.findall(r'\b\w{3,}\b', query.lower())) # Consider words >= 3 chars
#         title_words = set(re.findall(r'\b\w+\b', title))
#         snippet_words = set(re.findall(r'\b\w+\b', snippet))
#         common_title = query_words.intersection(title_words)
#         common_snippet = query_words.intersection(snippet_words)
#         if common_title: score += 15.0 * len(common_title) # Weight by number of common words
#         if common_snippet: score += 5.0 * len(common_snippet)

#         # 3. Doc Keywords Bonus
#         if any(k in combined_text for k in ["documentation", "api", "reference", "guide", "manual", "docs"]): score += 10.0
#         if any(k in combined_text for k in ["tutorial", "example", "how-to", "usage", "getting started"]): score += 5.0

#         # 4. Penalties (Already filtered most, but apply ranking penalties too)
#         if parsed_url.scheme != "https": score -= 10.0
#         # Check again here for ranking penalty (might have passed filter)
#         is_likely_non_doc = any(site in netloc for site in NON_DOC_SITES)
#         if "github.com" in netloc and ("/blob/" in parsed_url.path or "/issues/" in parsed_url.path or "/pull/" in parsed_url.path):
#              is_likely_non_doc = True
#         elif "github.com" in netloc: # Allow non-code github pages
#              is_likely_non_doc = False
#         if is_likely_non_doc: score -= 50.0

#         result['relevance_score'] = round(score, 1) # Store score for inspection
#         return score

#     # Sort aggregated results and take top N
#     ranked_results = sorted(all_results_raw, key=rank_result, reverse=True)
#     final_results = ranked_results[:max_results]

#     # --- Fetch Content (if requested) ---
#     content_fetched_success = False # Track if content was successfully fetched
#     if fetch_content_level in ['full_raw'] and final_results:
#         # Fetch for the top result only
#         top_result = final_results[0]
#         link_to_fetch = top_result.get("link")

#         if link_to_fetch:
#             log.info(f"Fetching content for top ranked result (Score: {top_result.get('relevance_score', 0):.1f}): {link_to_fetch}")
#             extracted_text, error_msg = await _fetch_and_extract_content(link_to_fetch)
#             top_result['content'] = {
#                 "level": fetch_content_level,
#                 "data": extracted_text if extracted_text else None,
#                 "error": error_msg
#             }
#             if not error_msg and extracted_text:
#                 content_fetched_success = True # Mark success only if no error and text extracted
#             elif error_msg:
#                  log.warning(f"Failed to get content for top result '{link_to_fetch}': {error_msg}")
#             elif not extracted_text:
#                  log.warning(f"Extracted empty content for top result '{link_to_fetch}'")

#     # Clean up temporary keys before returning
#     for res in final_results:
#         res.pop('normalized_link', None)

#     log.info(f"Returning {len(final_results)} ranked documentation results (content fetched: {content_fetched_success}).")
#     return final_results

# Chromium
# packages/mcp-server/src/mcp_server/tools/doc_search_v2.py

import asyncio
import logging
import re
import json
import os
import time # <-- Add time import
from typing import Dict, Optional, Any, List, Union, Tuple
from urllib.parse import urlparse, urlunparse

# Remove httpx if only used for fetching content, keep if used elsewhere (e.g., CSE API)
import httpx # Keep for Google CSE API call
import trafilatura # For extracting main content from HTML

# --- Selenium Imports ---
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
    Options = None # type: ignore
    WebDriverException = Exception # type: ignore
    TimeoutException = asyncio.TimeoutError # type: ignore

log = logging.getLogger(__name__)

# --- Configuration ---
KNOWN_DOC_SITES = {
    # ... (keep existing sites) ...
    "actix": "actix.rs", # Add actix explicitly
    "actix web": "actix.rs",
    "python": "docs.python.org",
    "python3": "docs.python.org",
    "requests": "requests.readthedocs.io",
    "numpy": "numpy.org",
    "np": "numpy.org", # Alias
    "pandas": "pandas.pydata.org",
    "pd": "pandas.pydata.org", # Alias
    "fastapi": "fastapi.tiangolo.com",
    "django": "docs.djangoproject.com",
    "flask": "flask.palletsprojects.com",
    "sqlalchemy": "docs.sqlalchemy.org",
    "pydantic": "docs.pydantic.dev",
    "httpx": "python-httpx.org", # Domain is www.python-httpx.org, normalize removes www
    "aiohttp": "docs.aiohttp.org",
    "beautifulsoup": "beautiful-soup-4.readthedocs.io",
    "bs4": "beautiful-soup-4.readthedocs.io", # Alias
    "selenium": "selenium.dev", # Domain is www.selenium.dev
    "jax": "jax.readthedocs.io",
    "go": "go.dev",             # Map 'go' to go.dev
    "golang": "go.dev",         # Map 'golang' to go.dev
}

DOC_URL_PATTERNS = [
    re.compile(r"actix\.rs/", re.I), # Add actix pattern
    re.compile(r"readthedocs\.io", re.I),
    re.compile(r"docs\.[\w-]+\.\w+", re.I), # docs.python.org, docs.djangoproject.com
    re.compile(r"[\w-]+\.pydata\.org", re.I), # pandas.pydata.org
    re.compile(r"[\w-]+\.palletsprojects\.com", re.I), # flask...
    re.compile(r"[\w-]+\.tiangolo\.com", re.I), # fastapi
    re.compile(r"python-[\w-]+\.org", re.I), # httpx (handle www removal)
    re.compile(r"numpy\.org/doc", re.I),
    re.compile(r"selenium\.dev/documentation", re.I),
    re.compile(r"pydantic\.dev", re.I),
    re.compile(r"go\.dev/(?:doc|ref|tour|pkg)/", re.I), # Added Go paths
    re.compile(r"pkg\.go\.dev/", re.I), # Added Go package site
    re.compile(r"/api/", re.I), # Common path segments
    re.compile(r"/reference/", re.I),
    re.compile(r"/guide/", re.I),
    re.compile(r"/tutorial/", re.I),
    re.compile(r"/docs/", re.I), # Common path segment
]

NON_DOC_SITES = [
    "stackoverflow.com", "github.com", "youtube.com", "reddit.com",
    "geeksforgeeks.org", "medium.com", "w3schools.com", "tutorialspoint.com",
]

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
SEARCH_API_URL = "https://www.googleapis.com/customsearch/v1"

# --- Constants for Selenium (copied/adapted from ecommerce) ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
# Increase timeouts slightly for potentially complex doc pages
SELENIUM_GENERAL_WAIT = 10 # seconds to wait for elements (e.g., cookie banner)
SELENIUM_PAGE_LOAD_TIMEOUT = 60 # Increased seconds for page to load initially
SELENIUM_RENDER_WAIT = 4 # seconds to wait after load for JS rendering (adjust as needed)

# --- Helper Functions ---

def normalize_url(url: str) -> str:
    # ... (keep existing normalize_url function) ...
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower().replace("www.", "") if parsed.netloc else ""
        path = parsed.path.rstrip('/') if parsed.path else ""
        normalized = urlunparse((str(scheme), str(netloc), str(path), '', '', ''))
        return normalized
    except Exception:
        log.warning(f"Failed to normalize URL: {url}", exc_info=True)
        return url

async def call_google_cse_api(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    # ... (keep existing call_google_cse_api function) ...
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        log.error("Google API Key or CSE ID not configured in environment variables.")
        return []
    params = { "key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID, "q": query, "num": max(1, min(num_results, 10)) }
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            log.debug(f"Calling Google CSE API with query: '{query}'")
            response = await client.get(SEARCH_API_URL, params=params)
            response.raise_for_status()
            data = response.json()
            if "items" in data:
                for item in data["items"]:
                    if item.get("link") and item.get("title"):
                        results.append({ "title": item.get("title"), "link": item.get("link"), "snippet": item.get("snippet", "") })
            else:
                log.warning(f"Google CSE returned no 'items' for query: '{query}'")
    except httpx.HTTPStatusError as e: log.error(f"Google CSE API HTTP error ({e.response.status_code}) for query '{query}': {e.response.text}")
    except httpx.RequestError as e: log.error(f"Google CSE API request error for query '{query}': {e}")
    except json.JSONDecodeError as e: log.error(f"Failed to decode JSON response from Google CSE API for query '{query}': {e}")
    except Exception as e: log.error(f"Unexpected error calling Google CSE API for query '{query}': {e}", exc_info=True)
    log.debug(f"Google CSE API returned {len(results)} results for query: '{query}'")
    return results


# --- START: Selenium Helper Functions (copied/adapted from ecommerce.py) ---
def get_selenium_driver() -> webdriver.Chrome:
    """Configures and returns a Selenium WebDriver instance."""
    if not SELENIUM_AVAILABLE or not Options:
        log.error("Selenium library not available. Cannot create driver.")
        raise RuntimeError("Selenium library (selenium) is required for this operation.")

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument(f"user-agent={USER_AGENT}")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options.add_argument('--log-level=3') # Suppress console noise
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_experimental_option("prefs", {"profile.default_content_setting_values.notifications": 2})
    try:
        # Consider adding service=Service(log_output=os.devnull) if needed
        driver = webdriver.Chrome(options=chrome_options)
        # Note: set_page_load_timeout is set per-driver call in the sync wrapper
        log.debug("Selenium WebDriver initialized successfully.")
        return driver
    except WebDriverException as e:
        log.error(f"Failed to initialize Selenium WebDriver: {e.msg}")
        log.error("Ensure ChromeDriver is installed, updated, and accessible in your PATH.")
        raise # Re-raise as a fatal error for this function

def click_cookie_banner(driver: webdriver.Chrome, selectors: List[str]) -> bool:
    """Attempts to click a cookie banner using a list of CSS or XPath selectors."""
    # This function can be complex. For doc search, let's start without it
    # and add it back if cookie banners prove problematic. If adding back,
    # copy the full version from ecommerce.py.
    log.debug("Cookie banner clicking currently disabled in doc search fetch.")
    return False # Assume no banner clicked for now
# --- END: Selenium Helper Functions ---


# --- MODIFIED _fetch_and_extract_content to use Selenium ---
async def _fetch_and_extract_content(url: str, timeout: int = SELENIUM_PAGE_LOAD_TIMEOUT + SELENIUM_RENDER_WAIT + 5) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetches URL content using Selenium, renders JS, and extracts main text using Trafilatura.
    Returns (extracted_text, error_message).
    """
    if not SELENIUM_AVAILABLE:
        log.error("Selenium is not available on the server. Cannot fetch dynamic content.")
        return None, "Selenium is not available on the server."

    def _fetch_with_selenium_sync(url_sync: str, load_timeout: int, render_wait: float) -> Tuple[Optional[str], Optional[str]]:
        driver = None
        extracted_text: Optional[str] = None
        error_msg: Optional[str] = None
        start_time = time.time()
        log.debug(f"Selenium: Initializing driver for {url_sync}")

        try:
            driver = get_selenium_driver()
            driver.set_page_load_timeout(load_timeout)

            log.info(f"Selenium: Navigating to {url_sync}")
            driver.get(url_sync)

            log.debug(f"Selenium: Waiting {render_wait}s for potential JS rendering...")
            time.sleep(render_wait) # Simple wait for JS

            # --- Optional: Cookie Banner Handling ---
            # Define potential cookie selectors for documentation sites if needed
            # cookie_selectors_docs = ["#cookie-accept", ...]
            # click_cookie_banner(driver, cookie_selectors_docs)
            # ---

            log.debug(f"Selenium: Getting page source for {url_sync} after render wait.")
            html_content = driver.page_source
            log.debug(f"Selenium: Got {len(html_content)} bytes of rendered page source.")

            # Extract using Trafilatura (on the rendered HTML)
            # Note: trafilatura.extract is synchronous, so it's fine here
            extracted_text = trafilatura.extract(
                html_content,
                include_comments=False,
                include_tables=True, # Keep tables for potential code examples
                no_fallback=True
            )
            if not extracted_text:
                log.warning(f"Selenium+Trafilatura (strict) extracted no main content from {url_sync}. Attempting fallback.")
                extracted_text = trafilatura.extract(
                    html_content,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False
                )
                if not extracted_text:
                    log.error(f"Selenium+Trafilatura: Fallback extraction also failed for {url_sync}.")
                    # Try getting just the body text as a last resort
                    try:
                        body_text = driver.find_element(By.TAG_NAME, 'body').text
                        if body_text:
                             log.warning("Using raw body text as final fallback.")
                             extracted_text = body_text
                        else:
                             error_msg = "Failed to extract main content or body text from rendered page."
                    except Exception as body_err:
                         log.error(f"Failed to get body text as fallback: {body_err}")
                         error_msg = "Failed to extract main content from rendered page (and body fallback failed)."

            if extracted_text:
                log.info(f"Selenium+Trafilatura: Extracted ~{len(extracted_text)} chars from {url_sync}")
                MAX_CONTENT_CHARS = 15000 # Keep truncation limit
                if len(extracted_text) > MAX_CONTENT_CHARS:
                    log.warning(f"Selenium+Trafilatura: Content from {url_sync} truncated.")
                    extracted_text = extracted_text[:MAX_CONTENT_CHARS] + "\n\n[... CONTENT TRUNCATED ...]"

        except TimeoutException:
            # This catches driver.get() timeout
            error_msg = f"Selenium timeout ({load_timeout}s) loading page."
            log.warning(f"{error_msg} URL: {url_sync}")
        except WebDriverException as e:
            error_msg = f"Selenium WebDriver error: {e.msg}"
            log.error(f"{error_msg} URL: {url_sync}", exc_info=False)
        except Exception as e:
            error_msg = f"Unexpected error during Selenium fetch/extraction: {e}"
            log.error(f"{error_msg} URL: {url_sync}", exc_info=True)
        finally:
            if driver:
                try:
                    driver.quit()
                    log.debug(f"Selenium: Driver quit for {url_sync}")
                except Exception as quit_err:
                     log.error(f"Selenium: Error quitting driver for {url_sync}: {quit_err}")
            duration = time.time() - start_time
            log.debug(f"Selenium fetch process for {url_sync} took {duration:.2f}s. Error: {error_msg is not None}")

        return extracted_text, error_msg

    # Call the synchronous Selenium function in a separate thread
    log.debug(f"Dispatching Selenium fetch for {url} to thread.")
    try:
        result = await asyncio.to_thread(_fetch_with_selenium_sync, url, SELENIUM_PAGE_LOAD_TIMEOUT, SELENIUM_RENDER_WAIT)
        return result
    except RuntimeError as e:
         # Catch potential errors if the thread pool is shut down etc.
         log.error(f"Runtime error dispatching Selenium fetch to thread for {url}: {e}")
         return None, f"Server error running fetch task: {e}"
    except Exception as e:
         log.error(f"Unexpected error using asyncio.to_thread for {url}: {e}")
         return None, f"Unexpected server error running fetch task: {e}"


# --- Main Tool Implementation ---

async def find_documentation(
    query: str,
    library_name: Optional[str] = None,
    version: Optional[str] = None,
    search_strategy: str = 'best_available',
    max_results: int = 5,
    fetch_content_level: str = 'full_raw'
) -> Union[List[Dict[str, Any]], Dict[str, str]]:
    """
    Performs a documentation search using web search APIs (Google CSE) and ranks results.
    Optionally fetches full content for the top-ranked result(s) using Selenium for JS rendering.

    Args:
        query: The search query (keywords, function name, concept).
        library_name: Optional specific library to focus the search.
        version: Optional specific version string.
        search_strategy: Currently unused hint ('best_available').
        max_results: Maximum number of final results to return.
        fetch_content_level: 'none', 'snippet', or 'full_raw'. ('full_raw' uses Selenium).

    Returns:
        List of ranked results (title, link, snippet, Optional[content]), or error dict.
        Requires Selenium and ChromeDriver on the server if fetch_content_level='full_raw'.
    """
    if not query:
        return {"error": "'query' argument is required."}
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
         log.error("Google CSE API Key/ID not configured on server. Documentation search unavailable.")
         return {"error": "Documentation search is not available due to server configuration."}
    # Check Selenium dependency ONLY if full content fetch is requested
    if fetch_content_level == 'full_raw' and not SELENIUM_AVAILABLE:
         log.error("Selenium requested for content fetch, but library is not installed on server.")
         return {"error": "Cannot fetch full page content: Server is missing the 'selenium' library."}


    log.info(f"Starting documentation search: query='{query}', library='{library_name or 'any'}', version='{version or 'any'}', fetch_level='{fetch_content_level}' (Selenium: {'Enabled' if fetch_content_level=='full_raw' else 'Disabled'})")

    # --- Construct Queries ---
    # ... (keep existing query construction logic) ...
    queries_to_try = []
    norm_lib_name = library_name.lower().strip().replace('-', '') if library_name else None
    version_str = f" {version}" if version else ""
    official_domain = None
    if norm_lib_name:
        official_domain = KNOWN_DOC_SITES.get(norm_lib_name)
        if official_domain:
             queries_to_try.append(f"site:{official_domain} {query}{version_str}")
             log.debug(f"Found known domain '{official_domain}'. Adding site-specific query.")
        else:
             log.debug(f"No pre-configured domain found for library '{library_name}'.")
    lib_prefix = f"\"{library_name}\"" if library_name else ""
    queries_to_try.append(f"{lib_prefix}{version_str} documentation {query}".strip())


    # --- Execute Searches ---
    # ... (keep existing search execution logic using call_google_cse_api) ...
    all_results_raw: List[Dict[str, Any]] = []
    processed_norm_urls = set()
    search_provider = call_google_cse_api
    for search_query in queries_to_try:
        try:
            basic_results = await search_provider(search_query, num_results=max_results + 5)
            for res in basic_results:
                link, title = res.get("link"), res.get("title")
                if link and title:
                    norm_link = normalize_url(link)
                    if norm_link not in processed_norm_urls:
                        parsed_for_filter = urlparse(norm_link)
                        is_likely_non_doc_site = False
                        if any(site in parsed_for_filter.netloc for site in NON_DOC_SITES):
                             if "github.com" in parsed_for_filter.netloc and ("/blob/" in parsed_for_filter.path or "/issues/" in parsed_for_filter.path or "/pull/" in parsed_for_filter.path): is_likely_non_doc_site = True
                             elif "github.com" not in parsed_for_filter.netloc: is_likely_non_doc_site = True
                        if is_likely_non_doc_site: continue
                        res['normalized_link'] = norm_link
                        res['search_type'] = 'google_cse'
                        all_results_raw.append(res)
                        processed_norm_urls.add(norm_link)
        except Exception as e: log.warning(f"Search provider failed for query '{search_query}': {e}", exc_info=True)
    if not all_results_raw:
        log.warning(f"No usable results found from Google CSE for: query='{query}', library='{library_name}'")
        return []


    # --- Rank Results ---
    # ... (keep existing ranking logic) ...
    def rank_result(result: Dict[str, Any]) -> float:
        score = 0.0; title = result.get("title", "").lower(); snippet = result.get("snippet", "").lower(); combined_text = title + " " + snippet; norm_link = result.get("normalized_link", ""); parsed_url = urlparse(norm_link); netloc = parsed_url.netloc
        if official_domain and official_domain == netloc: score += 100.0
        elif netloc in KNOWN_DOC_SITES.values(): score += 70.0
        elif any(pattern.search(norm_link) for pattern in DOC_URL_PATTERNS): score += 40.0
        query_words = set(re.findall(r'\b\w{3,}\b', query.lower())); title_words = set(re.findall(r'\b\w+\b', title)); snippet_words = set(re.findall(r'\b\w+\b', snippet))
        common_title = query_words.intersection(title_words); common_snippet = query_words.intersection(snippet_words)
        if common_title: score += 15.0 * len(common_title)
        if common_snippet: score += 5.0 * len(common_snippet)
        if any(k in combined_text for k in ["documentation", "api", "reference", "guide", "manual", "docs"]): score += 10.0
        if any(k in combined_text for k in ["tutorial", "example", "how-to", "usage", "getting started"]): score += 5.0
        if parsed_url.scheme != "https": score -= 10.0
        is_likely_non_doc = any(site in netloc for site in NON_DOC_SITES)
        if "github.com" in netloc and ("/blob/" in parsed_url.path or "/issues/" in parsed_url.path or "/pull/" in parsed_url.path): is_likely_non_doc = True
        elif "github.com" in netloc: is_likely_non_doc = False
        if is_likely_non_doc: score -= 50.0
        result['relevance_score'] = round(score, 1)
        return score
    ranked_results = sorted(all_results_raw, key=rank_result, reverse=True)
    final_results = ranked_results[:max_results]


    # --- Fetch Content (Uses MODIFIED _fetch_and_extract_content) ---
    content_fetched_success = False
    # Only fetch if requested AND Selenium is available (check done earlier)
    if fetch_content_level == 'full_raw' and final_results:
        top_result = final_results[0]
        link_to_fetch = top_result.get("link")

        if link_to_fetch:
            log.info(f"Fetching content (using Selenium) for top ranked result (Score: {top_result.get('relevance_score', 0):.1f}): {link_to_fetch}")
            # Call the modified function which now uses Selenium internally
            extracted_text, error_msg = await _fetch_and_extract_content(link_to_fetch)
            top_result['content'] = {
                "level": fetch_content_level,
                "data": extracted_text if extracted_text else None,
                "error": error_msg
            }
            if not error_msg and extracted_text:
                content_fetched_success = True
            elif error_msg:
                 log.warning(f"Failed to get content for top result '{link_to_fetch}': {error_msg}")
            elif not extracted_text:
                 log.warning(f"Extracted empty content for top result '{link_to_fetch}'")

    # Clean up temporary keys before returning
    for res in final_results:
        res.pop('normalized_link', None)

    log.info(f"Returning {len(final_results)} ranked documentation results (content fetched via Selenium: {content_fetched_success}).")
    return final_results
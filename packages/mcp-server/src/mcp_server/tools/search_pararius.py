# File: src/ai_agent/tools/search_pararius.py
import typing
from typing import List, Dict, Any, Optional, Tuple
import asyncio
import time
import urllib.parse
import re
import logging

# NEW: Import HTTP libraries
import aiohttp
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# --- Constants and Config ---
PARARIUS_CONFIG = {
    "selectors": {
        "content": ".listing-search-item", # Search results page listing container
        "title": ".listing-search-item__title a",
        "price": ".listing-search-item__price",
        "location": ".listing-search-item__sub-title",
        "features": ".illustrated-features__item, .listing-features__feature", # For area/rooms on search page
        # Detail Page Selectors for Energy Label (will be used with BeautifulSoup)
        "energy_label_class": "[class*='listing-features__description--energy-label-']", # Preferred
        "energy_label_dt_xpath": "//dt[contains(., 'Energy label') or contains(., 'Energielabel')]/following-sibling::dd[1]", # Keep for reference, use bs4 logic
    },
    "pagination": {
        "selector": "//a[contains(text(),'Next')]",
    },
    "cookie_selectors": [
        "//button[contains(text(), 'Accept')]",
        "//button[contains(text(), 'I agree')]",
        "//button[contains(text(), 'Agree')]"
    ],
    "wait_time": 3,
    "page_load_wait": 5,
    "scroll_pause": 0.5 # Reduced scroll pause
}
DEFAULT_PARARIUS_URL = "https://www.pararius.com/apartments/rotterdam/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
# Max concurrent requests for detail pages
MAX_CONCURRENT_REQUESTS = 10 # Adjustable: Start lower (e.g., 5-10) and increase if stable
# Timeout for fetching detail pages
DETAIL_FETCH_TIMEOUT = 15 # seconds

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)


# --- Helper Functions (URL normalization, price/rooms/energy parsing - slightly adjusted) ---
def normalize_url(url: str) -> str:
    if not url: return ""
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    # Ensure path starts with '/' and remove trailing '/' unless it's the root
    path = parsed.path if parsed.path.startswith('/') else '/' + parsed.path
    path = path.rstrip('/') if len(path) > 1 else path
    # Rebuild without params, query, fragment
    normalized = urllib.parse.urlunparse((scheme, netloc, path, '', '', ''))
    return normalized

def parse_price(price_str: str) -> Optional[float]:
    """
    Extracts a numeric value from a price string like '€ 2.995', '€1,103 per month'.
    Handles common European number formats.
    """
    if not price_str:
        return None
    try:
        # 1. Find the first sequence of digits, allowing for dot/comma separators
        #    This is more forgiving than enforcing strict thousands separators.
        match = re.search(r'([\d.,]+)', price_str)
        if match:
            number_part = match.group(1)
            # 2. Clean the number part: remove thousands separators (dots or commas)
            #    Assume the *last* comma/dot might be a decimal separator if present.
            #    Remove all but the last one if it's a comma/dot. This is heuristic.
            #    A simpler approach: just remove all dots/commas commonly used as thousands sep.
            price_cleaned = number_part.replace('.', '').replace(',', '')

            # 3. Convert to float
            price_num = float(price_cleaned)
            return price_num
        else:
            # Only log warning if regex simply found nothing
            log.warning(f"Could not find numeric part in price string: '{price_str}'")
            return None
    except ValueError as ve:
        # Log specific conversion error
        log.warning(f"Could not convert parsed number to float from price string '{price_str}': {ve}")
        return None
    except Exception as e:
        # Log other unexpected errors during parsing
        log.warning(f"Unexpected error parsing price '{price_str}': {type(e).__name__} - {e}")
        return None


def parse_rooms(rooms_str: str) -> Optional[int]:
    if not rooms_str: return None
    try:
        match = re.search(r'(\d+)\s+(room|kamer)', rooms_str.lower())
        if match:
            return int(match.group(1))
    except Exception as e:
        log.warning(f"Could not parse rooms '{rooms_str}': {e}")
    return None

def parse_energy_label_from_text(label_str: str) -> Optional[str]:
    """Extracts energy label (A+++ to G) from a string using regex."""
    if not label_str: return None
    try:
        # Regex: Optional prefix, then A-G, then optionally up to 4 '+' (adjust if needed)
        match = re.search(r'\b([A-G](?:\+{0,4})?)\b', label_str.strip(), re.IGNORECASE)
        if match:
            return match.group(1).upper()
    except Exception as e:
         log.warning(f"Could not parse energy label from text '{label_str}': {e}")
    return None

def safe_price_key(item: Dict[str, Any]) -> float:
    """Helper function for sorting listings by price, handling missing/invalid prices."""
    price_str = item.get("price")
    parsed_price = parse_price(price_str) if price_str else None
    return parsed_price if parsed_price is not None else float('inf') # Put items without price at the end


# --- Selenium Functions (Cookie banner, Next page) ---
# (Implementations mostly unchanged, added logging)
def click_pararius_cookie_banner(driver: webdriver.Chrome) -> bool:
    # (Implementation remains the same as previous version, with logging)
    try:
        wait = WebDriverWait(driver, PARARIUS_CONFIG.get("wait_time", 3))
        for xpath in PARARIUS_CONFIG.get("cookie_selectors", []):
            try:
                element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                element.click()
                log.info(f"Clicked cookie banner using XPath: {xpath}")
                return True
            except (NoSuchElementException, TimeoutException):
                continue
            except Exception as e:
                 log.warning(f"Non-critical error clicking cookie banner element ({xpath}): {e}")
                 continue
    except Exception as e:
        log.error(f"Error finding/waiting for cookie banner: {e}")
    return False

def click_next_page(driver: webdriver.Chrome) -> bool:
    # (Implementation remains the same as previous version, with logging)
    try:
        # First try to locate the overlapping element and dismiss it
        try:
            overlay_selectors = [
                ".search-controls__container--other-controls",
                # Add other potential overlay selectors if needed
            ]
            for selector in overlay_selectors:
                 try:
                    overlay = driver.find_element(By.CSS_SELECTOR, selector)
                    # Try to dismiss it by clicking elsewhere or using JavaScript to hide it
                    driver.execute_script("arguments[0].style.display = 'none';", overlay)
                    log.debug(f"Attempted to hide potential overlay: {selector}")
                 except NoSuchElementException:
                    continue # Element not found, try next selector
        except Exception as e:
            log.warning(f"Non-critical error trying to dismiss overlay: {e}")


        wait = WebDriverWait(driver, PARARIUS_CONFIG.get("wait_time", 5)) # Slightly longer wait might help
        next_button_xpath = PARARIUS_CONFIG["pagination"]["selector"]
        next_button = wait.until(EC.element_to_be_clickable((By.XPATH, next_button_xpath)))

        # Scroll to button if needed
        driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
        time.sleep(0.3) # Brief pause after scroll

        # Try clicking directly first
        try:
             next_button.click()
             log.info("Clicked 'Next' page button via direct click.")
             return True
        except Exception as e1:
            log.warning(f"Direct click failed for 'Next' button ({e1}), trying JS click.")
            # Fallback to JavaScript click
            try:
                driver.execute_script("arguments[0].click();", next_button)
                log.info("Clicked 'Next' page button via JavaScript.")
                return True
            except Exception as e2:
                log.error(f"Both direct and JS click failed for 'Next' button: {e2}")
                return False

    except (NoSuchElementException, TimeoutException):
        log.info("Next page button not found or not clickable within timeout.")
        return False
    except Exception as e:
        log.error(f"Unexpected error clicking next page: {e}", exc_info=True)
        return False

# --- Selenium Function: Extract Basic Info from Search Results ---
def extract_basic_listing_info(elem: webdriver.remote.webelement.WebElement) -> Optional[Dict[str, Any]]:
    """Extracts info available directly on the search results card (NO energy label here)."""
    info = {}
    try:
        # Title and Link (Required)
        title_elem = elem.find_element(By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["title"])
        info["title"] = title_elem.text.strip()
        raw_link = title_elem.get_attribute("href")
        info["link"] = normalize_url(raw_link) # Normalize URL immediately
        if not info["title"] or not info["link"]:
            log.warning("Missing title or link for a listing card, skipping.")
            return None

        # Price
        try:
            price_elem = elem.find_element(By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["price"])
            info["price"] = price_elem.text.strip() # Keep raw string for now, parse later if needed
        except NoSuchElementException:
            info["price"] = None

        # Location
        try:
            location_elem = elem.find_element(By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["location"])
            info["location"] = location_elem.text.strip()
        except NoSuchElementException:
            info["location"] = ""

        # Area and Rooms (from feature elements)
        info["area"] = None
        info["rooms"] = None
        try:
            features = elem.find_elements(By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["features"])
            for feature in features:
                text = feature.text.strip()
                if not text: continue
                # Improve area/rooms parsing to be more robust
                area_match = re.search(r'(\d+)\s*m²', text)
                rooms_match = re.search(r'(\d+)\s+(?:room|rooms|kamer|kamers)', text, re.IGNORECASE)

                if info["area"] is None and area_match:
                    info["area"] = text # Keep raw string or parse: int(area_match.group(1))
                    continue
                if info["rooms"] is None and rooms_match:
                    info["rooms"] = text # Keep raw string or parse: int(rooms_match.group(1))
                    continue
        except Exception as e:
            log.warning(f"Error extracting features (area/rooms) for {info.get('title', 'N/A')}: {e}")

        # Energy label is NOT extracted here
        info["energy_label"] = None # Initialize as None
        info["energy_rating"] = None # Initialize as None

        return info

    except NoSuchElementException as e:
         log.error(f"Core element (e.g., title) not found in a listing item card, skipping: {e}")
         return None
    except Exception as e:
        log.error(f"Unexpected error extracting basic info from search card: {e}")
        return None

# --- Selenium Function: Scrape Search Results for Links & Basic Info ---
# ! This function is BLOCKING and should be run in a thread pool when called from async code !
def scrape_pararius_for_links(starting_url: str = DEFAULT_PARARIUS_URL,
                             max_pages: int = 3,
                             filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Uses Selenium to scrape basic listing info and LINKS from search result pages.
    Applies filters based on info available on the search page (price, rooms).
    DOES NOT visit detail pages. This is a SYNCHRONOUS/BLOCKING function.
    """
    basic_listings: List[Dict[str, Any]] = []
    seen_urls = set() # Use normalized URLs

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080") # Might help with element visibility
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument(f"user-agent={USER_AGENT}")
    # Suppress console logs from Chrome DevTools Protocol
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options.add_argument('--log-level=3') # Only show fatal errors from chrome driver itself

    driver = None
    try:
        log.info("Initializing WebDriver for link scraping...")
        # Consider specifying executable path if needed:
        # from selenium.webdriver.chrome.service import Service
        # service = Service(executable_path='/path/to/chromedriver')
        # driver = webdriver.Chrome(service=service, options=chrome_options)
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60) # Increased timeout

        page_count = 0
        current_url = starting_url.rstrip("/")

        while page_count < max_pages:
            log.info(f"Selenium: Scraping search results page {page_count + 1}: {current_url}")
            try:
                driver.get(current_url)
            except TimeoutException:
                log.error(f"Selenium: Timeout loading page {page_count + 1}: {current_url}. Stopping.")
                break
            except Exception as e:
                log.error(f"Selenium: Error loading page {page_count + 1} ({current_url}): {e}. Stopping.")
                break

            # Wait for listing content to be present
            try:
                WebDriverWait(driver, PARARIUS_CONFIG.get("page_load_wait", 10)).until( # Increased wait
                    EC.presence_of_element_located((By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["content"]))
                )
            except TimeoutException:
                 log.warning(f"Selenium: Listings content selector '{PARARIUS_CONFIG['selectors']['content']}' not found on page {page_count + 1}. Trying next page (if available).")
                 # Attempt to proceed even if selector isn't found, maybe pagination still works
                 # (Next page logic handles the case where the button isn't found)

            # Handle cookie banner only if needed (might slow things down)
            if page_count == 0: # Usually only needed on the first page
                 if click_pararius_cookie_banner(driver):
                     time.sleep(1) # Allow banner to disappear

            # Scroll down to potentially trigger lazy loading (optional)
            # driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            # time.sleep(PARARIUS_CONFIG.get("scroll_pause", 0.5))
            # driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            # time.sleep(PARARIUS_CONFIG.get("scroll_pause", 0.5))

            elements = driver.find_elements(By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["content"])
            log.info(f"Selenium: Found {len(elements)} potential listing elements on page {page_count + 1}.")

            page_listings_added = 0
            for elem in elements:
                info = extract_basic_listing_info(elem) # Extracts basic info ONLY
                if info is None or not info.get("link"): # Ensure link exists
                    continue

                # URL uniqueness check (using already normalized URL from extract_basic_listing_info)
                if info["link"] in seen_urls:
                    continue
                seen_urls.add(info["link"])

                # Apply filters based on data available on search page *before* adding
                passes_filter = True
                if filters:
                    # Price Filter
                    if "price_max" in filters and filters["price_max"] is not None:
                        parsed_price = parse_price(info.get("price"))
                        if parsed_price is None or parsed_price > float(filters["price_max"]):
                            passes_filter = False
                            log.debug(f"Filtering out '{info['title']}' due to price ({info.get('price')}) > {filters['price_max']}")
                    # Rooms Filter
                    if passes_filter and "rooms_min" in filters and filters["rooms_min"] is not None:
                        parsed_rooms = parse_rooms(info.get("rooms")) # Use raw 'rooms' text
                        if parsed_rooms is None or parsed_rooms < int(filters["rooms_min"]):
                            passes_filter = False
                            log.debug(f"Filtering out '{info['title']}' due to rooms ({info.get('rooms')}) < {filters['rooms_min']}")
                    # Add other simple filters here if needed (e.g., location substring)

                if passes_filter:
                    info["page_scraped_from"] = page_count + 1 # Track source page
                    basic_listings.append(info) # Add listing with basic info + link
                    page_listings_added += 1

            log.info(f"Selenium: Added {page_listings_added} new listings for detail page fetching from page {page_count + 1}.")

            # Navigate to next page
            if page_count < max_pages - 1:
                log.info(f"Selenium: Attempting to navigate to page {page_count + 2}...")
                if not click_next_page(driver):
                    log.info("Selenium: Could not navigate to next page. Stopping link collection.")
                    break
                # Wait for URL to change or for a known element on the next page
                try:
                    WebDriverWait(driver, 15).until(EC.url_changes(current_url))
                    current_url = normalize_url(driver.current_url) # Normalize next page URL
                    log.info(f"Selenium: Successfully navigated to next page: {current_url}")
                except TimeoutException:
                    log.warning("Selenium: URL did not change after clicking 'Next'. Assuming navigation failed or took too long. Stopping.")
                    break
                # Optional brief pause after page load confirmed
                time.sleep(PARARIUS_CONFIG.get("wait_time", 3) / 2)
                page_count += 1
            else:
                 log.info("Selenium: Reached max_pages limit for link collection.")
                 break

    except Exception as e:
        log.error(f"Selenium: An unexpected error occurred during link scraping: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()
            log.info("Selenium: Browser driver closed.")

    log.info(f"Selenium: Link scraping phase finished. Collected basic info for {len(basic_listings)} listings.")
    return basic_listings


# --- NEW: Async Function to Fetch and Parse Detail Page for Energy Label ---
async def fetch_and_extract_energy_label(session: aiohttp.ClientSession,
                                         listing_url: str) -> Tuple[str, Optional[str]]:
    """
    Asynchronously fetches a listing detail page and extracts the energy label using BeautifulSoup.

    Args:
        session: The aiohttp client session.
        listing_url: The URL of the listing detail page (should be normalized).

    Returns:
        A tuple containing (normalized_listing_url, energy_label or None).
    """
    headers = {'User-Agent': USER_AGENT}
    # Ensure URL is normalized (should be already, but double-check)
    normalized_url = normalize_url(listing_url)
    if not normalized_url:
        log.warning("Received empty URL for detail fetching.")
        return "", None

    try:
        log.debug(f"AIOHTTP: Fetching {normalized_url}")
        async with session.get(normalized_url, headers=headers, timeout=DETAIL_FETCH_TIMEOUT, ssl=False) as response: # Added ssl=False for potential SSL issues
            # Check status code BEFORE raising for status to provide more info
            if response.status != 200:
                 log.warning(f"AIOHTTP: Received status {response.status} for {normalized_url}")
                 # Optionally handle redirects here if needed (3xx)
                 if response.status >= 400: # Treat client/server errors as fetch failures
                      return normalized_url, None # Don't raise, just return None label

            html_content = await response.text()
            soup = BeautifulSoup(html_content, 'html.parser')

            energy_label = None

            # --- Try different selectors for energy label ---

            # 1. Class-based selector (preferred)
            # Example class: listing-features__description--energy-label-a-plus-plus
            label_element = soup.select_one(PARARIUS_CONFIG["selectors"]["energy_label_class"])
            if label_element:
                class_list = label_element.get('class', [])
                for class_name in class_list:
                    # Extract label like 'a', 'b', 'a-plus', 'a-plus-plus' etc.
                    match = re.search(r'energy-label-([a-g](?:-plus)*)$', class_name, re.IGNORECASE)
                    if match:
                        raw_label = match.group(1)
                        # Convert 'a-plus-plus' to 'A++'
                        formatted_label = raw_label.replace('-plus', '+').upper()
                        energy_label = formatted_label
                        log.debug(f"Found energy label '{energy_label}' via class selector for {normalized_url}")
                        break # Found it

            # 2. DT/DD structure (if class method failed)
            if energy_label is None:
                # Find 'dt' containing "Energy label" or "Energielabel", case-insensitive
                dt_elements = soup.find_all('dt', string=re.compile(r'\s*Energy\s+label\s*|\s*Energielabel\s*', re.IGNORECASE))
                for dt in dt_elements:
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        label_text = dd.get_text(strip=True)
                        parsed_label = parse_energy_label_from_text(label_text) # Use helper
                        if parsed_label:
                            energy_label = parsed_label
                            log.debug(f"Found energy label '{energy_label}' via dt/dd for {normalized_url}")
                            break # Found it

            # 3. Fallback: Search specific text blocks (less reliable)
            #    (Add more specific searches here if the above often fail)
            #    Example: Search within a known features list container
            #    if energy_label is None:
            #        features_section = soup.select_one(".some-features-container-selector")
            #        if features_section:
            #             # Search logic within this section...

            if energy_label is None:
                log.debug(f"Energy label not found on page {normalized_url}")

            return normalized_url, energy_label

    except asyncio.TimeoutError:
        log.warning(f"AIOHTTP: Timeout fetching energy label for {normalized_url}")
        return normalized_url, None
    except aiohttp.ClientConnectorError as e:
         log.warning(f"AIOHTTP: Connection error for {normalized_url}: {e}")
         return normalized_url, None
    except aiohttp.ClientResponseError as e:
         log.warning(f"AIOHTTP: HTTP error {e.status} for {normalized_url}: {e.message}")
         return normalized_url, None
    except aiohttp.ClientError as e: # Catch other client errors
        log.warning(f"AIOHTTP: ClientError fetching energy label for {normalized_url}: {type(e).__name__} - {e}")
        return normalized_url, None
    except Exception as e:
        # Catch potential BeautifulSoup errors or other unexpected issues
        log.error(f"AIOHTTP: Error parsing energy label for {normalized_url}: {e}", exc_info=False) # Set exc_info=False for less noise in logs
        return normalized_url, None


# --- Main Async Search Function (Orchestrator) ---
async def search_pararius(starting_url: str = DEFAULT_PARARIUS_URL,
                          max_pages: int = 3,
                          filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Asynchronously scrapes Pararius using a hybrid approach:
    1. Uses Selenium (in a thread) to get basic info & links from search pages, applying initial filters.
    2. Uses aiohttp concurrently to fetch detail pages for energy labels.
    3. Merges data, applies final filters (like energy label), and sorts the results.
    """
    start_time_total = time.time()
    log.info(f"Starting Pararius search: URL={starting_url}, Max Pages={max_pages}, Filters={filters}")

    # Step 1: Get basic info and links using Selenium (run blocking I/O in thread pool)
    log.info("Phase 1: Starting Selenium link scraping...")
    start_time_selenium = time.time()
    try:
        # Run the blocking Selenium function in the default thread pool executor
        basic_listings = await asyncio.to_thread(
            scrape_pararius_for_links, starting_url, max_pages, filters
        )
    except Exception as e:
        log.error(f"Fatal error during Selenium scraping phase: {e}", exc_info=True)
        basic_listings = [] # Ensure it's an empty list on error

    selenium_duration = time.time() - start_time_selenium
    log.info(f"Phase 1: Selenium link scraping finished in {selenium_duration:.2f}s. Found {len(basic_listings)} candidate listings matching initial filters.")

    if not basic_listings:
        log.warning("No listings found or survived initial filtering. Aborting detail page fetch.")
        return []

    # Step 2: Fetch energy labels concurrently using aiohttp
    log.info(f"Phase 2: Starting concurrent fetch for {len(basic_listings)} detail pages (Max Concurrent: {MAX_CONCURRENT_REQUESTS})...")
    start_time_aiohttp = time.time()
    tasks = []
    # Use a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    # Shared Client Session
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=None), # Let semaphore control concurrency
                                      timeout=aiohttp.ClientTimeout(total=DETAIL_FETCH_TIMEOUT + 5) # Overall timeout slightly > request timeout
                                      ) as session:

        async def fetch_with_semaphore(listing_dict):
            # Pass the whole dict or just the URL
            url = listing_dict.get('link')
            if not url:
                return None # Skip if no URL somehow
            async with semaphore:
                # Add a small random delay before each request to seem less robotic
                await asyncio.sleep(0.1 + 0.2 * hash(url) % 1) # Small pseudo-random delay
                return await fetch_and_extract_energy_label(session, url)

        # Create tasks
        for listing in basic_listings:
            task = asyncio.create_task(fetch_with_semaphore(listing))
            tasks.append(task)

        # Gather results (tuples of url, energy_label or None)
        energy_label_results_tuples = await asyncio.gather(*tasks, return_exceptions=True)

    aiohttp_duration = time.time() - start_time_aiohttp
    log.info(f"Phase 2: Concurrent fetch finished in {aiohttp_duration:.2f}s.")

    # Process results and build a lookup map
    energy_labels_map = {}
    errors_count = 0
    success_count = 0
    none_count = 0 # Count pages where label wasn't found vs errors

    for result in energy_label_results_tuples:
        if isinstance(result, Exception):
            # Logged by gather already if return_exceptions=True, but we can add more context
            log.error(f"Error during energy label fetch task processing: {result}")
            errors_count += 1
        elif isinstance(result, tuple) and len(result) == 2:
            url, label = result
            if url: # Ensure we have a URL to map
                 energy_labels_map[url] = label # Use the returned normalized URL as key
                 if label is not None:
                     success_count +=1
                 else:
                     none_count += 1
            else:
                 log.warning(f"Received result tuple without a valid URL: {result}")
                 errors_count += 1
        elif result is None: # Handle case where fetch_with_semaphore returned None (e.g., no URL)
            errors_count += 1
        else:
            log.warning(f"Unexpected result type from fetch task: {type(result)} - {result}")
            errors_count += 1

    log.info(f"Energy label fetching summary: Success={success_count}, Label Not Found={none_count}, Errors={errors_count}")


    # Step 3: Merge energy labels back into listings
    results_with_labels = []
    missing_label_count = 0
    for listing in basic_listings:
        # Use the already normalized URL from the listing dict
        norm_url = listing.get('link')
        if norm_url:
             fetched_label = energy_labels_map.get(norm_url) # Look up using normalized URL
             listing['energy_label'] = fetched_label
             # Add 'energy_rating' key for compatibility if needed (can be same as label)
             listing['energy_rating'] = fetched_label
             results_with_labels.append(listing)
        else:
             missing_label_count +=1
             log.warning(f"Skipping listing merge due to missing link: {listing.get('title','N/A')}")

    if missing_label_count > 0:
        log.warning(f"Could not merge labels for {missing_label_count} listings due to missing links.")

    log.info(f"Phase 3: Merged energy labels. Listings count: {len(results_with_labels)}")


    # Step 4: Apply final filters (including energy rating)
    final_results = results_with_labels
    if filters and "energy_rating_min" in filters and filters["energy_rating_min"]:
        min_rating_str = filters["energy_rating_min"].upper()
        # Define order (lower number is worse, higher is better)
        ratings_order = {
             "G": 1, "F": 2, "E": 3, "D": 4, "C": 5, "B": 6,
             "A": 7, "A+": 8, "A++": 9, "A+++": 10, "A++++": 11,
             # Add A+++++ if needed
             None: 0 # Treat missing label as the worst score for filtering
         }
        # Reverse map for potential display sorting later if needed
        # rating_display = {v: k for k, v in ratings_order.items()}

        min_score = ratings_order.get(min_rating_str, 0) # Default to 0 if invalid filter value

        if min_score > 0: # Only filter if a valid min rating is given
            original_count = len(final_results)
            filtered_results = [
                listing for listing in final_results
                # Get score for listing's label (default to 0 if None/missing), compare to min_score
                if ratings_order.get(listing.get("energy_rating"), 0) >= min_score
            ]
            log.info(f"Applied energy rating filter (Min Rating >= {min_rating_str} / Score >= {min_score}). Kept {len(filtered_results)} of {original_count} listings.")
            final_results = filtered_results
        else:
            log.info(f"No valid energy rating filter applied (Filter value: {min_rating_str}).")
    else:
        log.info("No energy rating filter specified.")

    # Step 5: Sort results by price (ascending)
    final_results.sort(key=safe_price_key)
    log.info("Phase 4: Sorted final results by price.")

    total_duration = time.time() - start_time_total
    log.info(f"Pararius search completed in {total_duration:.2f}s. Returning {len(final_results)} listings.")
    return final_results

# # File: src/ai_agent/tools/search_pararius.py
# import typing
# from typing import List, Dict, Any, Optional, Tuple
# import asyncio
# import time
# import urllib.parse
# import re
# import logging
# import random # For random delay

# # Import HTTP libraries
# import aiohttp
# from bs4 import BeautifulSoup

# # Import Selenium components
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.common.exceptions import NoSuchElementException, TimeoutException

# # --- Constants and Config ---
# PARARIUS_CONFIG = {
#     "selectors": {
#         "content": ".listing-search-item",
#         "title": ".listing-search-item__title a",
#         "price": ".listing-search-item__price",
#         "location": ".listing-search-item__sub-title",
#         "features": ".illustrated-features__item, .listing-features__feature",
#         "energy_label_class": "[class*='listing-features__description--energy-label-']",
#         "energy_label_dt_xpath": "//dt[contains(., 'Energy label') or contains(., 'Energielabel')]/following-sibling::dd[1]",
#     },
#     "pagination": {"selector": "//a[contains(text(),'Next')]"},
#     "cookie_selectors": ["//button[contains(text(), 'Accept')]", "//button[contains(text(), 'I agree')]", "//button[contains(text(), 'Agree')]"],
#     "wait_time": 3, "page_load_wait": 10, "scroll_pause": 0.5, "navigation_wait": 15
# }
# DEFAULT_PARARIUS_URL = "https://www.pararius.com/apartments/rotterdam/"
# USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
# MAX_CONCURRENT_REQUESTS = 10
# DETAIL_FETCH_TIMEOUT = 15

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# log = logging.getLogger(__name__)


# # --- Helper Functions ---
# def normalize_url(url: str) -> str:
#     if not url: return ""
#     try:
#         parsed = urllib.parse.urlparse(url)
#         scheme = parsed.scheme.lower() if parsed.scheme else 'https'
#         netloc = parsed.netloc.lower()
#         path = parsed.path if parsed.path and parsed.path.startswith('/') else '/' + (parsed.path or '')
#         path = path.rstrip('/') if len(path) > 1 else path
#         normalized = urllib.parse.urlunparse((scheme, netloc, path, '', '', ''))
#         return normalized
#     except Exception as e: log.warning(f"Could not normalize URL '{url}': {e}"); return url

# def parse_price(price_str: str) -> Optional[float]:
#     """Extracts numeric price. Logs 'Price on request' at DEBUG level."""
#     if not price_str: return None
#     price_lower = price_str.lower()
#     if "request" in price_lower or "aanvraag" in price_lower:
#         # --- CHANGED: Log at DEBUG level ---
#         log.debug(f"Ignoring non-numeric price: '{price_str}'")
#         return None
#     try:
#         match = re.search(r'([\d.,]+)', price_str)
#         if match:
#             number_part = match.group(1)
#             if ',' in number_part and '.' in number_part: price_cleaned = number_part.replace('.', '').replace(',', '.')
#             else: price_cleaned = number_part.replace('.', '').replace(',', '')
#             return float(price_cleaned)
#         else:
#             # --- CHANGED: Warning only if *not* 'Price on request' and no number found ---
#             log.warning(f"Could not find numeric part in price string: '{price_str}'")
#             return None
#     except ValueError as ve: log.warning(f"Could not convert number to float from '{price_str}': {ve}"); return None
#     except Exception as e: log.warning(f"Unexpected error parsing price '{price_str}': {type(e).__name__} - {e}"); return None

# def parse_rooms(rooms_str: str) -> Optional[int]:
#     if not rooms_str: return None
#     try:
#         match = re.search(r'(\d+)\s+(room|rooms|kamer|kamers)', rooms_str.lower())
#         if match: return int(match.group(1))
#         match_num = re.search(r'^(\d+)$', rooms_str.strip())
#         if match_num: log.debug(f"Parsing rooms from number only: {rooms_str}"); return int(match_num.group(1))
#     except Exception as e: log.warning(f"Could not parse rooms '{rooms_str}': {e}")
#     return None

# def parse_area(area_str: str) -> Optional[float]:
#     if not area_str: return None
#     try:
#         match = re.search(r'(\d+)\s*m²', area_str)
#         if match: return float(match.group(1))
#     except Exception as e: log.warning(f"Could not parse area '{area_str}': {e}")
#     return None

# def parse_energy_label_from_text(label_str: str) -> Optional[str]:
#     if not label_str: return None
#     try:
#         match = re.search(r'\b([A-G](?:\+{0,4})?)\b', label_str.strip(), re.IGNORECASE)
#         if match: return match.group(1).upper()
#     except Exception as e: log.warning(f"Could not parse energy label from text '{label_str}': {e}")
#     return None

# # --- CORRECTED: Use the parsed_price field ---
# def price_key_from_parsed(item: Dict[str, Any]) -> float:
#     """Helper function for sorting listings by the pre-parsed numeric price."""
#     parsed_price = item.get('parsed_price') # Get the value stored earlier
#     return parsed_price if parsed_price is not None else float('inf')
# # --- END CORRECTION ---

# # --- Selenium Functions ---
# def click_pararius_cookie_banner(driver: webdriver.Chrome) -> bool:
#     log.debug("Attempting to find and click cookie banner...")
#     try:
#         wait = WebDriverWait(driver, PARARIUS_CONFIG.get("wait_time", 3))
#         for xpath in PARARIUS_CONFIG.get("cookie_selectors", []):
#             try:
#                 element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
#                 element.click(); log.info(f"Clicked cookie banner: {xpath}"); time.sleep(0.7); return True
#             except (NoSuchElementException, TimeoutException): log.debug(f"Cookie selector not found/clickable: {xpath}"); continue
#             except Exception as e: log.warning(f"Non-critical error clicking cookie element ({xpath}): {e}"); continue
#         log.debug("No clickable cookie banner found.")
#     except Exception as e: log.error(f"Error waiting for cookie banner: {e}")
#     return False

# def click_next_page(driver: webdriver.Chrome) -> bool:
#     try:
#         overlay_selectors = [".search-controls__container--other-controls"]
#         for selector in overlay_selectors:
#             try:
#                 overlay = driver.find_element(By.CSS_SELECTOR, selector)
#                 if overlay.is_displayed(): driver.execute_script("arguments[0].style.display = 'none';", overlay); log.debug(f"Hid potential overlay: {selector}")
#             except NoSuchElementException: continue
#             except Exception as e: log.warning(f"Non-critical error dismissing overlay {selector}: {e}")

#         wait = WebDriverWait(driver, PARARIUS_CONFIG.get("wait_time", 5))
#         next_button_xpath = PARARIUS_CONFIG["pagination"]["selector"]
#         next_button = wait.until(EC.element_to_be_clickable((By.XPATH, next_button_xpath)))
#         driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button); time.sleep(0.3)

#         try: next_button.click(); log.info("Clicked 'Next' page button via direct click."); return True
#         except Exception as e1:
#             log.warning(f"Direct click failed for 'Next' ({e1}), trying JS click.")
#             try: driver.execute_script("arguments[0].click();", next_button); log.info("Clicked 'Next' page button via JS."); return True
#             except Exception as e2: log.error(f"Both direct and JS click failed for 'Next': {e2}"); return False
#     except (NoSuchElementException, TimeoutException): log.info("Next page button not found/clickable."); return False
#     except Exception as e: log.error(f"Unexpected error clicking next page: {e}", exc_info=True); return False

# def extract_basic_listing_info(elem: webdriver.remote.webelement.WebElement) -> Optional[Dict[str, Any]]:
#     info = {}
#     try:
#         title_elem = elem.find_element(By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["title"])
#         info["title"] = title_elem.text.strip()
#         info["link"] = normalize_url(title_elem.get_attribute("href"))
#         if not info["title"] or not info["link"]: return None

#         try: info["price"] = elem.find_element(By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["price"]).text.strip()
#         except NoSuchElementException: info["price"] = None
#         try: info["location"] = elem.find_element(By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["location"]).text.strip()
#         except NoSuchElementException: info["location"] = ""

#         info["area"] = None; info["rooms"] = None
#         try:
#             features = elem.find_elements(By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["features"])
#             for feature in features:
#                 text = feature.text.strip()
#                 if not text: continue
#                 area_match = re.search(r'(\d+)\s*m²', text)
#                 rooms_match = re.search(r'(\d+)\s+(?:room|rooms|kamer|kamers)', text, re.IGNORECASE)
#                 if info["area"] is None and area_match: info["area"] = text; continue
#                 if info["rooms"] is None and rooms_match: info["rooms"] = text; continue
#         except Exception as e: log.warning(f"Error extracting features for {info.get('title', 'N/A')}: {e}")

#         # Initialize fields
#         info["parsed_price"] = None; info["parsed_rooms"] = None; info["parsed_area"] = None
#         info["energy_label"] = None; info["energy_rating"] = None
#         return info
#     except Exception as e: log.error(f"Error extracting basic info from card: {e}"); return None

# # ! BLOCKING function - run in asyncio.to_thread !
# def scrape_pararius_for_links(starting_url: str = DEFAULT_PARARIUS_URL,
#                              max_pages: int = 3,
#                              filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
#     """
#     Uses Selenium to scrape basic listing info and LINKS from search result pages.
#     Applies filters based on info available on the search page (price, rooms).
#     Parses basic numeric fields for filtering and stores them.
#     DOES NOT visit detail pages. This is SYNCHRONOUS/BLOCKING.
#     """
#     basic_listings: List[Dict[str, Any]] = []
#     seen_urls = set()
#     chrome_options = Options()
#     chrome_options.add_argument("--headless"); chrome_options.add_argument("--disable-gpu"); chrome_options.add_argument("--no-sandbox")
#     chrome_options.add_argument("--disable-dev-shm-usage"); chrome_options.add_argument("--window-size=1920,1080")
#     chrome_options.add_argument("--disable-blink-features=AutomationControlled"); chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
#     chrome_options.add_argument(f"user-agent={USER_AGENT}"); chrome_options.add_argument('--log-level=3')
#     driver = None
#     try:
#         log.info("Initializing WebDriver for link scraping...")
#         driver = webdriver.Chrome(options=chrome_options)
#         driver.set_page_load_timeout(60)
#         page_count = 0; current_url = starting_url.rstrip("/")
#         while page_count < max_pages:
#             log.info(f"Selenium: Scraping search page {page_count + 1}: {current_url}")
#             try: driver.get(current_url)
#             except TimeoutException: log.error(f"Selenium: Timeout loading page {page_count + 1}. Stopping."); break
#             except Exception as e: log.error(f"Selenium: Error loading page {page_count + 1}: {e}. Stopping."); break

#             try: WebDriverWait(driver, PARARIUS_CONFIG.get("page_load_wait", 10)).until(EC.presence_of_element_located((By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["content"])))
#             except TimeoutException: log.warning(f"Selenium: Listings content not found on page {page_count + 1}.")

#             if page_count == 0: click_pararius_cookie_banner(driver)

#             elements = driver.find_elements(By.CSS_SELECTOR, PARARIUS_CONFIG["selectors"]["content"])
#             log.info(f"Selenium: Found {len(elements)} potential listings on page {page_count + 1}.")

#             page_listings_added = 0
#             for elem in elements:
#                 info = extract_basic_listing_info(elem)
#                 if info is None or not info.get("link"): continue
#                 if info["link"] in seen_urls: continue
#                 seen_urls.add(info["link"])

#                 # --- PARSE & STORE for filtering ---
#                 current_parsed_price = parse_price(info.get("price")) # CALL #1 (logs DEBUG for "Price on request")
#                 current_parsed_rooms = parse_rooms(info.get("rooms"))
#                 info['parsed_price'] = current_parsed_price
#                 info['parsed_rooms'] = current_parsed_rooms
#                 # --- END PARSE & STORE ---

#                 passes_filter = True
#                 if filters:
#                     if "price_max" in filters and filters["price_max"] is not None:
#                         if current_parsed_price is None or current_parsed_price > float(filters["price_max"]):
#                             passes_filter = False; log.debug(f"Filtering out '{info['title']}' due to price > {filters['price_max']}")
#                     if passes_filter and "rooms_min" in filters and filters["rooms_min"] is not None:
#                         if current_parsed_rooms is None or current_parsed_rooms < int(filters["rooms_min"]):
#                             passes_filter = False; log.debug(f"Filtering out '{info['title']}' due to rooms < {filters['rooms_min']}")

#                 if passes_filter:
#                     info["page_scraped_from"] = page_count + 1
#                     basic_listings.append(info)
#                     page_listings_added += 1

#             log.info(f"Selenium: Added {page_listings_added} listings passing filters from page {page_count + 1}.")

#             if page_count < max_pages - 1:
#                 log.info(f"Selenium: Attempting navigation to page {page_count + 2}...")
#                 if not click_next_page(driver): log.info("Selenium: Could not navigate to next page."); break
#                 try:
#                     WebDriverWait(driver, PARARIUS_CONFIG.get("navigation_wait", 15)).until(EC.url_changes(current_url))
#                     current_url = normalize_url(driver.current_url); log.info(f"Selenium: Navigated to: {current_url}"); time.sleep(1)
#                 except TimeoutException: log.warning("Selenium: URL did not change after clicking 'Next'. Stopping."); break
#                 page_count += 1
#             else: log.info("Selenium: Reached max_pages limit."); break
#     except Exception as e: log.error(f"Selenium: Unexpected error during link scraping: {e}", exc_info=True)
#     finally:
#         if driver: driver.quit(); log.info("Selenium: Browser driver closed.")
#     log.info(f"Selenium: Link scraping finished. Collected {len(basic_listings)} listings passing initial filters.")
#     return basic_listings

# # --- Async Function to Fetch Detail Page ---
# async def fetch_and_extract_energy_label(session: aiohttp.ClientSession, listing_url: str) -> Tuple[str, Optional[str]]:
#     headers = {'User-Agent': USER_AGENT}; normalized_url = normalize_url(listing_url)
#     if not normalized_url: return "", None
#     try:
#         log.debug(f"AIOHTTP: Fetching {normalized_url}")
#         async with session.get(normalized_url, headers=headers, timeout=DETAIL_FETCH_TIMEOUT, ssl=False) as response:
#             if response.status != 200: log.warning(f"AIOHTTP: Status {response.status} for {normalized_url}"); return normalized_url, None
#             html_content = await response.text(); soup = BeautifulSoup(html_content, 'html.parser')
#             energy_label = None
#             label_element = soup.select_one(PARARIUS_CONFIG["selectors"]["energy_label_class"])
#             if label_element:
#                 for class_name in label_element.get('class', []):
#                     match = re.search(r'energy-label-([a-g](?:-plus)*)$', class_name, re.IGNORECASE)
#                     if match: energy_label = match.group(1).replace('-plus', '+').upper(); log.debug(f"Found label '{energy_label}' via class for {normalized_url}"); break
#             if energy_label is None:
#                 dt_elements = soup.find_all('dt', string=re.compile(r'\s*Energy\s+label\s*|\s*Energielabel\s*', re.IGNORECASE))
#                 for dt in dt_elements:
#                     dd = dt.find_next_sibling('dd')
#                     if dd: energy_label = parse_energy_label_from_text(dd.get_text(strip=True));
#                     if energy_label: log.debug(f"Found label '{energy_label}' via dt/dd for {normalized_url}"); break
#             if energy_label is None: log.debug(f"Energy label not found on {normalized_url}")
#             return normalized_url, energy_label
#     except asyncio.TimeoutError: log.warning(f"AIOHTTP: Timeout for {normalized_url}"); return normalized_url, None
#     except aiohttp.ClientError as e: log.warning(f"AIOHTTP: ClientError for {normalized_url}: {type(e).__name__}"); return normalized_url, None
#     except Exception as e: log.error(f"AIOHTTP: Error parsing {normalized_url}: {e}", exc_info=False); return normalized_url, None

# # --- Main Async Search Function ---
# @typing.no_type_check
# async def search_pararius(starting_url: str = DEFAULT_PARARIUS_URL,
#                           max_pages: int = 3,
#                           filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
#     """
#     Asynchronously scrapes Pararius using a hybrid approach: Selenium (threaded) for links,
#     aiohttp for details, merges data, filters, parses numeric values once, and sorts.
#     """
#     start_time_total = time.time()
#     log.info(f"Starting Pararius search: URL={starting_url}, Max Pages={max_pages}, Filters={filters}")

#     # Step 1: Get links & basic info via Selenium (threaded)
#     log.info("Phase 1: Starting Selenium link scraping...")
#     start_time_selenium = time.time()
#     try: basic_listings = await asyncio.to_thread(scrape_pararius_for_links, starting_url, max_pages, filters)
#     except Exception as e: log.error(f"Fatal error during Selenium phase: {e}", exc_info=True); basic_listings = []
#     selenium_duration = time.time() - start_time_selenium
#     log.info(f"Phase 1: Selenium finished in {selenium_duration:.2f}s. Found {len(basic_listings)} candidates.")
#     if not basic_listings: return []

#     # Step 2: Fetch energy labels concurrently via aiohttp
#     log.info(f"Phase 2: Starting concurrent detail page fetch ({len(basic_listings)} URLs)...")
#     start_time_aiohttp = time.time()
#     tasks = []; semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
#     connector = aiohttp.TCPConnector(limit=None, ssl=False, force_close=True)
#     async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=DETAIL_FETCH_TIMEOUT + 5)) as session:
#         async def fetch_with_semaphore(url):
#             async with semaphore: await asyncio.sleep(0.1 + random.uniform(0.1, 0.4)); return await fetch_and_extract_energy_label(session, url)
#         for listing in basic_listings:
#             link = listing.get('link');
#             if link: tasks.append(asyncio.create_task(fetch_with_semaphore(link)))
#             else: log.warning(f"Skipping detail fetch for listing without link: {listing.get('title','N/A')}")
#         energy_label_results_tuples = await asyncio.gather(*tasks, return_exceptions=True)
#     aiohttp_duration = time.time() - start_time_aiohttp
#     log.info(f"Phase 2: Concurrent fetch finished in {aiohttp_duration:.2f}s.")

#     # Process fetch results
#     energy_labels_map = {}; errors_count = 0; success_count = 0; none_count = 0
#     for result in energy_label_results_tuples:
#         if isinstance(result, Exception): errors_count += 1; log.error(f"Error in fetch task result: {result}")
#         elif isinstance(result, tuple) and len(result) == 2 and result[0]:
#             url, label = result; energy_labels_map[url] = label
#             if label is not None: success_count += 1
#             else: none_count += 1
#         elif result is None: errors_count += 1; log.warning("Received None result from fetch task.")
#         else: errors_count += 1; log.warning(f"Unexpected/invalid fetch task result: {type(result)} - {result}")
#     log.info(f"Energy label fetching summary: Success={success_count}, Label Not Found={none_count}, Errors={errors_count}")

#     # Step 3: Merge, Parse Area, Apply Final Filters
#     log.info("Phase 3: Merging data, parsing area, and applying final filters...")
#     final_results = []; parsed_area_count = 0
#     for listing in basic_listings:
#         norm_url = listing.get('link');
#         if not norm_url: continue

#         fetched_label = energy_labels_map.get(norm_url)
#         listing['energy_label'] = fetched_label
#         listing['energy_rating'] = fetched_label # Compatibility key

#         # --- PARSE AREA ONCE ---
#         listing['parsed_area'] = parse_area(listing.get("area"))
#         if listing['parsed_area'] is not None: parsed_area_count += 1
#         # --- END PARSE AREA ---

#         passes_final_filter = True
#         if filters and "energy_rating_min" in filters and filters["energy_rating_min"]:
#             min_rating_str = filters["energy_rating_min"].upper()
#             ratings_order = {"G": 1, "F": 2, "E": 3, "D": 4, "C": 5, "B": 6, "A": 7, "A+": 8, "A++": 9, "A+++": 10, "A++++": 11, None: 0}
#             min_score = ratings_order.get(min_rating_str, 0)
#             if min_score > 0 and ratings_order.get(listing.get("energy_rating"), 0) < min_score:
#                 passes_final_filter = False; log.debug(f"Filtering out '{listing['title']}' due to energy rating '{listing.get('energy_rating')}' < {min_rating_str}")

#         if passes_final_filter: final_results.append(listing)

#     log.info(f"Parsed area for {parsed_area_count} listings.")
#     log.info(f"Phase 3: Merging, parsing, final filtering complete. Count: {len(final_results)}")

#     # --- Step 4: Sort results by PARSED price ---
#     log.info("Phase 4: Sorting final results by price...")
#     final_results.sort(key=price_key_from_parsed) # Use the corrected key function
#     log.info("Phase 4: Sorting complete.")
#     # --- End Step 4 ---

#     total_duration = time.time() - start_time_total
#     log.info(f"Pararius search completed in {total_duration:.2f}s. Returning {len(final_results)} listings.")
#     return final_results
# File: src/ai_agent/tools/ecommerce.py

import logging
import asyncio
import re
import time # Needed for Selenium pauses
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import quote_plus, urljoin

# Keep BS4 for potential future use or if other tools need it
from bs4 import BeautifulSoup

# --- Selenium Imports ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.remote.webelement import WebElement # For type hinting

log = logging.getLogger(__name__)

# --- Constants ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
SELENIUM_WAIT_TIMEOUT = 10 # seconds to wait for elements
SELENIUM_PAGE_LOAD_TIMEOUT = 45 # seconds for page to load initially

# --- Store Configurations (CRITICAL: Update these selectors after manual inspection!) ---
ECOMMERCE_CONFIG = {
    # --- AMAZON Section Updated ---
    "amazon_nl": {
        "base_url": "https://www.amazon.nl",
        "search_url_template": "https://www.amazon.nl/s?k={query}",
        "item_selector": "div[data-component-type='s-search-result']",
        # Be much more flexible with the title selector
        "title_selector": "h2 .a-text-normal, h2 a span, .a-size-medium.a-color-base.a-text-normal, span.a-text-normal, .a-text-normal",
        "price_selector": "span.a-price > span.a-offscreen, .a-price .a-offscreen",
        "url_selector": "h2 a, .a-link-normal.a-text-normal",
        "availability_selector": None,
        "cookie_selectors": ["#sp-cc-accept"],
    },
    # --- BOL Section (Working) ---
    "bol_com": {
        "base_url": "https://www.bol.com",
        "search_url_template": "https://www.bol.com/nl/nl/s/?searchtext={query}",
        "item_selector": "li.product-item--row",
        "title_selector": ".product-title",
        "price_selector": "[data-test='price'], .promo-price",
        "url_selector": "a.product-title",
        "availability_selector": ".product-delivery-highlight",
        "cookie_selectors": ["button[data-test='consent-modal-ofc-confirm-button']"], # Assume this works or adjust if needed
    },
    # --- COOLBLUE Section Updated ---
    "coolblue_nl": {
        "base_url": "https://www.coolblue.nl",
        "search_url_template": "https://www.coolblue.nl/zoeken?query={query}",
        # This is finding products correctly
        "item_selector": ".product-grid__item, .product-card, .product-block",
        # Update title selector based on screenshot
        "title_selector": ".product-card__title",
        # Price selector looks OK
        "price_selector": ".sales-price__current",
        # This is the critical fix - I see the product cards have parent <a> tags in your screenshot
        "url_selector": ".product-grid__item > a, .product-card, .product-block > a, a:has(.product-card__title)",
        "availability_selector": ".product-card__availability-information",
        # This XPath selector is working
        "cookie_selectors": ["//button[contains(., 'Oké')]"],
    },
    # Add other stores here
}

# --- Helper Functions (parse_price updated) ---
def parse_price(price_str: str) -> Optional[float]:
    """Extracts numeric price from various string formats (Updated for ',-' handling)."""
    if not price_str: return None
    try:
        # Log the original price string for debugging
        log.debug(f"Parsing price from string: '{price_str}'")

        price_cleaned = re.sub(r'[€$£\s]', '', price_str).strip()
        log.debug(f"After removing currency symbols and spaces: '{price_cleaned}'")

        if price_cleaned.endswith(',-'):
            price_cleaned = price_cleaned[:-2]
            log.debug(f"After handling ',-' notation: '{price_cleaned}'")

        if ',' in price_cleaned and '.' in price_cleaned:
            price_cleaned = price_cleaned.replace('.', '').replace(',', '.')
            log.debug(f"After handling European number format with both comma and dot: '{price_cleaned}'")
        elif ',' in price_cleaned:
            price_cleaned = price_cleaned.replace(',', '')
            log.debug(f"After handling comma as thousands separator: '{price_cleaned}'")

        price_final_clean = "".join(c for i, c in enumerate(price_cleaned) if c.isdigit() or (c == '.' and price_cleaned.count('.') <= 1))
        log.debug(f"Final cleaned price string: '{price_final_clean}'")

        if not price_final_clean:
            log.warning(f"Price string became empty after cleaning: '{price_cleaned}' from '{price_str}'")
            return None

        result = float(price_final_clean)
        log.debug(f"Successfully parsed price: {result}")
        return result
    except ValueError as ve:
        log.warning(f"Could not convert cleaned price '{price_final_clean}' to float (from '{price_str}'): {ve}")
        return None
    except Exception as e:
        log.warning(f"Unexpected error parsing price '{price_str}': {e}")
        return None


def get_selenium_driver() -> webdriver.Chrome:
    """Configures and returns a Selenium WebDriver instance."""
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
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_experimental_option("prefs", {"profile.default_content_setting_values.notifications": 2})
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(SELENIUM_PAGE_LOAD_TIMEOUT)
        log.debug("Selenium WebDriver initialized successfully.")
        return driver
    except WebDriverException as e:
        log.error(f"Failed to initialize Selenium WebDriver: {e.msg}")
        log.error("Ensure ChromeDriver is installed, updated, and accessible in your PATH.")
        raise

def click_cookie_banner(driver: webdriver.Chrome, selectors: List[str]) -> bool:
    """Attempts to click a cookie banner using a list of CSS or XPath selectors."""
    if not selectors: return False
    clicked = False
    wait = WebDriverWait(driver, 5)

    # First check if there's any visible cookie banner before trying to click
    try:
        # Common cookie banner containers
        banner_selectors = [
            ".cookie-banner",
            "#cookie-banner",
            ".cookies-notification",
            "#cookies",
            ".cookie-dialog",
            "[class*='cookie']",
            "[id*='cookie']",
            "[class*='Cookie']",
            "[id*='Cookie']"
        ]

        banner_found = False
        for banner_sel in banner_selectors:
            try:
                banners = driver.find_elements(By.CSS_SELECTOR, banner_sel)
                if any(b.is_displayed() for b in banners):
                    banner_found = True
                    log.debug(f"Cookie banner container found with selector: {banner_sel}")
                    break
            except: pass

        if not banner_found:
            log.debug("No visible cookie banner detected, skipping click attempt")
            return False

    except Exception as e:
        log.debug(f"Error while checking for cookie banner presence: {e}")

    # Try all the provided selectors
    for selector in selectors:
        try:
            log.debug(f"Trying cookie selector: {selector}")
            by = By.XPATH if selector.startswith(("/", "(")) else By.CSS_SELECTOR

            # First check if element exists
            elements = driver.find_elements(by, selector)
            if not elements:
                log.debug(f"No elements found with cookie selector: {selector}")
                continue

            # Check if element is visible
            if not any(e.is_displayed() for e in elements):
                log.debug(f"Cookie selector elements found but not visible: {selector}")
                continue

            # Try to make clickable and click
            element = wait.until(EC.element_to_be_clickable((by, selector)))
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", element)
            time.sleep(0.5)

            try:
                log.debug(f"Attempting direct click on selector: {selector}")
                element.click()
                log.debug(f"Direct click succeeded on cookie banner with selector: {selector}")
            except Exception as click_error:
                log.debug(f"Direct click failed, error: {click_error}")
                log.debug(f"Trying JavaScript click instead")
                driver.execute_script("arguments[0].click();", element)
                log.debug(f"JavaScript click executed on cookie banner")

            log.info(f"Clicked cookie banner using selector: {selector}")
            clicked = True
            time.sleep(1.5)  # Give more time for the banner to disappear
            break
        except (NoSuchElementException, TimeoutException):
            log.debug(f"Cookie selector not found or clickable: {selector}")
            continue
        except Exception as e:
            log.warning(f"Non-critical error clicking cookie banner ({selector}): {e}")
            continue

    if not clicked:
        log.debug("Could not click any cookie banner with provided selectors")

    return clicked

# --- Selenium Function: Extract Product Info from WebElement ---
def extract_product_info_selenium(element: WebElement, store_key: str, config: Dict) -> Optional[Dict[str, Any]]:
    """Extracts product info from a Selenium WebElement based on store config."""
    store_config = config.get(store_key)
    if not store_config: return None

    # Log the entire element HTML at the beginning
    try:
        element_html = element.get_attribute('outerHTML')
        log.debug(f"Processing element in {store_key}:\n{element_html[:1000]}...")
    except Exception as e:
        log.debug(f"Could not get element HTML: {e}")

    info = {"store": store_key, "product_title": None, "price": None, "currency": None, "url": None, "availability": "Check on page"}
    base_url = store_config.get("base_url", "")
    title_found, price_found, url_found = False, False, False

    # Title extraction with enhanced logging
    if store_config.get("title_selector"):
        try:
            log.debug(f"Looking for title with selector: '{store_config['title_selector']}'")
            title_elements = element.find_elements(By.CSS_SELECTOR, store_config["title_selector"])

            if title_elements:
                title_elem = title_elements[0]
                log.debug(f"Title element found. Attributes: class='{title_elem.get_attribute('class')}', tag='{title_elem.tag_name}'")

                # Try multiple ways to get the text content
                title_text = title_elem.text
                title_text_content = title_elem.get_attribute('textContent')
                title_inner_text = title_elem.get_attribute('innerText')

                log.debug(f"Title extraction attempts: text='{title_text}', textContent='{title_text_content}', innerText='{title_inner_text}'")

                title_text = (title_text or title_text_content or title_inner_text or "").strip()
                if title_text:
                    info["product_title"] = title_text
                    title_found = True
                    log.debug(f"Title extracted successfully: '{title_text}'")
                else:
                    log.debug(f"{store_key}: Title element found but text was empty. Selector: '{store_config['title_selector']}'")

                    # Try alternative approach - check for nested elements
                    nested_elements = title_elem.find_elements(By.CSS_SELECTOR, "*")
                    if nested_elements:
                        log.debug(f"Found {len(nested_elements)} nested elements inside title element")
                        for i, ne in enumerate(nested_elements[:3]):  # Check first 3 nested elements
                            log.debug(f"Nested element {i}: tag='{ne.tag_name}', text='{ne.text}', class='{ne.get_attribute('class')}'")
            else:
                log.debug(f"{store_key}: No title elements found with selector '{store_config['title_selector']}'")

                # Try to find any text-containing elements for debugging
                debug_text_elements = element.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4, h5, a, span, div")
                log.debug(f"Found {len(debug_text_elements)} potential text elements for debugging")
                for i, te in enumerate(debug_text_elements[:5]):  # Log first 5 for debugging
                    if te.text.strip():
                        log.debug(f"Text element {i}: tag='{te.tag_name}', text='{te.text[:50]}...', class='{te.get_attribute('class')}'")
        except Exception as e:
            log.warning(f"{store_key}: Error getting title: {e}", exc_info=True)
    else:
        log.debug(f"{store_key}: No title selector configured")

    # Price extraction with enhanced logging
    if store_config.get("price_selector"):
        try:
            log.debug(f"Looking for price with selector: '{store_config['price_selector']}'")
            price_elements = element.find_elements(By.CSS_SELECTOR, store_config["price_selector"])

            if price_elements:
                price_elem = price_elements[0]
                log.debug(f"Price element found. Attributes: class='{price_elem.get_attribute('class')}', tag='{price_elem.tag_name}'")

                price_text = price_elem.text
                price_content = price_elem.get_attribute("content")
                price_inner_text = price_elem.get_attribute("innerText")

                log.debug(f"Price extraction attempts: text='{price_text}', content='{price_content}', innerText='{price_inner_text}'")

                price_str = (price_text or price_content or price_inner_text or "").strip()
                if price_str:
                    info["price"] = parse_price(price_str)
                    log.debug(f"Raw price string: '{price_str}', Parsed price: {info['price']}")

                    if info["price"] is not None:
                        price_found = True
                        if "€" in price_str or store_key.endswith(("_nl", "_de", "_fr")):
                            info["currency"] = "EUR"
                        elif "£" in price_str or store_key.endswith("_uk"):
                            info["currency"] = "GBP"
                        elif "$" in price_str or store_key.endswith("_com"):
                            info["currency"] = "USD"
                        else:
                            info["currency"] = "N/A"
                        log.debug(f"Price extracted successfully: {info['price']} {info['currency']}")
                    else:
                        log.debug(f"Failed to parse price from string: '{price_str}'")
                else:
                    log.debug(f"{store_key}: Price element found but text/content was empty.")
            else:
                log.debug(f"{store_key}: No price elements found with selector '{store_config['price_selector']}'")

                # Try to find any potential price elements for debugging
                debug_price_elements = element.find_elements(By.CSS_SELECTOR, ".price, [class*='price'], span:contains('€'), span:contains('$')")
                log.debug(f"Found {len(debug_price_elements)} potential price elements for debugging")
                for i, pe in enumerate(debug_price_elements[:3]):  # Log first 3 for debugging
                    log.debug(f"Potential price element {i}: tag='{pe.tag_name}', text='{pe.text}', class='{pe.get_attribute('class')}'")
        except Exception as e:
            log.warning(f"{store_key}: Error getting price: {e}", exc_info=True)
    else:
        log.debug(f"{store_key}: No price selector configured")

    # URL extraction with enhanced logging
    if store_config.get("url_selector"):
        try:
            log.debug(f"Looking for URL with selector: '{store_config['url_selector']}'")
            url_elements = element.find_elements(By.CSS_SELECTOR, store_config["url_selector"])

            if url_elements:
                url_elem = url_elements[0]
                log.debug(f"URL element found. Attributes: class='{url_elem.get_attribute('class')}', tag='{url_elem.tag_name}'")

                raw_url = url_elem.get_attribute("href")
                log.debug(f"Raw URL from href attribute: '{raw_url}'")

                if raw_url:
                    info["url"] = urljoin(base_url, raw_url)
                    url_found = True
                    log.debug(f"URL extracted successfully: '{info['url']}'")
                else:
                    log.debug(f"{store_key}: URL element found but href was empty.")
            else:
                log.debug(f"{store_key}: No URL elements found with selector '{store_config['url_selector']}'")

                # Try to find any links for debugging
                debug_url_elements = element.find_elements(By.TAG_NAME, "a")
                log.debug(f"Found {len(debug_url_elements)} potential link elements for debugging")
                for i, ue in enumerate(debug_url_elements[:3]):  # Log first 3 for debugging
                    href = ue.get_attribute("href")
                    log.debug(f"Link element {i}: text='{ue.text[:30]}', href='{href}'")
        except Exception as e:
            log.warning(f"{store_key}: Error getting URL: {e}", exc_info=True)

        # Fallback URL extraction from title element if different from URL selector
        if not url_found and title_found and store_config.get("title_selector") != store_config.get("url_selector"):
            try:
                log.debug(f"Attempting fallback URL extraction from title element")
                title_elem_for_url = element.find_element(By.CSS_SELECTOR, store_config["title_selector"])
                raw_url = title_elem_for_url.get_attribute("href")
                log.debug(f"Fallback raw URL from title element's href attribute: '{raw_url}'")

                if raw_url:
                    info["url"] = urljoin(base_url, raw_url)
                    url_found = True
                    log.debug(f"Used title element's href as fallback URL: '{info['url']}'")
            except Exception as fb_err:
                log.debug(f"Fallback URL extraction failed: {fb_err}")

        # Additional fallback specifically for URL extraction
        if not url_found:
            log.debug(f"Trying to find ANY links in this element for debugging")
            all_links = element.find_elements(By.TAG_NAME, "a")
            for i, link in enumerate(all_links):
                href = link.get_attribute("href")
                log.debug(f"Link {i}: href={href}, text={link.text[:30]}, class={link.get_attribute('class')}")
                # For Coolblue specifically, add a desperate fallback
                if store_key == 'coolblue_nl' and href and ('coolblue.nl' in href or href.startswith('/')):
                    info["url"] = urljoin(base_url, href)
                    url_found = True
                    log.debug(f"Using fallback link discovery for Coolblue: {info['url']}")
                    break
    else:
        log.debug(f"{store_key}: No URL selector configured")

    # Availability extraction with enhanced logging
    if store_config.get("availability_selector"):
        try:
            log.debug(f"Looking for availability with selector: '{store_config['availability_selector']}'")
            avail_elements = element.find_elements(By.CSS_SELECTOR, store_config["availability_selector"])

            if avail_elements:
                avail_elem = avail_elements[0]
                log.debug(f"Availability element found. Attributes: class='{avail_elem.get_attribute('class')}', tag='{avail_elem.tag_name}'")

                avail_text = (avail_elem.text or avail_elem.get_attribute("innerText") or "").strip().lower()
                log.debug(f"Raw availability text: '{avail_text}'")

                if avail_text:
                    if any(term in avail_text for term in ["niet leverbaar", "out of stock", "uitverkocht", "not available"]):
                        info["availability"] = "Out of stock"
                        log.debug(f"Availability status determined: Out of stock")
                    elif any(term in avail_text for term in ["voorraad", "in stock", "leverbaar", "morgen in huis", "available"]):
                        info["availability"] = "In Stock"
                        log.debug(f"Availability status determined: In Stock")
                    else:
                        log.debug(f"Availability text found but status unclear: '{avail_text}'")
                else:
                    log.debug(f"{store_key}: Availability element found but text was empty.")
            else:
                log.debug(f"{store_key}: No availability elements found with selector '{store_config['availability_selector']}'")
        except Exception as e:
            log.warning(f"{store_key}: Error getting availability: {e}", exc_info=True)
    else:
        log.debug(f"{store_key}: No availability selector configured")

    # Final validation with detailed logging
    if title_found and price_found and url_found:
        log.debug(f"{store_key}: Successfully parsed item: {info['product_title'][:30]}... | Price: {info['price']} {info['currency']}, URL: {info['url'][:40]}...")
        return info
    else:
        missing = [field for field, found in [("title", title_found), ("price", price_found), ("url", url_found)] if not found]
        log.warning(f"{store_key}: Skipping item. Missing essential fields: {', '.join(missing)}.")

        # Log found fields for debugging
        found_fields = [field for field, found in [("title", title_found), ("price", price_found), ("url", url_found)] if found]
        if found_fields:
            log.debug(f"{store_key}: Successfully found fields: {', '.join(found_fields)}")
            for field in found_fields:
                if field == "title" and title_found:
                    log.debug(f"Found title: '{info['product_title']}'")
                elif field == "price" and price_found:
                    log.debug(f"Found price: {info['price']} {info['currency']}")
                elif field == "url" and url_found:
                    log.debug(f"Found URL: '{info['url']}'")

        return None

# --- BLOCKING Selenium Function per Store ---
def scrape_store_with_selenium(store_key: str, search_query: str, config: Dict) -> List[Dict[str, Any]]:
    """Uses Selenium to scrape search results for a single store."""
    store_config = config.get(store_key)
    if not store_config: log.error(f"No config for {store_key}"); return []
    search_url_template = store_config.get("search_url_template")
    item_selector = store_config.get("item_selector")
    cookie_selectors = store_config.get("cookie_selectors", [])
    if not search_url_template or not item_selector: log.error(f"Missing config for {store_key}"); return []
    search_url = search_url_template.format(query=quote_plus(search_query))
    log.info(f"Selenium: Starting scrape for {store_key} - URL: {search_url}")
    driver = None; results = []; start_time = time.time(); processed_count = 0; count = 0; limit = 5

    try:
        driver = get_selenium_driver()
        log.debug(f"Navigating to {search_url}...")
        driver.get(search_url)

        # Add page source logging to debug page load issues
        log.debug(f"Page loaded for {store_key} with title: '{driver.title}'")
        log.debug(f"Current URL after load: {driver.current_url}")

        # Take a screenshot right after page load
        try:
            driver.save_screenshot(f"{store_key}_initial_load.png")
            log.info(f"Initial page screenshot saved to {store_key}_initial_load.png")
        except Exception as ss_err:
            log.error(f"Failed to save initial screenshot: {ss_err}")

        click_cookie_banner(driver, cookie_selectors)

        # Add logging for page state after cookie banner handling
        log.debug(f"Page state after cookie handling - Title: '{driver.title}'")

        log.debug(f"Selenium: Waiting for items matching '{item_selector}' for {store_key}...")
        try:
            WebDriverWait(driver, SELENIUM_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, item_selector)))
            log.debug(f"Selenium: Item selector '{item_selector}' found for {store_key}.")
            time.sleep(1.0)

            # Take screenshot after finding elements
            driver.save_screenshot(f"{store_key}_elements_found.png")
            log.info(f"Elements found screenshot saved to {store_key}_elements_found.png")
        except TimeoutException:
            log.warning(f"Selenium: Timeout waiting for item selector '{item_selector}' on {store_key}.")

            # Log page source on timeout to help debug selector issues
            log.debug(f"Page source on timeout (first 2000 chars): {driver.page_source[:2000]}...")

            try:
                driver.save_screenshot(f"{store_key}_timeout_debug.png")
                log.info(f"Debug screenshot saved to {store_key}_timeout_debug.png")
            except Exception as ss_err:
                log.error(f"Failed to save timeout screenshot: {ss_err}")
            return []

        elements = driver.find_elements(By.CSS_SELECTOR, item_selector)
        log.info(f"Selenium: Found {len(elements)} potential product elements using '{item_selector}' for {store_key}.")

        # Log presence of other key elements on the page
        for k, selector_config in config[store_key].items():
            if k.endswith("_selector") and k != "item_selector" and k != "cookie_selectors" and selector_config:
                try:
                    count = len(driver.find_elements(By.CSS_SELECTOR, selector_config))
                    log.debug(f"Found {count} elements matching {k}: '{selector_config}'")
                except Exception as e:
                    log.debug(f"Error checking selector {k}: {e}")

        for elem in elements:
            if processed_count >= limit: log.debug(f"Selenium: Reached processing limit of {limit} for {store_key}."); break
            processed_count += 1
            try:
                element_html = elem.get_attribute('outerHTML')
                log.debug(f"--- HTML for {store_key} Element #{processed_count} ---")
                log.debug(element_html[:1000] + ("..." if len(element_html) > 1000 else ""))
                log.debug(f"--- End HTML for {store_key} Element #{processed_count} ---")
            except Exception as log_err:
                log.warning(f"Could not get/log outerHTML for element {processed_count}: {log_err}")

            info = extract_product_info_selenium(elem, store_key, config)
            if info:
                results.append(info)
                count += 1
                log.debug(f"Added product to results: {info['product_title'][:30]}...")
            else:
                log.debug(f"Product info extraction failed for element #{processed_count}")

    except WebDriverException as e:
        log.error(f"Selenium WebDriverException for {store_key} ({search_url}): {e.msg}", exc_info=False)
        try:
            if driver: driver.save_screenshot(f"{store_key}_webdriver_error.png")
        except Exception as ss_err:
             log.error(f"Failed to save webdriver error screenshot: {ss_err}")
    except Exception as e:
        log.error(f"Selenium: Unexpected error scraping {store_key} ({search_url}): {e}", exc_info=True)
        try:
            if driver: driver.save_screenshot(f"{store_key}_unexpected_error.png")
        except Exception as ss_err:
            log.error(f"Failed to save unexpected error screenshot: {ss_err}")
    finally:
        if driver:
            try: driver.quit(); log.debug(f"Selenium: WebDriver instance for {store_key} quit.")
            except Exception as quit_err: log.error(f"Selenium: Error quitting WebDriver for {store_key}: {quit_err}")

    duration = time.time() - start_time
    log.info(f"Selenium: Scrape finished for {store_key} in {duration:.2f}s. Found {len(results)} valid results out of {processed_count} elements processed.")
    return results


# --- Main Async Tool Function (Orchestrator) ---
async def compare_product_prices(
    product_name: str,
    model_number: Optional[str] = None,
    stores: Optional[List[str]] = None,
    country_code: str = "NL" # Default to Netherlands
) -> List[Dict[str, Any]]:
    """
    [Selenium Version] Finds and compares product prices by scraping search results using Selenium.

    Args:
        product_name: Name of the product (e.g., "Sony WH-1000XM5 headphones").
        model_number: Optional specific model number.
        stores: List of store keys (e.g., ["amazon_nl", "bol_com", "coolblue_nl"]). If None, uses defaults based on country_code.
        country_code: Two-letter country code (e.g., "NL", "DE", "US", "UK"). Used to select default stores and potentially affects store URLs.

    Returns:
        A list of product offer dictionaries, or a list containing an error/message dictionary if issues occur or no results found.
        Note: Relies on Selenium, which can be slow and requires ChromeDriver setup. Consider running via 'start_background_task'..
    """
    default_stores = { "NL": ["amazon_nl", "bol_com", "coolblue_nl"], "DE": ["amazon_de"], "UK": ["amazon_co.uk"], "US": ["amazon_com"], }
    if stores is None:
        stores_to_check = default_stores.get(country_code.upper(), default_stores["NL"])
        log.info(f"No stores specified, using defaults for country '{country_code.upper()}': {stores_to_check}")
    else:
        stores_to_check = [s.lower().replace('.', '_') for s in stores]
        log.info(f"Using specified stores: {stores_to_check}")

    valid_store_keys = []
    for store_key in stores_to_check:
        if store_key in ECOMMERCE_CONFIG:
            store_country = store_key.split('_')[-1]
            is_match = False
            if store_country == country_code.lower(): is_match = True
            elif store_key == "bol_com" and country_code.upper() in ["NL", "BE"]: is_match = True
            elif store_key == "amazon_com" and country_code.upper() == "US": is_match = True
            # Add more rules here if needed
            if is_match:
                valid_store_keys.append(store_key)
                log.debug(f"Store '{store_key}' added to valid stores for country code '{country_code}'.")
            else:
                log.warning(f"Skipping store '{store_key}' because it doesn't seem appropriate for country code '{country_code}'.")
        else:
            log.warning(f"Store key '{store_key}' requested but not found in ECOMMERCE_CONFIG.")

    if not valid_store_keys:
        log.error(f"No valid stores to check for country '{country_code}'. Req: {stores}")
        return [{"error": f"No valid/configured stores found for '{country_code}'."}]

    search_query = f"{product_name} {model_number}" if model_number else product_name
    log.info(f"Comparing prices for '{search_query}' via Selenium across stores: {valid_store_keys}")
    tasks = []
    all_results = []

    for store_key in valid_store_keys:
        tasks.append(asyncio.to_thread(scrape_store_with_selenium, store_key, search_query, ECOMMERCE_CONFIG))

    log.info(f"Waiting for {len(tasks)} Selenium scraping tasks to complete...")
    start_gather = time.time()
    results_per_store = await asyncio.gather(*tasks, return_exceptions=True)
    gather_duration = time.time() - start_gather
    log.info(f"Selenium tasks finished in {gather_duration:.2f}s.")

    for i, result_or_exception in enumerate(results_per_store):
        store_key = valid_store_keys[i]
        if isinstance(result_or_exception, Exception):
            log.error(f"Selenium task for store '{store_key}' failed: {result_or_exception}", exc_info=False)
        elif isinstance(result_or_exception, list):
            log.info(f"Received {len(result_or_exception)} results from {store_key} scrape.")
            all_results.extend(result_or_exception)
        else:
            log.warning(f"Unexpected result type ({type(result_or_exception)}) from Selenium task for '{store_key}'.")

    # Sort results by price (lowest first)
    all_results.sort(key=lambda x: x.get('price') if isinstance(x.get('price'), (int, float)) else float('inf'))
    log.info(f"Selenium price comparison finished. Returning {len(all_results)} total valid results.")

    if not all_results:
        return [{"message": f"I searched on {', '.join(valid_store_keys)} using Selenium, but couldn't find any definitive results for '{search_query}'. The stores might be out of stock, the product name might be too general, or the website structure might have changed."}]

    return all_results


# --- Example Usage (for testing) ---
async def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.getLogger('ai_agent.tools.ecommerce').setLevel(logging.DEBUG) # Debug this tool
    logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.WARNING)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

    # --- Example Test Cases ---
    test_product_1 = "Samsung Galaxy S24"
    print(f"\n--- Comparing prices for: '{test_product_1}' (NL) using Selenium ---")
    results_nl = await compare_product_prices(product_name=test_product_1, country_code="NL")

    if isinstance(results_nl, list) and results_nl and ("error" in results_nl[0] or "message" in results_nl[0]):
        print(f"  Result: {results_nl[0]}")
    elif not results_nl:
         print("  No results returned.")
    else:
        for res in results_nl:
            print(f"  --- RESULT ---")
            print(f"  Store: {res.get('store', 'N/A')}")
            print(f"  Title: {res.get('product_title', 'N/A')}")
            print(f"  Price: {res.get('price', 'N/A')} {res.get('currency', '')}")
            print(f"  Avail: {res.get('availability', 'N/A')}")
            print(f"  URL:   {res.get('url', 'N/A')}")
            print(f"  --------------")


if __name__ == "__main__":
    print("Running Selenium E-commerce Tool Test...")
    print("Ensure ChromeDriver is installed and accessible.")
    print("NOTE: This will launch headless Chrome instances and may take some time.")
    try:
        asyncio.run(main())
    except WebDriverException as e:
         print(f"\nError: WebDriverException occurred. ChromeDriver might be missing/incompatible.")
         print(f"Details: {e.msg}")
    except Exception as e:
         print(f"\nAn unexpected error occurred: {e}")
         import traceback
         traceback.print_exc()
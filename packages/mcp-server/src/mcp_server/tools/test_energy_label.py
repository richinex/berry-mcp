import asyncio
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import time

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def setup_chrome_driver():
    """Set up Chrome WebDriver with appropriate options."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=chrome_options)

def test_energy_label_extraction(url):
    """Test energy label extraction for a specific URL."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)

    try:
        logger.info(f"\nTesting URL: {url}")
        driver.get(url)

        # Wait for page to load
        time.sleep(5)  # Give JavaScript time to execute

        # For listing pages, we need to look in the listing details
        if "/apartment-for-rent/" in url:
            # Look in the features section
            features_selectors = [
                ".listing-features",
                ".listing-features__main",
                ".listing-features__sub",
                ".listing-features__description"
            ]

            for selector in features_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(f"\nFeatures section '{selector}' found:")
                        for elem in elements:
                            logger.info(f"  Content: {elem.text}")
                            if 'energy' in elem.text.lower():
                                logger.info(f"  Found energy-related text: {elem.text}")
                except Exception as e:
                    logger.info(f"Error with features selector {selector}: {str(e)}")

        # Try all our selectors
        logger.info("\n1. Testing CSS Selectors:")
        css_selectors = [
            "[class*='energy']",
            "[class*='label']",
            "[data-label]",
            ".listing-features__description",
            ".listing-features__feature",
            "[title*='Energy']",
            ".listing-features__main",
            ".listing-features__sub",
            ".energy-label",
            ".listing-label",
            ".listing-features__summary [class*='icon']"
        ]

        for selector in css_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    logger.info(f"\nSelector '{selector}' found {len(elements)} elements:")
                    for elem in elements:
                        text = elem.text.strip()
                        class_name = elem.get_attribute('class')
                        data_label = elem.get_attribute('data-label')
                        title = elem.get_attribute('title')
                        aria_label = elem.get_attribute('aria-label')

                        logger.info(f"  Element found:")
                        if text: logger.info(f"    - Text: {text}")
                        if class_name: logger.info(f"    - Class: {class_name}")
                        if data_label: logger.info(f"    - Data-label: {data_label}")
                        if title: logger.info(f"    - Title: {title}")
                        if aria_label: logger.info(f"    - Aria-label: {aria_label}")

                        # Check parent element
                        parent = elem.find_element(By.XPATH, "./..")
                        parent_text = parent.text.strip()
                        if parent_text and ('energy' in parent_text.lower() or 'label' in parent_text.lower()):
                            logger.info(f"    - Parent text: {parent_text}")
            except Exception as e:
                logger.info(f"Error with selector {selector}: {str(e)}")

        # 2. Try XPath Selectors with improved patterns
        logger.info("\n2. Testing XPath Selectors:")
        xpath_selectors = [
            ".//*[contains(translate(text(),'ENERGY','energy'),'energy')]",
            ".//*[contains(translate(text(),'LABEL','label'),'label')]",
            ".//*[contains(@class,'energy') or contains(@class,'label')]",
            ".//div[contains(@class,'features')]//span[contains(@class,'icon')]",
            ".//div[contains(@class,'details')]//span[contains(@class,'label')]",
            ".//*[contains(@title,'Energy') or contains(@title,'Energie')]",
            ".//div[contains(@class,'features')]//li[contains(translate(text(),'ENERGY','energy'),'energy')]"
        ]

        for selector in xpath_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                if elements:
                    logger.info(f"\nXPath '{selector}' found {len(elements)} elements:")
                    for elem in elements:
                        text = elem.text.strip()
                        html = elem.get_attribute('outerHTML')
                        if text or ('energy' in html.lower()):
                            logger.info(f"  - Text: {text}")
                            logger.info(f"  - HTML: {html}")
            except Exception as e:
                logger.info(f"Error with XPath {selector}: {str(e)}")

        # 3. Look for energy label pattern in full page text
        logger.info("\n3. Searching for energy label pattern in full page:")
        page_text = driver.page_source
        energy_patterns = [
            r'energy\s*label\s*([A-G](?:\+{1,4})?)',
            r'energie\s*label\s*([A-G](?:\+{1,4})?)',
            r'energy\s*class\s*([A-G](?:\+{1,4})?)',
            r'energy\s*rating\s*([A-G](?:\+{1,4})?)',
            r'(?:energy|energie)\s*(?:label|klasse|rating)?\s*:\s*([A-G](?:\+{1,4})?)'
        ]

        for pattern in energy_patterns:
            matches = re.finditer(pattern, page_text, re.IGNORECASE)
            for match in matches:
                context_start = max(0, match.start() - 50)
                context_end = min(len(page_text), match.end() + 50)
                context = page_text[context_start:context_end]
                logger.info(f"\nFound energy label: {match.group(1)}")
                logger.info(f"Pattern: {pattern}")
                logger.info(f"Context: ...{context}...")

    finally:
        driver.quit()

def main():
    # Test URLs - including specific listing pages
    test_urls = [
        "https://www.pararius.com/apartment-for-rent/rotterdam/1d42af54/schietbaanlaan",
        "https://www.pararius.com/apartment-for-rent/rotterdam/8b502d85/baan",
        "https://www.pararius.com/apartment-for-rent/rotterdam/8112990d/prins-hendriklaan",
        # Add a search results page as well
        "https://www.pararius.com/apartments/rotterdam/2-bedrooms/0-2000"
    ]

    for url in test_urls:
        test_energy_label_extraction(url)
        print("\n" + "="*80 + "\n")  # Separator between tests

if __name__ == "__main__":
    main()
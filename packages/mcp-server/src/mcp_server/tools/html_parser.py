# src/ai_agent/tools/html_parser.py
from typing import Dict, Any
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

def click_cookie_banner(driver: webdriver.Chrome) -> bool:
    """
    Attempts to click a cookie consent banner using common XPath selectors.

    Returns:
        True if a cookie banner was found and clicked; False otherwise.
    """
    try:
        wait = WebDriverWait(driver, 5)
        xpaths = [
            "//button[contains(text(), 'Accept')]",
            "//button[contains(text(), 'I agree')]",
            "//button[contains(text(), 'Agree')]",
            "//button[contains(text(), 'Accept all')]",
            "//button[contains(text(), 'Yes, I accept')]",
            "//button[@id='onetrust-accept-btn-handler']"
        ]
        for xpath in xpaths:
            try:
                element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                element.click()
                print(f"Clicked cookie banner using XPath: {xpath}")
                return True
            except Exception:
                continue
    except Exception as e:
        print(f"Error handling cookie banner: {e}")
    return False

def parse_html(url: str) -> Dict[str, Any]:
    """
    Fetches a URL using Selenium and parses its HTML content with BeautifulSoup.
    Automatically clicks on cookie consent banners if present.

    Args:
        url (str): The URL of the page to parse.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - title: The text from the <title> tag (or og:title if available).
            - meta_description: The meta description or og:description content.
            - paragraphs: A list of text content from all <p> tags.
        If an error occurs, an "error" key is added.
    """
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        # Attempt to click any cookie banner if present.
        click_cookie_banner(driver)
        time.sleep(2)  # Wait for the page to load fully.
        page_source = driver.page_source
        try:
            soup = BeautifulSoup(page_source, "lxml")
        except Exception:
            soup = BeautifulSoup(page_source, "html.parser")

        # Extract title (prefer og:title if available)
        title = "No title found"
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Extract meta description (prefer og:description)
        meta_description = ""
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            meta_description = og_desc["content"].strip()
        else:
            meta_tag = soup.find("meta", attrs={"name": "description"})
            if meta_tag and meta_tag.get("content"):
                meta_description = meta_tag["content"].strip()

        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]

        return {
            "title": title,
            "meta_description": meta_description,
            "paragraphs": paragraphs,
        }
    except Exception as e:
        return {
            "error": str(e),
            "title": "No title found",
            "meta_description": "",
            "paragraphs": []
        }
    finally:
        driver.quit()

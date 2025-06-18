# src/ai_agent/tools/safety_analyzer.py
import logging
import asyncio
from typing import Dict, Any, List, Tuple
import os
from datetime import datetime
import asyncpraw
import time
import re
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Cache for search results to avoid repeated API calls
SEARCH_CACHE = {}

# Rate limiting settings
RATE_LIMIT_DELAY = 2  # Delay between requests in seconds
MAX_RETRIES = 3  # Maximum number of retries for rate-limited requests

# Initialize Reddit client once
async def get_reddit_client():
    """Initialize and return an AsyncPRAW Reddit client."""
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "RotterdamSafetyAnalyzer/1.0")

    if not client_id or not client_secret:
        logger.error("Missing Reddit API credentials")
        logger.error(f"Client ID: {client_id[:4] if client_id else 'None'}")
        logger.error(f"Client Secret: {client_secret[:4] if client_secret else 'None'}")
        logger.error(f"User Agent: {user_agent}")
        return None

    try:
        reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        return reddit
    except Exception as e:
        logger.error(f"Error initializing Reddit client: {e}")
        return None

# Global Reddit client
REDDIT_CLIENT = None

# Rotterdam district mapping
ROTTERDAM_DISTRICTS = {
    # Central districts
    "Centrum": ["Oude", "Binnenstad", "Cool", "Stadsdriehoek"],
    "Noord": ["Bergpolder", "Blijdorp", "Liskwartier", "Oude Noorden", "Agniesebuurt"],
    "Zuid": ["Feijenoord", "Afrikaanderwijk", "Bloemhof", "Hillesluis", "Katendrecht", "Kop van Zuid", "Noordereiland", "Vreewijk"],
    "West": ["Delfshaven", "Bospolder", "Tussendijken", "Spangen", "Nieuwe Westen", "Middelland", "Schiemond"],
    "Oost": ["Kralingen", "Crooswijk", "Kralingen-West", "Kralingen-Oost", "Struisenburg"],

    # Other major districts
    "Charlois": ["Tarwewijk", "Carnisse", "Zuidwijk", "Pendrecht", "Wielewaal", "Oud-Charlois"],
    "Delfshaven": ["Schieweg", "Nieuwe Westen", "Middelland", "Spangen", "Bospolder"],
    "Feijenoord": ["Kop van Zuid", "Katendrecht", "Afrikaanderwijk", "Bloemhof", "Hillesluis"],
    "Hillegersberg-Schiebroek": ["Hillegersberg", "Schiebroek", "Terbregge"],
    "IJsselmonde": ["Beverwaard", "Lombardijen", "Groot-IJsselmonde"],
    "Prins Alexander": ["Ommoord", "Zevenkamp", "Oosterflank", "Het Lage Land"],
    "Overschie": ["Kleinpolder", "Landzicht"]
}

def get_district_for_street(street: str) -> Tuple[str, str]:
    """
    Get the broader district for a street name.
    Returns a tuple of (district, subdistrict).
    """
    street_lower = street.lower()

    # First check if the street contains a district name
    for district, subdistricts in ROTTERDAM_DISTRICTS.items():
        if district.lower() in street_lower:
            return district, district

        # Check subdistricts
        for subdistrict in subdistricts:
            if subdistrict.lower() in street_lower:
                return district, subdistrict

    return None, None

def extract_district(area: str, url: str = None) -> Tuple[str, str]:
    """
    Extract district and subdistrict from area or URL.
    Returns a tuple of (district, subdistrict).
    """
    if url:
        try:
            path = unquote(urlparse(url).path)
            parts = path.split('/')
            # Find the part after 'rotterdam' but before the last part
            for i, part in enumerate(parts):
                if part.lower() == 'rotterdam' and i + 1 < len(parts) - 1:
                    location = parts[i + 1].replace('-', ' ').title()
                    if not location.isdigit():
                        district, subdistrict = get_district_for_street(location)
                        if district:
                            return district, subdistrict or location
        except Exception as e:
            logger.warning(f"Error extracting district from URL: {e}")

    # If no district found in URL, try area name
    area_name = area.split(',')[0].strip()
    district, subdistrict = get_district_for_street(area_name)
    if district:
        return district, subdistrict

    # If still no match, return the area name as both district and subdistrict
    return area_name, area_name

def generate_search_terms(area: str, district: str, subdistrict: str) -> List[str]:
    """Generate search terms for safety-related information."""
    search_terms = []

    # Basic area terms
    area_terms = [area.split(',')[0].strip()]
    if district and district not in area_terms:
        area_terms.append(district)
    if subdistrict and subdistrict not in area_terms:
        area_terms.append(subdistrict)

    # Safety-related keywords
    safety_keywords = [
        "safe", "safety", "unsafe", "dangerous", "crime", "incident",
        "neighborhood", "area", "district", "living", "residents",
        "veilig", "onveilig", "buurt", "wijk", "wonen", "bewoners"
    ]

    # Combine area terms with safety keywords
    for term in area_terms:
        search_terms.append(term)
        for keyword in safety_keywords:
            search_terms.append(f"{term} {keyword}")

    return search_terms

async def _search_with_retry(subreddit, search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Helper function to search Reddit with retry logic for rate limits."""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            results = []
            async for submission in subreddit.search(search_term, limit=limit):
                if submission.created_utc > time.time() - (365 * 24 * 60 * 60):  # Posts within last year
                    results.append({
                        "title": submission.title,
                        "url": f"https://reddit.com{submission.permalink}",
                        "created_utc": submission.created_utc,
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "subreddit": subreddit.display_name
                    })
            return results
        except Exception as e:
            if "429" in str(e):  # Rate limit error
                retries += 1
                if retries < MAX_RETRIES:
                    wait_time = RATE_LIMIT_DELAY * (2 ** retries)  # Exponential backoff
                    logger.warning(f"Rate limited, waiting {wait_time} seconds before retry {retries}/{MAX_RETRIES}")
                    await asyncio.sleep(wait_time)
                    continue
            logger.error(f"Error during Reddit search: {e}")
            return []
    return []

async def _search_safety_info(search_term: str) -> List[Dict[str, Any]]:
    """Function to search Reddit for safety information."""
    global REDDIT_CLIENT

    if not REDDIT_CLIENT:
        REDDIT_CLIENT = await get_reddit_client()

    if not REDDIT_CLIENT:
        logger.error("Reddit client not initialized")
        return []

    try:
        # Check cache first
        cache_key = f"{search_term}_{datetime.now().strftime('%Y-%m-%d')}"
        if cache_key in SEARCH_CACHE:
            return SEARCH_CACHE[cache_key]

        results = []
        subreddits = ["Rotterdam", "Netherlands"]  # Add more relevant subreddits if needed

        for subreddit_name in subreddits:
            try:
                logger.info(f"Checking r/{subreddit_name} for mentions of {search_term}")
                subreddit = await REDDIT_CLIENT.subreddit(subreddit_name)

                # Add delay between subreddit searches
                if results:  # If we've already searched one subreddit
                    await asyncio.sleep(RATE_LIMIT_DELAY)

                # Search with retry logic
                subreddit_results = await _search_with_retry(subreddit, search_term)
                results.extend(subreddit_results)

            except Exception as e:
                logger.warning(f"Error accessing r/{subreddit_name}: {e}")
                continue

        # Cache results
        SEARCH_CACHE[cache_key] = results
        logger.info(f"Found {len(results)} posts mentioning {search_term}")
        return results

    except Exception as e:
        logger.error(f"Error searching Reddit: {e}")
        return []

async def search_safety_info(area: str, district: str, subdistrict: str) -> List[Dict[str, Any]]:
    """Search for safety-related information about an area."""
    search_terms = generate_search_terms(area, district, subdistrict)
    all_results = []
    seen_urls = set()

    for term in search_terms:
        term_results = await _search_safety_info(term)
        for result in term_results:
            if result["url"] not in seen_urls:
                seen_urls.add(result["url"])
                all_results.append(result)

    return all_results

async def get_rotterdam_safety_info() -> List[Dict[str, Any]]:
    """Get general safety information about Rotterdam."""
    global REDDIT_CLIENT

    if not REDDIT_CLIENT:
        REDDIT_CLIENT = await get_reddit_client()

    if not REDDIT_CLIENT:
        logger.error("Reddit client not initialized")
        return []

    # Check cache first
    cache_key = f"rotterdam_safety_{datetime.now().strftime('%Y-%m-%d')}"
    if cache_key in SEARCH_CACHE:
        return SEARCH_CACHE[cache_key]

    search_terms = [
        "rotterdam safety",
        "rotterdam safe",
        "rotterdam unsafe",
        "rotterdam dangerous",
        "rotterdam crime",
        "rotterdam neighborhood",
        "rotterdam district",
        "rotterdam living",
        "rotterdam veilig",
        "rotterdam onveilig",
        "rotterdam wijk",
        "rotterdam wonen"
    ]

    all_results = []
    seen_urls = set()

    try:
        subreddits = ["Rotterdam", "Netherlands"]
        for subreddit_name in subreddits:
            try:
                subreddit = await REDDIT_CLIENT.subreddit(subreddit_name)
                for term in search_terms:
                    logger.info(f"Checking r/{subreddit_name} for {term}")
                    try:
                        async for submission in subreddit.search(term, limit=5):
                            if (submission.created_utc > time.time() - (365 * 24 * 60 * 60) and  # Posts within last year
                                submission.url not in seen_urls):
                                seen_urls.add(submission.url)
                                all_results.append({
                                    "title": submission.title,
                                    "url": f"https://reddit.com{submission.permalink}",
                                    "created_utc": submission.created_utc,
                                    "score": submission.score,
                                    "num_comments": submission.num_comments,
                                    "subreddit": subreddit_name
                                })
                    except Exception as e:
                        logger.warning(f"Error searching for {term} in r/{subreddit_name}: {e}")
                        continue
            except Exception as e:
                logger.warning(f"Error accessing r/{subreddit_name}: {e}")
                continue

        # Cache results
        SEARCH_CACHE[cache_key] = all_results
        return all_results

    except Exception as e:
        logger.error(f"Error getting Rotterdam safety info: {e}")
        return []

async def analyze_area_safety(area: str, url: str = None) -> Dict[str, Any]:
    """Map an area to its district and provide district and safety information."""
    try:
        logger.info(f"Analyzing district for {area}")

        # Get district information
        district, subdistrict = extract_district(area, url)
        logger.info(f"Mapped to district: {district}, subdistrict: {subdistrict}")

        # Get general Rotterdam safety information
        safety_info = await get_rotterdam_safety_info()

        # Filter relevant posts for this area/district
        area_terms = set([
            term.lower() for term in [
                area.split(',')[0].strip(),
                district,
                subdistrict
            ] if term
        ])

        relevant_posts = []
        for post in safety_info:
            if any(term in post['title'].lower() for term in area_terms):
                relevant_posts.append(post)

        return {
            "area": area,
            "district": district,
            "subdistrict": subdistrict,
            "district_info": {
                "name": district,
                "subdistricts": ROTTERDAM_DISTRICTS.get(district, []),
                "is_central": district in ["Centrum", "Noord", "Zuid", "West", "Oost"]
            },
            "reddit_mentions": relevant_posts,
            "general_safety_info": {
                "total_posts_analyzed": len(safety_info),
                "area_specific_posts": len(relevant_posts),
                "note": "Safety information is based on available Reddit discussions. Areas with no specific mentions may still be safe - please consult local authorities or residents for detailed safety information."
            }
        }

    except Exception as e:
        logger.error(f"Error analyzing district for {area}: {str(e)}")
        return {
            "area": area,
            "error": str(e)
        }

def get_safe_areas() -> List[Dict[str, Any]]:
    """Get information about Rotterdam districts."""
    return [
        {
            "district": district,
            "subdistricts": subdistricts,
            "is_central": district in ["Centrum", "Noord", "Zuid", "West", "Oost"]
        }
        for district, subdistricts in ROTTERDAM_DISTRICTS.items()
    ]
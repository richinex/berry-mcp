# src/ai_agent/tools/market_analyzer.py

import asyncio
import logging
import statistics
from typing import Dict, Optional, Any, List
from collections import defaultdict
import time
import re

# Import the scraper and its helpers (assuming they are accessible)
try:
    from .search_pararius import search_pararius, parse_price, parse_rooms # Need parsing helpers too
except ImportError:
    log = logging.getLogger(__name__)
    log.error("Could not import search_pararius tool. Market analysis tool will not function.")
    # Define dummy functions if import fails, so loader doesn't break
    async def search_pararius(*args, **kwargs) -> List: return []
    def parse_price(*args) -> Optional[float]: return None
    def parse_rooms(*args) -> Optional[int]: return None

log = logging.getLogger(__name__)

# Define helper to parse area (m²)
def parse_area(area_str: str) -> Optional[float]:
    if not area_str: return None
    try:
        match = re.search(r'(\d+)\s*m²', area_str)
        if match:
            return float(match.group(1))
    except Exception as e:
        log.warning(f"Could not parse area '{area_str}': {e}")
    return None

# Helper to extract neighborhood (heuristic)
def extract_neighborhood(location_str: Optional[str], title_str: Optional[str]) -> Optional[str]:
    """Tries to extract a plausible neighborhood from location or title."""
    if not location_str:
        # Fallback to title if location is empty
        if title_str:
             # Simple heuristic: assume second word in title might be street/neighborhood
             parts = title_str.split()
             if len(parts) > 1:
                 # Avoid generic terms like 'Apartment', 'House'
                 if parts[0].lower() not in ['apartment', 'flat', 'house', 'woning', 'studio']:
                     return parts[0] # Assume first word is neighborhood? Less reliable
                 elif len(parts) > 2:
                      return parts[1] # Assume second word is neighborhood/street
        return "Unknown" # Give up if no info

    # If location_str exists, try common patterns
    # Example patterns: "Neighborhood, City", "Street, Neighborhood", "PostalCode City (Neighborhood)"
    parts = location_str.split(',')
    if len(parts) > 1:
        # Assume first part before comma might be neighborhood/street
        potential_neighborhood = parts[0].strip()
        # Very basic check to avoid just getting postal code like '3011 AA'
        if not re.match(r'^\d{4}\s?[A-Z]{2}$', potential_neighborhood):
            return potential_neighborhood

    # If no comma, or first part looks like postal code, return the whole string or parts of it
    # This needs more sophisticated logic for real accuracy (e.g., using known neighborhood lists or GIS data)
    simplified_location = location_str.split('(')[0].strip() # Remove text in brackets
    return simplified_location if simplified_location else "Unknown"


async def generate_rental_market_report(
    location: str,
    property_type: str = "apartments", # Pararius URL structure often includes this
    min_bedrooms: Optional[int] = None,
    max_price: Optional[float] = None,
    max_pages_to_scan: int = 5 # Limit how deep the underlying scrape goes
) -> Dict[str, Any]:
    """
    Analyzes the current rental market for a given location based on Pararius listings.

    Provides a snapshot report including average price, median price, price per square meter,
    and distribution by neighborhood based on *currently available* listings.

    Note: This tool performs a live scrape via search_pararius and analyzes the results.
          It does NOT use historical data for trend analysis. Accuracy depends on
          the scraped data quality and Pararius's current listings.

    Args:
        location: The primary location (e.g., 'Rotterdam', 'Amsterdam Zuid').
                  The underlying scraper will build the appropriate starting URL.
        property_type: Type of property (e.g., 'apartments', 'houses'). Affects starting URL.
        min_bedrooms: Minimum number of bedrooms required for listings to be included.
        max_price: Maximum rental price for listings to be included.
        max_pages_to_scan: How many search result pages to scan for data (max ~10 recommended).

    Returns:
        A dictionary containing the market analysis report.
    """
    log.info(f"Generating market report for: location='{location}', property_type='{property_type}', "
             f"min_bedrooms={min_bedrooms}, max_price={max_price}, max_pages={max_pages_to_scan}")
    start_time = time.time()

    # --- 1. Prepare Scraper Call ---
    # Construct the starting URL based on location and property type
    # (This logic might need refinement based on how pararius structures URLs)
    location_slug = location.lower().replace(' ', '-')
    start_url = f"https://www.pararius.com/{property_type}/{location_slug}/"
    log.info(f"Using starting URL: {start_url}")

    # Prepare filters for the scraper
    scraper_filters = {}
    if min_bedrooms is not None:
        scraper_filters["rooms_min"] = min_bedrooms # Assuming scraper filter uses 'rooms' terminology
    if max_price is not None:
        scraper_filters["price_max"] = max_price
    # Add other filters if the scraper supports them (e.g., energy_rating_min)
    # scraper_filters["energy_rating_min"] = "C" # Example

    # --- 2. Gather Data ---
    try:
        log.info(f"Calling search_pararius with filters: {scraper_filters}, max_pages: {max_pages_to_scan}")
        # Important: search_pararius should return enough data for analysis.
        # It already applies these basic filters during scraping.
        listings = await search_pararius(
            starting_url=start_url,
            max_pages=max_pages_to_scan,
            filters=scraper_filters
        )
        log.info(f"search_pararius returned {len(listings)} listings matching criteria.")

    except Exception as e:
        log.error(f"Error calling search_pararius: {e}", exc_info=True)
        return {
            "error": f"Failed to retrieve listing data via search_pararius: {e}",
            "parameters": locals() # Include args for debugging
        }

    if not listings:
        return {
            "message": "No listings found matching the specified criteria.",
            "parameters": { # Echo back parameters
                 "location": location, "property_type": property_type, "min_bedrooms": min_bedrooms,
                 "max_price": max_price, "max_pages_scanned": max_pages_to_scan
            },
            "listing_count": 0,
            "analysis_timestamp": time.time(),
        }

    # --- 3. Analyze Data ---
    log.info("Analyzing retrieved listings...")
    valid_prices = []
    valid_prices_per_sqm = []
    neighborhood_data = defaultdict(lambda: {'count': 0, 'prices': [], 'prices_per_sqm': []})
    parsed_listings_count = 0

    for listing in listings:
        price = parse_price(listing.get("price"))
        area = parse_area(listing.get("area"))
        # Optionally parse rooms again if needed for different analysis,
        # but the scraper filter should have handled min_bedrooms
        # rooms = parse_rooms(listing.get("rooms"))

        # Only include listings with valid price for most metrics
        if price is None:
            continue

        parsed_listings_count += 1
        valid_prices.append(price)
        neighborhood = extract_neighborhood(listing.get("location"), listing.get("title")) or "Unknown"

        neighborhood_data[neighborhood]['count'] += 1
        neighborhood_data[neighborhood]['prices'].append(price)

        # Calculate price per sqm only if area is valid and > 0
        if area is not None and area > 0:
            price_per_sqm = round(price / area, 2)
            valid_prices_per_sqm.append(price_per_sqm)
            neighborhood_data[neighborhood]['prices_per_sqm'].append(price_per_sqm)

    log.info(f"Successfully parsed price data for {parsed_listings_count} listings.")
    log.info(f"Found {len(valid_prices_per_sqm)} listings with valid area for price/sqm analysis.")

    # --- 4. Calculate Metrics ---
    report = {
        "parameters": {
            "location": location,
            "property_type": property_type,
            "min_bedrooms": min_bedrooms,
            "max_price": max_price,
            "max_pages_scanned": max_pages_to_scan
        },
        "analysis_timestamp": time.time(),
        "total_listings_found": len(listings), # Before price/area parsing checks
        "listings_analyzed": parsed_listings_count, # Listings with valid price
        "overall_metrics": {},
        "neighborhood_breakdown": {},
        "caveats": [
            "Analysis based on currently listed properties found on Pararius.",
            "Data accuracy depends on scraped information.",
            "Does not include historical trends.",
            "Neighborhood extraction is heuristic and may require refinement.",
            "Price per sqm calculations exclude listings with missing/invalid area data."
        ]
    }

    if valid_prices:
        report["overall_metrics"]["average_price"] = round(statistics.mean(valid_prices), 2)
        report["overall_metrics"]["median_price"] = round(statistics.median(valid_prices), 2)
        report["overall_metrics"]["min_price"] = round(min(valid_prices), 2)
        report["overall_metrics"]["max_price"] = round(max(valid_prices), 2) # Should be <= filter max_price
    else:
        report["overall_metrics"]["average_price"] = None
        report["overall_metrics"]["median_price"] = None
        # Add message if no valid prices found

    if valid_prices_per_sqm:
        report["overall_metrics"]["average_price_per_sqm"] = round(statistics.mean(valid_prices_per_sqm), 2)
        report["overall_metrics"]["median_price_per_sqm"] = round(statistics.median(valid_prices_per_sqm), 2)
    else:
        report["overall_metrics"]["average_price_per_sqm"] = None
        report["overall_metrics"]["median_price_per_sqm"] = None

    # Calculate neighborhood metrics
    for hood, data in neighborhood_data.items():
        avg_price = round(statistics.mean(data['prices']), 2) if data['prices'] else None
        median_price = round(statistics.median(data['prices']), 2) if data['prices'] else None
        avg_price_sqm = round(statistics.mean(data['prices_per_sqm']), 2) if data['prices_per_sqm'] else None
        report["neighborhood_breakdown"][hood] = {
            "count": data['count'],
            "average_price": avg_price,
            "median_price": median_price,
            "average_price_per_sqm": avg_price_sqm
        }

    # Sort neighborhood breakdown by count descending
    report["neighborhood_breakdown"] = dict(sorted(
        report["neighborhood_breakdown"].items(),
        key=lambda item: item[1]['count'],
        reverse=True
    ))

    end_time = time.time()
    report["analysis_duration_seconds"] = round(end_time - start_time, 2)
    log.info(f"Market report generation complete in {report['analysis_duration_seconds']:.2f} seconds.")

    return report
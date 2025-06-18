# File: src/ai_agent/tools/finance.py

import logging
import asyncio
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import aiohttp
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

log = logging.getLogger(__name__)

# Get API key from environment variables with fallback
EXCHANGERATE_API_KEY = os.environ.get("EXCHANGERATE_API_KEY", "YOUR_API_KEY_HERE")
BASE_API_URL = "https://v6.exchangerate-api.com/v6/"

async def convert_currency(amount: float, from_currency: str, to_currency: str) -> Dict[str, Any]:
    """
    Converts an amount from one currency to another using real-time exchange rates
    obtained from exchangerate-api.com.

    Args:
        amount: The amount of money to convert. Must be a positive number.
        from_currency: The 3-letter ISO 4217 currency code to convert FROM (e.g., "USD", "EUR").
        to_currency: The 3-letter ISO 4217 currency code to convert TO (e.g., "GBP", "JPY").

    Returns:
        A dictionary containing the conversion details on success,
        or a dictionary with an "error" key on failure.
        Example Success:
        {
            "original_amount": 100.0,
            "from_currency": "USD",
            "converted_amount": 92.53,
            "to_currency": "EUR",
            "rate": 0.9253,
            "timestamp": "2023-10-27T15:00:01Z" # ISO 8601 format UTC
        }
        Example Error:
        {
            "error": "API request failed with status 404: Not Found. Check currency codes.",
            "details": {"amount": 100, "from": "USX", "to": "EUR"}
        }
    """
    func_args = {"amount": amount, "from": from_currency, "to": to_currency} # For error reporting
    log.info(f"Attempting currency conversion: {amount} {from_currency} to {to_currency}")

    # --- Input Validation ---
    if not isinstance(amount, (int, float)) or amount <= 0:
        log.error(f"Invalid amount for conversion: {amount}")
        return {"error": "Amount must be a positive number.", "details": func_args}
    if not from_currency or not isinstance(from_currency, str) or len(from_currency) != 3:
        log.error(f"Invalid 'from_currency' code: {from_currency}")
        return {"error": "Invalid 'from_currency'. Please use 3-letter ISO code (e.g., USD).", "details": func_args}
    if not to_currency or not isinstance(to_currency, str) or len(to_currency) != 3:
        log.error(f"Invalid 'to_currency' code: {to_currency}")
        return {"error": "Invalid 'to_currency'. Please use 3-letter ISO code (e.g., EUR).", "details": func_args}

    # --- API Key Check ---
    if not EXCHANGERATE_API_KEY or EXCHANGERATE_API_KEY == "YOUR_API_KEY_HERE":
        log.error("ExchangeRate-API key is missing or not configured.")
        # Debugging the environment variable
        log.debug(f"Environment variable value: {os.environ.get('EXCHANGERATE_API_KEY', 'Not set')}")
        # Avoid exposing key status in the error message returned to the user/agent
        return {"error": "Currency conversion service is not configured correctly.", "details": func_args}

    # Normalize currency codes to uppercase
    from_curr_upper = from_currency.upper()
    to_curr_upper = to_currency.upper()
    func_args["from"] = from_curr_upper # Update args dict for potential error reporting
    func_args["to"] = to_curr_upper

    # --- API Call ---
    api_endpoint = f"{BASE_API_URL}{EXCHANGERATE_API_KEY}/latest/{from_curr_upper}"
    log.debug(f"Calling ExchangeRate-API: {api_endpoint}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_endpoint, timeout=10) as response: # 10 second timeout
                # Check HTTP status first
                if response.status != 200:
                    error_detail = f"API request failed with status {response.status}: {response.reason}"
                    try:
                        # Try to get more specific error from API response body if available
                        api_error_data = await response.json()
                        if api_error_data and 'error-type' in api_error_data:
                            error_detail += f" (API Error: {api_error_data['error-type']})"
                    except Exception:
                        pass # Ignore if response body isn't valid JSON or doesn't contain error info
                    log.error(error_detail + f" for conversion: {func_args}")
                    return {"error": error_detail + ". Check currency codes or API key.", "details": func_args}

                # Parse the successful JSON response
                data = await response.json()

                # --- Process Response ---
                if data.get("result") != "success":
                    api_error_type = data.get("error-type", "unknown_error")
                    log.error(f"ExchangeRate-API returned non-success result: {api_error_type} for {func_args}")
                    return {"error": f"API indicated failure: {api_error_type}", "details": func_args}

                rates = data.get("conversion_rates")
                timestamp_unix = data.get("time_last_update_unix")

                if not rates or to_curr_upper not in rates:
                    log.error(f"Target currency '{to_curr_upper}' not found in API rates for base '{from_curr_upper}'.")
                    return {"error": f"Could not find rate for target currency '{to_curr_upper}'.", "details": func_args}

                rate = rates[to_curr_upper]
                converted_amount = round(amount * float(rate), 4) # Round to sensible decimal places

                # Convert timestamp to ISO 8601 format UTC
                timestamp_dt = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc) if timestamp_unix else datetime.now(timezone.utc)
                timestamp_iso = timestamp_dt.isoformat(timespec='seconds').replace('+00:00', 'Z')

                result = {
                    "original_amount": float(amount),
                    "from_currency": from_curr_upper,
                    "converted_amount": converted_amount,
                    "to_currency": to_curr_upper,
                    "rate": float(rate),
                    "timestamp": timestamp_iso
                }
                log.info(f"Conversion successful: {amount} {from_curr_upper} = {converted_amount} {to_curr_upper} @ {rate}")
                return result

    except aiohttp.ClientConnectorError as e:
        log.error(f"Network connection error during currency conversion: {e}", exc_info=False)
        return {"error": f"Network error connecting to currency service: {e}", "details": func_args}
    except asyncio.TimeoutError:
        log.error("Timeout during currency conversion API call.")
        return {"error": "Request timed out while contacting currency service.", "details": func_args}
    except Exception as e:
        log.exception(f"Unexpected error during currency conversion for {func_args}: {e}") # Log full traceback for unexpected
        return {"error": f"An unexpected error occurred: {type(e).__name__}", "details": func_args}


# --- Example Usage (for testing) ---
async def main():
    # Configure logging for testing
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log.setLevel(logging.DEBUG) # Ensure our tool's logger is also DEBUG

    # Debug API key status
    log.debug(f"API Key from environment: {'Set (value hidden)' if os.environ.get('EXCHANGERATE_API_KEY') else 'Not set'}")
    log.debug(f"Using API Key: {'Using env var' if EXCHANGERATE_API_KEY != 'YOUR_API_KEY_HERE' else 'Using placeholder'}")

    # --- Tests ---
    print("-" * 20)
    print("Test 1: Valid Conversion (USD to EUR)")
    result1 = await convert_currency(100, "USD", "EUR")
    print(result1)

    print("-" * 20)
    print("Test 2: Valid Conversion (GBP to JPY)")
    result2 = await convert_currency(50, "GBP", "JPY")
    print(result2)

    print("-" * 20)
    print("Test 3: Invalid 'from' currency")
    result3 = await convert_currency(100, "USX", "EUR")
    print(result3)

    print("-" * 20)
    print("Test 4: Invalid 'to' currency")
    result4 = await convert_currency(100, "USD", "EURO")
    print(result4)

    print("-" * 20)
    print("Test 5: Zero amount")
    result5 = await convert_currency(0, "USD", "EUR")
    print(result5)

    print("-" * 20)
    print("Test 6: Negative amount")
    result6 = await convert_currency(-10, "USD", "EUR")
    print(result6)

    # Add more tests if needed

if __name__ == "__main__":
    # Quick check if API key is placeholder
    if not EXCHANGERATE_API_KEY or EXCHANGERATE_API_KEY == "YOUR_API_KEY_HERE":
        print("\n*** WARNING: 'EXCHANGERATE_API_KEY' is not set or is using the placeholder. API calls will fail. ***")
        print("*** Please set the EXCHANGERATE_API_KEY environment variable in your .env file. ***\n")
    else:
        print(f"\n*** Using API key from environment: {EXCHANGERATE_API_KEY[:4]}...{EXCHANGERATE_API_KEY[-4:]} ***\n")

    asyncio.run(main())
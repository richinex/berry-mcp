# packages/mcp-server/src/mcp_server/tools/calendar_tools.py
import os
import base64
import logging
import json
import datetime
from typing import List, Dict, Optional, Any

# Google OAuth/API Libraries
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

# --- Configuration ---

# Load Base64 encoded client config from environment for CALENDAR
# *** USE A DIFFERENT ENV VAR NAME THAN GMAIL'S ***
CLIENT_CONFIG_B64 = os.getenv('MCP_CALENDAR_CLIENT_CONFIG_B64')
# Keep token path configurable or use a default, DIFFERENT from Gmail's token
# *** USE A DIFFERENT TOKEN FILENAME THAN GMAIL'S ***
TOKEN_PATH = os.getenv('MCP_CALENDAR_TOKEN_PATH', 'calendar_token.json')

# Define the scopes needed for Calendar.
# https://developers.google.com/calendar/api/guides/auth
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly', # To view calendars and events
    'https://www.googleapis.com/auth/calendar.events'    # To create, modify, delete events
]

# --- Authentication Helper ---

def get_calendar_service():
    """Gets authenticated Google Calendar API service object using config from env."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            log.debug(f"Loaded Calendar credentials from {TOKEN_PATH}")
        except Exception as e:
            log.warning(f"Failed to load Calendar token file {TOKEN_PATH}: {e}. Need re-authentication.")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                log.info("Refreshing expired Calendar credentials...")
                creds.refresh(Request())
                log.info("Calendar credentials refreshed successfully.")
            except Exception as e:
                log.error(f"Failed to refresh Calendar credentials: {e}. Need full re-authentication.")
                creds = None
        else:
            log.info("No valid Calendar credentials found or need re-authentication. Starting OAuth flow...")
            # --- Load config from environment variable ---
            if not CLIENT_CONFIG_B64:
                log.critical("CRITICAL: Environment variable MCP_CALENDAR_CLIENT_CONFIG_B64 is not set.")
                raise ValueError("Google Calendar client configuration not found in environment variables.")
            try:
                client_config_bytes = base64.b64decode(CLIENT_CONFIG_B64)
                client_config_json = client_config_bytes.decode('utf-8')
                client_config_dict = json.loads(client_config_json)

                flow = InstalledAppFlow.from_client_config(client_config_dict, SCOPES)
                creds = flow.run_local_server(port=0) # Can potentially conflict if run simultaneously with Gmail auth the very first time
                log.info("Calendar OAuth flow completed successfully.")
            except base64.binascii.Error as b64_err:
                 log.critical(f"CRITICAL: Failed to decode Base64 Calendar credentials from env var: {b64_err}")
                 raise ValueError(f"Invalid Base64 data in MCP_CALENDAR_CLIENT_CONFIG_B64: {b64_err}")
            except json.JSONDecodeError as json_err:
                 log.critical(f"CRITICAL: Failed to parse decoded Calendar credentials JSON: {json_err}")
                 raise ValueError(f"Invalid JSON data after decoding MCP_CALENDAR_CLIENT_CONFIG_B64: {json_err}")
            except Exception as e:
                 log.critical(f"CRITICAL: Calendar OAuth flow failed: {e}", exc_info=True)
                 raise ConnectionRefusedError(f"Calendar OAuth authorization failed: {e}")

        if creds:
            try:
                with open(TOKEN_PATH, 'w') as token_file:
                    token_file.write(creds.to_json())
                log.info(f"Calendar credentials saved to {TOKEN_PATH}")
            except Exception as e:
                log.error(f"Failed to save Calendar credentials to {TOKEN_PATH}: {e}")
        else:
             log.error("Calendar credentials object is unexpectedly None after potential auth flow.")

    if not creds:
        log.critical("Could not obtain valid Calendar credentials.")
        raise PermissionError("Failed to get valid Calendar credentials after authentication attempts.")

    try:
        # *** Build the Calendar service, using v3 ***
        service = build('calendar', 'v3', credentials=creds)
        log.debug("Google Calendar API service built successfully.")
        return service
    except Exception as e:
        log.error(f"Failed to build Calendar service: {e}", exc_info=True)
        raise ConnectionError(f"Could not build Calendar service: {e}")

# --- Calendar Tool Functions ---

def list_calendar_events(
    calendar_id: str = 'primary',
    max_results: int = 10,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    query: Optional[str] = None
) -> Dict[str, Any]:
    """
    Lists events from a specified Google Calendar.
    Requires 'calendar.readonly' or 'calendar.events' scope.

    Args:
        calendar_id: Calendar identifier (e.g., 'primary' for the main calendar, or an email address).
        max_results: Maximum number of events to return.
        time_min: Optional start time (ISO 8601 format string, e.g., '2023-10-27T00:00:00Z').
                  If None, defaults to the current time.
        time_max: Optional end time (ISO 8601 format string). If set, filters events ending before this time.
        query: Optional free-text search query.

    Returns:
        A dictionary containing a list of events or an error message.
    """
    log.info(f"Listing calendar events. Calendar: {calendar_id}, Max: {max_results}, TimeMin: {time_min}, TimeMax: {time_max}, Query: '{query or 'None'}'")

    if time_min is None:
        # Default to now if time_min is not provided
        time_min = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time

    try:
        service = get_calendar_service()
        events_result = service.events().list(
            calendarId=calendar_id,
            maxResults=max(1, min(max_results, 250)), # API limits vary, 250 is safe
            timeMin=time_min,
            timeMax=time_max,
            q=query,
            singleEvents=True, # Expand recurring events into single instances
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date')) # Handles all-day events
            end = event['end'].get('dateTime', event['end'].get('date'))
            formatted_events.append({
                'id': event['id'],
                'summary': event.get('summary', '(No Title)'),
                'start': start,
                'end': end,
                'description': event.get('description', ''),
                'location': event.get('location', ''),
                'link': event.get('htmlLink', '')
            })

        log.info(f"Successfully listed {len(formatted_events)} events from calendar '{calendar_id}'.")
        return {"status": "success", "events": formatted_events}

    except HttpError as error:
        log.error(f"An HTTP error occurred listing calendar events: {error}")
        error_details = json.loads(error.content).get('error', {})
        err_msg = error_details.get('message', str(error))
        if error.resp.status == 403:
             err_msg += " (Check if 'calendar.readonly' or 'calendar.events' scope was granted)"
        elif error.resp.status == 404:
             err_msg = f"Calendar with ID '{calendar_id}' not found or insufficient permissions."
        return {"status": "error", "error_type": "HttpError", "code": error.resp.status, "message": err_msg}
    except FileNotFoundError as e: # Should be caught by get_calendar_service, but belt-and-suspenders
         log.error(f"Calendar Tool Configuration Error: {e}")
         return {"status": "error", "error_type": "ConfigurationError", "message": str(e)}
    except (PermissionError, ConnectionRefusedError, ValueError) as e: # Catch auth/config errors from get_calendar_service
         log.error(f"Calendar Tool Authentication/Configuration Error: {e}")
         return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
    except Exception as e:
        log.exception("An unexpected error occurred listing calendar events:")
        return {"status": "error", "error_type": type(e).__name__, "message": str(e)}


def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    calendar_id: str = 'primary',
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    time_zone: str = 'UTC' # Or get from user's system/profile if possible
) -> Dict[str, Any]:
    """
    Creates a new event on a specified Google Calendar.
    Requires 'calendar.events' scope.

    Args:
        summary: The title of the event.
        start_time: Start time (ISO 8601 format string, e.g., '2023-10-28T10:00:00'). Include offset or use time_zone.
        end_time: End time (ISO 8601 format string, e.g., '2023-10-28T11:00:00'). Include offset or use time_zone.
        calendar_id: Calendar identifier (default 'primary').
        description: Optional description of the event.
        location: Optional location of the event.
        attendees: Optional list of attendee email addresses.
        time_zone: The time zone for the start and end times (e.g., 'America/Los_Angeles', 'Europe/Berlin', 'UTC').

    Returns:
        A dictionary containing the details of the created event or an error message.
    """
    log.info(f"Creating calendar event. Calendar: {calendar_id}, Summary: '{summary}', Start: {start_time}, End: {end_time}, TZ: {time_zone}")

    event_body = {
        'summary': summary,
        'start': {
            'dateTime': start_time,
            'timeZone': time_zone,
        },
        'end': {
            'dateTime': end_time,
            'timeZone': time_zone,
        },
    }
    if description:
        event_body['description'] = description
    if location:
        event_body['location'] = location
    if attendees:
        event_body['attendees'] = [{'email': email} for email in attendees]

    # Basic validation (more robust validation could be added)
    try:
        datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        datetime.datetime.fromisoformat(end_time.replace('Z', '+00:00'))
    except ValueError as ve:
        msg = f"Invalid start_time or end_time format. Use ISO 8601 (e.g., 'YYYY-MM-DDTHH:MM:SS' or with timezone 'YYYY-MM-DDTHH:MM:SS+HH:MM'): {ve}"
        log.error(msg)
        return {"status": "error", "error_type": "ValueError", "message": msg}


    try:
        service = get_calendar_service() # Requires calendar.events scope
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event_body
        ).execute()

        event_id = created_event.get('id')
        event_link = created_event.get('htmlLink')
        log.info(f"Successfully created event '{summary}' (ID: {event_id}) in calendar '{calendar_id}'. Link: {event_link}")
        return {
            "status": "success",
            "event_id": event_id,
            "summary": created_event.get('summary'),
            "start": created_event.get('start', {}).get('dateTime'),
            "end": created_event.get('end', {}).get('dateTime'),
            "html_link": event_link
        }

    except HttpError as error:
        log.error(f"An HTTP error occurred creating calendar event: {error}")
        error_details = json.loads(error.content).get('error', {})
        err_msg = error_details.get('message', str(error))
        if error.resp.status == 403:
             err_msg += " (Check if 'calendar.events' scope was granted)"
        elif error.resp.status == 404:
             err_msg = f"Calendar with ID '{calendar_id}' not found or insufficient permissions."
        elif error.resp.status == 400: # Often Bad Request due to time format or missing fields
            err_msg += f" (Bad Request - Check time formats/zone ('{time_zone}') and required fields)"
        return {"status": "error", "error_type": "HttpError", "code": error.resp.status, "message": err_msg}
    except FileNotFoundError as e:
         log.error(f"Calendar Tool Configuration Error: {e}")
         return {"status": "error", "error_type": "ConfigurationError", "message": str(e)}
    except (PermissionError, ConnectionRefusedError, ValueError) as e: # Catch auth/config errors
         log.error(f"Calendar Tool Authentication/Configuration Error: {e}")
         return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
    except Exception as e:
        log.exception("An unexpected error occurred creating calendar event:")
        return {"status": "error", "error_type": type(e).__name__, "message": str(e)}


def delete_calendar_event(
    event_id: str,
    calendar_id: str = 'primary'
) -> Dict[str, Any]:
    """
    Deletes an event from a specified Google Calendar.
    Requires 'calendar.events' scope.

    Args:
        event_id: The ID of the event to delete.
        calendar_id: Calendar identifier (default 'primary').

    Returns:
        A dictionary indicating success or failure.
    """
    log.info(f"Attempting to delete event {event_id} from calendar {calendar_id}.")
    try:
        service = get_calendar_service() # Requires calendar.events scope
        # The delete operation doesn't return a body on success (204 No Content)
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()
        log.info(f"Event {event_id} successfully deleted from calendar {calendar_id}.")
        return {"status": "success", "message": f"Event {event_id} deleted."}

    except HttpError as error:
        log.error(f"An HTTP error occurred deleting event {event_id}: {error}")
        error_details = json.loads(error.content).get('error', {})
        err_msg = error_details.get('message', str(error))
        if error.resp.status == 403:
             err_msg += " (Check if 'calendar.events' scope was granted)"
        elif error.resp.status == 404: # Often means event not found, or calendar ID wrong
             err_msg = f"Event with ID {event_id} not found in calendar {calendar_id}, or insufficient permissions."
        elif error.resp.status == 410: # Gone - Event already deleted
             log.warning(f"Event {event_id} seems to have been already deleted (410 Gone).")
             return {"status": "success", "message": f"Event {event_id} was already deleted."} # Treat as success
        return {"status": "error", "error_type": "HttpError", "code": error.resp.status, "message": err_msg}
    except FileNotFoundError as e:
         log.error(f"Calendar Tool Configuration Error: {e}")
         return {"status": "error", "error_type": "ConfigurationError", "message": str(e)}
    except (PermissionError, ConnectionRefusedError, ValueError) as e: # Catch auth/config errors
         log.error(f"Calendar Tool Authentication/Configuration Error: {e}")
         return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
    except Exception as e:
        log.exception(f"An unexpected error occurred deleting event {event_id}:")
        return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
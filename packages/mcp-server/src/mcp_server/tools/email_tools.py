# packages/mcp-server/src/mcp_server/tools/doc_search_v2.py
import os
import base64
import logging
import json
from email.message import EmailMessage
from typing import List, Dict, Optional, Any

# Google OAuth/API Libraries
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

# --- Configuration ---

# Load Base64 encoded client config from environment
CLIENT_CONFIG_B64 = os.getenv('MCP_GMAIL_CLIENT_CONFIG_B64')
# Keep token path configurable or use a default
TOKEN_PATH = os.getenv('MCP_GMAIL_TOKEN_PATH', 'token.json')

# Define the scopes needed. Must match what you configured in Cloud Console.
# *** IMPORTANT: Added gmail.modify scope for delete/mark read actions ***
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify' # <--- REQUIRED for delete/mark read/unread
]

# --- Authentication Helper ---

def get_gmail_service():
    """Gets authenticated Gmail API service object using config from env."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            log.debug(f"Loaded credentials from {TOKEN_PATH}")
        except Exception as e:
            log.warning(f"Failed to load token file {TOKEN_PATH}: {e}. Need re-authentication.")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                log.info("Refreshing expired Gmail credentials...")
                creds.refresh(Request())
                log.info("Credentials refreshed successfully.")
            except Exception as e:
                log.error(f"Failed to refresh credentials: {e}. Need full re-authentication.")
                creds = None
        else:
            log.info("No valid credentials found or need re-authentication. Starting OAuth flow...")
            # --- Load config from environment variable ---
            if not CLIENT_CONFIG_B64:
                log.critical("CRITICAL: Environment variable MCP_GMAIL_CLIENT_CONFIG_B64 is not set.")
                raise ValueError("Gmail client configuration not found in environment variables.")
            try:
                # Decode Base64 -> Bytes -> JSON String -> Dict
                client_config_bytes = base64.b64decode(CLIENT_CONFIG_B64)
                client_config_json = client_config_bytes.decode('utf-8')
                client_config_dict = json.loads(client_config_json)

                # *** Use from_client_config instead of from_client_secrets_file ***
                flow = InstalledAppFlow.from_client_config(client_config_dict, SCOPES)
                creds = flow.run_local_server(port=0)
                log.info("OAuth flow completed successfully.")
            except base64.binascii.Error as b64_err:
                 log.critical(f"CRITICAL: Failed to decode Base64 credentials from env var: {b64_err}")
                 raise ValueError(f"Invalid Base64 data in MCP_GMAIL_CLIENT_CONFIG_B64: {b64_err}")
            except json.JSONDecodeError as json_err:
                 log.critical(f"CRITICAL: Failed to parse decoded credentials JSON: {json_err}")
                 raise ValueError(f"Invalid JSON data after decoding MCP_GMAIL_CLIENT_CONFIG_B64: {json_err}")
            except Exception as e:
                 log.critical(f"CRITICAL: OAuth flow failed: {e}", exc_info=True)
                 raise ConnectionRefusedError(f"OAuth authorization failed: {e}")

        if creds:
            try:
                with open(TOKEN_PATH, 'w') as token_file:
                    token_file.write(creds.to_json())
                log.info(f"Credentials saved to {TOKEN_PATH}")
            except Exception as e:
                log.error(f"Failed to save credentials to {TOKEN_PATH}: {e}")
        else:
             log.error("Credentials object is unexpectedly None after potential auth flow.")

    if not creds:
        log.critical("Could not obtain valid Gmail credentials.")
        raise PermissionError("Failed to get valid Gmail credentials after authentication attempts.")

    try:
        service = build('gmail', 'v1', credentials=creds)
        log.debug("Gmail API service built successfully.")
        return service
    except Exception as e:
        log.error(f"Failed to build Gmail service: {e}", exc_info=True)
        raise ConnectionError(f"Could not build Gmail service: {e}")

# --- Email Tool Functions ---

def send_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    """
    Sends an email using the authenticated Gmail account.
    Requires 'gmail.send' scope.

    Args:
        to: The recipient's email address.
        subject: The subject line of the email.
        body: The plain text body of the email.

    Returns:
        A dictionary containing the status and sent message ID or an error.
    """
    log.info(f"Attempting to send email. To: {to}, Subject: '{subject}'")
    try:
        service = get_gmail_service()
        message = EmailMessage()
        message.set_content(body)
        message['To'] = to
        message['From'] = 'me'
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        send_message = service.users().messages().send(userId='me', body=create_message).execute()
        sent_id = send_message.get('id')
        log.info(f"Email sent successfully. Message ID: {sent_id}")
        return {"status": "success", "message_id": sent_id, "thread_id": send_message.get('threadId')}

    except HttpError as error:
        log.error(f"An HTTP error occurred sending email: {error}")
        error_details = json.loads(error.content).get('error', {})
        err_msg = error_details.get('message', str(error))
        # Check for specific permission error
        if error.resp.status == 403:
             err_msg += " (Check if 'gmail.send' scope was granted)"
        return {"status": "error", "error_type": "HttpError", "code": error.resp.status, "message": err_msg}
    except FileNotFoundError as e:
         log.error(f"Email Tool Configuration Error: {e}")
         return {"status": "error", "error_type": "ConfigurationError", "message": str(e)}
    except (PermissionError, ConnectionRefusedError, ValueError) as e: # Catch auth/config errors
         log.error(f"Email Tool Authentication/Configuration Error: {e}")
         return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
    except Exception as e:
        log.exception("An unexpected error occurred sending email:")
        return {"status": "error", "error_type": type(e).__name__, "message": str(e)}


def read_emails(
    query: Optional[str] = None,
    max_results: int = 5,
    folder_label_ids: Optional[List[str]] = None,
    include_body_snippet: bool = True
) -> Dict[str, Any]:
    """
    Reads emails from the authenticated Gmail account, optionally filtering them.
    Requires 'gmail.readonly' scope.

    Args:
        query: Optional search query (like in Gmail search box, e.g., 'from:boss subject:urgent').
        max_results: Maximum number of emails to return.
        folder_label_ids: Optional list of label IDs to filter by (e.g., ["INBOX", "UNREAD"]). Common IDs: 'INBOX', 'SENT', 'SPAM', 'TRASH', 'UNREAD', 'STARRED'.
        include_body_snippet: Whether to include a short snippet of the body.

    Returns:
        A dictionary containing a list of emails or an error.
    """
    if folder_label_ids is None:
        folder_label_ids = ["INBOX"]

    log.info(f"Reading emails. Query: '{query or 'None'}', Max: {max_results}, Labels: {folder_label_ids}")
    emails_list = []
    try:
        service = get_gmail_service() # Requires readonly scope

        list_kwargs = {
            "userId": 'me',
            "maxResults": max(1, min(max_results, 50)),
            "labelIds": folder_label_ids
        }
        if query:
            list_kwargs["q"] = query

        results = service.users().messages().list(**list_kwargs).execute()
        messages = results.get('messages', [])

        if not messages:
            log.info("No messages found matching the criteria.")
            return {"status": "success", "emails": []}

        log.debug(f"Found {len(messages)} message IDs. Fetching details...")

        for msg_ref in messages:
            msg_id = msg_ref['id']
            get_kwargs = {"userId": 'me', "id": msg_id, "format": 'metadata', "metadataHeaders": ['Subject', 'From', 'To', 'Date']}
            msg = service.users().messages().get(**get_kwargs).execute()

            email_data = {"id": msg.get('id'), "thread_id": msg.get('threadId')}
            headers = msg.get('payload', {}).get('headers', [])
            header_map = {h['name'].lower(): h['value'] for h in headers}

            email_data['subject'] = header_map.get('subject', '')
            email_data['from'] = header_map.get('from', '')
            email_data['to'] = header_map.get('to', '')
            email_data['date'] = header_map.get('date', '')
            email_data['labels'] = msg.get('labelIds', [])

            if include_body_snippet:
                email_data['snippet'] = msg.get('snippet', '')

            emails_list.append(email_data)

        log.info(f"Successfully read details for {len(emails_list)} emails.")
        return {"status": "success", "emails": emails_list}

    except HttpError as error:
        log.error(f"An HTTP error occurred reading emails: {error}")
        error_details = json.loads(error.content).get('error', {})
        err_msg = error_details.get('message', str(error))
        if error.resp.status == 403:
             err_msg += " (Check if 'gmail.readonly' scope was granted)"
        return {"status": "error", "error_type": "HttpError", "code": error.resp.status, "message": err_msg}
    except FileNotFoundError as e:
         log.error(f"Email Tool Configuration Error: {e}")
         return {"status": "error", "error_type": "ConfigurationError", "message": str(e)}
    except (PermissionError, ConnectionRefusedError, ValueError) as e:
         log.error(f"Email Tool Authentication/Configuration Error: {e}")
         return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
    except Exception as e:
        log.exception("An unexpected error occurred reading emails:")
        return {"status": "error", "error_type": type(e).__name__, "message": str(e)}


# --- NEW FUNCTIONS ---

def delete_email(message_id: str) -> Dict[str, Any]:
    """
    Moves the specified email to the trash.
    Requires 'gmail.modify' scope.

    Args:
        message_id: The ID of the email message to move to trash.

    Returns:
        A dictionary indicating success or failure.
    """
    log.info(f"Attempting to move email {message_id} to trash.")
    try:
        service = get_gmail_service() # Requires modify scope
        # Use trash() instead of delete() for safety (moves to bin)
        service.users().messages().trash(userId='me', id=message_id).execute()
        log.info(f"Email {message_id} successfully moved to trash.")
        return {"status": "success", "message": f"Email {message_id} moved to trash."}

    except HttpError as error:
        log.error(f"An HTTP error occurred deleting email {message_id}: {error}")
        error_details = json.loads(error.content).get('error', {})
        err_msg = error_details.get('message', str(error))
        if error.resp.status == 403:
             err_msg += " (Check if 'gmail.modify' scope was granted)"
        elif error.resp.status == 404:
             err_msg = f"Email with ID {message_id} not found."
        return {"status": "error", "error_type": "HttpError", "code": error.resp.status, "message": err_msg}
    except FileNotFoundError as e:
         log.error(f"Email Tool Configuration Error: {e}")
         return {"status": "error", "error_type": "ConfigurationError", "message": str(e)}
    except (PermissionError, ConnectionRefusedError, ValueError) as e:
         log.error(f"Email Tool Authentication/Configuration Error: {e}")
         return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
    except Exception as e:
        log.exception(f"An unexpected error occurred deleting email {message_id}:")
        return {"status": "error", "error_type": type(e).__name__, "message": str(e)}


def mark_email_read(message_id: str) -> Dict[str, Any]:
    """
    Marks the specified email as read by removing the 'UNREAD' label.
    Requires 'gmail.modify' scope.

    Args:
        message_id: The ID of the email message to mark as read.

    Returns:
        A dictionary indicating success or failure.
    """
    log.info(f"Attempting to mark email {message_id} as read.")
    try:
        service = get_gmail_service() # Requires modify scope
        # To mark as read, we remove the 'UNREAD' label
        body = {'removeLabelIds': ['UNREAD']}
        service.users().messages().modify(userId='me', id=message_id, body=body).execute()
        log.info(f"Email {message_id} successfully marked as read.")
        return {"status": "success", "message": f"Email {message_id} marked as read."}

    except HttpError as error:
        log.error(f"An HTTP error occurred marking email {message_id} as read: {error}")
        error_details = json.loads(error.content).get('error', {})
        err_msg = error_details.get('message', str(error))
        if error.resp.status == 403:
             err_msg += " (Check if 'gmail.modify' scope was granted)"
        elif error.resp.status == 404:
             err_msg = f"Email with ID {message_id} not found."
        return {"status": "error", "error_type": "HttpError", "code": error.resp.status, "message": err_msg}
    except FileNotFoundError as e:
         log.error(f"Email Tool Configuration Error: {e}")
         return {"status": "error", "error_type": "ConfigurationError", "message": str(e)}
    except (PermissionError, ConnectionRefusedError, ValueError) as e:
         log.error(f"Email Tool Authentication/Configuration Error: {e}")
         return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
    except Exception as e:
        log.exception(f"An unexpected error occurred marking email {message_id} as read:")
        return {"status": "error", "error_type": type(e).__name__, "message": str(e)}


def mark_email_unread(message_id: str) -> Dict[str, Any]:
    """
    Marks the specified email as unread by adding the 'UNREAD' label.
    Requires 'gmail.modify' scope.

    Args:
        message_id: The ID of the email message to mark as unread.

    Returns:
        A dictionary indicating success or failure.
    """
    log.info(f"Attempting to mark email {message_id} as unread.")
    try:
        service = get_gmail_service() # Requires modify scope
        # To mark as unread, we add the 'UNREAD' label
        body = {'addLabelIds': ['UNREAD']}
        service.users().messages().modify(userId='me', id=message_id, body=body).execute()
        log.info(f"Email {message_id} successfully marked as unread.")
        return {"status": "success", "message": f"Email {message_id} marked as unread."}

    except HttpError as error:
        log.error(f"An HTTP error occurred marking email {message_id} as unread: {error}")
        error_details = json.loads(error.content).get('error', {})
        err_msg = error_details.get('message', str(error))
        if error.resp.status == 403:
             err_msg += " (Check if 'gmail.modify' scope was granted)"
        elif error.resp.status == 404:
             err_msg = f"Email with ID {message_id} not found."
        return {"status": "error", "error_type": "HttpError", "code": error.resp.status, "message": err_msg}
    except FileNotFoundError as e:
         log.error(f"Email Tool Configuration Error: {e}")
         return {"status": "error", "error_type": "ConfigurationError", "message": str(e)}
    except (PermissionError, ConnectionRefusedError, ValueError) as e:
         log.error(f"Email Tool Authentication/Configuration Error: {e}")
         return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
    except Exception as e:
        log.exception(f"An unexpected error occurred marking email {message_id} as unread:")
        return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
"""Google Sheets integration for fetching whitelist data."""

import logging
from typing import List, Dict, Any

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config import SHEET_ID, GOOGLE_CREDS_PATH

logger = logging.getLogger(__name__)

# Google Sheets API scopes
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def fetch_whitelist_rows() -> List[Dict[str, Any]]:
    """
    Fetch all rows from the whitelist Google Sheet.

    Returns a list of dicts, one per row, with column headers as keys.
    Returns empty list on error.
    """
    try:
        if not GOOGLE_CREDS_PATH.exists():
            logger.error(f"Google credentials file not found: {GOOGLE_CREDS_PATH}")
            return []

        if not SHEET_ID:
            logger.error("SHEET_ID not configured")
            return []

        creds = ServiceAccountCredentials.from_json_keyfile_name(
            str(GOOGLE_CREDS_PATH), SCOPES
        )
        client = gspread.authorize(creds)

        sheet = client.open_by_key(SHEET_ID)
        worksheet = sheet.get_worksheet(0)  # First worksheet

        # Get all records as list of dicts
        records = worksheet.get_all_records()
        logger.info(f"Fetched {len(records)} rows from Google Sheets")
        return records

    except gspread.exceptions.APIError as e:
        logger.error(f"Google Sheets API error: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching from Google Sheets: {e}")
        return []

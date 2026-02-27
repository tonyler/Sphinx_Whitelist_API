"""Configuration module - loads environment variables."""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file from whitelist-api directory
load_dotenv()

# Discord bot token for API calls
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# Google Sheets ID to sync from
SHEET_ID = os.getenv("SHEET_ID", "")

# Discord guild ID for member lookups
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")

# API key for authenticating requests
API_KEY = os.getenv("API_KEY", "")

# Port to run the API server on
PORT = int(os.getenv("PORT", "8002"))

# Path to Google service account credentials (relative to whitelist-api/)
GOOGLE_CREDS_PATH = Path(
    os.getenv("GOOGLE_CREDS_PATH", str(Path(__file__).parent.parent / "google.json"))
)


def validate_config() -> None:
    """Validate required configuration at startup. Raises RuntimeError if invalid."""
    missing = []

    if not DISCORD_TOKEN:
        missing.append("DISCORD_TOKEN")
    if not SHEET_ID:
        missing.append("SHEET_ID")
    if not DISCORD_GUILD_ID:
        missing.append("DISCORD_GUILD_ID")
    if not API_KEY:
        missing.append("API_KEY")
    if not GOOGLE_CREDS_PATH.exists():
        missing.append(f"GOOGLE_CREDS_PATH (file not found: {GOOGLE_CREDS_PATH})")

    if missing:
        raise RuntimeError(f"Missing required configuration: {', '.join(missing)}")

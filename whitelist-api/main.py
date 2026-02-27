"""FastAPI application for whitelist verification."""

import hmac
import logging
from logging.handlers import RotatingFileHandler
import re
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware

from config import API_KEY, PORT, validate_config
from cache import lookup, cache_size
from stats import stats
from scheduler import start_scheduler
from discord_resolver import close_http_client

# Configure logging with rotation (5 MB per file, keep 3 backups)
_log_handler = RotatingFileHandler(
    "/tmp/whitelist-api.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
)
_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])
logger = logging.getLogger(__name__)

# Discord ID validation pattern (17-19 digit snowflake)
DISCORD_ID_PATTERN = re.compile(r'^\d{17,19}$')

# Global scheduler reference
scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    global scheduler

    # Validate configuration before starting
    logger.info("Validating configuration...")
    validate_config()

    logger.info("Starting whitelist verification API...")
    scheduler = start_scheduler()
    yield
    logger.info("Shutting down...")
    if scheduler:
        scheduler.shutdown(wait=False)
    close_http_client()


app = FastAPI(
    title="Whitelist Verification API",
    description="API for verifying Discord users against a whitelist for Galxe/Taskon",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for Galxe dashboard compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dashboard.galxe.com",
        "https://app.galxe.com",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def verify_api_key(authorization: Optional[str] = Header(None)) -> bool:
    """Verify the API key from Authorization header."""
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Expected format: "Bearer <API_KEY>"
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization format")

    # Timing-safe comparison
    if not hmac.compare_digest(parts[1], API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return True


@app.get("/health")
async def health():
    """Health check endpoint - no auth required."""
    s = stats.to_dict()
    return {
        "status": "healthy",
        "cache_size": cache_size(),
        "last_sync_at": s.get("last_sync_at"),
        "last_sheet_change_at": s.get("last_sheet_change_at"),
    }


@app.get("/check")
async def check_discord_id(
    discord_id: str = Query(..., description="Discord user ID to verify"),
    authorization: Optional[str] = Header(None),
):
    """
    Check if a Discord ID is in the whitelist.

    Returns {"isValid": true/false} for Galxe/Taskon compatibility.
    """
    verify_api_key(authorization)

    discord_id = discord_id.strip()

    if not discord_id:
        raise HTTPException(status_code=400, detail="discord_id is required")

    if not DISCORD_ID_PATTERN.match(discord_id):
        raise HTTPException(status_code=400, detail="Invalid discord_id format (must be 17-19 digits)")

    entry = lookup(discord_id)
    is_valid = entry is not None

    stats.record_check(is_valid)
    logger.info(f"Check discord_id={discord_id} isValid={is_valid}")

    return {"isValid": is_valid}


@app.get("/stats")
async def get_stats(authorization: Optional[str] = Header(None)):
    """Get API statistics - requires auth."""
    verify_api_key(authorization)

    return {
        **stats.to_dict(),
        "cache_size": cache_size(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)

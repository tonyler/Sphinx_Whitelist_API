"""Background scheduler for syncing whitelist data."""

import hashlib
import logging
from typing import Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler

from sheets import fetch_whitelist_rows
from discord_resolver import fetch_all_guild_members, resolve_from_lookup
from cache import update_cache, cache_size
from stats import stats

logger = logging.getLogger(__name__)

# Hash of the last seen sheet handles — used to skip Discord fetch when nothing changed
_last_sheet_hash: str = ""

# Column names in the Google Sheet
DISCORD_HANDLE_COL = "Discord Handle"
EMAIL_COL = "Email"
TWITTER_COL = "Twitter"
TELEGRAM_COL = "Telegram"
COMPANY_COL = "Company"
SUBSCRIBED_COL = "Subscribed"


def _hash_handles(rows: list) -> str:
    """Return a stable hash of the Discord handles in the sheet rows."""
    handles = sorted(
        str(row.get(DISCORD_HANDLE_COL, "")).strip().lower()
        for row in rows
        if row.get(DISCORD_HANDLE_COL, "")
    )
    return hashlib.sha256("\n".join(handles).encode()).hexdigest()


def sync_whitelist() -> None:
    """
    Sync whitelist from Google Sheets.

    1. Fetch rows from sheets
    2. Hash Discord handles — skip Discord fetch if unchanged
    3. Resolve Discord handles to IDs
    4. Build new cache dict and atomically replace

    On sheet fetch error, keeps existing cache.
    """
    global _last_sheet_hash

    logger.info("Starting whitelist sync...")

    rows = fetch_whitelist_rows()

    if not rows:
        logger.warning("No rows fetched from sheet, keeping existing cache")
        return

    sheet_hash = _hash_handles(rows)
    if sheet_hash == _last_sheet_hash:
        logger.info("Sheet unchanged, skipping Discord fetch")
        stats.record_sync(sheet_changed=False)
        return

    # --- Bulk fetch all guild members (primary strategy) ---
    member_lookup, member_count = fetch_all_guild_members()
    if member_count > 0:
        logger.info(f"Bulk fetch succeeded: {member_count} members in lookup")
    else:
        logger.warning("Bulk fetch unavailable — will use per-handle search fallback for all entries")

    new_cache: Dict[str, Dict[str, Any]] = {}
    resolved_count = 0
    failed_count = 0
    total_with_handle = 0

    for row in rows:
        discord_handle = row.get(DISCORD_HANDLE_COL, "")

        if not discord_handle:
            continue

        total_with_handle += 1
        discord_id = resolve_from_lookup(str(discord_handle), member_lookup)

        if not discord_id:
            failed_count += 1
            continue

        resolved_count += 1

        # Build entry with user data
        new_cache[discord_id] = {
            "email": row.get(EMAIL_COL, ""),
            "twitter": row.get(TWITTER_COL, ""),
            "telegram": row.get(TELEGRAM_COL, ""),
            "company": row.get(COMPANY_COL, ""),
            "subscribed": row.get(SUBSCRIBED_COL, ""),
            "discord_handle": discord_handle,
        }

    # Atomically replace cache and persist hash
    update_cache(new_cache)
    _last_sheet_hash = sheet_hash
    stats.record_sync(sheet_changed=True)

    logger.info(
        f"Sync complete: {resolved_count} resolved, "
        f"{failed_count} not in server, cache size: {cache_size()}"
    )


def create_scheduler() -> BackgroundScheduler:
    """Create and configure the background scheduler."""
    scheduler = BackgroundScheduler()

    # Run sync every 30 seconds
    scheduler.add_job(
        sync_whitelist,
        "interval",
        seconds=60,
        id="whitelist_sync",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping syncs
        coalesce=True,    # Skip missed runs
    )

    return scheduler


def start_scheduler() -> BackgroundScheduler:
    """Start the scheduler and run initial sync."""
    scheduler = create_scheduler()
    scheduler.start()

    # Run sync immediately on startup
    logger.info("Running initial whitelist sync...")
    sync_whitelist()

    return scheduler

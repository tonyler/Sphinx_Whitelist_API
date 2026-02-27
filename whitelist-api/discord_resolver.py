"""Discord handle to ID resolution — bulk member fetch + search fallback."""

import logging
import time
from typing import Dict, Optional, Tuple

import httpx

from config import DISCORD_TOKEN, DISCORD_GUILD_ID
from stats import stats

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"

# Rate limiting config
MAX_RETRIES = 3
BULK_FETCH_DELAY = 0.5   # 500ms between bulk-fetch pages
SEARCH_DELAY = 0.5       # 500ms between search requests
REQUEST_TIMEOUT = 10.0   # 10 second timeout

# Module-level HTTP client for connection pooling
_http_client: Optional[httpx.Client] = None


def get_http_client() -> httpx.Client:
    """Get or create the HTTP client with connection pooling."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(timeout=REQUEST_TIMEOUT)
    return _http_client


def close_http_client() -> None:
    """Close the HTTP client. Call on shutdown."""
    global _http_client
    if _http_client and not _http_client.is_closed:
        _http_client.close()
        _http_client = None


def normalize_handle(handle: str) -> str:
    """
    Normalize a Discord handle for comparison.

    - Strips leading @
    - Strips legacy #discriminator suffix
    - Lowercases + strips whitespace
    """
    handle = handle.strip().lstrip("@")
    if "#" in handle:
        handle = handle.split("#")[0]
    return handle.lower().strip()


def build_member_lookup(members: list) -> Dict[str, str]:
    """
    Build a name → discord_id lookup dict from a list of member objects.

    Indexes every name variant so any of them resolves to the user's ID:
      - user.username  (unique login handle, e.g. "alice")
      - user.global_name  (display name, e.g. "Alice Smith")
      - member.nick  (server nickname, e.g. "alice | acme")

    All keys are lowercased for case-insensitive O(1) lookups.
    Later entries overwrite earlier ones on collision — acceptable trade-off.
    """
    lookup: Dict[str, str] = {}
    for member in members:
        user = member.get("user", {})
        discord_id = user.get("id")
        if not discord_id:
            continue

        for name in (
            user.get("username"),
            user.get("global_name"),
            member.get("nick"),
        ):
            if name:
                lookup[name.lower().strip()] = discord_id

    return lookup


def fetch_all_guild_members() -> Tuple[Dict[str, str], int]:
    """
    Fetch every member of the guild using paginated GET /guilds/{id}/members.

    Returns (lookup_dict, total_count) where lookup_dict maps lowered name
    variants to discord_id.  Returns ({}, 0) on failure (e.g. 403 = bot lacks
    GUILD_MEMBERS privileged intent — caller should fall back to search).
    """
    if not DISCORD_TOKEN or not DISCORD_GUILD_ID:
        logger.warning("Discord credentials not configured — skipping bulk fetch")
        return {}, 0

    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json",
    }

    client = get_http_client()
    all_members: list = []
    after: Optional[str] = None  # pagination cursor (last member ID seen)
    page = 0

    while True:
        params: Dict[str, object] = {"limit": 1000}
        if after:
            params["after"] = after

        url = f"{DISCORD_API_BASE}/guilds/{DISCORD_GUILD_ID}/members"

        for attempt in range(MAX_RETRIES):
            try:
                time.sleep(BULK_FETCH_DELAY)
                response = client.get(url, headers=headers, params=params)

                if response.status_code == 429:
                    retry_after = float(response.json().get("retry_after", 1))
                    logger.warning(
                        f"Bulk fetch rate-limited (page {page}, attempt {attempt + 1}), "
                        f"waiting {retry_after}s"
                    )
                    time.sleep(retry_after)
                    continue

                if response.status_code == 403:
                    logger.warning(
                        "Bulk member fetch returned 403 — bot likely missing "
                        "GUILD_MEMBERS privileged intent; will use search fallback"
                    )
                    return {}, 0

                if response.status_code != 200:
                    logger.error(
                        f"Bulk fetch error (page {page}): {response.status_code} — {response.text}"
                    )
                    return {}, 0

                page_members = response.json()
                break  # successful response — exit retry loop

            except httpx.TimeoutException:
                logger.warning(f"Bulk fetch timeout (page {page}, attempt {attempt + 1})")
                if attempt == MAX_RETRIES - 1:
                    logger.error("Bulk fetch failed after max retries (timeout)")
                    return {}, 0
            except httpx.RequestError as exc:
                logger.error(f"Bulk fetch request error: {exc}")
                return {}, 0
            except Exception as exc:
                logger.error(f"Unexpected error during bulk fetch: {exc}")
                return {}, 0
        else:
            # All retries exhausted (only reached if loop didn't break)
            logger.error("Bulk fetch exhausted retries without a successful response")
            return {}, 0

        all_members.extend(page_members)
        page += 1

        if len(page_members) < 1000:
            # Last page — no more members
            break

        # Advance cursor to the last member ID in this page
        after = page_members[-1]["user"]["id"]

    total = len(all_members)
    lookup = build_member_lookup(all_members)
    logger.info(f"Fetched {total} guild members across {page} page(s), built lookup with {len(lookup)} entries")
    return lookup, total


def resolve_from_lookup(handle: str, lookup: Dict[str, str]) -> Optional[str]:
    """
    Resolve a handle using the pre-built bulk-fetch lookup dict.

    Returns discord_id string or None.
    """
    if not handle or not lookup:
        return None
    key = normalize_handle(handle)
    return lookup.get(key)


def resolve_via_search(handle: str) -> Optional[str]:
    """
    Resolve a Discord handle via the guild member search endpoint.

    Fallback for when bulk fetch is unavailable or the handle wasn't found
    in the bulk lookup.  Fetches up to 10 candidates and checks all of them
    against username, global_name, and nick — not just the first result.

    Returns discord_id string or None.
    """
    if not DISCORD_TOKEN or not DISCORD_GUILD_ID:
        logger.warning("Discord credentials not configured")
        return None

    if not handle or not handle.strip():
        return None

    normalized = normalize_handle(handle)
    if not normalized:
        return None

    url = f"{DISCORD_API_BASE}/guilds/{DISCORD_GUILD_ID}/members/search"
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json",
    }
    params = {"query": normalized, "limit": 10}

    client = get_http_client()

    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(SEARCH_DELAY)
            response = client.get(url, headers=headers, params=params)

            if response.status_code == 429:
                retry_after = float(response.json().get("retry_after", 1))
                logger.warning(
                    f"Search rate-limited for '{normalized}' (attempt {attempt + 1}), "
                    f"waiting {retry_after}s"
                )
                time.sleep(retry_after)
                continue

            if response.status_code != 200:
                logger.error(f"Discord search error for '{normalized}': {response.status_code} — {response.text}")
                stats.record_resolve_error()
                return None

            members = response.json()

            if not members:
                logger.debug(f"Search returned no results for handle: '{normalized}'")
                return None

            # Check all candidates — not just the first one
            for member in members:
                user = member.get("user", {})
                discord_id = user.get("id")
                if not discord_id:
                    continue

                candidates = [
                    user.get("username", ""),
                    user.get("global_name") or "",
                    member.get("nick") or "",
                ]

                for candidate in candidates:
                    if candidate and candidate.lower().strip() == normalized:
                        logger.debug(f"Search resolved '{normalized}' -> {discord_id} (via '{candidate}')")
                        return discord_id

            logger.debug(
                f"Search found {len(members)} candidate(s) but none matched '{normalized}'"
            )
            return None

        except httpx.TimeoutException:
            logger.warning(f"Discord search timeout for '{normalized}' (attempt {attempt + 1})")
            if attempt == MAX_RETRIES - 1:
                stats.record_resolve_error()
                return None
        except httpx.RequestError as exc:
            logger.error(f"Discord search request error for '{normalized}': {exc}")
            stats.record_resolve_error()
            return None
        except Exception as exc:
            logger.error(f"Unexpected error resolving '{normalized}': {exc}")
            stats.record_resolve_error()
            return None

    stats.record_resolve_error()
    return None

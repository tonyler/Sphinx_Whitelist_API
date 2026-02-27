"""Thread-safe cache for whitelist data."""

import copy
import threading
from typing import Dict, Any, Optional

# Module-level cache storage
# Key: discord_id (str), Value: dict with email, twitter, telegram, company, subscribed
_whitelist: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def update_cache(new_dict: Dict[str, Dict[str, Any]]) -> None:
    """Atomically replace the entire cache with new data (deep copy)."""
    global _whitelist
    with _lock:
        _whitelist = copy.deepcopy(new_dict)


def get_cache() -> Dict[str, Dict[str, Any]]:
    """Get a deep copy of the current cache."""
    with _lock:
        return copy.deepcopy(_whitelist)


def lookup(discord_id: str) -> Optional[Dict[str, Any]]:
    """Look up a single discord_id in the cache. Returns a copy."""
    with _lock:
        entry = _whitelist.get(discord_id)
        return entry.copy() if entry else None


def cache_size() -> int:
    """Return the number of entries in the cache."""
    with _lock:
        return len(_whitelist)

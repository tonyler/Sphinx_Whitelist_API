"""Statistics tracking for the API."""

import threading
from datetime import datetime
from typing import Dict, Any


class Stats:
    """Thread-safe statistics tracker."""

    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = datetime.utcnow()
        self.last_sync_at: datetime | None = None
        self.total_checks = 0
        self.valid_hits = 0
        self.invalid_hits = 0
        self.discord_resolve_errors = 0
        self.total_syncs = 0

    def record_check(self, is_valid: bool) -> None:
        """Record a verification check."""
        with self._lock:
            self.total_checks += 1
            if is_valid:
                self.valid_hits += 1
            else:
                self.invalid_hits += 1

    def record_resolve_error(self) -> None:
        """Record a Discord resolution error."""
        with self._lock:
            self.discord_resolve_errors += 1

    def record_sync(self) -> None:
        """Record a successful sync."""
        with self._lock:
            self.last_sync_at = datetime.utcnow()
            self.total_syncs += 1

    def to_dict(self) -> Dict[str, Any]:
        """Return stats as a dictionary."""
        with self._lock:
            return {
                "start_time": self.start_time.isoformat(),
                "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
                "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
                "total_checks": self.total_checks,
                "valid_hits": self.valid_hits,
                "invalid_hits": self.invalid_hits,
                "discord_resolve_errors": self.discord_resolve_errors,
                "total_syncs": self.total_syncs,
            }


# Global stats instance
stats = Stats()

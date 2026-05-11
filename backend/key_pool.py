"""Multi-key pool with round-robin rotation and health tracking.

Provides KeyPool - manages multiple API keys per provider, automatically
skipping rate-limited or failed keys so the application keeps working even
when individual keys are exhausted.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class KeyEntry:
    key: str
    label: str = ""
    cooldown_until: float = 0.0
    consecutive_failures: int = 0
    disabled: bool = False
    total_uses: int = 0
    total_failures: int = 0


class KeyPool:
    """Round-robin key pool with per-key health tracking and cooldown."""

    def __init__(
        self,
        keys: list[str],
        *,
        cooldown_sec: float = 60.0,
        max_failures: int = 3,
    ) -> None:
        if not keys:
            raise ValueError("KeyPool requires at least one key")
        self._entries = [
            KeyEntry(key=k, label=f"key-{i + 1}") for i, k in enumerate(keys)
        ]
        self._cooldown_sec = cooldown_sec
        self._max_failures = max_failures
        self._index: int = 0
        self._lock = asyncio.Lock()
        self._last_hint: str | None = None  # label of most recently returned key

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    async def acquire(self) -> str:
        """Return the next healthy key, waiting if all keys are unavailable."""
        while True:
            async with self._lock:
                now = time.monotonic()
                # Expire cooldowns that have elapsed.
                for e in self._entries:
                    if e.cooldown_until > 0 and now >= e.cooldown_until:
                        e.cooldown_until = 0.0
                        logger.info("Key %s cooldown expired", e.label)

                available = [e for e in self._entries if not e.disabled and e.cooldown_until <= now]
                if available:
                    # Round-robin: find the next healthy key, then advance.
                    for offset in range(len(self._entries)):
                        candidate = self._entries[(self._index + offset) % len(self._entries)]
                        if not candidate.disabled and candidate.cooldown_until <= now:
                            self._index = (self._index + offset + 1) % len(self._entries)
                            candidate.total_uses += 1
                            self._last_hint = candidate.label
                            return candidate.key

                # No key is available - compute the soonest cooldown expiry.
                cooldowns = [e.cooldown_until for e in self._entries if e.cooldown_until > now and not e.disabled]
                if cooldowns:
                    wait = min(cooldowns) - now + 0.5
                    logger.warning("All %d keys in cooldown, waiting %.1fs", len(self._entries), wait)
                else:
                    wait = 5.0
                    logger.error("All %d keys are disabled or unavailable", len(self._entries))

            await asyncio.sleep(wait)

    def report_result(self, key: str, *, success: bool, http_status: int | None = None) -> None:
        """Update health state after an API call completes."""
        entry = self._find(key)
        if entry is None:
            return

        if success:
            entry.consecutive_failures = 0
            return

        entry.total_failures += 1
        entry.consecutive_failures += 1

        if http_status == 429:
            # Rate-limited - exponential cooldown.
            delay = self._cooldown_sec * (2 ** (entry.consecutive_failures - 1))
            entry.cooldown_until = time.monotonic() + delay
            logger.warning(
                "Key %s rate-limited (429), cooldown %.0fs (failure #%d)",
                entry.label, delay, entry.consecutive_failures,
            )
        elif http_status in (401, 403):
            # Auth error - permanently disable (until config reload).
            entry.disabled = True
            logger.error(
                "Key %s disabled due to auth error (HTTP %d)",
                entry.label, http_status,
            )
        elif entry.consecutive_failures >= self._max_failures:
            # Too many consecutive non-rate-limit failures - cool down.
            entry.cooldown_until = time.monotonic() + self._cooldown_sec
            logger.warning(
                "Key %s cooled down after %d consecutive failures",
                entry.label, entry.consecutive_failures,
            )
        # For other transient failures (502, 503, 504), don't penalise
        # the key - those are upstream issues, not key-specific.

    # ------------------------------------------------------------------
    # introspection
    # ------------------------------------------------------------------

    @property
    def available_count(self) -> int:
        now = time.monotonic()
        return sum(1 for e in self._entries if not e.disabled and e.cooldown_until <= now)

    @property
    def total_count(self) -> int:
        return len(self._entries)

    @property
    def last_hint(self) -> str | None:
        """Label of the key most recently returned by acquire()."""
        return self._last_hint

    def status(self) -> dict:
        """Return a summary for admin/monitoring."""
        now = time.monotonic()
        keys_status = []
        for e in self._entries:
            state = "disabled" if e.disabled else ("cooldown" if e.cooldown_until > now else "active")
            keys_status.append({
                "label": e.label,
                "state": state,
                "total_uses": e.total_uses,
                "total_failures": e.total_failures,
                "cooldown_remaining_sec": max(0.0, e.cooldown_until - now) if e.cooldown_until > now else 0.0,
            })
        return {
            "total": self.total_count,
            "available": self.available_count,
            "keys": keys_status,
        }

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _find(self, key: str) -> KeyEntry | None:
        for e in self._entries:
            if e.key == key:
                return e
        return None

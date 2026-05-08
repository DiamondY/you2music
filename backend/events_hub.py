from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserEventHub:
    """In-process pub/sub for per-user realtime events (FastAPI mode).

    This is intentionally simple: one process, in-memory fanout. It enables
    SSE/WebSocket style updates across multiple browser tabs/devices logged in
    as the same user.
    """

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _subs: dict[int, set[asyncio.Queue[dict[str, Any]]]] = field(default_factory=dict)

    async def subscribe(self, user_id: int, *, max_queue: int = 200) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue)
        async with self._lock:
            self._subs.setdefault(int(user_id), set()).add(q)
        return q

    async def unsubscribe(self, user_id: int, q: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            group = self._subs.get(int(user_id))
            if not group:
                return
            group.discard(q)
            if not group:
                self._subs.pop(int(user_id), None)

    async def publish(self, user_id: int, event: dict[str, Any]) -> None:
        # Copy subscribers under lock to avoid holding the lock while pushing.
        async with self._lock:
            targets = list(self._subs.get(int(user_id), set()))

        if not targets:
            return

        for q in targets:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the oldest event and keep the newest to avoid dead connections
                # causing unbounded memory growth.
                try:
                    _ = q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(event)
                except Exception:
                    # Give up for this subscriber.
                    pass


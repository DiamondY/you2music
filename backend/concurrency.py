"""Concurrency control for music generation API calls.

Provides:
- ProviderQueue: Per-provider job queue with controlled worker pool
- TokenBucket: Simple token-bucket rate limiter (zero external deps)
- run_with_retry: Exponential-backoff retry for transient HTTP errors
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Default concurrency settings
# ---------------------------------------------------------------------------

DEFAULT_CONCURRENCY: dict[str, Any] = {
    "minimax": {
        "max_concurrent": 3,
        "rate_limit_per_sec": 2.0,
    },
    "acestep": {
        "max_concurrent": 2,
        "rate_limit_per_sec": 1.0,
    },
    "retry": {
        "max_retries": 3,
        "base_delay_sec": 2.0,
        "retryable_statuses": [429, 502, 503, 504],
    },
    "queue_timeout_sec": 300,  # Max seconds a job can wait in queue before being marked failed
}


def _merge_concurrency(user_cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Merge user config over defaults, preserving unset keys."""
    if not user_cfg:
        return dict(DEFAULT_CONCURRENCY)
    merged: dict[str, Any] = {}
    for provider in ("minimax", "acestep"):
        base = dict(DEFAULT_CONCURRENCY.get(provider, {}))
        override = user_cfg.get(provider)
        if isinstance(override, dict):
            base.update(override)
        merged[provider] = base
    retry_base = dict(DEFAULT_CONCURRENCY.get("retry", {}))
    retry_override = user_cfg.get("retry")
    if isinstance(retry_override, dict):
        retry_base.update(retry_override)
    merged["retry"] = retry_base
    # Top-level scalar keys (e.g. queue_timeout_sec)
    for key in DEFAULT_CONCURRENCY:
        if key in ("minimax", "acestep", "retry"):
            continue
        if key in user_cfg:
            merged[key] = user_cfg[key]
        elif key in DEFAULT_CONCURRENCY:
            merged[key] = DEFAULT_CONCURRENCY[key]
    return merged


# ---------------------------------------------------------------------------
# TokenBucket — simple async rate limiter
# ---------------------------------------------------------------------------


class TokenBucket:
    """Token-bucket rate limiter (pure Python, zero external deps).

    *rate* is tokens per second. *capacity* is the burst size (defaults to
    max(1, int(rate))).
    """

    def __init__(self, rate: float, capacity: int | None = None) -> None:
        if rate <= 0:
            raise ValueError(f"TokenBucket rate must be > 0, got {rate}")
        self._rate = rate
        self._capacity = capacity or max(1, int(rate))
        self._tokens = float(self._capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available, then consume it."""
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            # Sleep a fraction of the refill interval
            await asyncio.sleep(1.0 / max(self._rate, 0.1))

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens (approximate)."""
        return self._tokens


# ---------------------------------------------------------------------------
# ProviderQueue — per-provider job queue with worker pool
# ---------------------------------------------------------------------------


@dataclass
class ProviderQueue:
    """Per-provider job queue with a controlled worker pool.

    * Workers are asyncio.Tasks that loop forever pulling job_ids from the
      queue and calling *handler*.
    * The number of workers equals *max_concurrent*, ensuring at most that
      many API calls are in flight at once.
    * Jobs are submitted via ``submit(job_id)`` and immediately return so the
      HTTP handler can respond to the client quickly.
    """

    queue: asyncio.Queue[str]
    max_concurrent: int
    _workers: list[asyncio.Task[Any]] = field(default_factory=list)
    _stopping: bool = False
    # Mirror of queue contents for position lookup / cancellation
    _pending_ids: list[str] = field(default_factory=list)
    _cancelled: set[str] = field(default_factory=set)

    @classmethod
    def create(cls, max_concurrent: int) -> ProviderQueue:
        return cls(queue=asyncio.Queue(), max_concurrent=max_concurrent)

    # -- lifecycle -----------------------------------------------------------

    def start_workers(
        self,
        handler: Callable[[str], Awaitable[None]],
        num_workers: int | None = None,
    ) -> None:
        """Start the worker pool. Call once during app startup."""
        n = num_workers or self.max_concurrent
        for _ in range(n):
            task = asyncio.create_task(self._worker_loop(handler))
            self._workers.append(task)

    async def stop_workers(self, timeout: float = 5.0) -> None:
        """Cancel all workers and wait for them to finish."""
        self._stopping = True
        for w in self._workers:
            w.cancel()
        if self._workers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                pass
        self._workers.clear()
        self._stopping = False

    # -- submit --------------------------------------------------------------

    async def submit(self, job_id: str) -> None:
        """Enqueue a job for processing. Returns immediately."""
        self._pending_ids.append(job_id)
        await self.queue.put(job_id)

    def submit_nowait(self, job_id: str) -> None:
        """Enqueue a job without awaiting (queue is unbounded)."""
        self._pending_ids.append(job_id)
        self.queue.put_nowait(job_id)

    # -- cancellation ---------------------------------------------------------

    def cancel(self, job_id: str) -> bool:
        """Mark a queued job as cancelled.

        The job is NOT removed from the underlying asyncio.Queue (that is not
        safely possible).  Instead it is added to an internal ``_cancelled``
        set.  When a worker eventually picks it up, the worker loop will
        detect the cancellation and skip processing.

        Returns True if the job was found in the pending list (and was
        cancelled), False if it was already gone (e.g. already picked up by
        a worker).
        """
        if job_id in self._pending_ids:
            self._cancelled.add(job_id)
            self._pending_ids.remove(job_id)
            return True
        return False

    # -- introspection -------------------------------------------------------

    @property
    def pending_count(self) -> int:
        """Number of jobs waiting in the queue."""
        return self.queue.qsize()

    @property
    def active_workers(self) -> int:
        """Number of running worker tasks."""
        return sum(1 for w in self._workers if not w.done())

    def get_position(self, job_id: str) -> int:
        """Return 1-based position of *job_id* in the queue, or 0 if not found."""
        try:
            return self._pending_ids.index(job_id) + 1
        except ValueError:
            return 0

    # -- internal ------------------------------------------------------------

    async def _worker_loop(
        self,
        handler: Callable[[str], Awaitable[None]],
    ) -> None:
        while True:
            job_id = await self.queue.get()
            # Check if this job was cancelled while it was sitting in the queue.
            if job_id in self._cancelled:
                self._cancelled.discard(job_id)
                # Also remove from _pending_ids if still present (defensive).
                try:
                    self._pending_ids.remove(job_id)
                except ValueError:
                    pass
                self.queue.task_done()
                continue
            # Remove from pending list now that a worker has picked it up.
            try:
                self._pending_ids.remove(job_id)
            except ValueError:
                pass
            try:
                await handler(job_id)
            except asyncio.CancelledError:
                # Re-queue the job so it isn't lost on shutdown if it was
                # pulled but not yet processed.
                if not self._stopping:
                    self.queue.put_nowait(job_id)
                self.queue.task_done()
                raise
            except Exception:
                # handler is expected to set the job status to "failed" internally.
                logger.exception("Worker error processing job %s", job_id)
            finally:
                self.queue.task_done()


# ---------------------------------------------------------------------------
# run_with_retry — exponential backoff for transient errors
# ---------------------------------------------------------------------------

# Error messages from our provider clients contain "HTTP {status}", so we
# match against that pattern rather than inspecting httpx responses here.
_RETRYABLE_STATUSES_DEFAULT = (429, 502, 503, 504)


async def run_with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    retryable_statuses: tuple[int, ...] | list[int] = _RETRYABLE_STATUSES_DEFAULT,
    base_delay: float = 2.0,
    retry_logger: logging.Logger | None = None,
) -> T:
    """Call *fn* with exponential-backoff retry on transient HTTP errors.

    Only retries on errors whose message contains ``HTTP {status}`` where
    *status* is in *retryable_statuses*. All other errors propagate
    immediately.
    """
    statuses = tuple(retryable_statuses)
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except RuntimeError as exc:
            msg = str(exc)
            is_retryable = any(f"HTTP {s}" in msg for s in statuses)
            if not is_retryable or attempt >= max_retries:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            if retry_logger:
                retry_logger.warning(
                    "Retry %d/%d after %.1fs: %s",
                    attempt + 1,
                    max_retries,
                    delay,
                    msg[:120],
                )
            await asyncio.sleep(delay)
    # Should not reach here, but satisfy type checker
    raise RuntimeError("run_with_retry exhausted retries")  # pragma: no cover

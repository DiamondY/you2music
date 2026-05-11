"""Tests for concurrency control (concurrency.py)."""

from __future__ import annotations

import asyncio
import time

import pytest

from concurrency import (
    ProviderQueue,
    TokenBucket,
    _merge_concurrency,
    run_with_retry,
)


# ---------------------------------------------------------------------------
# _merge_concurrency
# ---------------------------------------------------------------------------


class TestMergeConcurrency:
    """Tests for the _merge_concurrency helper."""

    def test_defaults_unchanged_with_none(self) -> None:
        """Passing None returns a copy of defaults."""
        merged = _merge_concurrency(None)
        assert merged["minimax"]["max_concurrent"] == 3
        assert merged["minimax"]["rate_limit_per_sec"] == 2.0
        assert merged["acestep"]["max_concurrent"] == 1  # forced to 1
        assert merged["retry"]["max_retries"] == 3

    def test_partial_override(self) -> None:
        """Partial user config merges with defaults."""
        user_cfg = {"minimax": {"max_concurrent": 5}, "queue_timeout_sec": 600}
        merged = _merge_concurrency(user_cfg)
        assert merged["minimax"]["max_concurrent"] == 5
        assert merged["minimax"]["rate_limit_per_sec"] == 2.0  # unchanged
        assert merged["acestep"]["max_concurrent"] == 1  # forced even if user sets
        assert merged["queue_timeout_sec"] == 600

    def test_acestep_always_serialized(self) -> None:
        """Even if user sets acestep max_concurrent > 1, it is forced to 1."""
        user_cfg = {"acestep": {"max_concurrent": 5}}
        merged = _merge_concurrency(user_cfg)
        assert merged["acestep"]["max_concurrent"] == 1


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------


class TestTokenBucket:
    """Tests for TokenBucket rate limiter."""

    def test_init_rejects_nonpositive_rate(self) -> None:
        """TokenBucket raises ValueError for rate <= 0."""
        with pytest.raises(ValueError):
            TokenBucket(rate=0)
        with pytest.raises(ValueError):
            TokenBucket(rate=-1)

    def test_default_capacity(self) -> None:
        """Default capacity equals max(1, int(rate))."""
        tb = TokenBucket(rate=5.0)
        assert tb.available_tokens == 5.0

        tb2 = TokenBucket(rate=0.5)
        assert tb2.available_tokens == 1.0  # max(1, 0)

    def test_custom_capacity(self) -> None:
        """Custom capacity is respected."""
        tb = TokenBucket(rate=10.0, capacity=20)
        assert tb.available_tokens == 20.0

    @pytest.mark.asyncio
    async def test_acquire_consumes_token(self) -> None:
        """acquire() decrements available tokens."""
        tb = TokenBucket(rate=100.0, capacity=10)
        assert tb.available_tokens == 10.0
        await tb.acquire()
        assert tb.available_tokens == 9.0

    @pytest.mark.asyncio
    async def test_acquire_blocks_when_empty(self) -> None:
        """acquire() waits when tokens are depleted."""
        tb = TokenBucket(rate=10.0, capacity=1)
        # Drain the single token
        await tb.acquire()
        assert tb.available_tokens < 1.0

        # Next acquire should wait for refill; use a timeout to verify it
        # completes (i.e., a token becomes available).
        start = time.monotonic()
        await asyncio.wait_for(tb.acquire(), timeout=2.0)
        elapsed = time.monotonic() - start
        # Should have waited roughly 1/rate = 0.1s for a token
        assert elapsed >= 0.05
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_rate_limit_observed(self) -> None:
        """Over many acquires, average rate is bounded by configured rate."""
        rate = 20.0
        tb = TokenBucket(rate=rate, capacity=int(rate))
        count = 30
        start = time.monotonic()
        for _ in range(count):
            await tb.acquire()
        elapsed = time.monotonic() - start
        # Expected minimum time = count / rate (seconds) minus capacity burst
        expected_min = (count - tb._capacity) / rate
        assert elapsed >= expected_min - 0.05  # small tolerance


# ---------------------------------------------------------------------------
# ProviderQueue
# ---------------------------------------------------------------------------


class TestProviderQueue:
    """Tests for ProviderQueue (submit, cancel, position, lifecycle)."""

    @pytest.mark.asyncio
    async def test_submit_and_pending_count(self) -> None:
        """submit_nowait increases pending_count."""
        pq = ProviderQueue.create(max_concurrent=2)
        assert pq.pending_count == 0
        pq.submit_nowait("job-1")
        pq.submit_nowait("job-2")
        assert pq.pending_count == 2

    @pytest.mark.asyncio
    async def test_get_position(self) -> None:
        """get_position returns 1-based index in the pending list."""
        pq = ProviderQueue.create(max_concurrent=2)
        pq.submit_nowait("job-a")
        pq.submit_nowait("job-b")
        pq.submit_nowait("job-c")
        assert pq.get_position("job-a") == 1
        assert pq.get_position("job-b") == 2
        assert pq.get_position("job-c") == 3
        assert pq.get_position("nonexistent") == 0

    @pytest.mark.asyncio
    async def test_cancel_removes_from_pending(self) -> None:
        """cancel marks job as cancelled and removes from pending list."""
        pq = ProviderQueue.create(max_concurrent=1)
        pq.submit_nowait("job-1")
        pq.submit_nowait("job-2")

        assert pq.cancel("job-1") is True
        assert pq.get_position("job-1") == 0
        assert pq.get_position("job-2") == 1  # shifted

    @pytest.mark.asyncio
    async def test_cancel_returns_false_for_unknown(self) -> None:
        """cancel returns False for unknown or already-gone jobs."""
        pq = ProviderQueue.create(max_concurrent=1)
        assert pq.cancel("nonexistent") is False

    @pytest.mark.asyncio
    async def test_cancel_double(self) -> None:
        """cancel is idempotent — second cancel returns False."""
        pq = ProviderQueue.create(max_concurrent=1)
        pq.submit_nowait("job-1")
        assert pq.cancel("job-1") is True
        assert pq.cancel("job-1") is False

    @pytest.mark.asyncio
    async def test_worker_skips_cancelled(self) -> None:
        """Worker loop skips cancelled jobs and does not invoke handler."""
        pq = ProviderQueue.create(max_concurrent=1)
        handled: list[str] = []

        async def handler(job_id: str) -> None:
            handled.append(job_id)

        pq.submit_nowait("cancelled-job")
        pq.cancel("cancelled-job")
        pq.submit_nowait("real-job")

        pq.start_workers(handler, num_workers=1)
        # Let the worker process
        await asyncio.sleep(0.2)
        await pq.stop_workers(timeout=2.0)

        assert "cancelled-job" not in handled
        assert "real-job" in handled

    @pytest.mark.asyncio
    async def test_worker_processes_jobs(self) -> None:
        """Worker processes submitted jobs via the handler."""
        pq = ProviderQueue.create(max_concurrent=2)
        handled: list[str] = []

        async def handler(job_id: str) -> None:
            handled.append(job_id)

        for i in range(5):
            pq.submit_nowait(f"job-{i}")

        pq.start_workers(handler, num_workers=2)
        # Wait for all to be picked up
        await asyncio.sleep(0.3)
        await pq.stop_workers(timeout=2.0)

        assert len(handled) == 5
        assert set(handled) == {f"job-{i}" for i in range(5)}

    @pytest.mark.asyncio
    async def test_active_workers(self) -> None:
        """active_workers reports the number of running worker tasks."""
        pq = ProviderQueue.create(max_concurrent=2)

        async def handler(job_id: str) -> None:
            await asyncio.sleep(10)  # block forever

        pq.start_workers(handler, num_workers=2)
        await asyncio.sleep(0.05)  # let them start
        assert pq.active_workers == 2
        await pq.stop_workers(timeout=1.0)
        assert pq.active_workers == 0


# ---------------------------------------------------------------------------
# run_with_retry
# ---------------------------------------------------------------------------


class TestRunWithRetry:
    """Tests for run_with_retry exponential backoff logic."""

    @pytest.mark.asyncio
    async def test_success_first_try(self) -> None:
        """Returns result immediately when function succeeds."""
        call_count = 0

        async def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await run_with_retry(succeed, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_transient(self) -> None:
        """Retries on RuntimeError containing retryable HTTP status."""
        attempts = 0

        async def fail_then_succeed() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("HTTP 502 Bad Gateway")
            return "finally"

        result = await run_with_retry(
            fail_then_succeed,
            max_retries=3,
            retryable_statuses=[502],
            base_delay=0.01,
        )
        assert result == "finally"
        assert attempts == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable(self) -> None:
        """Does NOT retry on RuntimeError without retryable status code."""
        attempts = 0

        async def fail_permanent() -> str:
            nonlocal attempts
            attempts += 1
            raise RuntimeError("HTTP 400 Bad Request")

        with pytest.raises(RuntimeError, match="HTTP 400"):
            await run_with_retry(
                fail_permanent,
                max_retries=3,
                retryable_statuses=[502, 503],
                base_delay=0.01,
            )
        assert attempts == 1

    @pytest.mark.asyncio
    async def test_exhausts_retries(self) -> None:
        """Raises last error after exhausting retries on transient errors."""
        attempts = 0

        async def always_fail() -> str:
            nonlocal attempts
            attempts += 1
            raise RuntimeError("HTTP 503 Service Unavailable")

        with pytest.raises(RuntimeError, match="HTTP 503"):
            await run_with_retry(
                always_fail,
                max_retries=2,
                retryable_statuses=[503],
                base_delay=0.01,
            )
        assert attempts == 3  # 1 initial + 2 retries

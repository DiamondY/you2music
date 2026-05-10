"""Tests for key_pool.KeyPool - multi-key rotation, cooldown, and failure handling."""

from __future__ import annotations

import pytest

from key_pool import KeyPool


class TestKeyPoolInit:
    def test_single_key(self) -> None:
        pool = KeyPool(["key1"])
        assert pool.total_count == 1
        assert pool.available_count == 1

    def test_multiple_keys(self) -> None:
        pool = KeyPool(["key1", "key2", "key3"])
        assert pool.total_count == 3
        assert pool.available_count == 3

    def test_empty_keys_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one key"):
            KeyPool([])


class TestKeyPoolAcquire:
    @pytest.mark.asyncio
    async def test_round_robin_rotation(self) -> None:
        pool = KeyPool(["a", "b", "c"])
        keys = [await pool.acquire() for _ in range(6)]
        assert keys == ["a", "b", "c", "a", "b", "c"]

    @pytest.mark.asyncio
    async def test_single_key_always_returns_same(self) -> None:
        pool = KeyPool(["only"])
        keys = [await pool.acquire() for _ in range(5)]
        assert all(k == "only" for k in keys)

    @pytest.mark.asyncio
    async def test_disabled_key_skipped(self) -> None:
        pool = KeyPool(["a", "b", "c"])
        # Disable key "b" by simulating a 401 error.
        pool.report_result("b", success=False, http_status=401)
        assert pool.available_count == 2

        keys = [await pool.acquire() for _ in range(5)]
        assert "b" not in keys
        assert set(keys) == {"a", "c"}

    @pytest.mark.asyncio
    async def test_cooldown_key_skipped(self) -> None:
        pool = KeyPool(["a", "b"], cooldown_sec=60.0)
        # Simulate a 429 on key "a".
        pool.report_result("a", success=False, http_status=429)
        assert pool.available_count == 1

        keys = [await pool.acquire() for _ in range(3)]
        assert all(k == "b" for k in keys)

    @pytest.mark.asyncio
    async def test_success_resets_consecutive_failures(self) -> None:
        pool = KeyPool(["a", "b"], max_failures=3)
        # Two failures on "a" then one success - should not trigger cooldown.
        pool.report_result("a", success=False, http_status=502)
        pool.report_result("a", success=False, http_status=502)
        pool.report_result("a", success=True)
        # Acquire should still include "a".
        keys = [await pool.acquire() for _ in range(4)]
        assert "a" in keys

    @pytest.mark.asyncio
    async def test_too_many_failures_triggers_cooldown(self) -> None:
        pool = KeyPool(["a", "b"], cooldown_sec=60.0, max_failures=2)
        # Two consecutive non-429 failures -> cooldown.
        pool.report_result("a", success=False, http_status=502)
        pool.report_result("a", success=False, http_status=502)
        assert pool.available_count == 1

        keys = [await pool.acquire() for _ in range(3)]
        assert all(k == "b" for k in keys)

    @pytest.mark.asyncio
    async def test_transient_502_does_not_penalize_key(self) -> None:
        """502/503/504 are upstream issues, not key-specific - should not trigger cooldown unless repeated."""
        pool = KeyPool(["a", "b"], cooldown_sec=60.0, max_failures=3)
        pool.report_result("a", success=False, http_status=502)
        assert pool.available_count == 2  # "a" still available after one 502
        keys = [await pool.acquire() for _ in range(4)]
        assert "a" in keys

    @pytest.mark.asyncio
    async def test_429_exponential_cooldown(self) -> None:
        pool = KeyPool(["a", "b"], cooldown_sec=1.0)
        # First 429 -> 2^0 * 1.0 = 1s cooldown
        pool.report_result("a", success=False, http_status=429)
        keys = [await pool.acquire() for _ in range(3)]
        assert all(k == "b" for k in keys)

        # Wait for cooldown to expire (very short test cooldown).
        import asyncio
        await asyncio.sleep(1.2)  # Slightly more than 1s

        # After cooldown expires, "a" should be available again.
        assert pool.available_count == 2
        keys_after = [await pool.acquire() for _ in range(2)]
        assert "a" in keys_after

    @pytest.mark.asyncio
    async def test_auth_error_disables_permanently(self) -> None:
        pool = KeyPool(["a", "b", "c"])
        pool.report_result("a", success=False, http_status=401)
        pool.report_result("c", success=False, http_status=403)

        status = pool.status()
        states = {k["label"]: k["state"] for k in status["keys"]}
        assert states["key-1"] == "disabled"
        assert states["key-2"] == "active"
        assert states["key-3"] == "disabled"

        # Only "b" remains.
        keys = [await pool.acquire() for _ in range(5)]
        assert all(k == "b" for k in keys)

    @pytest.mark.asyncio
    async def test_all_keys_down_waits_and_recovers(self) -> None:
        pool = KeyPool(["a", "b"], cooldown_sec=0.1)
        # Rate-limit both keys.
        pool.report_result("a", success=False, http_status=429)
        pool.report_result("b", success=False, http_status=429)
        assert pool.available_count == 0

        # acquire() should not raise - it waits until a key recovers.
        import asyncio
        key = await asyncio.wait_for(pool.acquire(), timeout=5.0)
        assert key in ("a", "b")


class TestKeyPoolStatus:
    def test_status_initial(self) -> None:
        pool = KeyPool(["k1", "k2"])
        s = pool.status()
        assert s["total"] == 2
        assert s["available"] == 2
        assert all(k["state"] == "active" for k in s["keys"])

    def test_status_counts_after_failures(self) -> None:
        pool = KeyPool(["a", "b", "c"])
        pool.report_result("a", success=False, http_status=401)
        pool.report_result("b", success=False, http_status=429)
        s = pool.status()
        assert s["total"] == 3
        assert s["available"] == 1  # only "c"

    @pytest.mark.asyncio
    async def test_status_includes_usage_stats(self) -> None:
        pool = KeyPool(["a", "b"])
        await pool.acquire()
        await pool.acquire()
        await pool.acquire()  # a, b, a
        pool.report_result("a", success=False, http_status=429)
        s = pool.status()
        key_a = next(k for k in s["keys"] if k["label"] == "key-1")
        assert key_a["total_uses"] == 2
        assert key_a["total_failures"] == 1


class TestConfigParseKeys:
    def test_parse_single_string(self) -> None:
        from config import _parse_keys
        assert _parse_keys("abc") == ["abc"]

    def test_parse_array_of_strings(self) -> None:
        from config import _parse_keys
        assert _parse_keys(["a", "b", "c"]) == ["a", "b", "c"]

    def test_parse_array_of_dicts(self) -> None:
        from config import _parse_keys
        raw = [{"key": "k1", "label": "first"}, {"key": "k2"}]
        assert _parse_keys(raw) == ["k1", "k2"]

    def test_parse_mixed_array(self) -> None:
        from config import _parse_keys
        raw = ["plain-key", {"key": "dict-key", "label": "labeled"}]
        assert _parse_keys(raw) == ["plain-key", "dict-key"]

    def test_parse_empty_string(self) -> None:
        from config import _parse_keys
        assert _parse_keys("") == []

    def test_parse_empty_list(self) -> None:
        from config import _parse_keys
        assert _parse_keys([]) == []

    def test_parse_none(self) -> None:
        from config import _parse_keys
        assert _parse_keys(None) == []

    def test_parse_key_single_string(self) -> None:
        from config import _parse_key_single
        assert _parse_key_single("abc") == "abc"

    def test_parse_key_single_from_array(self) -> None:
        from config import _parse_key_single
        assert _parse_key_single(["abc", "def"]) == "abc"

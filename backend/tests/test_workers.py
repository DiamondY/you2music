from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
async def isolated_state(tmp_path: Path, monkeypatch: Any):
    """Create an isolated AppState instance and monkeypatch global STATE users.

    Worker code imports `STATE` as a module-level singleton, so we patch both:
      - `backend/state.py:STATE`
      - `backend/workers.py:STATE`
    """
    monkeypatch.setenv("AI_MUSIC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AI_MUSIC_TEST_MODE", "1")
    monkeypatch.setenv("AI_MUSIC_JWT_SECRET", "test-secret")
    monkeypatch.setenv("AI_MUSIC_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AI_MUSIC_ADMIN_PASSWORD", "adminpw123")
    monkeypatch.setenv("AI_MUSIC_DEFAULT_DAILY_QUOTA", "10")
    # Defensive: ensure non-test paths never hit real network.
    monkeypatch.setenv("ACESTEP_BASE_URL", "http://localhost:0")

    from app_state import AppState
    import state as state_module
    import workers as workers_module

    st = AppState.create()
    # Make retries fast for unit tests.
    cc = dict(st.settings.concurrency_config or {})
    cc["retry"] = {"max_retries": 1, "base_delay_sec": 0.0, "retryable_statuses": [429]}
    st.settings = replace(st.settings, concurrency_config=cc)

    monkeypatch.setattr(state_module, "STATE", st, raising=True)
    monkeypatch.setattr(workers_module, "STATE", st, raising=True)

    try:
        yield st
    finally:
        # Ensure httpx clients are closed to avoid resource warnings.
        for client in list(st.http_clients.values()):
            try:
                await client.aclose()
            except Exception:
                pass


def _create_user(*, st: Any, username: str = "u") -> Any:
    from auth import hash_password

    admin = st.user_store.get_by_username("admin")
    assert admin is not None
    invite = st.user_store.create_invite_code(created_by=int(admin.id))

    return st.user_store.create_user(
        username=username,
        password_hash=hash_password("pw12345678"),
        invite_code=str(invite.code),
        daily_quota=10,
    )


@pytest.mark.asyncio
async def test_worker_test_mode_succeeds_and_writes_audio(isolated_state: Any) -> None:
    import workers as workers_module

    st = isolated_state
    user = _create_user(st=st, username="u1")
    q = await st.event_hub.subscribe(int(user.id))
    try:
        params = {"provider": "acestep", "duration_sec": 30, "vocals": True, "seed": None, "provider_params": {}}
        job_id = st.store.create_job(provider="acestep", prompt="hello", params=params, user_id=int(user.id))
        rec = st.store.get(job_id)
        assert rec is not None
        assert rec.status == "queued"

        await workers_module._execute_queued_job(job_id=job_id, rec=rec, params=params)

        done = st.store.get(job_id)
        assert done is not None
        assert done.status == "succeeded"
        assert done.output_path
        out_path = Path(str(done.output_path))
        assert out_path.exists()
        assert out_path.suffix == ".wav"

        # Ensure we emitted at least running + succeeded.
        seen: list[dict[str, Any]] = []
        for _ in range(20):
            try:
                seen.append(q.get_nowait())
            except asyncio.QueueEmpty:
                break
        assert any(e.get("type") == "job_updated" and e.get("status") == "running" for e in seen), seen
        assert any(e.get("type") == "job_updated" and e.get("status") == "succeeded" for e in seen), seen
    finally:
        await st.event_hub.unsubscribe(int(user.id), q)


@pytest.mark.asyncio
async def test_worker_test_mode_disables_provider_cooldown(isolated_state: Any) -> None:
    import workers as workers_module

    st = isolated_state
    cc = dict(st.settings.concurrency_config or {})
    acestep_cfg = dict(cc.get("acestep") or {})
    acestep_cfg["cooldown_sec"] = 30.0
    cc["acestep"] = acestep_cfg
    st.settings = replace(st.settings, concurrency_config=cc)

    assert workers_module._provider_cooldown_seconds("acestep") == 0.0


@pytest.mark.asyncio
async def test_worker_test_mode_forced_error_marks_failed(monkeypatch: Any, isolated_state: Any) -> None:
    import workers as workers_module

    st = isolated_state
    monkeypatch.setenv("AI_MUSIC_TEST_FORCE_ERROR", "1")
    user = _create_user(st=st, username="u2")
    st.user_store.consume_quota(user_id=int(user.id), amount=1, daily_quota=int(user.daily_quota))
    assert int(st.user_store.quota_status(user_id=int(user.id), daily_quota=int(user.daily_quota))["used"]) == 1

    params = {"provider": "acestep", "duration_sec": 30, "vocals": True, "seed": None, "provider_params": {}}
    job_id = st.store.create_job(provider="acestep", prompt="boom", params=params, user_id=int(user.id))
    rec = st.store.get(job_id)
    assert rec is not None

    await workers_module._execute_queued_job(job_id=job_id, rec=rec, params=params)

    failed = st.store.get(job_id)
    assert failed is not None
    assert failed.status == "failed"
    assert "forced error for testing" in str(failed.error or "")
    assert int(st.user_store.quota_status(user_id=int(user.id), daily_quota=int(user.daily_quota))["used"]) == 0


@pytest.mark.asyncio
async def test_worker_retries_on_retryable_http_status(monkeypatch: Any, isolated_state: Any) -> None:
    import concurrency
    import workers as workers_module

    st = isolated_state
    # Eliminate random jitter so the test is deterministic and fast.
    monkeypatch.setattr(concurrency.random, "uniform", lambda _a, _b: 0.0)

    user = _create_user(st=st, username="u3")
    params = {"provider": "acestep", "duration_sec": 30, "vocals": True, "seed": None, "provider_params": {}}
    job_id = st.store.create_job(provider="acestep", prompt="retry-me", params=params, user_id=int(user.id))
    rec = st.store.get(job_id)
    assert rec is not None

    original = workers_module._run_job
    calls = {"n": 0}

    async def flaky_run_job(*, job_id: str, prompt: str, params: dict[str, Any]) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("HTTP 429")
        await original(job_id=job_id, prompt=prompt, params=params)

    monkeypatch.setattr(workers_module, "_run_job", flaky_run_job)

    await workers_module._execute_queued_job(job_id=job_id, rec=rec, params=params)

    done = st.store.get(job_id)
    assert done is not None
    assert done.status == "succeeded"
    assert calls["n"] == 2

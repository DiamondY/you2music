from __future__ import annotations

import pytest

import test_env  # noqa: F401


def test_quota_consumed_on_generate(client, auth_headers, factories) -> None:
    before = client.get("/api/auth/me", headers=auth_headers).json()["user"]["quota"]["used"]
    job_id = factories.create_succeeded_job(prompt="quota", duration_sec=5)
    assert job_id
    after = client.get("/api/auth/me", headers=auth_headers).json()["user"]["quota"]["used"]
    assert int(after) == int(before) + 1


def test_quota_exhaustion_returns_429_without_extra_job(client, auth_headers, factories) -> None:
    from state import STATE

    me = client.get("/api/auth/me", headers=auth_headers).json()["user"]
    user_id = int(me["id"])
    STATE.user_store.update_user(user_id, daily_quota=1)

    first = factories.create_succeeded_job(prompt="quota-once", duration_sec=5)
    assert first
    before_jobs = STATE.store.count_jobs(user_id=user_id)

    second = client.post(
        "/api/generate",
        json={"prompt": "quota-twice", "duration_sec": 5, "vocals": True},
        headers=auth_headers,
    )
    assert second.status_code == 429, second.text
    assert STATE.store.count_jobs(user_id=user_id) == before_jobs


def test_quota_refunded_when_submission_fails(client, auth_headers, monkeypatch) -> None:
    from state import STATE

    me = client.get("/api/auth/me", headers=auth_headers).json()["user"]
    user_id = int(me["id"])
    before = int(me["quota"]["used"])

    async def fail_submit(_job_id: str) -> None:
        raise RuntimeError("submit failed")

    monkeypatch.setattr(STATE.provider_queues["acestep"], "submit", fail_submit)

    with pytest.raises(RuntimeError, match="submit failed"):
        client.post(
            "/api/generate",
            json={"prompt": "submit fail", "duration_sec": 5, "vocals": True},
            headers=auth_headers,
        )

    after = client.get("/api/auth/me", headers=auth_headers).json()["user"]["quota"]["used"]
    assert int(after) == before
    records = STATE.store.list_page(user_id=user_id, include_all=False)
    assert all(j.status != "queued" for j in records)


def test_generate_store_refunds_quota_when_submission_fails(client, auth_headers, monkeypatch) -> None:
    from state import STATE

    me = client.get("/api/auth/me", headers=auth_headers).json()["user"]
    user_id = int(me["id"])
    before = int(me["quota"]["used"])

    async def fail_submit(_job_id: str) -> None:
        raise RuntimeError("store submit failed")

    monkeypatch.setattr(STATE.provider_queues["acestep"], "submit", fail_submit)

    with pytest.raises(RuntimeError, match="store submit failed"):
        client.post(
            "/api/generate_store",
            json={"prompt": "store submit fail", "duration_sec": 5, "vocals": True},
            headers=auth_headers,
        )

    after = client.get("/api/auth/me", headers=auth_headers).json()["user"]["quota"]["used"]
    assert int(after) == before
    records = STATE.store.list_page(user_id=user_id, include_all=False)
    assert all(j.status != "queued" for j in records)

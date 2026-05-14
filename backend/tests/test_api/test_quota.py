from __future__ import annotations

import test_env  # noqa: F401


def test_quota_consumed_on_generate(client, auth_headers, factories) -> None:
    before = client.get("/api/auth/me", headers=auth_headers).json()["user"]["quota"]["used"]
    job_id = factories.create_succeeded_job(prompt="quota", duration_sec=5)
    assert job_id
    after = client.get("/api/auth/me", headers=auth_headers).json()["user"]["quota"]["used"]
    assert int(after) == int(before) + 1


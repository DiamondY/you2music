from __future__ import annotations

import test_env  # noqa: F401


def test_history_lists_own_jobs(client, auth_headers, factories) -> None:
    factories.create_succeeded_job(prompt="h1")
    factories.create_succeeded_job(prompt="h2")
    r = client.get("/api/jobs/history?offset=0&limit=20", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] >= 2
    assert len(data["jobs"]) >= 2


from __future__ import annotations

import test_env  # noqa: F401


def test_history_lists_own_jobs(client, auth_headers, factories) -> None:
    first = factories.create_succeeded_job(prompt="h1")
    second = factories.create_succeeded_job(prompt="h2")
    r = client.get("/api/jobs/history?offset=0&limit=20", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] >= 2
    assert len(data["jobs"]) >= 2

    recent = client.get("/api/jobs/recent?limit=10", headers=auth_headers)
    assert recent.status_code == 200, recent.text
    recent_ids = {j["job_id"] for j in recent.json()["jobs"]}
    assert first in recent_ids
    assert second in recent_ids

    one = client.get(f"/api/jobs/{first}", headers=auth_headers)
    assert one.status_code == 200, one.text
    assert one.json()["job_id"] == first

    many = client.get(f"/api/jobs?ids={first},{second}", headers=auth_headers)
    assert many.status_code == 200, many.text
    assert {j["job_id"] for j in many.json()["jobs"]} == {first, second}

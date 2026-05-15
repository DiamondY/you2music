from __future__ import annotations

import test_env  # noqa: F401


def _job_params() -> dict:
    return {
        "base_prompt": "queued",
        "duration_sec": 5,
        "vocals": True,
        "seed": None,
        "provider": "acestep",
        "provider_params": {},
    }


def test_generate_succeeds_in_test_mode(client, auth_headers, factories) -> None:
    job_id = factories.create_job(prompt="hello", duration_sec=5)
    rec = factories.wait_job(job_id, expect_status="succeeded", timeout_s=10.0)
    assert rec["job_id"] == job_id
    assert rec["status"] == "succeeded"
    assert rec.get("audio_url"), rec

    audio = client.get(rec["audio_url"], headers=auth_headers)
    assert audio.status_code == 200, audio.text
    assert int(audio.headers.get("content-length") or "0") > 10


def test_generate_many_creates_variations_and_consumes_quota(client, auth_headers) -> None:
    before = client.get("/api/auth/me", headers=auth_headers).json()["user"]["quota"]["used"]
    resp = client.post(
        "/api/generate_many",
        json={"prompt": "many", "duration_sec": 5, "vocals": True, "count": 3},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["job_ids"]) == 3
    assert int(data["quota"]["used"]) == int(before) + 3

    jobs = client.get("/api/jobs?ids=" + ",".join(data["job_ids"]), headers=auth_headers)
    assert jobs.status_code == 200, jobs.text
    assert {j["job_id"] for j in jobs.json()["jobs"]} == set(data["job_ids"])


def test_generate_store_creates_store_job(client, auth_headers, factories) -> None:
    resp = client.post(
        "/api/generate_store",
        json={"prompt": "store", "duration_sec": 5, "vocals": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    rec = factories.wait_job(job_id, expect_status="succeeded", timeout_s=10.0)
    assert rec["job_id"] == job_id
    assert rec["params"]["store_for_inpainting"] is True


def test_cancel_queued_job(client, auth_headers) -> None:
    from state import STATE

    me = client.get("/api/auth/me", headers=auth_headers).json()["user"]
    user_id = int(me["id"])
    before = int(me["quota"]["used"])
    STATE.user_store.consume_quota(user_id=user_id, amount=1, daily_quota=int(me["daily_quota"]))
    job_id = STATE.store.create_job(provider="acestep", prompt="queued", params=_job_params(), user_id=user_id)

    resp = client.post(f"/api/jobs/{job_id}/cancel", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    rec = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
    assert rec.status_code == 200, rec.text
    assert rec.json()["status"] == "failed"
    after = client.get("/api/auth/me", headers=auth_headers).json()["user"]["quota"]["used"]
    assert int(after) == int(before)


def test_delete_single_and_bulk_delete_terminal_jobs(client, auth_headers, factories) -> None:
    first = factories.create_succeeded_job(prompt="delete-one", duration_sec=5)
    delete_one = client.delete(f"/api/jobs/{first}", headers=auth_headers)
    assert delete_one.status_code == 200, delete_one.text
    assert delete_one.json()["ok"] is True
    assert client.get(f"/api/jobs/{first}", headers=auth_headers).status_code == 404

    second = factories.create_succeeded_job(prompt="delete-bulk", duration_sec=5)
    bulk = client.delete("/api/jobs", headers=auth_headers)
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["deleted"] >= 1
    assert client.get(f"/api/jobs/{second}", headers=auth_headers).status_code == 404


def test_inpaint_returns_501(client, auth_headers) -> None:
    resp = client.post(
        "/api/inpaint",
        json={"source_job_id": "x", "composition_plan": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 501


def test_stems_returns_501(client, auth_headers, factories) -> None:
    job_id = factories.create_succeeded_job(prompt="stems")
    resp = client.get(f"/api/stems/{job_id}", headers=auth_headers)
    assert resp.status_code == 501

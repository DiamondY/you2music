from __future__ import annotations

import test_env  # noqa: F401


def test_generate_succeeds_in_test_mode(client, auth_headers, factories) -> None:
    job_id = factories.create_job(prompt="hello", duration_sec=5)
    rec = factories.wait_job(job_id, expect_status="succeeded", timeout_s=10.0)
    assert rec["job_id"] == job_id
    assert rec["status"] == "succeeded"
    assert rec.get("audio_url"), rec

    audio = client.get(rec["audio_url"], headers=auth_headers)
    assert audio.status_code == 200, audio.text
    assert int(audio.headers.get("content-length") or "0") > 10


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

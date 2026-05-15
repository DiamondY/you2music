from __future__ import annotations

from pathlib import Path

import test_env  # noqa: F401


def _assert_wav_response(resp) -> None:
    assert resp.status_code == 200, resp.text
    assert resp.content[:4] == b"RIFF"
    assert resp.content[8:12] == b"WAVE"
    assert resp.headers.get("content-type", "").startswith("audio/wav")


def test_private_audio_requires_owner(client, auth_headers, factories) -> None:
    job_id = factories.create_succeeded_job(prompt="priv-audio")
    r = client.get(f"/api/audio/{job_id}")
    assert r.status_code == 403
    ok = client.get(f"/api/audio/{job_id}", headers=auth_headers)
    _assert_wav_response(ok)


def test_other_user_cannot_read_private_job_or_audio(client, multi_auth_headers) -> None:
    owner_headers, other_headers = multi_auth_headers(2)
    create = client.post(
        "/api/generate",
        json={"prompt": "owner-private", "duration_sec": 5, "vocals": True},
        headers=owner_headers,
    )
    assert create.status_code == 200, create.text
    job_id = create.json()["job_id"]

    private_job = client.get(f"/api/jobs/{job_id}", headers=other_headers)
    assert private_job.status_code == 403
    private_audio = client.get(f"/api/audio/{job_id}", headers=other_headers)
    assert private_audio.status_code == 403


def test_published_audio_accessible_without_login(client, factories) -> None:
    job_id = factories.create_published_job(prompt="pub-audio", share_permission="listen_only")
    r = client.get(f"/api/community/{job_id}/audio")
    _assert_wav_response(r)


def test_mp3_compat_route_serves_wav_when_test_mode_outputs_wav(client, auth_headers, factories) -> None:
    job_id = factories.create_succeeded_job(prompt="compat-audio")
    r = client.get(f"/api/audio/{job_id}.mp3", headers=auth_headers)
    _assert_wav_response(r)


def test_audio_path_traversal_blocked(client, auth_headers, factories) -> None:
    from state import STATE

    job_id = factories.create_job(prompt="pth", duration_sec=5)
    # Force job to succeeded but point output_path outside audio_dir.
    outside = Path(__file__).resolve()
    STATE.store.set_status(job_id, status="succeeded", output_path=str(outside))
    r = client.get(f"/api/audio/{job_id}", headers=auth_headers)
    assert r.status_code == 403

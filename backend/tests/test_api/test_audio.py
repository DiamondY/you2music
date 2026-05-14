from __future__ import annotations

from pathlib import Path

import test_env  # noqa: F401


def test_private_audio_requires_owner(client, auth_headers, factories) -> None:
    job_id = factories.create_succeeded_job(prompt="priv-audio")
    r = client.get(f"/api/audio/{job_id}")
    assert r.status_code == 403
    ok = client.get(f"/api/audio/{job_id}", headers=auth_headers)
    assert ok.status_code == 200


def test_published_audio_accessible_without_login(client, factories) -> None:
    job_id = factories.create_published_job(prompt="pub-audio", share_permission="listen_only")
    r = client.get(f"/api/community/{job_id}/audio")
    assert r.status_code == 200


def test_audio_path_traversal_blocked(client, auth_headers, factories) -> None:
    from state import STATE

    job_id = factories.create_job(prompt="pth", duration_sec=5)
    # Force job to succeeded but point output_path outside audio_dir.
    outside = Path(__file__).resolve()
    STATE.store.set_status(job_id, status="succeeded", output_path=str(outside))
    r = client.get(f"/api/audio/{job_id}", headers=auth_headers)
    assert r.status_code == 403


from __future__ import annotations

import time

import pytest

import test_env  # noqa: F401


def test_auth_boundary_validation(client) -> None:
    short_username = client.post(
        "/api/auth/register",
        json={"username": "ab", "password": "pw12345678", "invite_code": "missing"},
    )
    assert short_username.status_code == 422

    long_password = client.post(
        "/api/auth/login",
        json={"username": "someone", "password": "x" * 257},
    )
    assert long_password.status_code == 422


def test_generate_prompt_length_validation(client, auth_headers) -> None:
    too_long = client.post(
        "/api/generate",
        json={"prompt": "x" * 5001, "duration_sec": 5, "vocals": True},
        headers=auth_headers,
    )
    assert too_long.status_code == 422


@pytest.mark.security
def test_serialize_job_recovers_from_invalid_params_json() -> None:
    from deps import _serialize_job
    from storage import JobRecord

    now = int(time.time() * 1000)
    record = JobRecord(
        job_id="bad-json",
        status="succeeded",
        created_at_ms=now,
        updated_at_ms=now,
        provider="acestep",
        prompt="bad json",
        params_json="{not json",
        output_path="/tmp/bad-json.wav",
        error=None,
        song_id=None,
        user_id=1,
        visibility="private",
        share_permission="listen_only",
    )
    assert _serialize_job(record)["params"] == {}

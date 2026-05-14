from __future__ import annotations

import test_env  # noqa: F401
from test_env import TEST_ENV


def _admin_headers(client) -> dict[str, str]:
    r = client.post(
        "/api/auth/login",
        json={"username": TEST_ENV["AI_MUSIC_ADMIN_USERNAME"], "password": TEST_ENV["AI_MUSIC_ADMIN_PASSWORD"]},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_admin_requires_admin_role(client, auth_headers) -> None:
    r = client.get("/api/admin/config", headers=auth_headers)
    assert r.status_code == 403


def test_admin_config_roundtrip_and_schema_validation(client) -> None:
    h = _admin_headers(client)
    r = client.get("/api/admin/config", headers=h)
    assert r.status_code == 200

    bad = client.post("/api/admin/config", headers=h, json={"config": {"unknown_key": 1}})
    assert bad.status_code == 400


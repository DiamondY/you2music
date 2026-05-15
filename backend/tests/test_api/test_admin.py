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


def test_admin_user_and_invite_code_matrix(client, auth_headers) -> None:
    h = _admin_headers(client)
    user = client.get("/api/auth/me", headers=auth_headers).json()["user"]
    user_id = int(user["id"])

    users = client.get("/api/admin/users", headers=h)
    assert users.status_code == 200, users.text
    assert user_id in {int(u["id"]) for u in users.json()["users"]}

    update = client.put(
        f"/api/admin/users/{user_id}",
        headers=h,
        json={"daily_quota": 7, "disabled": False},
    )
    assert update.status_code == 200, update.text
    assert update.json()["user"]["daily_quota"] == 7

    invite = client.post("/api/admin/invite-codes", headers=h)
    assert invite.status_code == 200, invite.text
    code = invite.json()["invite_code"]["code"]
    invites = client.get("/api/admin/invite-codes", headers=h)
    assert invites.status_code == 200, invites.text
    assert code in {item["code"] for item in invites.json()["invite_codes"]}

    delete = client.delete(f"/api/admin/users/{user_id}", headers=h)
    assert delete.status_code == 200, delete.text
    assert delete.json()["ok"] is True

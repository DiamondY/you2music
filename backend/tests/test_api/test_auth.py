from __future__ import annotations

import test_env  # noqa: F401


def test_me_requires_auth(client) -> None:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_register_login_me_flow(client, auth_headers) -> None:
    me = client.get("/api/auth/me", headers=auth_headers)
    assert me.status_code == 200, me.text
    user = me.json()["user"]
    assert user["username"]
    assert user["role"] in ("user", "admin")
    assert "quota" in user


def test_register_requires_invite_code(client) -> None:
    resp = client.post("/api/auth/register", json={"username": "abc", "password": "pw12345678", "invite_code": ""})
    assert resp.status_code in (400, 422)


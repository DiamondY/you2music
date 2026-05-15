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


def test_login_bad_password_returns_401(client, auth_headers) -> None:
    username = client.get("/api/auth/me", headers=auth_headers).json()["user"]["username"]
    resp = client.post("/api/auth/login", json={"username": username, "password": "wrong-password"})
    assert resp.status_code == 401


def test_update_profile_and_password(client, auth_headers) -> None:
    me = client.get("/api/auth/me", headers=auth_headers).json()["user"]
    avatar = "/avatars/test.png"
    update = client.put("/api/auth/me", headers=auth_headers, json={"avatar_path": avatar})
    assert update.status_code == 200, update.text
    assert update.json()["user"]["avatar_path"] == avatar

    password = client.put(
        "/api/auth/password",
        headers=auth_headers,
        json={"old_password": "pw12345678", "new_password": "newpw123456"},
    )
    assert password.status_code == 200, password.text

    old_login = client.post("/api/auth/login", json={"username": me["username"], "password": "pw12345678"})
    assert old_login.status_code == 401

    new_login = client.post("/api/auth/login", json={"username": me["username"], "password": "newpw123456"})
    assert new_login.status_code == 200, new_login.text

from __future__ import annotations

import test_env  # noqa: F401


def test_providers_requires_auth(client) -> None:
    r = client.get("/api/providers")
    assert r.status_code == 401


def test_providers_list_and_random_sample(client, auth_headers) -> None:
    p = client.get("/api/providers", headers=auth_headers)
    assert p.status_code == 200, p.text
    providers = p.json()["providers"]
    assert any(x.get("id") == "acestep" for x in providers)

    s = client.get("/api/random_sample", headers=auth_headers)
    assert s.status_code == 200, s.text
    data = s.json()
    assert data.get("prompt")
    assert data.get("lyrics")
    assert int(data.get("duration") or 0) > 0


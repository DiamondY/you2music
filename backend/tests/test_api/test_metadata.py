from __future__ import annotations

import time

import test_env  # noqa: F401


def _wait_job(client, job_id: str, headers: dict[str, str], *, timeout_s: float = 10.0) -> dict:
    deadline = time.time() + timeout_s
    last: dict | None = None
    while time.time() < deadline:
        resp = client.get(f"/api/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        last = resp.json()
        if last.get("status") == "succeeded":
            return last
        time.sleep(0.05)
    raise AssertionError(f"job did not reach succeeded: {last}")


def test_owner_can_update_succeeded_job_metadata(client, auth_headers, factories) -> None:
    job_id = factories.create_succeeded_job(prompt="original prompt", duration_sec=5)

    resp = client.patch(
        f"/api/jobs/{job_id}/metadata",
        json={
            "title": "  My Song  ",
            "author": " Alice ",
            "album": " First Album ",
            "tags": [" pop ", "", "电子", "xss<script>"],
            "description": "  hello <b>world</b>  ",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()["job"]
    assert job["prompt"].startswith("original prompt")
    assert job["metadata"] == {
        "title": "My Song",
        "author": "Alice",
        "album": "First Album",
        "tags": ["pop", "电子", "xss<script>"],
        "description": "hello <b>world</b>",
    }

    fetched = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["metadata"]["title"] == "My Song"


def test_metadata_update_requires_owner_even_for_admin(client, multi_auth_headers) -> None:
    owner_headers, other_headers = multi_auth_headers(2)
    create = client.post(
        "/api/generate",
        json={"prompt": "owner-only-metadata", "duration_sec": 5, "vocals": True},
        headers=owner_headers,
    )
    assert create.status_code == 200, create.text
    job_id = create.json()["job_id"]
    _wait_job(client, job_id, owner_headers)

    other = client.patch(
        f"/api/jobs/{job_id}/metadata",
        json={"title": "stolen"},
        headers=other_headers,
    )
    assert other.status_code == 403

    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": test_env.TEST_ENV["AI_MUSIC_ADMIN_USERNAME"],
            "password": test_env.TEST_ENV["AI_MUSIC_ADMIN_PASSWORD"],
        },
    )
    assert admin_login.status_code == 200, admin_login.text
    admin = client.patch(
        f"/api/jobs/{job_id}/metadata",
        json={"title": "admin-edit"},
        headers={"Authorization": f"Bearer {admin_login.json()['token']}"},
    )
    assert admin.status_code == 403


def test_metadata_update_requires_succeeded_job(client, auth_headers, factories) -> None:
    job_id = factories.create_job(prompt="queued-metadata", duration_sec=5)
    resp = client.patch(
        f"/api/jobs/{job_id}/metadata",
        json={"title": "too early"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_published_community_includes_metadata(client, auth_headers, factories) -> None:
    job_id = factories.create_published_job(prompt="community-metadata", share_permission="listen_only")
    update = client.patch(
        f"/api/jobs/{job_id}/metadata",
        json={"title": "Community Title", "author": "Alice", "album": "Album", "tags": ["tag1", "tag2"]},
        headers=auth_headers,
    )
    assert update.status_code == 200, update.text

    community = client.get("/api/community?offset=0&limit=50")
    assert community.status_code == 200, community.text
    item = next(j for j in community.json()["jobs"] if j["job_id"] == job_id)
    assert item["metadata"]["title"] == "Community Title"
    assert item["metadata"]["author"] == "Alice"
    assert item["metadata"]["album"] == "Album"
    assert item["metadata"]["tags"] == ["tag1", "tag2"]

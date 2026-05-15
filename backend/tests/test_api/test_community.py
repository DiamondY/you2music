from __future__ import annotations

import test_env  # noqa: F401


def test_community_list_requires_no_auth_for_published_jobs(client, factories) -> None:
    job_id = factories.create_published_job(prompt="pub-listen", share_permission="listen_only")
    r = client.get("/api/community?offset=0&limit=50")
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    ids = {j["job_id"] for j in jobs}
    assert job_id in ids
    item = next(j for j in jobs if j["job_id"] == job_id)
    assert item["visibility"] == "published"
    assert item["share_permission"] == "listen_only"
    assert item.get("download_url") is None


def test_community_downloadable_has_download_url(client, factories) -> None:
    job_id = factories.create_published_job(prompt="pub-dl", share_permission="downloadable")
    r = client.get("/api/community?offset=0&limit=50")
    assert r.status_code == 200, r.text
    item = next(j for j in r.json()["jobs"] if j["job_id"] == job_id)
    assert item.get("download_url")


def test_unpublish_removes_job_from_community(client, auth_headers, factories) -> None:
    job_id = factories.create_published_job(prompt="pub-unpublish", share_permission="listen_only")
    r = client.post(f"/api/jobs/{job_id}/unpublish", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["job"]["visibility"] == "private"

    community = client.get("/api/community?offset=0&limit=50")
    assert community.status_code == 200, community.text
    assert job_id not in {j["job_id"] for j in community.json()["jobs"]}


def test_invalid_share_permission_rejected(client, auth_headers, factories) -> None:
    job_id = factories.create_succeeded_job(prompt="bad-share")
    r = client.post(
        f"/api/jobs/{job_id}/publish",
        json={"share_permission": "edit"},
        headers=auth_headers,
    )
    assert r.status_code == 400

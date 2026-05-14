"""Tests for JobStore (storage.py)."""

from __future__ import annotations

import json
import time

from storage import ApiLogStore, JobStore


class TestJobStore:
    """CRUD and query tests for JobStore."""

    def test_create_and_get_job(self, job_store: JobStore) -> None:
        """create_job → get returns the job with correct fields."""
        job_id = job_store.create_job(
            provider="acestep",
            prompt="test prompt",
            params={"duration_sec": 30, "vocals": True},
            user_id=1,
        )
        assert job_id
        assert len(job_id) == 32  # uuid4 hex

        rec = job_store.get(job_id)
        assert rec is not None
        assert rec.job_id == job_id
        assert rec.status == "queued"
        assert rec.provider == "acestep"
        assert rec.prompt == "test prompt"
        assert rec.user_id == 1
        assert rec.error is None
        assert rec.output_path is None

    def test_set_status_succeeded(self, job_store: JobStore) -> None:
        """set_status updates status, output_path, and timestamps."""
        job_id = job_store.create_job(
            provider="acestep",
            prompt="p",
            params={},
        )
        job_store.set_status(job_id, status="succeeded", output_path="/tmp/out.mp3")
        rec = job_store.get(job_id)
        assert rec is not None
        assert rec.status == "succeeded"
        assert rec.output_path == "/tmp/out.mp3"
        assert rec.updated_at_ms >= rec.created_at_ms

    def test_set_status_failed(self, job_store: JobStore) -> None:
        """set_status sets error field on failure."""
        job_id = job_store.create_job(provider="acestep", prompt="p", params={})
        job_store.set_status(job_id, status="failed", error="something broke")
        rec = job_store.get(job_id)
        assert rec is not None
        assert rec.status == "failed"
        assert rec.error == "something broke"

    def test_get_nonexistent(self, job_store: JobStore) -> None:
        """get returns None for unknown job_id."""
        assert job_store.get("nonexistent") is None

    def test_list_recent(self, job_store: JobStore) -> None:
        """list_recent returns jobs ordered by created_at_ms DESC, job_id ASC."""
        ids: list[str] = []
        for i in range(5):
            jid = job_store.create_job(provider="acestep", prompt=f"p{i}", params={})
            ids.append(jid)

        results = job_store.list_recent(limit=3, include_all=True)
        assert len(results) == 3

        # Build expected ordering based on the store's ordering contract.
        # This makes the test stable even when multiple rows share the same millisecond timestamp.
        created: list[tuple[int, str]] = []
        for jid in ids:
            rec = job_store.get(jid)
            assert rec is not None
            created.append((int(rec.created_at_ms), str(rec.job_id)))

        # storage.JobStore.list_recent uses: ORDER BY created_at_ms DESC, job_id ASC
        created_sorted = sorted(created, key=lambda x: (-x[0], x[1]))
        expected_ids = [jid for _, jid in created_sorted[:3]]
        assert [r.job_id for r in results] == expected_ids

    def test_list_page_pagination(self, job_store: JobStore) -> None:
        """list_page with offset/limit returns correct slice."""
        for i in range(10):
            job_store.create_job(provider="acestep", prompt=f"p{i}", params={})

        page1 = job_store.list_page(offset=0, limit=3)
        page2 = job_store.list_page(offset=3, limit=3)
        page3 = job_store.list_page(offset=6, limit=3)
        page4 = job_store.list_page(offset=9, limit=3)

        assert len(page1) == 3
        assert len(page2) == 3
        assert len(page3) == 3
        assert len(page4) == 1
        # No overlap
        all_ids = {r.job_id for r in page1 + page2 + page3 + page4}
        assert len(all_ids) == 10

    def test_count_jobs(self, job_store: JobStore) -> None:
        """count_jobs returns correct total."""
        assert job_store.count_jobs() == 0
        for _ in range(7):
            job_store.create_job(provider="acestep", prompt="p", params={})
        assert job_store.count_jobs() == 7

    def test_count_jobs_with_status_filter(self, job_store: JobStore) -> None:
        """count_jobs filters by status when provided."""
        j1 = job_store.create_job(provider="acestep", prompt="p", params={})
        j2 = job_store.create_job(provider="acestep", prompt="p", params={})
        job_store.set_status(j1, status="succeeded", output_path="/tmp/a.mp3")
        job_store.set_status(j2, status="failed", error="err")

        assert job_store.count_jobs(status="queued") == 0
        assert job_store.count_jobs(status="succeeded") == 1
        assert job_store.count_jobs(status="failed") == 1
        assert job_store.count_jobs() == 2  # no filter → all

    def test_list_page_with_status_filter(self, job_store: JobStore) -> None:
        """list_page filters by status."""
        j1 = job_store.create_job(provider="acestep", prompt="ok", params={})
        j2 = job_store.create_job(provider="acestep", prompt="fail", params={})
        job_store.set_status(j1, status="succeeded", output_path="/tmp/a.mp3")
        job_store.set_status(j2, status="failed", error="err")

        succeeded = job_store.list_page(offset=0, limit=10, status="succeeded")
        assert len(succeeded) == 1
        assert succeeded[0].job_id == j1

        failed = job_store.list_page(offset=0, limit=10, status="failed")
        assert len(failed) == 1
        assert failed[0].job_id == j2

    def test_delete_existing(self, job_store: JobStore) -> None:
        """delete removes the job and returns True."""
        jid = job_store.create_job(provider="acestep", prompt="p", params={})
        assert job_store.delete(jid) is True
        assert job_store.get(jid) is None
        assert job_store.count_jobs() == 0

    def test_delete_nonexistent(self, job_store: JobStore) -> None:
        """delete returns False for unknown job_id."""
        assert job_store.delete("nonexistent") is False

    def test_delete_all(self, job_store: JobStore) -> None:
        """delete_all removes terminal jobs only (succeeded/failed)."""
        # Two terminal jobs
        j1 = job_store.create_job(provider="acestep", prompt="ok", params={})
        j2 = job_store.create_job(provider="acestep", prompt="fail", params={})
        job_store.set_status(j1, status="succeeded", output_path="/tmp/a.mp3")
        job_store.set_status(j2, status="failed", error="err")
        # One queued job should be kept to avoid orphaning workers in bulk deletes.
        _queued = job_store.create_job(provider="acestep", prompt="q", params={})

        assert job_store.delete_all() == 2
        assert job_store.count_jobs(include_all=True) == 1

    def test_delete_for_user(self, job_store: JobStore) -> None:
        """delete_for_user removes terminal jobs for that user only."""
        u1_ok = job_store.create_job(provider="acestep", prompt="u1", params={}, user_id=1)
        u1_fail = job_store.create_job(provider="acestep", prompt="u1b", params={}, user_id=1)
        u1_q = job_store.create_job(provider="acestep", prompt="u1q", params={}, user_id=1)
        u2_ok = job_store.create_job(provider="acestep", prompt="u2", params={}, user_id=2)
        job_store.set_status(u1_ok, status="succeeded", output_path="/tmp/u1.mp3")
        job_store.set_status(u1_fail, status="failed", error="err")
        job_store.set_status(u2_ok, status="succeeded", output_path="/tmp/u2.mp3")

        assert job_store.delete_for_user(user_id=1) == 2
        # Remaining: u1 queued + u2 succeeded
        assert job_store.count_jobs(include_all=True) == 2
        remaining = job_store.list_recent(limit=10, include_all=True)
        remaining_ids = {r.job_id for r in remaining}
        assert u1_q in remaining_ids
        assert u2_ok in remaining_ids

    def test_params_json_roundtrip(self, job_store: JobStore) -> None:
        """params are stored as JSON and can be parsed back."""
        params = {"duration_sec": 45, "vocals": False, "lyrics": "hello world"}
        jid = job_store.create_job(provider="acestep", prompt="p", params=params)
        rec = job_store.get(jid)
        assert rec is not None
        parsed = json.loads(rec.params_json)
        assert parsed == params

    def test_list_page_boundary_clamping(self, job_store: JobStore) -> None:
        """list_page clamps invalid offset/limit values."""
        for _ in range(3):
            job_store.create_job(provider="acestep", prompt="p", params={})
        # Negative offset → 0
        result = job_store.list_page(offset=-5, limit=200)
        assert len(result) == 3

    def test_audio_upload_metadata_and_expiry(self, job_store: JobStore) -> None:
        """audio_uploads table stores per-user records and supports expiry listing."""
        now_ms = int(time.time() * 1000)
        job_store.create_audio_upload(
            user_id=1,
            upload_id="a" * 32,
            fmt="mp3",
            filename="a.mp3",
            size_bytes=123,
            expires_at_ms=now_ms + 60_000,
        )
        rec = job_store.get_audio_upload(user_id=1, upload_id="a" * 32)
        assert rec is not None
        assert rec["user_id"] == 1
        assert rec["upload_id"] == "a" * 32
        assert rec["fmt"] == "mp3"
        assert rec["deleted_at_ms"] is None

        # Wrong user cannot see it.
        assert job_store.get_audio_upload(user_id=2, upload_id="a" * 32) is None

        # Expired listing should include items at/under now.
        job_store.create_audio_upload(
            user_id=2,
            upload_id="b" * 32,
            fmt="wav",
            filename="b.wav",
            size_bytes=456,
            expires_at_ms=now_ms - 1,
        )
        expired = job_store.list_expired_audio_uploads(now_ms=now_ms, limit=10)
        ids = {(r["user_id"], r["upload_id"]) for r in expired}
        assert (2, "b" * 32) in ids


class TestApiLogStore:
    def test_backfill_http_status_from_legacy_error(self, tmp_db_path) -> None:
        """Legacy rows with http_status=NULL get backfilled from error text."""
        store = ApiLogStore(tmp_db_path)
        store.init()
        store.log(
            job_id="job1",
            provider="acestep",
            method="POST",
            endpoint="/v1/chat/completions",
            request_body="{}",
            response_body=None,
            http_status=None,
            elapsed_ms=123,
            api_key_hint=None,
            error='ACE-Step API error 500: {"error":{"message":"Internal server error","type":"server_error"}}',
        )
        # Filter 5xx should include it after backfill.
        logs = store.list_page(http_status_min=500, http_status_max=599, limit=20)
        assert len(logs) == 1
        assert logs[0]["http_status"] == 500

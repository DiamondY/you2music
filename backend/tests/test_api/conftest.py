from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator

import pytest
from fastapi.testclient import TestClient

# Defensive import: ensure module-level env defaults are applied before importing backend modules.
_test_api_dir = Path(__file__).resolve().parent
if str(_test_api_dir) not in sys.path:
    sys.path.insert(0, str(_test_api_dir))

import test_env  # noqa: E402,F401
from test_env import TEST_ENV  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_test_env() -> Any:
    """Set env vars before STATE is created at module import time."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        os.environ.update(TEST_ENV)
        os.environ["AI_MUSIC_DATA_DIR"] = str(tmp)
        yield


@pytest.fixture(scope="session")
def app() -> Any:
    assert os.environ.get("AI_MUSIC_TEST_MODE") == "1", "Test env not initialized"
    assert os.environ.get("AI_MUSIC_JWT_SECRET"), "AI_MUSIC_JWT_SECRET not set"
    assert os.environ.get("AI_MUSIC_DATA_DIR"), "AI_MUSIC_DATA_DIR not set"
    from main import app as _app
    return _app


@pytest.fixture(scope="session")
def client(app: Any) -> Iterator[TestClient]:
    # IMPORTANT: Use context manager so FastAPI startup/shutdown events run.
    # Without this, background job workers may not start and jobs will stay "queued".
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def test_id() -> str:
    """Session-level unique id to avoid username collisions across runs."""
    return uuid.uuid4().hex[:8]


@pytest.fixture(autouse=True)
def db_clean() -> Any:
    """Clear test tables between tests (keeps admin user)."""
    from state import STATE

    STATE.store.clear_for_tests()
    STATE.user_store.clear_for_tests(exclude_admin=True)
    yield


def _register_user(client: TestClient, *, username: str, password: str) -> dict[str, Any]:
    admin_login = client.post(
        "/api/auth/login",
        json={"username": TEST_ENV["AI_MUSIC_ADMIN_USERNAME"], "password": TEST_ENV["AI_MUSIC_ADMIN_PASSWORD"]},
    )
    assert admin_login.status_code == 200, admin_login.text
    admin_token = admin_login.json()["token"]
    invite = client.post("/api/admin/invite-codes", headers={"Authorization": f"Bearer {admin_token}"})
    assert invite.status_code == 200, invite.text
    invite_code = invite.json()["invite_code"]["code"]

    reg = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "invite_code": invite_code},
    )
    assert reg.status_code == 200, reg.text
    return reg.json()


@pytest.fixture
def auth_headers(client: TestClient, test_id: str) -> dict[str, str]:
    username = f"u_{test_id}_{uuid.uuid4().hex[:8]}"
    password = "pw12345678"
    data = _register_user(client, username=username, password=password)
    token = data["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def multi_auth_headers(client: TestClient, test_id: str) -> Callable[[int], list[dict[str, str]]]:
    """Factory: create N independent users for concurrency tests."""

    def _make(n: int) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for _ in range(int(n)):
            username = f"u_{test_id}_{uuid.uuid4().hex[:10]}"
            password = "pw12345678"
            data = _register_user(client, username=username, password=password)
            out.append({"Authorization": f"Bearer {data['token']}"})
        return out

    return _make


@pytest.fixture
def factories(client: TestClient, auth_headers: dict[str, str]):
    class Factories:
        def __init__(self, client: TestClient, headers: dict[str, str]) -> None:
            self._client = client
            self._headers = headers

        def create_job(self, prompt: str = "test song", duration_sec: int = 30, **kwargs: Any) -> str:
            payload = {"prompt": prompt, "duration_sec": int(duration_sec), "vocals": True}
            payload.update(kwargs)
            resp = self._client.post("/api/generate", json=payload, headers=self._headers)
            assert resp.status_code == 200, resp.text
            return str(resp.json()["job_id"])

        def wait_job(self, job_id: str, *, expect_status: str = "succeeded", timeout_s: float = 5.0) -> dict[str, Any]:
            deadline = time.time() + float(timeout_s)
            last: dict[str, Any] | None = None
            while time.time() < deadline:
                r = self._client.get(f"/api/jobs/{job_id}", headers=self._headers)
                assert r.status_code == 200, r.text
                last = r.json()
                if last.get("status") == expect_status:
                    return last
                time.sleep(0.05)
            raise AssertionError(f"job did not reach {expect_status}: {last}")

        def create_succeeded_job(self, prompt: str = "succeeded song", **kwargs: Any) -> str:
            job_id = self.create_job(prompt=prompt, **kwargs)
            self.wait_job(job_id, expect_status="succeeded", timeout_s=10.0)
            return job_id

        def create_published_job(self, prompt: str = "published song", share_permission: str = "listen_only") -> str:
            job_id = self.create_succeeded_job(prompt=prompt)
            resp = self._client.post(
                f"/api/jobs/{job_id}/publish",
                json={"share_permission": share_permission},
                headers=self._headers,
            )
            assert resp.status_code == 200, resp.text
            return job_id

    return Factories(client, auth_headers)


@pytest.fixture
def read_sse_event() -> Callable[[AsyncIterator[str]], Any]:
    """Factory fixture: read a single SSE event from an aiter_lines() iterator."""

    async def _read_sse_event(aiter: AsyncIterator[str], *, timeout_s: float = 5.0) -> dict[str, Any]:
        event: dict[str, Any] = {}

        async def _read_one() -> dict[str, Any]:
            async for line in aiter:
                line = line.strip()
                if line == "":
                    # empty line = event boundary
                    if event:
                        return event
                    continue
                if line.startswith("event:"):
                    event["event"] = line[6:].strip()
                elif line.startswith("data:"):
                    event.setdefault("data", "")
                    event["data"] += line[5:].strip()
            return event

        try:
            return await asyncio.wait_for(_read_one(), timeout=float(timeout_s))
        except asyncio.TimeoutError:
            return {}

    return _read_sse_event

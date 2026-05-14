from __future__ import annotations

import asyncio
import test_env  # noqa: F401

import pytest
from test_env import TEST_ENV


def test_sse_requires_auth(client) -> None:
    r = client.get("/api/events")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_sse_hello_event(app) -> None:
    """Read the initial hello frame without relying on HTTP client streaming semantics.

    Some TestClient/ASGITransport combinations buffer StreamingResponse bodies and can
    hang on infinite streams. The contract we care about here is:
      - endpoint uses SSE media type
      - first frame is `event: hello`
    """
    from main import events as events_endpoint
    from state import STATE
    from starlette.requests import Request

    username = str(TEST_ENV["AI_MUSIC_ADMIN_USERNAME"])
    admin = STATE.user_store.get_by_username(username)
    assert admin is not None

    async def _receive():
        await asyncio.sleep(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/events",
        "raw_path": b"/api/events",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope, receive=_receive)

    resp = await events_endpoint(request, current_user=admin)
    assert getattr(resp, "media_type", "") == "text/event-stream"

    # Read the first yielded chunk, then close to trigger unsubscribe cleanup.
    first = await resp.body_iterator.__anext__()
    try:
        assert b"event: hello" in first, first
    finally:
        try:
            await resp.body_iterator.aclose()
        except Exception:
            pass

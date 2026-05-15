from __future__ import annotations

import asyncio

import httpx
import pytest

import test_env  # noqa: F401


@pytest.mark.asyncio
async def test_concurrent_generate_requests_keep_independent_quota(
    app,
    client,
    multi_auth_headers,
) -> None:
    headers_list = multi_auth_headers(4)
    transport = httpx.ASGITransport(app=app)

    async def create_one(headers: dict[str, str], idx: int) -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await ac.post(
                "/api/generate",
                json={"prompt": f"concurrent {idx}", "duration_sec": 5, "vocals": True},
                headers=headers,
            )

    responses = await asyncio.gather(*(create_one(headers, idx) for idx, headers in enumerate(headers_list)))
    assert [r.status_code for r in responses] == [200, 200, 200, 200]

    for headers in headers_list:
        quota = client.get("/api/auth/me", headers=headers).json()["user"]["quota"]
        assert int(quota["used"]) == 1
        assert int(quota["remaining"]) == int(quota["limit"]) - 1

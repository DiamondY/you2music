from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ReplicateResult:
    audio_url: str
    prediction_id: str


class ReplicateClient:
    def __init__(self, *, api_token: str, base_url: str, timeout_s: float) -> None:
        if not api_token:
            raise ValueError("REPLICATE_API_TOKEN is required for replicate provider.")
        self._token = api_token
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    async def create_prediction(self, *, version: str, input_json: dict[str, Any]) -> str:
        url = f"{self._base}/v1/predictions"
        # Replicate uses Bearer auth in recent docs, but older clients used "Token".
        # Try Bearer first, then fall back to Token only on 401/403.
        headers_primary = {"Authorization": f"Bearer {self._token}"}
        headers_fallback = {"Authorization": f"Token {self._token}"}
        body = {"version": version, "input": input_json}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers_primary, json=body)
            if resp.status_code in (401, 403):
                resp = await client.post(url, headers=headers_fallback, json=body)
            resp.raise_for_status()
            data = resp.json()
            pid = data.get("id")
            if not pid:
                raise RuntimeError(f"replicate create missing id: {data}")
            return str(pid)

    async def poll_until_done(self, *, prediction_id: str, poll_interval_s: float = 1.0, max_wait_s: float = 300.0) -> dict[str, Any]:
        url = f"{self._base}/v1/predictions/{prediction_id}"
        headers_primary = {"Authorization": f"Bearer {self._token}"}
        headers_fallback = {"Authorization": f"Token {self._token}"}
        deadline = asyncio.get_event_loop().time() + max_wait_s
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while True:
                resp = await client.get(url, headers=headers_primary)
                if resp.status_code in (401, 403):
                    resp = await client.get(url, headers=headers_fallback)
                resp.raise_for_status()
                data = resp.json()
                status = str(data.get("status") or "").lower()
                if status == "succeeded":
                    return data
                if status in ("failed", "canceled"):
                    raise RuntimeError(f"replicate prediction failed: {data}")
                if asyncio.get_event_loop().time() > deadline:
                    raise TimeoutError("replicate prediction timed out")
                await asyncio.sleep(poll_interval_s)

    @staticmethod
    def extract_audio_url(result_json: dict[str, Any]) -> str:
        out = result_json.get("output")
        if isinstance(out, str) and out.startswith("http"):
            return out
        if isinstance(out, list) and out:
            first = out[0]
            if isinstance(first, str) and first.startswith("http"):
                return first
        raise RuntimeError(f"replicate output missing audio url: {result_json}")

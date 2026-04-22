from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class FalResult:
    audio_url: str
    request_id: str


class FalQueueClient:
    """
    Minimal fal.ai queue client.

    We use the queue API so we can poll for completion and then download the audio URL.
    """

    def __init__(self, *, key: str, queue_base_url: str, timeout_s: float) -> None:
        if not key:
            raise ValueError("FAL_KEY is required for fal provider.")
        self._key = key
        self._base = queue_base_url.rstrip("/")
        self._timeout = timeout_s

    async def submit(self, *, model_id: str, input_json: dict[str, Any]) -> str:
        url = f"{self._base}/{model_id}"
        headers = {"Authorization": f"Key {self._key}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=input_json)
            resp.raise_for_status()
            data = resp.json()
            request_id = data.get("request_id") or data.get("id")
            if not request_id:
                raise RuntimeError(f"fal queue submit missing request_id: {data}")
            return str(request_id)

    async def poll_until_done(
        self,
        *,
        model_id: str,
        request_id: str,
        poll_interval_s: float = 1.0,
        max_wait_s: float = 300.0,
    ) -> dict[str, Any]:
        url = f"{self._base}/{model_id}/requests/{request_id}"
        headers = {"Authorization": f"Key {self._key}"}
        deadline = asyncio.get_event_loop().time() + max_wait_s
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while True:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                status = str(data.get("status") or "").upper()
                if status in ("COMPLETED", "SUCCESS", "SUCCEEDED"):
                    return data
                if status in ("FAILED", "ERROR"):
                    raise RuntimeError(f"fal request failed: {data}")
                if asyncio.get_event_loop().time() > deadline:
                    raise TimeoutError("fal request timed out")
                await asyncio.sleep(poll_interval_s)

    @staticmethod
    def extract_audio_url(result_json: dict[str, Any]) -> str:
        # Typical result has `audio` object with `url`
        audio = result_json.get("audio")
        if isinstance(audio, dict) and isinstance(audio.get("url"), str):
            return audio["url"]
        # Some fal models return `output` wrapper
        output = result_json.get("output")
        if isinstance(output, dict):
            audio2 = output.get("audio")
            if isinstance(audio2, dict) and isinstance(audio2.get("url"), str):
                return audio2["url"]
        raise RuntimeError(f"fal result missing audio url: {result_json}")


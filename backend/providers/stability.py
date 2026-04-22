from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class StabilityResult:
    audio_bytes: bytes
    content_type: str


class StabilityAudioClient:
    """
    Stability official API client (experimental).

    Stability has multiple API surfaces; Stable Audio endpoints may evolve.
    We try to be resilient by:
    - sending multipart form fields
    - accepting either direct audio/* responses or JSON with a URL we can fetch.
    """

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("STABILITY_API_KEY is required for stability provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    async def text_to_audio(
        self,
        *,
        endpoint_path: str,
        prompt: str,
        seconds_total: int | None,
        seed: int | None,
        steps: int | None,
        cfg_scale: float | None,
        output_format: str | None,
    ) -> StabilityResult:
        url = f"{self._base}{endpoint_path}"
        headers = {"Authorization": f"Bearer {self._key}"}

        data: dict[str, str] = {"prompt": prompt}
        if seconds_total is not None:
            data["seconds_total"] = str(int(seconds_total))
        if seed is not None:
            data["seed"] = str(int(seed))
        if steps is not None:
            data["steps"] = str(int(steps))
        if cfg_scale is not None:
            data["cfg_scale"] = str(float(cfg_scale))
        if output_format:
            data["output_format"] = output_format

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, data=data)
            # Some stability endpoints return binary audio on 200, JSON error otherwise.
            if resp.status_code >= 400:
                raise RuntimeError(f"stability HTTP {resp.status_code}: {resp.text}")

            ctype = resp.headers.get("content-type", "")
            if ctype.startswith("audio/") or ctype in ("application/octet-stream",):
                return StabilityResult(audio_bytes=resp.content, content_type=ctype or "application/octet-stream")

            # Try JSON response with URL(s)
            try:
                j = resp.json()
            except Exception:
                return StabilityResult(audio_bytes=resp.content, content_type=ctype or "application/octet-stream")

            url_candidate = None
            if isinstance(j, dict):
                for k in ("audio_url", "url", "result_url", "output_url"):
                    if isinstance(j.get(k), str) and j[k].startswith("http"):
                        url_candidate = j[k]
                        break
                if url_candidate is None and isinstance(j.get("audio"), dict) and isinstance(j["audio"].get("url"), str):
                    url_candidate = j["audio"]["url"]

            if not url_candidate:
                raise RuntimeError(f"stability response missing audio url: {j}")

            dl = await client.get(url_candidate)
            dl.raise_for_status()
            return StabilityResult(
                audio_bytes=dl.content,
                content_type=dl.headers.get("content-type", "application/octet-stream"),
            )


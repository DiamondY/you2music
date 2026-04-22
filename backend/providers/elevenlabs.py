from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ElevenLabsResult:
    audio_bytes: bytes
    content_type: str
    song_id: str | None


class ElevenLabsMusicProvider:
    name = "elevenlabs"

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is required for the ElevenLabs provider.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s

    async def compose(
        self,
        *,
        prompt: str | None,
        composition_plan: dict[str, Any] | None,
        music_length_ms: int | None,
        force_instrumental: bool,
        seed: int | None,
        model_id: str | None,
        output_format: str,
    ) -> ElevenLabsResult:
        url = f"{self._base_url}/v1/music"
        headers = {"xi-api-key": self._api_key}
        params = {"output_format": output_format} if output_format else None

        body: dict[str, Any] = {"force_instrumental": force_instrumental}
        if composition_plan is not None:
            body["composition_plan"] = composition_plan
        else:
            body["prompt"] = prompt or ""
        if music_length_ms is not None:
            body["music_length_ms"] = int(music_length_ms)
        if seed is not None:
            body["seed"] = int(seed)
        if model_id:
            body["model_id"] = model_id

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, params=params, json=body)
            resp.raise_for_status()
            song_id = resp.headers.get("song-id")
            content_type = resp.headers.get("content-type", "audio/mpeg")
            return ElevenLabsResult(audio_bytes=resp.content, content_type=content_type, song_id=song_id)

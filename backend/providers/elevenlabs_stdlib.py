from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ElevenLabsStdlibResult:
    audio_bytes: bytes
    content_type: str
    song_id: str | None


@dataclass(frozen=True)
class ElevenLabsStdlibStemsResult:
    vocals_bytes: bytes | None
    instrumental_bytes: bytes | None
    vocals_content_type: str
    instrumental_content_type: str


class ElevenLabsMusicProviderStdlib:
    name = "elevenlabs"

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is required for the ElevenLabs provider.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s

    def compose(
        self,
        *,
        prompt: str | None,
        composition_plan: dict[str, Any] | None,
        music_length_ms: int | None,
        force_instrumental: bool,
        seed: int | None,
        model_id: str | None,
        output_format: str,
    ) -> ElevenLabsStdlibResult:
        query = {"output_format": output_format} if output_format else {}
        url = f"{self._base_url}/v1/music"
        if query:
            url = url + "?" + urllib.parse.urlencode(query)

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

        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            method="POST",
            data=data,
            headers={
                "xi-api-key": self._api_key,
                "content-type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                audio = resp.read()
                content_type = resp.headers.get("content-type", "audio/mpeg")
                song_id = resp.headers.get("song-id")
                return ElevenLabsStdlibResult(audio_bytes=audio, content_type=content_type, song_id=song_id)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            raise RuntimeError(f"ElevenLabs HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"ElevenLabs request failed: {e}") from e

    def get_stems(
        self,
        *,
        song_id: str,
        output_format: str = "mp3_192kbps",
    ) -> ElevenLabsStdlibStemsResult:
        """Separate vocals and instrumental from a generated song.

        Args:
            song_id: The song ID returned from a previous compose call
            output_format: Output format for the stems

        Returns:
            ElevenLabsStdlibStemsResult with vocals and instrumental audio bytes
        """
        url = f"{self._base_url}/v1/music/{song_id}/stems?output_format={urllib.parse.quote(output_format)}"
        req = urllib.request.Request(
            url=url,
            method="GET",
            headers={
                "xi-api-key": self._api_key,
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            raise RuntimeError(f"ElevenLabs Stems HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"ElevenLabs Stems request failed: {e}") from e

        vocals_bytes = None
        instrumental_bytes = None
        vocals_content_type = "audio/mpeg"
        instrumental_content_type = "audio/mpeg"

        # Download stems from URLs
        if data.get("vocals_url"):
            with urllib.request.urlopen(data["vocals_url"], timeout=self._timeout) as r:
                vocals_bytes = r.read()
                vocals_content_type = r.headers.get("content-type", "audio/mpeg")

        if data.get("instrumental_url"):
            with urllib.request.urlopen(data["instrumental_url"], timeout=self._timeout) as r:
                instrumental_bytes = r.read()
                instrumental_content_type = r.headers.get("content-type", "audio/mpeg")

        return ElevenLabsStdlibStemsResult(
            vocals_bytes=vocals_bytes,
            instrumental_bytes=instrumental_bytes,
            vocals_content_type=vocals_content_type,
            instrumental_content_type=instrumental_content_type,
        )

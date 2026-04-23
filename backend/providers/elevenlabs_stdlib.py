from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


_ELEVENLABS_OUTPUT_FORMAT_ALIASES: dict[str, str] = {
    # Legacy values used by older versions of this project.
    "mp3_128kbps": "mp3_44100_128",
    "mp3_192kbps": "mp3_44100_192",
}

DEFAULT_ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_192"


def _normalize_elevenlabs_output_format(output_format: str | None) -> str | None:
    if output_format is None:
        return None
    fmt = str(output_format).strip()
    if not fmt:
        return None
    return _ELEVENLABS_OUTPUT_FORMAT_ALIASES.get(fmt, fmt)


def _friendly_plan_error(detail_text: str) -> str | None:
    """Return a friendly Chinese error for common account/plan limitations."""
    try:
        data = json.loads(detail_text)
    except Exception:
        return None

    detail = data.get("detail") if isinstance(data, dict) else None
    if not isinstance(detail, dict):
        return None
    code = str(detail.get("code") or "").strip()
    msg = str(detail.get("message") or "").strip()
    request_id = str(detail.get("request_id") or "").strip()

    if code == "paid_plan_required":
        tail = f"（request_id={request_id}）" if request_id else ""
        return (
            "ElevenLabs Music API 需要付费套餐，免费账号无法使用。"
            "请升级 ElevenLabs 付费计划，或在 UI 中切换到其他 provider（fal/replicate/stability/suno）。"
            f"{tail}"
        )

    if msg and "not available for free users" in msg:
        tail = f"（request_id={request_id}）" if request_id else ""
        return (
            "ElevenLabs Music API 对免费账号不可用。"
            "请升级 ElevenLabs 付费计划，或切换到其他 provider。"
            f"{tail}"
        )
    return None


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


@dataclass(frozen=True)
class ElevenLabsStdlibInpaintResult:
    audio_bytes: bytes
    content_type: str
    song_id: str | None


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
        fmt = _normalize_elevenlabs_output_format(output_format)
        query = {"output_format": fmt} if fmt else {}
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
            if e.code == 402:
                friendly = _friendly_plan_error(detail)
                if friendly:
                    raise RuntimeError(friendly) from e
            raise RuntimeError(f"ElevenLabs HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"ElevenLabs request failed: {e}") from e

    def get_stems(
        self,
        *,
        song_id: str,
        output_format: str = DEFAULT_ELEVENLABS_OUTPUT_FORMAT,
    ) -> ElevenLabsStdlibStemsResult:
        """Separate vocals and instrumental from a generated song.

        Args:
            song_id: The song ID returned from a previous compose call
            output_format: Output format for the stems

        Returns:
            ElevenLabsStdlibStemsResult with vocals and instrumental audio bytes
        """
        fmt = _normalize_elevenlabs_output_format(output_format)
        url = f"{self._base_url}/v1/music/{song_id}/stems"
        if fmt:
            url = url + "?output_format=" + urllib.parse.quote(fmt)
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
            if e.code == 402:
                friendly = _friendly_plan_error(detail)
                if friendly:
                    raise RuntimeError(friendly) from e
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

    def compose_detailed(
        self,
        *,
        prompt: str | None,
        composition_plan: dict[str, Any] | None,
        music_length_ms: int | None,
        force_instrumental: bool,
        seed: int | None,
        model_id: str | None,
        output_format: str,
        store_for_inpainting: bool = False,
    ) -> ElevenLabsStdlibResult:
        """Compose music with detailed options including store_for_inpainting.

        This endpoint stores the song for later inpainting operations (Enterprise-only).

        Args:
            store_for_inpainting: If True, stores the song for later inpainting

        Returns:
            ElevenLabsStdlibResult with audio bytes and song_id
        """
        fmt = _normalize_elevenlabs_output_format(output_format)
        query = {"output_format": fmt} if fmt else {}
        url = f"{self._base_url}/v1/music/detailed"
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
        if store_for_inpainting:
            body["store_for_inpainting"] = True

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
            if e.code == 402:
                friendly = _friendly_plan_error(detail)
                if friendly:
                    raise RuntimeError(friendly) from e
            raise RuntimeError(f"ElevenLabs Detailed HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"ElevenLabs Detailed request failed: {e}") from e

    def inpaint(
        self,
        *,
        composition_plan: dict[str, Any],
        output_format: str = DEFAULT_ELEVENLABS_OUTPUT_FORMAT,
    ) -> ElevenLabsStdlibInpaintResult:
        """Edit an existing song using composition plan with source_from.

        This is an Enterprise-only feature. Use source_from in sections to:
        - Keep sections unchanged (with song_id + range)
        - Regenerate sections (omit source_from)
        - Regenerate portions inside kept sections (negative_ranges)

        Args:
            composition_plan: Composition plan with source_from references
            output_format: Output audio format

        Returns:
            ElevenLabsStdlibInpaintResult with edited audio
        """
        fmt = _normalize_elevenlabs_output_format(output_format)
        query = {"output_format": fmt} if fmt else {}
        url = f"{self._base_url}/v1/music"
        if query:
            url = url + "?" + urllib.parse.urlencode(query)

        body: dict[str, Any] = {
            "composition_plan": composition_plan,
            "force_instrumental": False,  # Not used for inpainting, but required by API
        }

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
                return ElevenLabsStdlibInpaintResult(
                    audio_bytes=audio,
                    content_type=content_type,
                    song_id=song_id,
                )
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            if e.code == 402:
                friendly = _friendly_plan_error(detail)
                if friendly:
                    raise RuntimeError(friendly) from e
            raise RuntimeError(f"ElevenLabs Inpaint HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"ElevenLabs Inpaint request failed: {e}") from e

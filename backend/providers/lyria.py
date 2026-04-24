"""Google Lyria AI Music Provider.

Google Lyria 3 音乐生成 API，通过 Gemini API 访问。
支持高质量音乐生成，需要代理访问国内。

API 文档: https://ai.google.dev/gemini-api/docs/lyria
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class LyriaResult:
    audio_url: str | None
    audio_bytes: bytes | None
    task_id: str | None = None


class LyriaClient:
    """Google Lyria 3 Music API client via Gemini API."""

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required for lyria provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    async def generate(
        self,
        *,
        prompt: str,
        model: str = "lyria-3-clip-preview",
        lyrics: str | None = None,
        seed: int | None = None,
        **kwargs: Any,
    ) -> LyriaResult:
        """Generate music using Google Lyria 3.

        Args:
            prompt: Music style/description
            model: Model name, "lyria-3-clip-preview" or "lyria-3-pro-preview"
            lyrics: Optional lyrics text
            seed: Optional seed for reproducibility

        Returns:
            LyriaResult with audio URL or bytes
        """
        # Gemini API format for Lyria
        # Endpoint: POST /v1beta/models/{model}:generateContent
        url = f"{self._base}/v1beta/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": self._key,
            "Content-Type": "application/json",
        }

        # Build the prompt with music generation instructions
        text_parts: list[str] = []
        if lyrics and lyrics.strip():
            text_parts.append(f"Generate music with these lyrics:\n{lyrics.strip()}")
            text_parts.append(f"Style: {prompt}")
        else:
            text_parts.append(f"Generate music: {prompt}")

        body: dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": "\n\n".join(text_parts)}
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
            },
        }

        if seed is not None:
            body["generationConfig"]["seed"] = seed

        # Add additional parameters
        for k, v in kwargs.items():
            if v is not None:
                if k.startswith("generationConfig_"):
                    config_key = k[len("generationConfig_"):]
                    body["generationConfig"][config_key] = v
                else:
                    body[k] = v

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=body)
            self._check_response(resp)
            data = resp.json()

            # Extract audio from response
            # Gemini returns audio in parts with inline_data
            candidates = data.get("candidates") or []
            if not candidates:
                raise RuntimeError(f"Lyria response missing candidates: {data}")

            candidate = candidates[0]
            content = candidate.get("content") or {}
            parts = content.get("parts") or []

            audio_bytes: bytes | None = None
            audio_url: str | None = None

            for part in parts:
                if "inline_data" in part:
                    # Audio is returned as base64
                    inline_data = part["inline_data"]
                    mime_type = inline_data.get("mime_type") or ""
                    b64_data = inline_data.get("data") or ""
                    if b64_data:
                        import base64
                        audio_bytes = base64.b64decode(b64_data)
                elif "file_data" in part:
                    # Audio is returned as a file reference
                    file_data = part["file_data"]
                    audio_url = file_data.get("file_uri")

            if audio_bytes:
                return LyriaResult(audio_url=None, audio_bytes=audio_bytes)
            if audio_url:
                return LyriaResult(audio_url=audio_url, audio_bytes=None)

            raise RuntimeError(f"Lyria response missing audio data: {data}")

    async def download_audio(self, audio_url: str) -> bytes:
        """Download audio from Lyria result URL."""
        # Gemini File API requires authentication
        headers = {"x-goog-api-key": self._key}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(audio_url, headers=headers)
            resp.raise_for_status()
            return resp.content

    def _check_response(self, resp: httpx.Response) -> None:
        """Check response status and raise friendly errors."""
        if resp.status_code < 400:
            return

        text = resp.text
        try:
            data = json.loads(text)
        except Exception:
            raise RuntimeError(f"Lyria API HTTP {resp.status_code}: {text}")

        error_msg = data.get("error", {}).get("message") or text
        raise RuntimeError(f"Lyria API error (HTTP {resp.status_code}): {error_msg}")


# Stdlib version (no httpx dependency)
class LyriaClientStdlib:
    """Google Lyria 3 Music API client using stdlib only."""

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required for lyria provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def generate(
        self,
        *,
        prompt: str,
        model: str = "lyria-3-clip-preview",
        lyrics: str | None = None,
        seed: int | None = None,
        **kwargs: Any,
    ) -> LyriaResult:
        """Generate music using Google Lyria 3 (sync version)."""
        import urllib.request
        import urllib.error
        import base64

        url = f"{self._base}/v1beta/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": self._key,
            "Content-Type": "application/json",
        }

        text_parts: list[str] = []
        if lyrics and lyrics.strip():
            text_parts.append(f"Generate music with these lyrics:\n{lyrics.strip()}")
            text_parts.append(f"Style: {prompt}")
        else:
            text_parts.append(f"Generate music: {prompt}")

        body: dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": "\n\n".join(text_parts)}
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
            },
        }

        if seed is not None:
            body["generationConfig"]["seed"] = seed

        for k, v in kwargs.items():
            if v is not None:
                if k.startswith("generationConfig_"):
                    config_key = k[len("generationConfig_"):]
                    body["generationConfig"][config_key] = v
                else:
                    body[k] = v

        data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url=url, method="POST", data=data_bytes, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                data = json.loads(text)
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            raise RuntimeError(f"Lyria API HTTP {e.code}: {text}") from e

        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Lyria response missing candidates: {data}")

        candidate = candidates[0]
        content = candidate.get("content") or {}
        parts = content.get("parts") or []

        audio_bytes: bytes | None = None
        audio_url: str | None = None

        for part in parts:
            if "inline_data" in part:
                inline_data = part["inline_data"]
                b64_data = inline_data.get("data") or ""
                if b64_data:
                    audio_bytes = base64.b64decode(b64_data)
            elif "file_data" in part:
                file_data = part["file_data"]
                audio_url = file_data.get("file_uri")

        if audio_bytes:
            return LyriaResult(audio_url=None, audio_bytes=audio_bytes)
        if audio_url:
            return LyriaResult(audio_url=audio_url, audio_bytes=None)

        raise RuntimeError(f"Lyria response missing audio data: {data}")

    def download_audio(self, audio_url: str) -> bytes:
        """Download audio from Lyria result URL (sync version)."""
        import urllib.request

        req = urllib.request.Request(
            url=audio_url,
            method="GET",
            headers={"x-goog-api-key": self._key},
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read()
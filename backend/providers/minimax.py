"""MiniMax Music API Provider.

MiniMax 官方音乐生成 API (music-2.6 模型)。
支持人声 + 中英文歌词，国内可直接访问。

API 文档: https://platform.minimax.io/docs/api-reference/music-generation
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


def _maybe_region_hint(*, msg: str, http_status: int | None = None) -> str:
    raw = (msg or "").strip()
    low = raw.lower()
    if http_status in (401, 403) or "invalidkey" in low or "invalid key" in low or "unauthorized" in low:
        return (
            " (Hint: check MiniMax API region/base_url: CN=https://api.minimaxi.com, "
            "INTL=https://api.minimax.io)"
        )
    return ""


@dataclass(frozen=True)
class MiniMaxMusicResult:
    audio_url: str | None
    task_id: str | None
    audio_bytes: bytes | None = None


class MiniMaxMusicClient:
    """MiniMax Music API client for music-2.6 model."""

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("MINIMAX_API_KEY is required for minimax provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    async def generate(
        self,
        *,
        prompt: str,
        lyrics: str | None = None,
        model: str = "music-2.6",
        sample_rate: int = 44100,
        bitrate: int = 256000,
        format: str = "mp3",
        output_format: str = "url",
        **kwargs: Any,
    ) -> MiniMaxMusicResult:
        """Generate music using MiniMax music-2.6 model.

        Args:
            prompt: 音乐风格描述 (genre, mood, style)
            lyrics: 歌词文本 (可选，支持中英文)
            model: 模型名称，默认 music-2.6
            sample_rate: 音频采样率
            bitrate: 音频比特率
            format: 输出格式 (mp3, wav)
            output_format: 输出类型 (url, bytes)

        Returns:
            MiniMaxMusicResult with audio URL or bytes
        """
        url = f"{self._base}/v1/music_generation"
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "audio_setting": {
                "sample_rate": sample_rate,
                "bitrate": bitrate,
                "format": format,
            },
            "output_format": output_format,
        }

        # MiniMax API supports running without lyrics when:
        # - is_instrumental=true, or
        # - lyrics_optimizer=true with empty lyrics
        # In those cases, the caller may pass lyrics="" intentionally.
        if lyrics is not None:
            body["lyrics"] = str(lyrics).strip()

        # Add additional parameters
        for k, v in kwargs.items():
            if v is not None:
                body[k] = v

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=body)
            self._check_response(resp)
            data = resp.json()

            base_resp = data.get("base_resp") or {}
            status_code = base_resp.get("status_code")
            if status_code != 0:
                status_msg = base_resp.get("status_msg") or "Unknown error"
                raise RuntimeError(
                    f"MiniMax API error: status_code={status_code}, msg={status_msg}"
                    f"{_maybe_region_hint(msg=str(status_msg))}"
                )

            # MiniMax docs: response uses `data.audio` (hex by default). With output_format=url,
            # some responses still use `data.audio` to carry the downloadable URL.
            data_obj = data.get("data") or {}
            task_id = data_obj.get("task_id")
            audio_val = data_obj.get("audio_url") or data_obj.get("audio")

            if not audio_val:
                raise RuntimeError(f"MiniMax response missing audio field: {data}")

            if str(output_format).lower() == "url":
                return MiniMaxMusicResult(audio_url=str(audio_val), task_id=task_id)

            audio_str = str(audio_val)
            try:
                audio_bytes = bytes.fromhex(audio_str)
            except ValueError:
                raise RuntimeError(f"MiniMax response audio is not hex: {data}")
            return MiniMaxMusicResult(audio_url=None, task_id=task_id, audio_bytes=audio_bytes)

    async def download_audio(self, audio_url: str) -> bytes:
        """Download audio from MiniMax result URL."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(audio_url)
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
            raise RuntimeError(f"MiniMax API HTTP {resp.status_code}: {text}")

        # MiniMax error format
        base_resp = data.get("base_resp") or {}
        status_code = base_resp.get("status_code")
        status_msg = base_resp.get("status_msg") or text

        if status_code:
            raise RuntimeError(
                f"MiniMax API error (status_code={status_code}): {status_msg}"
                f"{_maybe_region_hint(msg=str(status_msg), http_status=resp.status_code)}"
            )

        raise RuntimeError(
            f"MiniMax API HTTP {resp.status_code}: {text}"
            f"{_maybe_region_hint(msg=text, http_status=resp.status_code)}"
        )

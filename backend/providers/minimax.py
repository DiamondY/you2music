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


@dataclass(frozen=True)
class MiniMaxMusicResult:
    audio_url: str
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

        if lyrics and lyrics.strip():
            body["lyrics"] = lyrics.strip()

        # Add additional parameters
        for k, v in kwargs.items():
            if v is not None:
                body[k] = v

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=body)
            self._check_response(resp)
            data = resp.json()

            # MiniMax response format
            # {"base_resp": {"status_code": 0, "status_msg": "success"}, "data": {"audio_url": "..."}}
            base_resp = data.get("base_resp") or {}
            status_code = base_resp.get("status_code")
            if status_code != 0:
                status_msg = base_resp.get("status_msg") or "Unknown error"
                raise RuntimeError(f"MiniMax API error: status_code={status_code}, msg={status_msg}")

            audio_url = data.get("data", {}).get("audio_url")
            task_id = data.get("data", {}).get("task_id")

            if not audio_url:
                raise RuntimeError(f"MiniMax response missing audio_url: {data}")

            return MiniMaxMusicResult(audio_url=audio_url, task_id=task_id)

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
            raise RuntimeError(f"MiniMax API error (status_code={status_code}): {status_msg}")

        raise RuntimeError(f"MiniMax API HTTP {resp.status_code}: {text}")

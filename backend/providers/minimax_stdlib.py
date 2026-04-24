"""MiniMax Music API Provider (stdlib version - no httpx).

MiniMax 官方音乐生成 API (music-2.6 模型)。
支持人声 + 中英文歌词，国内可直接访问。

API 文档: https://platform.minimax.io/docs/api-reference/music-generation
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


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
class MiniMaxMusicStdlibResult:
    audio_url: str | None
    task_id: str | None
    audio_bytes: bytes | None = None


class MiniMaxMusicClientStdlib:
    """MiniMax Music API client using stdlib only."""

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("MINIMAX_API_KEY is required for minimax provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def _request_json(self, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make HTTP request and return JSON response."""
        data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(url=url, method=method, data=data_bytes, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            try:
                data = json.loads(text)
                base_resp = data.get("base_resp") or {}
                status_code = base_resp.get("status_code")
                status_msg = base_resp.get("status_msg") or text
                raise RuntimeError(
                    f"MiniMax API error (status_code={status_code}): {status_msg}"
                    f"{_maybe_region_hint(msg=str(status_msg), http_status=e.code)}"
                ) from e
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"MiniMax API HTTP {e.code}: {text}{_maybe_region_hint(msg=text, http_status=e.code)}"
                ) from e

    def generate(
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
    ) -> MiniMaxMusicStdlibResult:
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
            MiniMaxMusicStdlibResult with audio URL
        """
        url = f"{self._base}/v1/music_generation"

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

        for k, v in kwargs.items():
            if v is not None:
                body[k] = v

        data = self._request_json("POST", url, body)

        base_resp = data.get("base_resp") or {}
        status_code = base_resp.get("status_code")
        if status_code != 0:
            status_msg = base_resp.get("status_msg") or "Unknown error"
            raise RuntimeError(
                f"MiniMax API error: status_code={status_code}, msg={status_msg}"
                f"{_maybe_region_hint(msg=str(status_msg))}"
            )

        data_obj = data.get("data") or {}
        task_id = data_obj.get("task_id")
        audio_val = data_obj.get("audio_url") or data_obj.get("audio")

        if not audio_val:
            raise RuntimeError(f"MiniMax response missing audio field: {data}")

        if str(output_format).lower() == "url":
            return MiniMaxMusicStdlibResult(audio_url=str(audio_val), task_id=task_id)

        audio_str = str(audio_val)
        try:
            audio_bytes = bytes.fromhex(audio_str)
        except ValueError:
            raise RuntimeError(f"MiniMax response audio is not hex: {data}")
        return MiniMaxMusicStdlibResult(audio_url=None, task_id=task_id, audio_bytes=audio_bytes)

    def download_audio(self, audio_url: str) -> bytes:
        """Download audio from MiniMax result URL."""
        with urllib.request.urlopen(audio_url, timeout=self._timeout) as resp:
            return resp.read()

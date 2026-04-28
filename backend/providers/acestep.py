"""ACE-Step 1.5 Music API Provider (OpenAI-Compatible).

ACE-Step 1.5 开源音乐生成模型，通过 acemusic.ai 云服务调用。
支持人声 + 50+ 语言歌词，100% 免费。

API 端点: https://api.acemusic.ai/v1/chat/completions (OpenAI 兼容)
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx


_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class ACEStepResult:
    """ACE-Step generation result."""
    audio_bytes: bytes
    task_id: str
    audio_url: str | None = None
    metadata: dict[str, Any] | None = None


class ACEStepClient:
    """ACE-Step 1.5 API client for acemusic.ai (OpenAI-compatible)."""

    # Model ID mapping for acemusic.ai
    MODEL_MAP = {
        "acestep-v15-turbo": "acemusic/acestep-v1.5-turbo",
        "acestep-v15-xl-turbo": "acemusic/acestep-v1.5-xl-turbo",
        "ACE-Step V1.5 Turbo": "acemusic/acestep-v1.5-turbo",
        "ACE-Step V1.5 XL Turbo": "acemusic/acestep-v1.5-xl-turbo",
    }

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("ACESTEP_API_KEY is required for acestep provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def _get_model_id(self, model: str) -> str:
        """Map friendly model names to API model IDs."""
        return self.MODEL_MAP.get(model, model)

    async def generate(
        self,
        *,
        prompt: str,
        lyrics: str | None = None,
        model: str = "acemusic/acestep-v1.5-turbo",
        audio_duration: float | None = None,
        audio_format: str = "mp3",
        **kwargs: Any,
    ) -> ACEStepResult:
        """Generate music using ACE-Step 1.5 model (OpenAI-compatible API).

        Args:
            prompt: 音乐描述
            lyrics: 歌词文本 (支持50+语言)
            model: 模型名称
            audio_duration: 时长(秒)
            audio_format: 输出格式 (mp3, wav, flac)

        Returns:
            ACEStepResult with audio_bytes
        """
        url = f"{self._base}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _DEFAULT_USER_AGENT,
        }

        # Build the prompt content
        content = prompt
        if lyrics:
            content = f"{prompt}\n\nLyrics:\n{lyrics}"

        # Map model name if needed
        model_id = self._get_model_id(model)

        body: dict[str, Any] = {
            "model": model_id,
            "messages": [
                {"role": "user", "content": content}
            ],
        }

        # Add optional parameters
        if audio_duration is not None:
            body["duration"] = int(audio_duration)
        if audio_format:
            body["audio_format"] = audio_format

        # Add any additional parameters
        for k, v in kwargs.items():
            if v is not None and k not in ("poll_interval_s", "max_wait_s", "inference_steps", "thinking", "batch_size", "seed"):
                body[k] = v

        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=body)
            self._check_response(resp)
            data = resp.json()

        # Parse the OpenAI-style response
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"ACE-Step API returned no choices: {data}")

        message = choices[0].get("message", {})
        audio_list = message.get("audio", [])

        if not audio_list:
            raise RuntimeError(f"ACE-Step API returned no audio: {data}")

        # Get the base64 audio data
        audio_url = audio_list[0].get("audio_url", {}).get("url", "")
        if not audio_url:
            raise RuntimeError(f"ACE-Step API returned no audio URL: {audio_list[0]}")

        # Parse data URL: data:audio/mpeg;base64,<data>
        if not audio_url.startswith("data:"):
            raise RuntimeError(f"ACE-Step returned non-data URL: {audio_url[:50]}...")

        # Extract base64 content
        try:
            # Format: data:audio/mpeg;base64,<base64_data>
            _, data_part = audio_url.split(",", 1)
            audio_bytes = base64.b64decode(data_part)
        except Exception as e:
            raise RuntimeError(f"Failed to decode base64 audio: {e}")

        # Generate a pseudo task_id from response
        task_id = data.get("id", "acestep-sync")

        return ACEStepResult(
            audio_bytes=audio_bytes,
            task_id=task_id,
            metadata={
                "model": model_id,
                "prompt": prompt,
                "lyrics": lyrics,
                "duration": audio_duration,
                "format": audio_format,
            },
        )

    async def generate_and_wait(
        self,
        *,
        prompt: str,
        lyrics: str | None = None,
        model: str = "acemusic/acestep-v1.5-turbo",
        audio_duration: float | None = None,
        audio_format: str = "mp3",
        **kwargs: Any,
    ) -> ACEStepResult:
        """Generate music and return result (synchronous API).

        For compatibility with the async interface, this just calls generate().
        """
        return await self.generate(
            prompt=prompt,
            lyrics=lyrics,
            model=model,
            audio_duration=audio_duration,
            audio_format=audio_format,
            **kwargs,
        )

    async def download_audio(self, audio_url: str) -> bytes:
        """Download audio from URL (not used for OpenAI-compatible API)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(audio_url)
            resp.raise_for_status()
            return resp.content

    def _check_response(self, resp: httpx.Response) -> None:
        """Check response status and raise friendly errors."""
        if resp.status_code < 400:
            return

        text = resp.text
        if resp.status_code == 403 and "error code: 1010" in text.lower():
            raise RuntimeError(
                "ACE-Step API HTTP 403 (Cloudflare error code: 1010). "
                "Check that ACESTEP_BASE_URL is set to 'https://api.acemusic.ai' (API domain), "
                "not 'https://acemusic.ai' (website domain)."
            )
        try:
            data = json.loads(text)
        except Exception:
            raise RuntimeError(f"ACE-Step API HTTP {resp.status_code}: {text}")

        error_msg = data.get("error", {}).get("message") or data.get("error") or text
        raise RuntimeError(f"ACE-Step API HTTP {resp.status_code}: {error_msg}")

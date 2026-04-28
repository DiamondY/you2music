"""ACE-Step 1.5 Music API Provider (stdlib version - no httpx).

ACE-Step 1.5 开源音乐生成模型，通过 acemusic.ai 云服务调用。
支持人声 + 50+ 语言歌词，100% 免费。

API 端点: https://api.acemusic.ai/v1/chat/completions (OpenAI 兼容)
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class ACEStepStdlibResult:
    """ACE-Step generation result."""
    audio_bytes: bytes
    task_id: str
    audio_url: str | None = None
    metadata: dict[str, Any] | None = None
    extra_audios: list[bytes] | None = None


class ACEStepClientStdlib:
    """ACE-Step 1.5 API client using stdlib only (OpenAI-compatible)."""

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

    def _request_json(self, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make HTTP request and return JSON response."""
        data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _DEFAULT_USER_AGENT,
        }

        req = urllib.request.Request(url=url, method=method, data=data_bytes, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            if int(getattr(e, "code", 0) or 0) == 403 and "error code: 1010" in text.lower():
                raise RuntimeError(
                    "ACE-Step API HTTP 403 (Cloudflare error code: 1010). "
                    "Check that ACESTEP_BASE_URL is set to 'https://api.acemusic.ai' (API domain), "
                    "not 'https://acemusic.ai' (website domain)."
                ) from e
            try:
                data = json.loads(text)
                error_msg = data.get("error", {}).get("message") or data.get("error") or text
                raise RuntimeError(f"ACE-Step API HTTP {e.code}: {error_msg}") from e
            except json.JSONDecodeError:
                raise RuntimeError(f"ACE-Step API HTTP {e.code}: {text}") from e

    def generate(
        self,
        *,
        prompt: str,
        lyrics: str | None = None,
        model: str = "acemusic/acestep-v1.5-turbo",
        audio_duration: float | None = None,
        audio_format: str = "mp3",
        bpm: int | None = None,
        key_scale: str | None = None,
        time_signature: str | None = None,
        vocal_language: str | None = None,
        thinking: bool = False,
        use_format: bool = False,
        batch_size: int = 1,
        **kwargs: Any,
    ) -> ACEStepStdlibResult:
        """Generate music using ACE-Step 1.5 model (OpenAI-compatible API).

        Args:
            prompt: 音乐描述
            lyrics: 歌词文本 (支持50+语言)
            model: 模型名称
            audio_duration: 时长(秒)
            audio_format: 输出格式 (mp3, wav, flac)
            bpm: 节拍速度 (30-300, None=auto)
            key_scale: 调性 (e.g. "C Major", "Am")
            time_signature: 拍号 (e.g. "4/4")
            vocal_language: 歌词语言 (en, zh, ja, ko, auto)
            thinking: 使用 5Hz LM 增强质量
            use_format: 让 LM 优化描述和歌词
            batch_size: 同时生成多个候选 (1-4)

        Returns:
            ACEStepStdlibResult with audio_bytes
        """
        url = f"{self._base}/v1/chat/completions"

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

        # Music attributes
        if bpm is not None:
            body["bpm"] = int(bpm)
        if key_scale:
            body["key_scale"] = key_scale
        if time_signature:
            body["time_signature"] = time_signature
        if vocal_language and vocal_language != "auto":
            body["vocal_language"] = vocal_language

        # Generation control
        if thinking:
            body["thinking"] = True
        if use_format:
            body["use_format"] = True
        if batch_size and batch_size > 1:
            body["batch_size"] = int(batch_size)

        # Add any additional parameters
        for k, v in kwargs.items():
            if v is not None and k not in ("poll_interval_s", "max_wait_s", "inference_steps", "seed"):
                body[k] = v

        data = self._request_json("POST", url, body)

        # Parse the OpenAI-style response
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"ACE-Step API returned no choices: {data}")

        message = choices[0].get("message", {})
        audio_list = message.get("audio", [])

        if not audio_list:
            raise RuntimeError(f"ACE-Step API returned no audio: {data}")

        # Generate a pseudo task_id from response
        task_id = data.get("id", "acestep-sync")

        def _decode_audio_item(item: dict) -> bytes:
            audio_url = item.get("audio_url", {}).get("url", "")
            if not audio_url:
                raise RuntimeError(f"ACE-Step API returned no audio URL: {item}")
            if not audio_url.startswith("data:"):
                raise RuntimeError(f"ACE-Step returned non-data URL: {audio_url[:50]}...")
            _, data_part = audio_url.split(",", 1)
            return base64.b64decode(data_part)

        # Primary audio
        audio_bytes = _decode_audio_item(audio_list[0])

        # Batch: extract additional audios
        extra_audios: list[bytes] | None = None
        if len(audio_list) > 1:
            extra_audios = [_decode_audio_item(item) for item in audio_list[1:]]

        return ACEStepStdlibResult(
            audio_bytes=audio_bytes,
            task_id=task_id,
            metadata={
                "model": model_id,
                "prompt": prompt,
                "lyrics": lyrics,
                "duration": audio_duration,
                "format": audio_format,
            },
            extra_audios=extra_audios,
        )

    def generate_and_wait(
        self,
        *,
        prompt: str,
        lyrics: str | None = None,
        model: str = "acemusic/acestep-v1.5-turbo",
        audio_duration: float | None = None,
        audio_format: str = "mp3",
        bpm: int | None = None,
        key_scale: str | None = None,
        time_signature: str | None = None,
        vocal_language: str | None = None,
        thinking: bool = False,
        use_format: bool = False,
        batch_size: int = 1,
        **kwargs: Any,
    ) -> ACEStepStdlibResult:
        """Generate music and return result (synchronous API)."""
        return self.generate(
            prompt=prompt,
            lyrics=lyrics,
            model=model,
            audio_duration=audio_duration,
            audio_format=audio_format,
            bpm=bpm,
            key_scale=key_scale,
            time_signature=time_signature,
            vocal_language=vocal_language,
            thinking=thinking,
            use_format=use_format,
            batch_size=batch_size,
            **kwargs,
        )

    def download_audio(self, audio_url: str) -> bytes:
        """Download audio from URL (not used for OpenAI-compatible API)."""
        with urllib.request.urlopen(audio_url, timeout=self._timeout) as resp:
            return resp.read()

"""Mureka AI Music Provider.

Mureka AI（昆仑万维）音乐生成 API。
支持人声 + 中英文歌词，国内直连。

API 文档: https://platform.mureka.ai/docs/
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class MurekaResult:
    audio_url: str
    task_id: str | None
    audio_bytes: bytes | None = None


class MurekaClient:
    """Mureka AI Music API client."""

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("MUREKA_API_KEY is required for mureka provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    async def generate_song(
        self,
        *,
        lyrics: str,
        prompt: str | None = None,
        model: str = "auto",
        poll_interval_s: float = 2.0,
        max_wait_s: float = 300.0,
        **kwargs: Any,
    ) -> MurekaResult:
        """Generate a song with lyrics.

        Args:
            lyrics: Structured lyrics with tags like [Verse], [Chorus] (max 3000 chars)
            prompt: Style/mood description, e.g., "r&b, slow, passionate, male vocal"
            model: Model version, "auto" for default
            poll_interval_s: Polling interval in seconds
            max_wait_s: Maximum wait time in seconds

        Returns:
            MurekaResult with audio URL
        """
        url = f"{self._base}/v1/song/generate"
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {
            "lyrics": lyrics,
            "model": model,
        }

        if prompt and prompt.strip():
            body["prompt"] = prompt.strip()

        for k, v in kwargs.items():
            if v is not None:
                body[k] = v

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=body)
            self._check_response(resp)
            data = resp.json()

            # Mureka returns async task, need to poll
            task_id = data.get("task_id") or data.get("id")
            audio_url = data.get("audio_url") or data.get("result", {}).get("audio_url")

            # If immediate result
            if audio_url:
                return MurekaResult(audio_url=audio_url, task_id=task_id)

            # If async task, poll for result
            if task_id:
                result = await self.poll_until_done(
                    task_id=task_id,
                    poll_interval_s=poll_interval_s,
                    max_wait_s=max_wait_s,
                )
                return result

            raise RuntimeError(f"Mureka response missing task_id or audio_url: {data}")

    async def poll_until_done(
        self,
        *,
        task_id: str,
        poll_interval_s: float = 2.0,
        max_wait_s: float = 300.0,
    ) -> MurekaResult:
        """Poll for task completion."""
        import asyncio

        url = f"{self._base}/v1/task/{task_id}"
        headers = {"Authorization": f"Bearer {self._key}"}
        deadline = asyncio.get_running_loop().time() + max_wait_s

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while True:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                status = str(data.get("status") or "").lower()
                if status in ("completed", "success", "succeeded", "done"):
                    audio_url = data.get("audio_url") or data.get("result", {}).get("audio_url")
                    if not audio_url:
                        raise RuntimeError(f"Mureka task completed but missing audio_url: {data}")
                    return MurekaResult(audio_url=audio_url, task_id=task_id)

                if status in ("failed", "error", "canceled"):
                    error_msg = data.get("error") or data.get("message") or "Unknown error"
                    raise RuntimeError(f"Mureka generation failed: {error_msg}")

                if asyncio.get_running_loop().time() > deadline:
                    raise TimeoutError("Mureka generation timed out")

                await asyncio.sleep(poll_interval_s)

    async def download_audio(self, audio_url: str) -> bytes:
        """Download audio from Mureka result URL."""
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
            raise RuntimeError(f"Mureka API HTTP {resp.status_code}: {text}")

        error_msg = data.get("error") or data.get("message") or text
        raise RuntimeError(f"Mureka API error (HTTP {resp.status_code}): {error_msg}")


# Stdlib version (no httpx dependency)
class MurekaClientStdlib:
    """Mureka AI Music API client using stdlib only."""

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("MUREKA_API_KEY is required for mureka provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def generate_song(
        self,
        *,
        lyrics: str,
        prompt: str | None = None,
        model: str = "auto",
        poll_interval_s: float = 2.0,
        max_wait_s: float = 300.0,
        **kwargs: Any,
    ) -> MurekaResult:
        """Generate a song with lyrics (sync version).

        Args:
            lyrics: Structured lyrics with tags like [Verse], [Chorus] (max 3000 chars)
            prompt: Style/mood description, e.g., "r&b, slow, passionate, male vocal"
            model: Model version, "auto" for default
            poll_interval_s: Polling interval in seconds
            max_wait_s: Maximum wait time in seconds
        """
        import urllib.request
        import urllib.error

        url = f"{self._base}/v1/song/generate"
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {
            "lyrics": lyrics,
            "model": model,
        }

        if prompt and prompt.strip():
            body["prompt"] = prompt.strip()

        for k, v in kwargs.items():
            if v is not None:
                body[k] = v

        data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url=url, method="POST", data=data_bytes, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                data = json.loads(text)
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            raise RuntimeError(f"Mureka API HTTP {e.code}: {text}") from e

        task_id = data.get("task_id") or data.get("id")
        audio_url = data.get("audio_url") or data.get("result", {}).get("audio_url")

        if audio_url:
            return MurekaResult(audio_url=audio_url, task_id=task_id)

        if task_id:
            result = self.poll_until_done(
                task_id=task_id,
                poll_interval_s=poll_interval_s,
                max_wait_s=max_wait_s,
            )
            return result

        raise RuntimeError(f"Mureka response missing task_id or audio_url: {data}")

    def poll_until_done(
        self,
        *,
        task_id: str,
        poll_interval_s: float = 2.0,
        max_wait_s: float = 300.0,
    ) -> MurekaResult:
        """Poll for task completion (sync version)."""
        import time
        import urllib.request

        url = f"{self._base}/v1/task/{task_id}"
        headers = {"Authorization": f"Bearer {self._key}"}
        deadline = time.time() + max_wait_s

        while True:
            req = urllib.request.Request(url=url, method="GET", headers=headers)
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                data = json.loads(text)

            status = str(data.get("status") or "").lower()
            if status in ("completed", "success", "succeeded", "done"):
                audio_url = data.get("audio_url") or data.get("result", {}).get("audio_url")
                if not audio_url:
                    raise RuntimeError(f"Mureka task completed but missing audio_url: {data}")
                return MurekaResult(audio_url=audio_url, task_id=task_id)

            if status in ("failed", "error", "canceled"):
                error_msg = data.get("error") or data.get("message") or "Unknown error"
                raise RuntimeError(f"Mureka generation failed: {error_msg}")

            if time.time() > deadline:
                raise TimeoutError("Mureka generation timed out")

            time.sleep(poll_interval_s)

    def download_audio(self, audio_url: str) -> bytes:
        """Download audio from Mureka result URL (sync version)."""
        import urllib.request

        with urllib.request.urlopen(audio_url, timeout=self._timeout) as resp:
            return resp.read()
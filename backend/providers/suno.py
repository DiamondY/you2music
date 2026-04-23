from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class SunoResult:
    audio_url: str
    task_id: str


def _join_url(base_url: str, path_or_url: str) -> str:
    v = str(path_or_url or "").strip()
    if not v:
        raise ValueError("Suno path/url is required")
    if v.startswith("http://") or v.startswith("https://"):
        return v
    base = str(base_url or "").rstrip("/")
    if not v.startswith("/"):
        v = "/" + v
    return base + v


class SunoClient:
    """Suno API client via third-party services like musicapi.ai"""

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("SUNO_API_KEY is required for suno provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    async def create_generation(
        self,
        *,
        prompt: str,
        duration_sec: int = 30,
        model: str = "v4.5",
        instrumental: bool = False,
        generate_path: str = "/suno/generate",
        **kwargs: Any,
    ) -> str:
        """Create a Suno generation task.

        Args:
            prompt: Text description of the music
            duration_sec: Target duration in seconds
            model: Suno model version (v4, v4.5, etc.)
            instrumental: Generate instrumental only (no vocals)

        Returns:
            Task ID for polling
        """
        url = _join_url(self._base, generate_path)
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        body = {
            "prompt": prompt,
            "duration": duration_sec,
            "model": model,
            "instrumental": instrumental,
        }
        # Add any additional params
        body.update(kwargs)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            # Response format varies by provider
            # Common patterns: {"task_id": "..."} or {"id": "..."}
            task_id = data.get("task_id") or data.get("id")
            if not task_id:
                raise RuntimeError(f"Suno create missing task id: {data}")
            return str(task_id)

    async def poll_until_done(
        self,
        *,
        task_id: str,
        task_path_template: str = "/suno/task/{task_id}",
        poll_interval_s: float = 2.0,
        max_wait_s: float = 300.0,
    ) -> dict[str, Any]:
        """Poll for generation completion."""
        url = _join_url(self._base, task_path_template.format(task_id=task_id))
        headers = {"Authorization": f"Bearer {self._key}"}
        deadline = asyncio.get_running_loop().time() + max_wait_s

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while True:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                # Status varies by provider: "completed", "success", "succeeded"
                status = str(data.get("status") or "").lower()
                if status in ("completed", "success", "succeeded"):
                    return data
                if status in ("failed", "error", "canceled"):
                    error_msg = data.get("error") or data.get("message") or "Unknown error"
                    raise RuntimeError(f"Suno generation failed: {error_msg}")

                if asyncio.get_running_loop().time() > deadline:
                    raise TimeoutError("Suno generation timed out")

                await asyncio.sleep(poll_interval_s)

    @staticmethod
    def extract_audio_url(result_json: dict[str, Any]) -> str:
        """Extract audio URL from Suno response.

        Response formats vary by provider:
        - {"audio_url": "..."}
        - {"output": {"audio": "..."}}
        - {"data": [{"audio_url": "..."}]}
        """
        # Direct audio_url
        if result_json.get("audio_url"):
            return str(result_json["audio_url"])

        # Nested in output
        output = result_json.get("output")
        if isinstance(output, dict):
            if output.get("audio_url"):
                return str(output["audio_url"])
            if output.get("audio"):
                return str(output["audio"])

        # Array in data
        data = result_json.get("data")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                if first.get("audio_url"):
                    return str(first["audio_url"])
                if first.get("audio"):
                    return str(first["audio"])
                if first.get("audioUrl"):
                    return str(first["audioUrl"])

        raise RuntimeError(f"Suno output missing audio url: {result_json}")

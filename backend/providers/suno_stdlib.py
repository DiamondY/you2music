from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SunoStdlibResult:
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


class SunoClientStdlib:
    """Suno API client via third-party services (stdlib-only version)"""

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("SUNO_API_KEY is required for suno provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def _request_json(
        self, method: str, url: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url=url, method=method, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            raise RuntimeError(f"Suno HTTP {e.code}: {detail}") from e

    def create_generation(
        self,
        *,
        prompt: str,
        duration_sec: int = 30,
        model: str = "v4.5",
        instrumental: bool = False,
        generate_path: str = "/suno/generate",
        **kwargs: Any,
    ) -> str:
        """Create a Suno generation task."""
        url = _join_url(self._base, generate_path)
        body = {
            "prompt": prompt,
            "duration": duration_sec,
            "model": model,
            "instrumental": instrumental,
        }
        body.update(kwargs)

        data = self._request_json("POST", url, body)
        task_id = data.get("task_id") or data.get("id")
        if not task_id:
            raise RuntimeError(f"Suno create missing task id: {data}")
        return str(task_id)

    def poll_until_done(
        self,
        *,
        task_id: str,
        task_path_template: str = "/suno/task/{task_id}",
        poll_interval_s: float = 2.0,
        max_wait_s: float = 300.0,
    ) -> dict[str, Any]:
        """Poll for generation completion."""
        url = _join_url(self._base, task_path_template.format(task_id=task_id))
        deadline = time.time() + max_wait_s

        while True:
            data = self._request_json("GET", url, None)
            status = str(data.get("status") or "").lower()

            if status in ("completed", "success", "succeeded"):
                return data
            if status in ("failed", "error", "canceled"):
                error_msg = data.get("error") or data.get("message") or "Unknown error"
                raise RuntimeError(f"Suno generation failed: {error_msg}")

            if time.time() > deadline:
                raise TimeoutError("Suno generation timed out")

            time.sleep(poll_interval_s)

    @staticmethod
    def extract_audio_url(result_json: dict[str, Any]) -> str:
        """Extract audio URL from Suno response."""
        if result_json.get("audio_url"):
            return str(result_json["audio_url"])
        if result_json.get("audioUrl"):
            return str(result_json["audioUrl"])

        output = result_json.get("output")
        if isinstance(output, dict):
            if output.get("audio_url"):
                return str(output["audio_url"])
            if output.get("audio"):
                return str(output["audio"])
            if output.get("audioUrl"):
                return str(output["audioUrl"])

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

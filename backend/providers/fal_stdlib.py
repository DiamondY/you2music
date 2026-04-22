from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FalStdlibResult:
    audio_url: str
    request_id: str


class FalQueueClientStdlib:
    def __init__(self, *, key: str, queue_base_url: str, timeout_s: float) -> None:
        if not key:
            raise ValueError("FAL_KEY is required for fal provider.")
        self._key = key
        self._base = queue_base_url.rstrip("/")
        self._timeout = timeout_s

    def submit(self, *, model_id: str, input_json: dict[str, Any]) -> str:
        url = f"{self._base}/{model_id}"
        data = json.dumps(input_json, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            method="POST",
            data=data,
            headers={"Authorization": f"Key {self._key}", "content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                out = json.loads(body) if body else {}
                request_id = out.get("request_id") or out.get("id")
                if not request_id:
                    raise RuntimeError(f"fal queue submit missing request_id: {out}")
                return str(request_id)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            raise RuntimeError(f"fal HTTP {e.code}: {detail}") from e

    def poll_until_done(
        self,
        *,
        model_id: str,
        request_id: str,
        poll_interval_s: float = 1.0,
        max_wait_s: float = 300.0,
    ) -> dict[str, Any]:
        url = f"{self._base}/{model_id}/requests/{request_id}"
        deadline = time.time() + max_wait_s
        req = urllib.request.Request(url=url, headers={"Authorization": f"Key {self._key}"})
        while True:
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    data = json.loads(body) if body else {}
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
                raise RuntimeError(f"fal HTTP {e.code}: {detail}") from e

            status = str(data.get("status") or "").upper()
            if status in ("COMPLETED", "SUCCESS", "SUCCEEDED"):
                return data
            if status in ("FAILED", "ERROR"):
                raise RuntimeError(f"fal request failed: {data}")
            if time.time() > deadline:
                raise TimeoutError("fal request timed out")
            time.sleep(poll_interval_s)

    @staticmethod
    def extract_audio_url(result_json: dict[str, Any]) -> str:
        audio = result_json.get("audio")
        if isinstance(audio, dict) and isinstance(audio.get("url"), str):
            return audio["url"]
        output = result_json.get("output")
        if isinstance(output, dict):
            audio2 = output.get("audio")
            if isinstance(audio2, dict) and isinstance(audio2.get("url"), str):
                return audio2["url"]
        raise RuntimeError(f"fal result missing audio url: {result_json}")


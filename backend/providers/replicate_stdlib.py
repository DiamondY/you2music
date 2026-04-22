from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplicateStdlibResult:
    audio_url: str
    prediction_id: str


class ReplicateClientStdlib:
    def __init__(self, *, api_token: str, base_url: str, timeout_s: float) -> None:
        if not api_token:
            raise ValueError("REPLICATE_API_TOKEN is required for replicate provider.")
        self._token = api_token
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def _request_json(self, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers_primary = {"Authorization": f"Bearer {self._token}", "content-type": "application/json"}
        headers_fallback = {"Authorization": f"Token {self._token}", "content-type": "application/json"}

        for idx, headers in enumerate((headers_primary, headers_fallback)):
            req = urllib.request.Request(url=url, method=method, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    text = resp.read().decode("utf-8", errors="replace")
                    return json.loads(text) if text else {}
            except urllib.error.HTTPError as e:
                # Only fall back on auth errors.
                if idx == 0 and int(getattr(e, "code", 0) or 0) in (401, 403):
                    continue
                detail = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
                raise RuntimeError(f"replicate HTTP {e.code}: {detail}") from e

    def create_prediction(self, *, version: str, input_json: dict[str, Any]) -> str:
        url = f"{self._base}/v1/predictions"
        body = {"version": version, "input": input_json}
        data = self._request_json("POST", url, body)
        pid = data.get("id")
        if not pid:
            raise RuntimeError(f"replicate create missing id: {data}")
        return str(pid)

    def poll_until_done(self, *, prediction_id: str, poll_interval_s: float = 1.0, max_wait_s: float = 300.0) -> dict[str, Any]:
        url = f"{self._base}/v1/predictions/{prediction_id}"
        deadline = time.time() + max_wait_s
        while True:
            data = self._request_json("GET", url, None)
            status = str(data.get("status") or "").lower()
            if status == "succeeded":
                return data
            if status in ("failed", "canceled"):
                raise RuntimeError(f"replicate prediction failed: {data}")
            if time.time() > deadline:
                raise TimeoutError("replicate prediction timed out")
            time.sleep(poll_interval_s)

    @staticmethod
    def extract_audio_url(result_json: dict[str, Any]) -> str:
        out = result_json.get("output")
        if isinstance(out, str) and out.startswith("http"):
            return out
        if isinstance(out, list) and out:
            first = out[0]
            if isinstance(first, str) and first.startswith("http"):
                return first
        raise RuntimeError(f"replicate output missing audio url: {result_json}")

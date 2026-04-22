from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StabilityStdlibResult:
    audio_bytes: bytes
    content_type: str


class StabilityAudioClientStdlib:
    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("STABILITY_API_KEY is required for stability provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def text_to_audio(
        self,
        *,
        endpoint_path: str,
        prompt: str,
        seconds_total: int | None,
        seed: int | None,
        steps: int | None,
        cfg_scale: float | None,
        output_format: str | None,
    ) -> StabilityStdlibResult:
        url = f"{self._base}{endpoint_path}"
        fields: dict[str, str] = {"prompt": prompt}
        if seconds_total is not None:
            fields["seconds_total"] = str(int(seconds_total))
        if seed is not None:
            fields["seed"] = str(int(seed))
        if steps is not None:
            fields["steps"] = str(int(steps))
        if cfg_scale is not None:
            fields["cfg_scale"] = str(float(cfg_scale))
        if output_format:
            fields["output_format"] = output_format

        data = urllib.parse.urlencode(fields).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            method="POST",
            data=data,
            headers={
                "Authorization": f"Bearer {self._key}",
                "content-type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read()
                ctype = resp.headers.get("content-type", "application/octet-stream")
                if ctype.startswith("audio/") or ctype == "application/octet-stream":
                    return StabilityStdlibResult(audio_bytes=body, content_type=ctype)
                # try JSON url
                try:
                    j = json.loads(body.decode("utf-8", errors="replace"))
                except Exception:
                    return StabilityStdlibResult(audio_bytes=body, content_type=ctype)

                url_candidate = None
                if isinstance(j, dict):
                    for k in ("audio_url", "url", "result_url", "output_url"):
                        if isinstance(j.get(k), str) and j[k].startswith("http"):
                            url_candidate = j[k]
                            break
                    if url_candidate is None and isinstance(j.get("audio"), dict) and isinstance(j["audio"].get("url"), str):
                        url_candidate = j["audio"]["url"]
                if not url_candidate:
                    raise RuntimeError(f"stability response missing audio url: {j}")
                dl_req = urllib.request.Request(url_candidate)
                with urllib.request.urlopen(dl_req, timeout=self._timeout) as dl:
                    return StabilityStdlibResult(audio_bytes=dl.read(), content_type=dl.headers.get("content-type", "application/octet-stream"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            raise RuntimeError(f"stability HTTP {e.code}: {detail}") from e


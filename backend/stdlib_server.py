from __future__ import annotations

import json
import os
import random
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from config import load_settings
from providers.registry import providers_payload
from providers.acestep_stdlib import ACEStepClientStdlib
from storage import JobStore
from admin_config import load_local_config, redacted_config, save_local_config
from shared import (
    RANDOM_LYRICS_TEMPLATES,
    RANDOM_PROMPTS,
    build_prompt,
    generate_random_bpm,
    generate_random_duration_sec,
    generate_random_key_scale,
    generate_random_lyrics,
    generate_random_prompt,
)

_VOCALS_TAG_WITH = "with vocals, singing (do not be instrumental-only)"
_VOCALS_TAG_INSTR = "instrumental only (no vocals)"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _error(handler: BaseHTTPRequestHandler, status: int, msg: str) -> None:
    _json_response(handler, status, {"error": msg})


def _validate_generate(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    prompt = str(payload.get("prompt") or "").strip()
    if len(prompt) > 5000:
        raise ValueError("prompt too long")

    lyrics = payload.get("lyrics")
    if lyrics is not None:
        lyrics = str(lyrics)
        if len(lyrics) > 12000:
            raise ValueError("lyrics too long")

    duration_sec = int(payload.get("duration_sec") or 0)
    if duration_sec < 3 or duration_sec > 600:  # ACE-Step supports up to 600s
        raise ValueError("duration_sec must be 3..600")

    vocals = bool(payload.get("vocals", True))

    seed = payload.get("seed")
    if seed is not None and seed != "":
        seed = int(seed)
        if seed < 0 or seed > 2_147_483_647:
            raise ValueError("seed out of range")
    else:
        seed = None

    model_id = payload.get("model_id")
    if model_id is not None and str(model_id).strip():
        model_id = str(model_id).strip()
        if len(model_id) > 128:
            raise ValueError("model_id too long")
    else:
        model_id = None

    provider = payload.get("provider")
    if provider is not None and str(provider).strip():
        provider = str(provider).strip()
        if len(provider) > 64:
            raise ValueError("provider too long")
    else:
        provider = None

    provider_params = payload.get("provider_params")
    if provider_params is None:
        provider_params = {}
    if not isinstance(provider_params, dict):
        raise ValueError("provider_params must be an object")

    params = {
        "base_prompt": prompt,
        "duration_sec": duration_sec,
        "vocals": vocals,
        "seed": seed,
        "model_id": model_id,
        "provider": provider,
        "provider_params": provider_params,
        "lyrics": lyrics,
    }

    effective_provider = str(provider or "acestep").strip() or "acestep"
    if effective_provider != "acestep":
        raise ValueError(f"unknown provider: {effective_provider}")
    params["provider"] = "acestep"

    if not prompt:
        raise ValueError("prompt is required")

    full_prompt = build_prompt(
        base_prompt=prompt,
        lyrics=lyrics,
        vocals=vocals,
    )
    return full_prompt, params


def _validate_count(payload: dict[str, Any], *, default: int = 1, max_count: int = 4) -> int:
    raw = payload.get("count", default)
    try:
        count = int(raw)
    except Exception:
        raise ValueError("count must be an integer")
    if count < 1 or count > max_count:
        raise ValueError(f"count must be 1..{max_count}")
    return count


def _validate_extend(payload: dict[str, Any], *, max_total_sec: int = 600) -> tuple[str, int]:
    parent_job_id = str(payload.get("job_id") or "").strip()
    if not parent_job_id:
        raise ValueError("job_id is required")
    extra_sec = int(payload.get("extra_sec") or 0)
    if extra_sec < 3 or extra_sec > 600:
        raise ValueError("extra_sec must be 3..600")
    return parent_job_id, extra_sec


def _check_admin(handler: BaseHTTPRequestHandler, *, expected_token: str) -> bool:
    expected = (expected_token or "").strip()
    if not expected:
        _error(handler, 403, "admin token not configured (set AI_MUSIC_ADMIN_TOKEN or config admin_token)")
        return False
    token = handler.headers.get("x-admin-token")
    if not token or token.strip() != expected:
        _error(handler, 403, "invalid admin token")
        return False
    return True


class AppState:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.data_dir = self.settings.data_dir
        self.audio_dir = self.data_dir / "audio"
        self.db_path = self.data_dir / "app.db"

        self.store = JobStore(self.db_path)
        self.store.init()
        self.apply_proxy_env()

    def apply_proxy_env(self) -> None:
        http_proxy = (self.settings.proxy_http or "").strip()
        https_proxy = (self.settings.proxy_https or "").strip()
        no_proxy = (self.settings.proxy_no or "").strip()

        def set_or_unset(key: str, value: str) -> None:
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

        set_or_unset("HTTP_PROXY", http_proxy)
        set_or_unset("http_proxy", http_proxy)
        set_or_unset("HTTPS_PROXY", https_proxy)
        set_or_unset("https_proxy", https_proxy)
        set_or_unset("NO_PROXY", no_proxy)
        set_or_unset("no_proxy", no_proxy)

    def reload(self) -> None:
        new_settings = load_settings()
        new_data_dir = new_settings.data_dir
        new_audio_dir = new_data_dir / "audio"
        new_db_path = new_data_dir / "app.db"

        self.settings = new_settings
        self.apply_proxy_env()

        if new_db_path != self.db_path:
            self.data_dir = new_data_dir
            self.audio_dir = new_audio_dir
            self.db_path = new_db_path
            self.store = JobStore(self.db_path)
            self.store.init()

    def run_job(self, *, job_id: str, prompt: str, params: dict[str, Any]) -> None:
        try:
            self.store.set_status(job_id, status="running")
            self.audio_dir.mkdir(parents=True, exist_ok=True)

            provider_name = str(params.get("provider") or "acestep").strip() or "acestep"
            if provider_name != "acestep":
                raise RuntimeError(f"unsupported provider: {provider_name}")
            vocals = bool(params["vocals"])
            provider_params = params.get("provider_params") or {}

            out_bytes: bytes
            out_ext = "mp3"
            song_id: str | None = None

            if provider_name == "acestep":
                # ACE-Step 1.5 via acemusic.ai (OpenAI-compatible API)
                # User-configurable timeout with minimum floor
                _min_timeout = 120
                _user_timeout = provider_params.get("request_timeout_s")
                if _user_timeout is not None:
                    try:
                        _timeout_s = max(int(_user_timeout), _min_timeout)
                    except (ValueError, TypeError):
                        _timeout_s = self.settings.request_timeout_s
                else:
                    _timeout_s = self.settings.request_timeout_s

                client = ACEStepClientStdlib(
                    api_key=self.settings.acestep_api_key,
                    base_url=self.settings.acestep_base_url,
                    timeout_s=_timeout_s,
                )
                model = str(provider_params.get("model") or "acemusic/acestep-v1.5-turbo")
                lyrics = params.get("lyrics") or provider_params.get("lyrics")
                audio_duration = provider_params.get("audio_duration")
                if audio_duration is None:
                    audio_duration = float(params["duration_sec"])
                audio_format = str(provider_params.get("audio_format") or "mp3")
                instrumental = not vocals

                # Extract base_prompt (strip vocals tag and lyrics embedded by build_prompt)
                acestep_prompt = str(params.get("base_prompt") or prompt).split("\n\nLyrics:\n")[0]
                for _tag in (_VOCALS_TAG_WITH, _VOCALS_TAG_INSTR):
                    acestep_prompt = acestep_prompt.replace("\n\n" + _tag, "").replace(_tag, "")
                acestep_prompt = acestep_prompt.strip()

                # Collect all ACE-Step params from provider_params
                acestep_kwargs: dict[str, Any] = {}
                for k in ("bpm", "key_scale", "time_signature", "vocal_language",
                           "thinking", "use_format", "inference_steps", "guidance_scale",
                           "shift", "infer_method", "timesteps", "task_type", "sample_mode",
                           "temperature", "top_p", "use_cot_caption", "use_cot_language",
                           "audio_cover_strength", "repainting_start", "repainting_end"):
                    val = provider_params.get(k)
                    if val is not None and val != "":
                        acestep_kwargs[k] = val

                # seed: prefer global params, fallback to provider_params
                seed_val = params.get("seed")
                if seed_val is None:
                    seed_val = provider_params.get("seed")
                if seed_val is not None and seed_val != "":
                    # allow seed=0, reject empty string
                    acestep_kwargs["seed"] = int(seed_val)

                # Audio input: base64-encoded audio for cover/repaint/lego/extract/complete tasks
                # Audio input: in stdlib mode we accept base64 from the client for now,
                # but we MUST NOT persist it to sqlite job params (handled in do_POST).
                src_audio_b64 = provider_params.get("src_audio_b64")
                src_audio_format = provider_params.get("src_audio_format") or "mp3"
                reference_audio_b64 = provider_params.get("reference_audio_b64")
                reference_audio_format = provider_params.get("reference_audio_format") or "mp3"
                if src_audio_b64:
                    acestep_kwargs["src_audio_b64"] = src_audio_b64
                    acestep_kwargs["src_audio_format"] = src_audio_format
                if reference_audio_b64:
                    acestep_kwargs["reference_audio_b64"] = reference_audio_b64
                    acestep_kwargs["reference_audio_format"] = reference_audio_format

                result = client.generate(
                    prompt=acestep_prompt,
                    lyrics=str(lyrics).strip() if lyrics else None,
                    model=model,
                    audio_duration=audio_duration,
                    audio_format=audio_format,
                    instrumental=instrumental,
                    **acestep_kwargs,
                )

                out_bytes = result.audio_bytes
                out_ext = audio_format
            else:
                raise RuntimeError(f"unknown provider: {provider_name}")

            out_path = self.audio_dir / f"{job_id}.{out_ext}"
            out_path.write_bytes(out_bytes)

            self.store.set_status(job_id, status="succeeded", output_path=str(out_path), song_id=song_id)
        except Exception as e:
            self.store.set_status(job_id, status="failed", error=str(e))


STATE = AppState()
STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"
ADMIN_HTML = STATIC_DIR / "admin.html"

# ========================================
# Random Sample Data
# ========================================
class Handler(BaseHTTPRequestHandler):
    server_version = "ai-music-tool/0.1"

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            data = _read_text(INDEX_HTML).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if self.path == "/admin" or self.path.startswith("/admin?"):
            data = _read_text(ADMIN_HTML).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if self.path == "/api/random_sample":
            prompt = generate_random_prompt() or random.choice(RANDOM_PROMPTS)
            lyrics = generate_random_lyrics() or random.choice(RANDOM_LYRICS_TEMPLATES)
            bpm = generate_random_bpm()
            key_scale = generate_random_key_scale()
            duration = generate_random_duration_sec()
            _json_response(
                self,
                200,
                {
                    "prompt": prompt,
                    "lyrics": lyrics,
                    "bpm": bpm,
                    "key_scale": key_scale,
                    "duration": duration,
                },
            )
            return

        if self.path.startswith("/api/jobs/history"):
            # /api/jobs/history?offset=0&limit=20
            offset = 0
            limit = 20
            if "?" in self.path:
                qs = self.path.split("?", 1)[1]
                for part in qs.split("&"):
                    if part.startswith("offset="):
                        raw = part.split("=", 1)[1].strip()
                        try:
                            offset = int(raw)
                        except Exception:
                            offset = 0
                    elif part.startswith("limit="):
                        raw = part.split("=", 1)[1].strip()
                        try:
                            limit = int(raw)
                        except Exception:
                            limit = 20
            if offset < 0:
                offset = 0
            if limit < 1:
                limit = 1
            if limit > 200:
                limit = 200

            total = STATE.store.count_jobs()
            out: list[dict[str, Any]] = []
            for rec in STATE.store.list_page(offset=offset, limit=limit):
                audio_url = None
                if rec.status == "succeeded" and rec.output_path:
                    audio_url = f"/api/audio/{rec.job_id}"
                out.append(
                    {
                        "job_id": rec.job_id,
                        "status": rec.status,
                        "created_at_ms": rec.created_at_ms,
                        "updated_at_ms": rec.updated_at_ms,
                        "provider": rec.provider,
                        "prompt": rec.prompt,
                        "params": json.loads(rec.params_json),
                        "audio_url": audio_url,
                        "error": rec.error,
                        "song_id": rec.song_id,
                    }
                )
            _json_response(self, 200, {"jobs": out, "total": total, "offset": offset, "limit": limit})
            return

        if self.path.startswith("/api/jobs/recent"):
            # /api/jobs/recent?limit=20
            limit = 20
            if "?" in self.path:
                qs = self.path.split("?", 1)[1]
                for part in qs.split("&"):
                    if part.startswith("limit="):
                        raw = part.split("=", 1)[1].strip()
                        try:
                            limit = int(raw)
                        except Exception:
                            limit = 20
                        break
            if limit < 1:
                limit = 1
            if limit > 50:
                limit = 50

            out: list[dict[str, Any]] = []
            for rec in STATE.store.list_recent(limit=limit):
                audio_url = None
                if rec.status == "succeeded" and rec.output_path:
                    audio_url = f"/api/audio/{rec.job_id}"
                out.append(
                    {
                        "job_id": rec.job_id,
                        "status": rec.status,
                        "created_at_ms": rec.created_at_ms,
                        "updated_at_ms": rec.updated_at_ms,
                        "provider": rec.provider,
                        "prompt": rec.prompt,
                        "params": json.loads(rec.params_json),
                        "audio_url": audio_url,
                        "error": rec.error,
                        "song_id": rec.song_id,
                    }
                )
            _json_response(self, 200, {"jobs": out})
            return

        if self.path.startswith("/api/jobs/"):
            job_id = self.path.split("/api/jobs/", 1)[1].strip().split("?", 1)[0]
            rec = STATE.store.get(job_id)
            if not rec:
                _error(self, 404, "job not found")
                return
            audio_url = None
            if rec.status == "succeeded" and rec.output_path:
                audio_url = f"/api/audio/{rec.job_id}"
            _json_response(
                self,
                200,
                {
                    "job_id": rec.job_id,
                    "status": rec.status,
                    "created_at_ms": rec.created_at_ms,
                    "updated_at_ms": rec.updated_at_ms,
                    "provider": rec.provider,
                    "prompt": rec.prompt,
                    "params": json.loads(rec.params_json),
                    "audio_url": audio_url,
                    "error": rec.error,
                    "song_id": rec.song_id,
                },
            )
            return

        if self.path.startswith("/api/jobs?ids="):
            ids_raw = self.path.split("/api/jobs?ids=", 1)[1].split("&", 1)[0]
            job_ids = [x for x in ids_raw.split(",") if x]
            out: list[dict[str, Any]] = []
            for job_id in job_ids[:20]:
                rec = STATE.store.get(job_id)
                if not rec:
                    continue
                audio_url = None
                if rec.status == "succeeded" and rec.output_path:
                    audio_url = f"/api/audio/{rec.job_id}"
                out.append(
                    {
                        "job_id": rec.job_id,
                        "status": rec.status,
                        "created_at_ms": rec.created_at_ms,
                        "updated_at_ms": rec.updated_at_ms,
                        "provider": rec.provider,
                        "prompt": rec.prompt,
                        "params": json.loads(rec.params_json),
                        "audio_url": audio_url,
                        "error": rec.error,
                        "song_id": rec.song_id,
                    }
                )
            _json_response(self, 200, {"jobs": out})
            return

        if self.path == "/api/random_sample":
            prompt = random.choice(RANDOM_PROMPTS)
            lyrics = random.choice(RANDOM_LYRICS_TEMPLATES)
            bpm = random.choice([60, 70, 80, 90, 100, 110, 120, 128, 140])
            keys = ["C major", "G major", "D major", "A minor", "E minor", "F major"]
            key_scale = random.choice(keys)
            durations = [30, 45, 60, 90, 120, 180]
            duration = random.choice(durations)
            _json_response(self, 200, {
                "prompt": prompt,
                "lyrics": lyrics,
                "bpm": bpm,
                "key_scale": key_scale,
                "duration": duration,
            })
            return

        if self.path == "/api/providers":
            _json_response(self, 200, providers_payload(STATE.settings))
            return

        if self.path == "/api/admin/providers":
            if not _check_admin(self, expected_token=STATE.settings.admin_token):
                return
            _json_response(self, 200, providers_payload(STATE.settings, include_disabled=True))
            return

        if self.path == "/api/admin/config":
            if not _check_admin(self, expected_token=STATE.settings.admin_token):
                return
            try:
                cfg = load_local_config()
                _json_response(self, 200, {"config": redacted_config(cfg)})
            except Exception as e:
                _error(self, 500, str(e))
            return

        if self.path.startswith("/api/audio/"):
            job_id = self.path.split("/api/audio/", 1)[1].strip().split("?", 1)[0]
            if job_id.endswith(".mp3"):
                job_id = job_id.rsplit(".", 1)[0]
            rec = STATE.store.get(job_id)
            if not rec or rec.status != "succeeded" or not rec.output_path:
                self.send_error(404)
                return
            path = Path(rec.output_path)
            if not path.exists():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            ctype = "application/octet-stream"
            if path.suffix.lower() == ".mp3":
                ctype = "audio/mpeg"
            elif path.suffix.lower() == ".wav":
                ctype = "audio/wav"
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # Client closed the connection (e.g. user navigated away / refresh / download cancelled).
                # Don't crash the request thread with noisy tracebacks.
                return
            return

        self.send_error(404)

    def do_DELETE(self) -> None:
        # DELETE /api/jobs  — delete all jobs
        if self.path == "/api/jobs" or self.path == "/api/jobs/":
            count = STATE.store.delete_all()
            _json_response(self, 200, {"deleted": count})
            return

        # DELETE /api/jobs/{job_id}  — delete single job
        if self.path.startswith("/api/jobs/"):
            job_id = self.path.split("/api/jobs/", 1)[1].strip().split("?", 1)[0]
            if not job_id:
                _error(self, 400, "missing job_id")
                return
            ok = STATE.store.delete(job_id)
            if not ok:
                _error(self, 404, "job not found")
                return
            _json_response(self, 200, {"deleted": 1})
            return

        self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/generate_many":
            try:
                length = int(self.headers.get("content-length") or "0")
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))
                count = _validate_count(payload, default=2, max_count=4)
                prompt, params = _validate_generate(payload)
            except ValueError as e:
                _error(self, 400, str(e))
                return
            except Exception:
                _error(self, 400, "invalid JSON")
                return

            provider_name = "acestep"
            if isinstance(payload, dict) and payload.get("provider") and str(payload.get("provider")).strip():
                requested = str(payload.get("provider")).strip()
                if requested != "acestep":
                    _error(self, 400, f"unknown provider: {requested}")
                    return

            provider_params = params.get("provider_params") or {}
            output_format = str(provider_params.get("output_format") or STATE.settings.output_format)
            run_params = {**params, "output_format": output_format, "provider": provider_name}
            # Do NOT persist base64 audio blobs into sqlite. Keep them only in-memory
            # for the immediate background thread execution (stdlib mode).
            storage_provider_params = dict(provider_params) if isinstance(provider_params, dict) else {}
            storage_provider_params.pop("src_audio_b64", None)
            storage_provider_params.pop("reference_audio_b64", None)
            storage_params = dict(run_params)
            storage_params["provider_params"] = storage_provider_params

            job_ids: list[str] = []
            for _ in range(count):
                job_id = STATE.store.create_job(provider=provider_name, prompt=prompt, params=storage_params, kind="variation")
                job_ids.append(job_id)

                t = threading.Thread(
                    target=STATE.run_job,
                    kwargs={"job_id": job_id, "prompt": prompt, "params": run_params},
                    daemon=True,
                )
                t.start()

            _json_response(self, 200, {"job_ids": job_ids})
            return

        if self.path == "/api/generate":
            try:
                length = int(self.headers.get("content-length") or "0")
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))
                prompt, params = _validate_generate(payload)
            except ValueError as e:
                _error(self, 400, str(e))
                return
            except Exception:
                _error(self, 400, "invalid JSON")
                return

            provider_name = "acestep"
            if isinstance(payload, dict) and payload.get("provider") and str(payload.get("provider")).strip():
                requested = str(payload.get("provider")).strip()
                if requested != "acestep":
                    _error(self, 400, f"unknown provider: {requested}")
                    return

            provider_params = params.get("provider_params") or {}
            output_format = str(provider_params.get("output_format") or STATE.settings.output_format)
            run_params = {**params, "output_format": output_format, "provider": provider_name}
            storage_provider_params = dict(provider_params) if isinstance(provider_params, dict) else {}
            storage_provider_params.pop("src_audio_b64", None)
            storage_provider_params.pop("reference_audio_b64", None)
            storage_params = dict(run_params)
            storage_params["provider_params"] = storage_provider_params
            job_id = STATE.store.create_job(provider=provider_name, prompt=prompt, params=storage_params, kind="generate")

            t = threading.Thread(
                target=STATE.run_job,
                kwargs={"job_id": job_id, "prompt": prompt, "params": run_params},
                daemon=True,
            )
            t.start()

            _json_response(self, 200, {"job_id": job_id})
            return

        if self.path == "/api/extend":
            try:
                length = int(self.headers.get("content-length") or "0")
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))
                parent_job_id, extra_sec = _validate_extend(payload)
            except ValueError as e:
                _error(self, 400, str(e))
                return
            except Exception:
                _error(self, 400, "invalid JSON")
                return

            parent = STATE.store.get(parent_job_id)
            if not parent:
                _error(self, 404, "job not found")
                return
            if parent.status != "succeeded":
                _error(self, 409, "job not ready")
                return

            try:
                parent_params = json.loads(parent.params_json)
            except Exception:
                parent_params = {}

            duration_sec = int(parent_params.get("duration_sec") or 0)
            new_duration = duration_sec + extra_sec
            if new_duration > 600:
                _error(self, 400, "total duration exceeds 600 seconds")
                return

            provider_name = str(parent.provider or "acestep")
            if provider_name != "acestep":
                _error(self, 400, f"unknown provider: {provider_name}")
                return
            new_params = dict(parent_params)
            new_params["duration_sec"] = new_duration

            if isinstance(payload, dict) and payload.get("provider") and str(payload.get("provider")).strip():
                new_params["provider"] = str(payload.get("provider")).strip()
            if isinstance(payload, dict) and isinstance(payload.get("provider_params"), dict):
                new_params["provider_params"] = payload.get("provider_params")
                new_params["output_format"] = str(
                    payload["provider_params"].get("output_format")
                    or new_params.get("output_format")
                    or STATE.settings.output_format
                )
            requested_provider = str(new_params.get("provider") or provider_name).strip() or provider_name
            if requested_provider != "acestep":
                _error(self, 400, f"unknown provider: {requested_provider}")
                return

            job_id = STATE.store.create_job(
                provider=str(new_params.get("provider") or provider_name),
                prompt=parent.prompt,
                params=new_params,
                kind="extend",
                parent_job_id=parent_job_id,
            )

            t = threading.Thread(
                target=STATE.run_job,
                kwargs={"job_id": job_id, "prompt": parent.prompt, "params": new_params},
                daemon=True,
            )
            t.start()

            _json_response(self, 200, {"job_id": job_id, "parent_job_id": parent_job_id})
            return

        if self.path == "/api/admin/config":
            if not _check_admin(self, expected_token=STATE.settings.admin_token):
                return
            try:
                length = int(self.headers.get("content-length") or "0")
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))
                cfg = payload.get("config")
                if not isinstance(cfg, dict):
                    raise ValueError("config must be an object")
            except Exception as e:
                _error(self, 400, str(e))
                return

            try:
                current = load_local_config()
                cur_secrets = current.get("secrets") if isinstance(current.get("secrets"), dict) else {}
                new_secrets = cfg.get("secrets") if isinstance(cfg.get("secrets"), dict) else {}
                merged_secrets: dict[str, Any] = dict(cur_secrets)
                for k, v in new_secrets.items():
                    if v == "********":
                        continue
                    merged_secrets[k] = v
                if merged_secrets:
                    cfg["secrets"] = merged_secrets

                if cfg.get("admin_token") == "********":
                    cfg["admin_token"] = current.get("admin_token", "")

                save_local_config(cfg)
                STATE.reload()
                _json_response(self, 200, {"ok": True})
            except Exception as e:
                _error(self, 500, str(e))
            return

        if self.path == "/api/admin/reload":
            if not _check_admin(self, expected_token=STATE.settings.admin_token):
                return
            STATE.reload()
            _json_response(self, 200, {"ok": True})
            return

        if self.path == "/api/admin/test":
            if not _check_admin(self, expected_token=STATE.settings.admin_token):
                return
            try:
                results = _run_admin_tests()
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "results": results,
                        "proxy": {
                            "settings": {
                                "http": STATE.settings.proxy_http,
                                "https": STATE.settings.proxy_https,
                                "no_proxy": STATE.settings.proxy_no,
                            },
                            "env": {
                                "HTTP_PROXY": os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "",
                                "HTTPS_PROXY": os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "",
                                "NO_PROXY": os.getenv("NO_PROXY") or os.getenv("no_proxy") or "",
                            },
                        },
                    },
                )
            except Exception as e:
                _error(self, 500, str(e))
            return

        _error(self, 404, "not found")

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    settings = STATE.settings
    host = settings.host
    port = settings.port
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"you2music running on http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def _run_admin_tests() -> list[dict[str, Any]]:
    providers = providers_payload(STATE.settings, include_disabled=True).get("providers", [])
    enabled = STATE.settings.enabled_providers or [p.get("id") for p in providers]
    enabled_set = set([x for x in enabled if isinstance(x, str)])

    import urllib.request
    import urllib.error

    def _is_auth_error(status: int) -> bool:
        return status in (401, 403)

    def attempt_get(
        *,
        name: str,
        url: str,
        headers: dict[str, str],
        ok_if_status: Any | None = None,
        timeout_s: float = 10.0,
    ) -> dict[str, Any]:
        started = time.monotonic()
        merged_headers = {
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        merged_headers.update(headers)
        req = urllib.request.Request(url, headers=merged_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                status = int(getattr(resp, "status", 200))
                ok = bool(ok_if_status(status)) if callable(ok_if_status) else (200 <= status < 300)
                kind = "ok" if ok else ("auth_error" if _is_auth_error(status) else "http_error")
                return {
                    "name": name,
                    "url": url,
                    "http_status": status,
                    "ok": ok,
                    "kind": kind,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
        except urllib.error.HTTPError as e:
            status = int(getattr(e, "code", 0) or 0)
            ok = bool(ok_if_status(status)) if callable(ok_if_status) else (200 <= status < 300)
            kind = "ok" if ok else ("auth_error" if _is_auth_error(status) else "http_error")
            return {
                "name": name,
                "url": url,
                "http_status": status,
                "ok": ok,
                "kind": kind,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
        except Exception as e:
            return {
                "name": name,
                "url": url,
                "ok": False,
                "kind": "network_error",
                "error": f"{type(e).__name__}: {e}",
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }

    def summarize_attempts(attempts: list[dict[str, Any]]) -> tuple[bool, str, str]:
        if any(a.get("ok") is True for a in attempts):
            return True, "ok", "ok"
        if any(a.get("kind") == "auth_error" for a in attempts):
            return False, "auth_error", "authentication failed (401/403)"
        if any(a.get("kind") == "network_error" for a in attempts):
            return False, "network_error", "network/proxy/TLS error"
        return False, "http_error", "unexpected HTTP status"

    out: list[dict[str, Any]] = []
    for p in providers:
        pid = p.get("id")
        if not isinstance(pid, str) or pid not in enabled_set:
            continue
        if p.get("ready") is False:
            out.append(
                {
                    "provider": pid,
                    "ok": False,
                    "kind": "not_ready",
                    "message": f"missing env: {p.get('missing_env')}",
                    "attempts": [],
                }
            )
            continue
        attempts: list[dict[str, Any]] = []
        try:
            if pid == "acestep":
                attempts.append(
                    attempt_get(
                        name="health",
                        url=f"{STATE.settings.acestep_base_url}/v1/models",
                        headers={"Authorization": f"Bearer {STATE.settings.acestep_api_key}"},
                    )
                )
            else:
                out.append(
                    {
                        "provider": pid,
                        "ok": False,
                        "kind": "unsupported",
                        "message": "unknown provider",
                        "attempts": [],
                    }
                )
                continue
        except Exception as e:
            attempts.append({"name": "internal", "ok": False, "kind": "internal_error", "error": str(e)})

        ok, kind, message = summarize_attempts(attempts)
        out.append({"provider": pid, "ok": ok, "kind": kind, "message": message, "attempts": attempts})
    return out


if __name__ == "__main__":
    main()

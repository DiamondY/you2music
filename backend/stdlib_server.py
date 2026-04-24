from __future__ import annotations

import json
import os
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from config import load_settings
from providers.elevenlabs_stdlib import ElevenLabsMusicProviderStdlib, ElevenLabsStdlibInpaintResult
from providers.fal_stdlib import FalQueueClientStdlib
from providers.registry import providers_payload
from providers.replicate_stdlib import ReplicateClientStdlib
from providers.stability_stdlib import StabilityAudioClientStdlib
from providers.suno_stdlib import SunoClientStdlib
from providers.minimax_stdlib import MiniMaxMusicClientStdlib
from providers.mureka import MurekaClientStdlib
from providers.lyria import LyriaClientStdlib
from storage import JobStore
from admin_config import load_local_config, redacted_config, save_local_config


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


def _is_minimax_music_model(version: str) -> bool:
    """Check if the Replicate model version is a MiniMax music model."""
    return version.lower().startswith("minimax/music")


def _build_prompt(*, base_prompt: str, lyrics: str | None, vocals: bool) -> str:
    parts: list[str] = [base_prompt.strip()]
    if vocals:
        parts.append("with vocals, singing (do not be instrumental-only)")
    else:
        parts.append("instrumental only (no vocals)")
    if lyrics and lyrics.strip():
        parts.append("Lyrics:\n" + lyrics.strip())
    return "\n\n".join(parts).strip()


def _validate_generate(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    if len(prompt) > 5000:
        raise ValueError("prompt too long")

    lyrics = payload.get("lyrics")
    if lyrics is not None:
        lyrics = str(lyrics)
        if len(lyrics) > 12000:
            raise ValueError("lyrics too long")

    duration_sec = int(payload.get("duration_sec") or 0)
    if duration_sec < 3 or duration_sec > 300:
        raise ValueError("duration_sec must be 3..300")

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
        "duration_sec": duration_sec,
        "vocals": vocals,
        "seed": seed,
        "model_id": model_id,
        "provider": provider,
        "provider_params": provider_params,
        "lyrics": lyrics,  # Pass lyrics to run_job for MiniMax music
    }

    # Providers that accept a separate `lyrics` field should not also get lyrics injected into `prompt`.
    state = globals().get("STATE", None)
    default_provider = getattr(getattr(state, "settings", None), "default_provider", None)
    effective_provider = str(provider or default_provider or "elevenlabs").strip()
    is_minimax_replicate = (
        effective_provider == "replicate"
        and _is_minimax_music_model(str(provider_params.get("version") or ""))
    )
    include_lyrics_in_prompt = not (effective_provider == "minimax" or is_minimax_replicate)

    raw_prompt = bool(provider_params.get("raw_prompt", False))
    if raw_prompt:
        parts = [prompt.strip()]
        if include_lyrics_in_prompt and lyrics and str(lyrics).strip():
            parts.append(str(lyrics).strip())
        full_prompt = "\n\n".join(parts).strip()
    else:
        full_prompt = _build_prompt(
            base_prompt=prompt,
            lyrics=(lyrics if include_lyrics_in_prompt else None),
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


def _validate_extend(payload: dict[str, Any], *, max_total_sec: int = 300) -> tuple[str, int]:
    parent_job_id = str(payload.get("job_id") or "").strip()
    if not parent_job_id:
        raise ValueError("job_id is required")
    extra_sec = int(payload.get("extra_sec") or 0)
    if extra_sec < 3 or extra_sec > 180:
        raise ValueError("extra_sec must be 3..180")
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

            provider_name = str(params.get("provider") or self.settings.default_provider or "elevenlabs").strip()
            duration_ms = int(params["duration_sec"]) * 1000
            vocals = bool(params["vocals"])
            provider_params = params.get("provider_params") or {}
            composition_plan = None
            if provider_params.get("use_composition_plan") is True:
                raw = provider_params.get("composition_plan_json")
                if isinstance(raw, dict):
                    composition_plan = raw
                elif isinstance(raw, str) and raw.strip():
                    composition_plan = json.loads(raw)

            out_bytes: bytes
            out_ext = "mp3"
            song_id: str | None = None

            if provider_name == "elevenlabs":
                provider = ElevenLabsMusicProviderStdlib(
                    api_key=self.settings.elevenlabs_api_key,
                    base_url=self.settings.elevenlabs_base_url,
                    timeout_s=self.settings.request_timeout_s,
                )
                result = provider.compose(
                    prompt=(None if composition_plan is not None else prompt),
                    composition_plan=composition_plan,
                    music_length_ms=duration_ms,
                    force_instrumental=(not vocals),
                    seed=params.get("seed"),
                    model_id=params.get("model_id"),
                    output_format=str(params.get("output_format") or self.settings.output_format),
                )
                out_bytes = result.audio_bytes
                out_ext = "mp3"
                song_id = result.song_id
            elif provider_name == "fal":
                client = FalQueueClientStdlib(
                    key=self.settings.fal_key,
                    queue_base_url=self.settings.fal_queue_base_url,
                    timeout_s=self.settings.request_timeout_s,
                )
                model_id = str(provider_params.get("model_id") or "fal-ai/stable-audio-25/text-to-audio")
                seconds_total = provider_params.get("seconds_total")
                if seconds_total is None:
                    seconds_total = int(params["duration_sec"])
                fal_input: dict[str, Any] = {"prompt": prompt, "seconds_total": int(seconds_total)}
                if provider_params.get("num_inference_steps") is not None:
                    fal_input["num_inference_steps"] = int(provider_params["num_inference_steps"])
                if provider_params.get("guidance_scale") is not None:
                    fal_input["guidance_scale"] = float(provider_params["guidance_scale"])
                seed = provider_params.get("seed", params.get("seed"))
                if seed is not None:
                    fal_input["seed"] = int(seed)
                request_id = client.submit(model_id=model_id, input_json=fal_input)
                result_json = client.poll_until_done(
                    model_id=model_id,
                    request_id=request_id,
                    poll_interval_s=float(provider_params.get("poll_interval_s") or 1.0),
                    max_wait_s=300.0,
                )
                audio_url = client.extract_audio_url(result_json)
                import urllib.request

                with urllib.request.urlopen(audio_url, timeout=self.settings.request_timeout_s) as dl:
                    out_bytes = dl.read()
                out_ext = "wav"
            elif provider_name == "replicate":
                client = ReplicateClientStdlib(
                    api_token=self.settings.replicate_api_token,
                    base_url=self.settings.replicate_base_url,
                    timeout_s=self.settings.request_timeout_s,
                )
                version = str(provider_params.get("version") or "stability-ai/stable-audio-2.5")

                # MiniMax music models have different input parameters
                is_minimax_music = _is_minimax_music_model(version)
                if is_minimax_music:
                    # MiniMax music: prompt, lyrics, style_strength (no duration)
                    inp: dict[str, Any] = {"prompt": prompt}
                    # Add lyrics if provided
                    lyrics = params.get("lyrics") or provider_params.get("lyrics")
                    if lyrics and str(lyrics).strip():
                        inp["lyrics"] = str(lyrics).strip()
                    # Add style_strength if provided (0.0-1.0)
                    if provider_params.get("style_strength") is not None:
                        inp["style_strength"] = float(provider_params["style_strength"])
                    seed = provider_params.get("seed", params.get("seed"))
                    if seed is not None:
                        inp["seed"] = int(seed)
                    out_ext = "mp3"  # MiniMax outputs mp3
                else:
                    # Standard Replicate models (Stable Audio, etc.)
                    duration = provider_params.get("duration")
                    if duration is None:
                        duration = int(params["duration_sec"])
                    inp = {"prompt": prompt, "duration": int(duration)}
                    seed = provider_params.get("seed", params.get("seed"))
                    if seed is not None:
                        inp["seed"] = int(seed)
                    if provider_params.get("steps") is not None:
                        inp["steps"] = int(provider_params["steps"])
                    if provider_params.get("cfg_scale") is not None:
                        inp["cfg_scale"] = float(provider_params["cfg_scale"])
                    out_ext = "wav"

                pid = client.create_prediction(version=version, input_json=inp)
                pred = client.poll_until_done(
                    prediction_id=pid,
                    poll_interval_s=float(provider_params.get("poll_interval_s") or 1.0),
                    max_wait_s=300.0,
                )
                audio_url = client.extract_audio_url(pred)
                import urllib.request

                with urllib.request.urlopen(audio_url, timeout=self.settings.request_timeout_s) as dl:
                    out_bytes = dl.read()
            elif provider_name == "stability":
                client = StabilityAudioClientStdlib(
                    api_key=self.settings.stability_api_key,
                    base_url=self.settings.stability_base_url,
                    timeout_s=self.settings.request_timeout_s,
                )
                endpoint_path = str(provider_params.get("endpoint_path") or "/v2beta/audio/stable-audio-2/text-to-audio")
                seconds_total = provider_params.get("seconds_total")
                if seconds_total is None:
                    seconds_total = int(params["duration_sec"])
                seed = provider_params.get("seed", params.get("seed"))
                steps = provider_params.get("steps")
                cfg_scale = provider_params.get("cfg_scale")
                output_format = provider_params.get("output_format")
                res = client.text_to_audio(
                    endpoint_path=endpoint_path,
                    prompt=prompt,
                    seconds_total=int(seconds_total) if seconds_total is not None else None,
                    seed=int(seed) if seed is not None else None,
                    steps=int(steps) if steps is not None else None,
                    cfg_scale=float(cfg_scale) if cfg_scale is not None else None,
                    output_format=str(output_format) if output_format else None,
                )
                out_bytes = res.audio_bytes
                out_ext = "wav" if "wav" in (res.content_type or "") else "bin"
            elif provider_name == "suno":
                client = SunoClientStdlib(
                    api_key=self.settings.suno_api_key,
                    base_url=self.settings.suno_base_url,
                    timeout_s=self.settings.request_timeout_s,
                )
                model = str(provider_params.get("model") or "v4.5")
                instrumental = bool(provider_params.get("instrumental", False))
                duration = provider_params.get("duration")
                if duration is None:
                    duration = int(params["duration_sec"])
                generate_path = str(provider_params.get("generate_path") or "/suno/generate")
                task_path_template = str(provider_params.get("task_path_template") or "/suno/task/{task_id}")
                max_wait_s = float(provider_params.get("max_wait_s") or 300.0)

                extra: dict[str, Any] = dict(provider_params)
                for k in (
                    "model",
                    "instrumental",
                    "duration",
                    "poll_interval_s",
                    "generate_path",
                    "task_path_template",
                    "max_wait_s",
                ):
                    extra.pop(k, None)
                task_id = client.create_generation(
                    prompt=prompt,
                    duration_sec=int(duration),
                    model=model,
                    instrumental=instrumental,
                    generate_path=generate_path,
                    **extra,
                )
                result_json = client.poll_until_done(
                    task_id=task_id,
                    poll_interval_s=float(provider_params.get("poll_interval_s") or 2.0),
                    max_wait_s=max_wait_s,
                    task_path_template=task_path_template,
                )
                audio_url = client.extract_audio_url(result_json)
                import urllib.request

                with urllib.request.urlopen(audio_url, timeout=self.settings.request_timeout_s) as dl:
                    out_bytes = dl.read()
                out_ext = "mp3"
            elif provider_name == "minimax":
                # MiniMax official API (music-2.6)
                client = MiniMaxMusicClientStdlib(
                    api_key=self.settings.minimax_api_key,
                    base_url=self.settings.minimax_base_url,
                    timeout_s=self.settings.request_timeout_s,
                )
                model = str(provider_params.get("model") or "music-2.6")
                lyrics_raw = params.get("lyrics") or provider_params.get("lyrics")
                lyrics_text = str(lyrics_raw).strip() if lyrics_raw is not None else ""
                sample_rate = int(provider_params.get("sample_rate") or 44100)
                bitrate = int(provider_params.get("bitrate") or 256000)
                audio_format = str(provider_params.get("format") or "mp3")

                lyrics_optimizer_val = provider_params.get("lyrics_optimizer")
                lyrics_optimizer = (
                    bool(lyrics_optimizer_val)
                    if isinstance(lyrics_optimizer_val, bool)
                    else (True if vocals and not lyrics_text else False)
                )
                is_instrumental = not vocals
                lyrics_to_send: str | None
                if is_instrumental:
                    lyrics_to_send = None
                    lyrics_optimizer = False
                elif lyrics_text:
                    lyrics_to_send = lyrics_text
                else:
                    lyrics_to_send = ""
                    lyrics_optimizer = True

                result = client.generate(
                    prompt=prompt,
                    lyrics=lyrics_to_send,
                    model=model,
                    sample_rate=sample_rate,
                    bitrate=bitrate,
                    format=audio_format,
                    lyrics_optimizer=lyrics_optimizer,
                    is_instrumental=is_instrumental,
                )
                if result.audio_bytes is not None:
                    out_bytes = result.audio_bytes
                else:
                    if not result.audio_url:
                        raise RuntimeError("MiniMax response missing audio_url")
                    out_bytes = client.download_audio(result.audio_url)
                out_ext = audio_format
            elif provider_name == "mureka":
                # Mureka AI (昆仑万维) Music API
                client = MurekaClientStdlib(
                    api_key=self.settings.mureka_api_key,
                    base_url=self.settings.mureka_base_url,
                    timeout_s=self.settings.request_timeout_s,
                )
                model = str(provider_params.get("model") or "auto")
                mureka_prompt = provider_params.get("prompt")  # Optional style description
                lyrics = params.get("lyrics") or provider_params.get("lyrics")
                poll_interval = float(provider_params.get("poll_interval_s", 2.0))
                max_wait = float(provider_params.get("max_wait_s", 300.0))

                result = client.generate_song(
                    lyrics=lyrics or "",
                    prompt=mureka_prompt,
                    model=model,
                    poll_interval_s=poll_interval,
                    max_wait_s=max_wait,
                )
                out_bytes = client.download_audio(result.audio_url)
                out_ext = "mp3"
            elif provider_name == "lyria":
                # Google Lyria 3 via Gemini API
                client = LyriaClientStdlib(
                    api_key=self.settings.google_api_key,
                    base_url=self.settings.google_base_url,
                    timeout_s=self.settings.request_timeout_s,
                )
                model = str(provider_params.get("model") or "lyria-3-clip-preview")
                lyrics = params.get("lyrics") or provider_params.get("lyrics")
                seed = provider_params.get("seed", params.get("seed"))

                result = client.generate(
                    prompt=prompt,
                    model=model,
                    lyrics=lyrics,
                    seed=int(seed) if seed is not None else None,
                )

                if result.audio_bytes:
                    out_bytes = result.audio_bytes
                elif result.audio_url:
                    out_bytes = client.download_audio(result.audio_url)
                else:
                    raise RuntimeError("Lyria result missing audio data")
                out_ext = "mp3"
            else:
                raise RuntimeError(f"unknown provider: {provider_name}")

            out_path = self.audio_dir / f"{job_id}.{out_ext}"
            out_path.write_bytes(out_bytes)

            self.store.set_status(job_id, status="succeeded", output_path=str(out_path), song_id=song_id)
        except Exception as e:
            self.store.set_status(job_id, status="failed", error=str(e))

    def run_job_store(self, *, job_id: str, prompt: str, params: dict[str, Any]) -> None:
        """Run a generate job with store_for_inpainting=True."""
        try:
            self.store.set_status(job_id, status="running")
            self.audio_dir.mkdir(parents=True, exist_ok=True)

            duration_ms = int(params["duration_sec"]) * 1000
            vocals = bool(params["vocals"])
            provider_params = params.get("provider_params") or {}
            store_for_inpainting = bool(params.get("store_for_inpainting", False))

            composition_plan = None
            if provider_params.get("use_composition_plan") is True:
                raw = provider_params.get("composition_plan_json")
                if isinstance(raw, dict):
                    composition_plan = raw
                elif isinstance(raw, str) and raw.strip():
                    composition_plan = json.loads(raw)

            provider = ElevenLabsMusicProviderStdlib(
                api_key=self.settings.elevenlabs_api_key,
                base_url=self.settings.elevenlabs_base_url,
                timeout_s=self.settings.request_timeout_s,
            )
            result = provider.compose_detailed(
                prompt=(None if composition_plan is not None else prompt),
                composition_plan=composition_plan,
                music_length_ms=duration_ms,
                force_instrumental=(not vocals),
                seed=params.get("seed"),
                model_id=params.get("model_id"),
                output_format=str(params.get("output_format") or self.settings.output_format),
                store_for_inpainting=store_for_inpainting,
            )

            out_path = self.audio_dir / f"{job_id}.mp3"
            out_path.write_bytes(result.audio_bytes)
            self.store.set_status(job_id, status="succeeded", output_path=str(out_path), song_id=result.song_id)
        except Exception as e:
            self.store.set_status(job_id, status="failed", error=str(e))

    def run_inpaint(self, *, job_id: str, composition_plan: dict[str, Any], output_format: str) -> None:
        """Run an inpaint job."""
        try:
            self.store.set_status(job_id, status="running")
            self.audio_dir.mkdir(parents=True, exist_ok=True)

            provider = ElevenLabsMusicProviderStdlib(
                api_key=self.settings.elevenlabs_api_key,
                base_url=self.settings.elevenlabs_base_url,
                timeout_s=self.settings.request_timeout_s,
            )
            result = provider.inpaint(
                composition_plan=composition_plan,
                output_format=output_format,
            )

            out_path = self.audio_dir / f"{job_id}.mp3"
            out_path.write_bytes(result.audio_bytes)
            self.store.set_status(job_id, status="succeeded", output_path=str(out_path), song_id=result.song_id)
        except Exception as e:
            self.store.set_status(job_id, status="failed", error=str(e))


STATE = AppState()
STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"
ADMIN_HTML = STATIC_DIR / "admin.html"


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
                        "params": json.loads(rec.params_json),
                        "audio_url": audio_url,
                        "error": rec.error,
                        "song_id": rec.song_id,
                    }
                )
            _json_response(self, 200, {"jobs": out})
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
            self.wfile.write(data)
            return

        # Stems endpoint
        if self.path.startswith("/api/stems/"):
            job_id = self.path.split("/api/stems/", 1)[1].strip().split("?", 1)[0]
            rec = STATE.store.get(job_id)
            if not rec:
                _error(self, 404, "job not found")
                return
            if rec.status != "succeeded":
                _error(self, 409, "job not succeeded")
                return
            if rec.provider != "elevenlabs":
                _error(self, 400, "stems only available for elevenlabs provider")
                return
            if not rec.song_id:
                _error(self, 404, "song_id not available for this job")
                return

            try:
                provider = ElevenLabsMusicProviderStdlib(
                    api_key=STATE.settings.elevenlabs_api_key,
                    base_url=STATE.settings.elevenlabs_base_url,
                    timeout_s=STATE.settings.request_timeout_s,
                )
                stems = provider.get_stems(song_id=rec.song_id)
            except Exception as e:
                _error(self, 500, f"stems separation failed: {e}")
                return

            vocals_url = None
            instrumental_url = None

            if stems.vocals_bytes:
                vocals_path = STATE.audio_dir / f"{job_id}_vocals.mp3"
                vocals_path.write_bytes(stems.vocals_bytes)
                vocals_url = f"/api/audio/{job_id}_vocals"

            if stems.instrumental_bytes:
                instrumental_path = STATE.audio_dir / f"{job_id}_instrumental.mp3"
                instrumental_path.write_bytes(stems.instrumental_bytes)
                instrumental_url = f"/api/audio/{job_id}_instrumental"

            _json_response(self, 200, {
                "job_id": job_id,
                "vocals_url": vocals_url,
                "instrumental_url": instrumental_url,
            })
            return

        # Stems audio files
        if self.path.startswith("/api/audio/") and ("_vocals" in self.path or "_instrumental" in self.path):
            job_id = self.path.split("/api/audio/", 1)[1].strip().split("?", 1)[0]
            if job_id.endswith(".mp3"):
                job_id = job_id.rsplit(".", 1)[0]
            path = STATE.audio_dir / f"{job_id}.mp3"
            if not path.exists():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", "audio/mpeg")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
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

            provider_name = STATE.settings.default_provider
            if isinstance(payload, dict) and payload.get("provider") and str(payload.get("provider")).strip():
                provider_name = str(payload.get("provider")).strip()
            if provider_name not in ("elevenlabs", "fal", "replicate", "stability", "suno", "minimax", "mureka", "lyria"):
                _error(self, 400, f"unknown provider: {provider_name}")
                return

            provider_params = params.get("provider_params") or {}
            output_format = str(provider_params.get("output_format") or STATE.settings.output_format)
            # force vocals off for non-elevenlabs/suno/minimax/mureka/lyria providers, unless MiniMax music via Replicate
            is_minimax_replicate = (
                provider_name == "replicate"
                and _is_minimax_music_model(str(provider_params.get("version") or ""))
            )
            if provider_name not in ("elevenlabs", "suno", "minimax", "mureka", "lyria") and not is_minimax_replicate:
                params["vocals"] = False
            params = {**params, "output_format": output_format, "provider": provider_name}

            job_ids: list[str] = []
            for _ in range(count):
                job_id = STATE.store.create_job(provider=provider_name, prompt=prompt, params=params, kind="variation")
                job_ids.append(job_id)

                t = threading.Thread(
                    target=STATE.run_job,
                    kwargs={"job_id": job_id, "prompt": prompt, "params": params},
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

            provider_name = STATE.settings.default_provider
            if isinstance(payload, dict) and payload.get("provider") and str(payload.get("provider")).strip():
                provider_name = str(payload.get("provider")).strip()
            if provider_name not in ("elevenlabs", "fal", "replicate", "stability", "suno", "minimax", "mureka", "lyria"):
                _error(self, 400, f"unknown provider: {provider_name}")
                return

            provider_params = params.get("provider_params") or {}
            output_format = str(provider_params.get("output_format") or STATE.settings.output_format)
            # force vocals off for non-elevenlabs/suno/minimax/mureka/lyria providers, unless MiniMax music via Replicate
            is_minimax_replicate = (
                provider_name == "replicate"
                and _is_minimax_music_model(str(provider_params.get("version") or ""))
            )
            if provider_name not in ("elevenlabs", "suno", "minimax", "mureka", "lyria") and not is_minimax_replicate:
                params["vocals"] = False
            params = {**params, "output_format": output_format, "provider": provider_name}
            job_id = STATE.store.create_job(provider=provider_name, prompt=prompt, params=params, kind="generate")

            t = threading.Thread(
                target=STATE.run_job,
                kwargs={"job_id": job_id, "prompt": prompt, "params": params},
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
            if new_duration > 300:
                _error(self, 400, "total duration exceeds 300 seconds")
                return

            # NOTE: ElevenLabs Music API doesn't expose a true "extend" continuation endpoint
            # in our current integration. We implement extend by re-composing a longer version
            # with the same prompt/params (best-effort continuity).
            provider_name = parent.provider
            new_params = dict(parent_params)
            new_params["duration_sec"] = new_duration

            # Optional override
            if isinstance(payload, dict) and payload.get("provider") and str(payload.get("provider")).strip():
                new_params["provider"] = str(payload.get("provider")).strip()
            if isinstance(payload, dict) and isinstance(payload.get("provider_params"), dict):
                new_params["provider_params"] = payload.get("provider_params")
                new_params["output_format"] = str(
                    payload["provider_params"].get("output_format")
                    or new_params.get("output_format")
                    or STATE.settings.output_format
                )
            if str(new_params.get("provider") or provider_name) not in ("elevenlabs", "fal", "replicate", "stability", "suno"):
                _error(self, 400, f"unknown provider: {new_params.get('provider')}")
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

        if self.path == "/api/generate_store":
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

            store_for_inpainting = bool(payload.get("store_for_inpainting", False))
            provider_name = "elevenlabs"  # Only elevenlabs supports this
            if payload.get("provider") and str(payload.get("provider")).strip() != "elevenlabs":
                _error(self, 400, "store_for_inpainting only available for elevenlabs provider")
                return

            provider_params = params.get("provider_params") or {}
            output_format = str(provider_params.get("output_format") or STATE.settings.output_format)
            params = {**params, "output_format": output_format, "provider": provider_name, "store_for_inpainting": store_for_inpainting}
            job_id = STATE.store.create_job(provider=provider_name, prompt=prompt, params=params, kind="generate_store")

            t = threading.Thread(
                target=STATE.run_job_store,
                kwargs={"job_id": job_id, "prompt": prompt, "params": params},
                daemon=True,
            )
            t.start()

            _json_response(self, 200, {"job_id": job_id})
            return

        if self.path == "/api/inpaint":
            try:
                length = int(self.headers.get("content-length") or "0")
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))

                source_job_id = str(payload.get("source_job_id") or "").strip()
                if not source_job_id:
                    raise ValueError("source_job_id is required")

                composition_plan = payload.get("composition_plan")
                if not isinstance(composition_plan, dict):
                    raise ValueError("composition_plan must be an object")

                output_format = str(payload.get("output_format") or STATE.settings.output_format)
            except ValueError as e:
                _error(self, 400, str(e))
                return
            except Exception:
                _error(self, 400, "invalid JSON")
                return

            source_job = STATE.store.get(source_job_id)
            if not source_job:
                _error(self, 404, "source job not found")
                return
            if source_job.status != "succeeded":
                _error(self, 409, "source job not succeeded")
                return
            if source_job.provider != "elevenlabs":
                _error(self, 400, "inpainting only available for elevenlabs provider")
                return
            if not source_job.song_id:
                _error(self, 404, "source job has no song_id (not stored for inpainting)")
                return

            params: dict[str, Any] = {
                "source_job_id": source_job_id,
                "source_song_id": source_job.song_id,
                "composition_plan": composition_plan,
                "output_format": output_format,
                "provider": "elevenlabs",
            }
            prompt = f"Inpaint: {source_job.prompt[:100]}..."
            job_id = STATE.store.create_job(provider="elevenlabs", prompt=prompt, params=params, kind="inpaint", parent_job_id=source_job_id)

            t = threading.Thread(
                target=STATE.run_inpaint,
                kwargs={"job_id": job_id, "composition_plan": composition_plan, "output_format": output_format},
                daemon=True,
            )
            t.start()

            _json_response(self, 200, {"job_id": job_id, "source_job_id": source_job_id, "source_song_id": source_job.song_id})
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
                # Reload settings in-place
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
        # Keep console noise low for local usage.
        return


def main() -> None:
    host = os.getenv("AI_MUSIC_HOST", "127.0.0.1")
    port = int(os.getenv("AI_MUSIC_PORT", "8000"))
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
    import time

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
        req = urllib.request.Request(url, headers=headers, method="GET")
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
            if pid == "elevenlabs":
                attempts.append(
                    attempt_get(
                        name="user",
                        url=f"{STATE.settings.elevenlabs_base_url}/v1/user",
                        headers={"xi-api-key": STATE.settings.elevenlabs_api_key},
                    )
                )
                if not attempts[-1]["ok"]:
                    attempts.append(
                        attempt_get(
                            name="models",
                            url=f"{STATE.settings.elevenlabs_base_url}/v1/models",
                            headers={"xi-api-key": STATE.settings.elevenlabs_api_key},
                        )
                    )
            elif pid == "replicate":
                attempts.append(
                    attempt_get(
                        name="account_bearer",
                        url=f"{STATE.settings.replicate_base_url}/v1/account",
                        headers={"Authorization": f"Bearer {STATE.settings.replicate_api_token}"},
                    )
                )
                if not attempts[-1]["ok"] and attempts[-1].get("http_status") in (401, 403):
                    attempts.append(
                        attempt_get(
                            name="account_token",
                            url=f"{STATE.settings.replicate_base_url}/v1/account",
                            headers={"Authorization": f"Token {STATE.settings.replicate_api_token}"},
                        )
                    )
            elif pid == "stability":
                attempts.append(
                    attempt_get(
                        name="user_account",
                        url=f"{STATE.settings.stability_base_url}/v1/user/account",
                        headers={"Authorization": f"Bearer {STATE.settings.stability_api_key}"},
                    )
                )
                if not attempts[-1]["ok"]:
                    attempts.append(
                        attempt_get(
                            name="user_balance",
                            url=f"{STATE.settings.stability_base_url}/v1/user/balance",
                            headers={"Authorization": f"Bearer {STATE.settings.stability_api_key}"},
                        )
                    )
            elif pid == "fal":
                attempts.append(
                    attempt_get(
                        name="platform_models",
                        url=f"{STATE.settings.fal_platform_base_url}/v1/models?limit=1",
                        headers={"Authorization": f"Key {STATE.settings.fal_key}"},
                    )
                )
                model_id = (
                    (STATE.settings.provider_ui_defaults or {}).get("fal", {}).get("model_id")
                    or "fal-ai/stable-audio-25/text-to-audio"
                )
                dummy_request_id = "00000000-0000-0000-0000-000000000000"
                attempts.append(
                    attempt_get(
                        name="queue_dummy_status",
                        url=f"{STATE.settings.fal_queue_base_url}/{model_id}/requests/{dummy_request_id}/status",
                        headers={"Authorization": f"Key {STATE.settings.fal_key}"},
                        ok_if_status=lambda s: (400 <= s < 500 and not _is_auth_error(s)) or (200 <= s < 300),
                    )
                )
            elif pid == "suno":
                attempts.append(
                    attempt_get(
                        name="suno_health",
                        url=f"{STATE.settings.suno_base_url}/health",
                        headers={"Authorization": f"Bearer {STATE.settings.suno_api_key}"},
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

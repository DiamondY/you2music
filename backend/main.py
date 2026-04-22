from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import FastAPI, HTTPException
from fastapi import Header, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app_state import AppState
from providers.elevenlabs import ElevenLabsMusicProvider, ElevenLabsInpaintResult
from providers.fal import FalQueueClient
from providers.replicate import ReplicateClient
from providers.registry import providers_payload
from providers.stability import StabilityAudioClient
from admin_config import load_local_config, redacted_config, save_local_config


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    lyrics: str | None = Field(default=None, max_length=12000)
    duration_sec: int = Field(ge=3, le=300)
    vocals: bool = True
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    model_id: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=64)
    provider_params: dict[str, Any] | None = Field(default=None)


class GenerateManyRequest(GenerateRequest):
    count: int = Field(default=2, ge=1, le=4)


class ExtendRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)
    extra_sec: int = Field(ge=3, le=180)
    provider: str | None = Field(default=None, max_length=64)
    provider_params: dict[str, Any] | None = Field(default=None)


class InpaintRequest(BaseModel):
    """Request to inpaint/edit an existing song.

    Inpainting is an Enterprise-only feature from ElevenLabs.
    Use source_from in composition_plan sections to reference existing song parts.
    """
    source_job_id: str = Field(min_length=1, max_length=64, description="Job ID of the source song to edit")
    composition_plan: dict[str, Any] = Field(description="Composition plan with source_from references")
    output_format: str | None = Field(default=None, max_length=32)


class GenerateStoreRequest(GenerateRequest):
    """Generate and store for inpainting (Enterprise-only)."""
    store_for_inpainting: bool = Field(default=False, description="Store song for later inpainting")


def _sanitize_filename(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "_", text.strip())[:80]
    return text or "audio"


def _build_prompt(*, base_prompt: str, lyrics: str | None, vocals: bool) -> str:
    parts: list[str] = [base_prompt.strip()]
    if vocals:
        # Nudge: "singing with vocals" helps the model choose a vocal style.
        parts.append("with vocals, singing (do not be instrumental-only)")
    else:
        parts.append("instrumental only (no vocals)")
    if lyrics and lyrics.strip():
        parts.append("Lyrics:\n" + lyrics.strip())
    return "\n\n".join(parts).strip()


def _apply_provider_prompt_options(
    *,
    base_prompt: str,
    lyrics: str | None,
    vocals: bool,
    provider_params: dict[str, Any] | None,
) -> str:
    raw_prompt = bool((provider_params or {}).get("raw_prompt", False))
    if raw_prompt:
        # Still include user-provided lyrics if any, but don't add our "vocals" nudge.
        parts = [base_prompt.strip()]
        if lyrics and lyrics.strip():
            parts.append(lyrics.strip())
        return "\n\n".join(parts).strip()
    return _build_prompt(base_prompt=base_prompt, lyrics=lyrics, vocals=vocals)


def _resolve_provider(req_provider: str | None) -> str:
    p = (req_provider or STATE.settings.default_provider or "elevenlabs").strip()
    return p or "elevenlabs"


def _resolve_output_format(provider_params: dict[str, Any] | None) -> str:
    raw = (provider_params or {}).get("output_format")
    if raw and isinstance(raw, str) and raw.strip():
        return raw.strip()
    return STATE.settings.output_format


def _parse_composition_plan(provider_params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not provider_params:
        return None
    if provider_params.get("use_composition_plan") is not True:
        return None
    raw = provider_params.get("composition_plan_json")
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"composition_plan_json invalid JSON: {e}")
    raise HTTPException(status_code=400, detail="composition_plan_json must be JSON object or string")


STATE = AppState.create()

app = FastAPI(title="you2music", version="0.1.0")

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))

@app.get("/admin", response_class=HTMLResponse)
def admin_page() -> HTMLResponse:
    return HTMLResponse((static_dir / "admin.html").read_text(encoding="utf-8"))


@app.get("/api/providers")
def get_providers() -> dict[str, Any]:
    return providers_payload(STATE.settings)


def _require_admin(token: str | None) -> None:
    expected = (STATE.settings.admin_token or "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="admin token not configured (set AI_MUSIC_ADMIN_TOKEN or config admin_token)")
    if not token or token.strip() != expected:
        raise HTTPException(status_code=403, detail="invalid admin token")


class AdminConfigRequest(BaseModel):
    config: dict[str, Any]


@app.get("/api/admin/config")
def admin_get_config(x_admin_token: str | None = Header(default=None, alias="x-admin-token")) -> dict[str, Any]:
    _require_admin(x_admin_token)
    cfg = load_local_config()
    return {"config": redacted_config(cfg)}


@app.get("/api/admin/providers")
def admin_get_providers(x_admin_token: str | None = Header(default=None, alias="x-admin-token")) -> dict[str, Any]:
    _require_admin(x_admin_token)
    # include_disabled=True so admin can enable/disable providers even when filtered
    return providers_payload(STATE.settings, include_disabled=True)


@app.post("/api/admin/config")
def admin_set_config(req: AdminConfigRequest, x_admin_token: str | None = Header(default=None, alias="x-admin-token")) -> dict[str, Any]:
    _require_admin(x_admin_token)
    current = load_local_config()
    new_cfg = req.config or {}

    # Preserve secrets if client sent masked values.
    cur_secrets = current.get("secrets") if isinstance(current.get("secrets"), dict) else {}
    new_secrets = new_cfg.get("secrets") if isinstance(new_cfg.get("secrets"), dict) else {}
    merged_secrets: dict[str, Any] = dict(cur_secrets)
    for k, v in new_secrets.items():
        if v == "********":
            continue
        merged_secrets[k] = v
    if merged_secrets:
        new_cfg["secrets"] = merged_secrets

    if new_cfg.get("admin_token") == "********":
        new_cfg["admin_token"] = current.get("admin_token", "")

    save_local_config(new_cfg)
    STATE.reload()
    return {"ok": True}


@app.post("/api/admin/reload")
def admin_reload(x_admin_token: str | None = Header(default=None, alias="x-admin-token")) -> dict[str, Any]:
    _require_admin(x_admin_token)
    STATE.reload()
    return {"ok": True}


@app.post("/api/admin/test")
async def admin_test(x_admin_token: str | None = Header(default=None, alias="x-admin-token")) -> dict[str, Any]:
    _require_admin(x_admin_token)
    # Run lightweight connectivity/auth checks. Avoid real generations by default.
    #
    # Notes:
    # - Prefer "whoami/account/balance" style endpoints.
    # - For fal queue we use a "dummy request_id status" probe so we don't enqueue jobs.
    import os
    import time

    providers = providers_payload(STATE.settings, include_disabled=True)["providers"]
    enabled = STATE.settings.enabled_providers or [p["id"] for p in providers]
    enabled_set = set(enabled)

    def _is_auth_error(status: int) -> bool:
        return status in (401, 403)

    async def _attempt_get(
        client: httpx.AsyncClient,
        *,
        name: str,
        url: str,
        headers: dict[str, str],
        ok_if_status: Callable[[int], bool] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            r = await client.get(url, headers=headers)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            status = int(r.status_code)
            ok = ok_if_status(status) if ok_if_status else (200 <= status < 300)
            kind = "ok" if ok else ("auth_error" if _is_auth_error(status) else "http_error")
            return {
                "name": name,
                "url": url,
                "http_status": status,
                "ok": ok,
                "kind": kind,
                "elapsed_ms": elapsed_ms,
            }
        except Exception as e:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return {
                "name": name,
                "url": url,
                "ok": False,
                "kind": "network_error",
                "error": f"{type(e).__name__}: {e}",
                "elapsed_ms": elapsed_ms,
            }

    def _summarize_attempts(attempts: list[dict[str, Any]]) -> tuple[bool, str, str]:
        if any(a.get("ok") is True for a in attempts):
            return True, "ok", "ok"
        if any(a.get("kind") == "auth_error" for a in attempts):
            return False, "auth_error", "authentication failed (401/403)"
        if any(a.get("kind") == "network_error" for a in attempts):
            return False, "network_error", "network/proxy/TLS error"
        return False, "http_error", "unexpected HTTP status"

    results: list[dict[str, Any]] = []
    proxy_info = {
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
    }

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, trust_env=True) as client:
        for p in providers:
            pid = p["id"]
            if pid not in enabled_set:
                continue
            if p.get("ready") is False:
                results.append(
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
                        await _attempt_get(
                            client,
                            name="user",
                            url=f"{STATE.settings.elevenlabs_base_url}/v1/user",
                            headers={"xi-api-key": STATE.settings.elevenlabs_api_key},
                        )
                    )
                    if not attempts[-1]["ok"]:
                        attempts.append(
                            await _attempt_get(
                                client,
                                name="models",
                                url=f"{STATE.settings.elevenlabs_base_url}/v1/models",
                                headers={"xi-api-key": STATE.settings.elevenlabs_api_key},
                            )
                        )
                elif pid == "replicate":
                    attempts.append(
                        await _attempt_get(
                            client,
                            name="account_bearer",
                            url=f"{STATE.settings.replicate_base_url}/v1/account",
                            headers={"Authorization": f"Bearer {STATE.settings.replicate_api_token}"},
                        )
                    )
                    if not attempts[-1]["ok"] and attempts[-1].get("http_status") in (401, 403):
                        attempts.append(
                            await _attempt_get(
                                client,
                                name="account_token",
                                url=f"{STATE.settings.replicate_base_url}/v1/account",
                                headers={"Authorization": f"Token {STATE.settings.replicate_api_token}"},
                            )
                        )
                elif pid == "stability":
                    attempts.append(
                        await _attempt_get(
                            client,
                            name="user_account",
                            url=f"{STATE.settings.stability_base_url}/v1/user/account",
                            headers={"Authorization": f"Bearer {STATE.settings.stability_api_key}"},
                        )
                    )
                    if not attempts[-1]["ok"]:
                        attempts.append(
                            await _attempt_get(
                                client,
                                name="user_balance",
                                url=f"{STATE.settings.stability_base_url}/v1/user/balance",
                                headers={"Authorization": f"Bearer {STATE.settings.stability_api_key}"},
                            )
                        )
                elif pid == "fal":
                    attempts.append(
                        await _attempt_get(
                            client,
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
                        await _attempt_get(
                            client,
                            name="queue_dummy_status",
                            url=f"{STATE.settings.fal_queue_base_url}/{model_id}/requests/{dummy_request_id}/status",
                            headers={"Authorization": f"Key {STATE.settings.fal_key}"},
                            ok_if_status=lambda s: (400 <= s < 500 and not _is_auth_error(s)) or (200 <= s < 300),
                        )
                    )
                else:
                    results.append(
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

            ok, kind, message = _summarize_attempts(attempts)
            results.append(
                {
                    "provider": pid,
                    "ok": ok,
                    "kind": kind,
                    "message": message,
                    "attempts": attempts,
                }
            )

    return {"ok": True, "results": results, "proxy": proxy_info}


@app.post("/api/generate")
async def generate(req: GenerateRequest) -> dict[str, Any]:
    provider_name = _resolve_provider(req.provider)
    if provider_name not in ("elevenlabs", "fal", "replicate", "stability"):
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider_name}")

    provider_params = req.provider_params or {}
    vocals = req.vocals
    if provider_name != "elevenlabs":
        vocals = False
    params: dict[str, Any] = {
        "duration_sec": req.duration_sec,
        "vocals": vocals,
        "seed": req.seed,
        "model_id": req.model_id,
        "output_format": _resolve_output_format(provider_params),
        "provider": provider_name,
        "provider_params": provider_params,
    }

    prompt = _apply_provider_prompt_options(
        base_prompt=req.prompt,
        lyrics=req.lyrics,
        vocals=vocals,
        provider_params=provider_params,
    )
    job_id = STATE.store.create_job(provider=provider_name, prompt=prompt, params=params, kind="generate")

    asyncio.create_task(_run_job(job_id=job_id, prompt=prompt, params=params))
    return {"job_id": job_id}


@app.post("/api/generate_many")
async def generate_many(req: GenerateManyRequest) -> dict[str, Any]:
    provider_name = _resolve_provider(req.provider)
    if provider_name not in ("elevenlabs", "fal", "replicate", "stability"):
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider_name}")
    provider_params = req.provider_params or {}
    vocals = req.vocals
    if provider_name != "elevenlabs":
        vocals = False
    params: dict[str, Any] = {
        "duration_sec": req.duration_sec,
        "vocals": vocals,
        "seed": req.seed,
        "model_id": req.model_id,
        "output_format": _resolve_output_format(provider_params),
        "provider": provider_name,
        "provider_params": provider_params,
    }
    prompt = _apply_provider_prompt_options(
        base_prompt=req.prompt,
        lyrics=req.lyrics,
        vocals=vocals,
        provider_params=provider_params,
    )

    job_ids: list[str] = []
    for _ in range(req.count):
        job_id = STATE.store.create_job(provider=provider_name, prompt=prompt, params=params, kind="variation")
        job_ids.append(job_id)
        asyncio.create_task(_run_job(job_id=job_id, prompt=prompt, params=params))

    return {"job_ids": job_ids}


@app.post("/api/extend")
async def extend(req: ExtendRequest) -> dict[str, Any]:
    parent = STATE.store.get(req.job_id)
    if not parent:
        raise HTTPException(status_code=404, detail="job not found")
    if parent.status != "succeeded":
        raise HTTPException(status_code=409, detail="job not ready")

    try:
        parent_params = json.loads(parent.params_json)
    except Exception:
        parent_params = {}

    duration_sec = int(parent_params.get("duration_sec") or 0)
    new_duration = duration_sec + int(req.extra_sec)
    if new_duration > 300:
        raise HTTPException(status_code=400, detail="total duration exceeds 300 seconds")

    new_params = dict(parent_params)
    new_params["duration_sec"] = new_duration
    if req.provider:
        new_provider = _resolve_provider(req.provider)
        if new_provider not in ("elevenlabs", "fal", "replicate", "stability"):
            raise HTTPException(status_code=400, detail=f"unknown provider: {new_provider}")
        new_params["provider"] = new_provider
    if req.provider_params:
        new_params["provider_params"] = req.provider_params
        new_params["output_format"] = _resolve_output_format(req.provider_params)

    job_id = STATE.store.create_job(
        provider=str(new_params.get("provider") or parent.provider),
        prompt=parent.prompt,
        params=new_params,
        kind="extend",
        parent_job_id=parent.job_id,
    )

    asyncio.create_task(_run_job(job_id=job_id, prompt=parent.prompt, params=new_params))
    return {"job_id": job_id, "parent_job_id": parent.job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")

    audio_url = None
    if rec.status == "succeeded" and rec.output_path:
        audio_url = f"/api/audio/{rec.job_id}"

    return {
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


@app.get("/api/jobs")
def get_jobs(ids: str = Query(default="")) -> dict[str, Any]:
    job_ids = [x for x in ids.split(",") if x][:20]
    out: list[dict[str, Any]] = []
    for job_id in job_ids:
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
            }
        )
    return {"jobs": out}


def _media_type_for_path(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".mp3":
        return "audio/mpeg"
    if suf == ".wav":
        return "audio/wav"
    return "application/octet-stream"


@app.get("/api/audio/{job_id}")
def get_audio(job_id: str):
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if rec.status != "succeeded" or not rec.output_path:
        raise HTTPException(status_code=404, detail="audio not ready")

    path = Path(rec.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio missing on disk")

    return FileResponse(str(path), media_type=_media_type_for_path(path), filename=path.name)


@app.get("/api/audio/{job_id}.mp3")
def get_audio_mp3_compat(job_id: str):
    # Backwards-compatible alias (older UI/clients).
    return get_audio(job_id)


@app.get("/api/stems/{job_id}")
async def get_stems(job_id: str) -> dict[str, Any]:
    """Get stems (vocals and instrumental) for a completed ElevenLabs job."""
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if rec.status != "succeeded":
        raise HTTPException(status_code=409, detail="job not succeeded")
    if rec.provider != "elevenlabs":
        raise HTTPException(status_code=400, detail="stems only available for elevenlabs provider")
    if not rec.song_id:
        raise HTTPException(status_code=404, detail="song_id not available for this job")

    provider = ElevenLabsMusicProvider(
        api_key=STATE.settings.elevenlabs_api_key,
        base_url=STATE.settings.elevenlabs_base_url,
        timeout_s=STATE.settings.request_timeout_s,
    )

    try:
        stems = await provider.get_stems(song_id=rec.song_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"stems separation failed: {e}")

    # Save stems to disk
    STATE.audio_dir.mkdir(parents=True, exist_ok=True)
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

    return {
        "job_id": job_id,
        "vocals_url": vocals_url,
        "instrumental_url": instrumental_url,
    }


@app.get("/api/audio/{job_id}_vocals")
def get_audio_vocals(job_id: str):
    """Get vocals stem for a job."""
    path = STATE.audio_dir / f"{job_id}_vocals.mp3"
    if not path.exists():
        raise HTTPException(status_code=404, detail="vocals stem not found")
    return FileResponse(str(path), media_type="audio/mpeg", filename=f"{job_id}_vocals.mp3")


@app.get("/api/audio/{job_id}_instrumental")
def get_audio_instrumental(job_id: str):
    """Get instrumental stem for a job."""
    path = STATE.audio_dir / f"{job_id}_instrumental.mp3"
    if not path.exists():
        raise HTTPException(status_code=404, detail="instrumental stem not found")
    return FileResponse(str(path), media_type="audio/mpeg", filename=f"{job_id}_instrumental.mp3")


@app.post("/api/generate_store")
async def generate_store(req: GenerateStoreRequest) -> dict[str, Any]:
    """Generate music and store for inpainting (Enterprise-only).

    This uses the compose_detailed endpoint with store_for_inpainting=True.
    The song_id will be saved for later inpainting operations.
    """
    provider_name = _resolve_provider(req.provider)
    if provider_name != "elevenlabs":
        raise HTTPException(status_code=400, detail="store_for_inpainting only available for elevenlabs provider")

    provider_params = req.provider_params or {}
    params: dict[str, Any] = {
        "duration_sec": req.duration_sec,
        "vocals": req.vocals,
        "seed": req.seed,
        "model_id": req.model_id,
        "output_format": _resolve_output_format(provider_params),
        "provider": provider_name,
        "provider_params": provider_params,
        "store_for_inpainting": req.store_for_inpainting,
    }

    prompt = _apply_provider_prompt_options(
        base_prompt=req.prompt,
        lyrics=req.lyrics,
        vocals=req.vocals,
        provider_params=provider_params,
    )
    job_id = STATE.store.create_job(provider=provider_name, prompt=prompt, params=params, kind="generate_store")

    asyncio.create_task(_run_job_store(job_id=job_id, prompt=prompt, params=params))
    return {"job_id": job_id}


@app.post("/api/inpaint")
async def inpaint(req: InpaintRequest) -> dict[str, Any]:
    """Inpaint/edit an existing song (Enterprise-only).

    Uses composition_plan with source_from to reference existing song sections.
    Sections with source_from will be kept from the original.
    Sections without source_from will be regenerated.
    Use negative_ranges to regenerate portions inside kept sections.
    """
    source_job = STATE.store.get(req.source_job_id)
    if not source_job:
        raise HTTPException(status_code=404, detail="source job not found")
    if source_job.status != "succeeded":
        raise HTTPException(status_code=409, detail="source job not succeeded")
    if source_job.provider != "elevenlabs":
        raise HTTPException(status_code=400, detail="inpainting only available for elevenlabs provider")
    if not source_job.song_id:
        raise HTTPException(status_code=404, detail="source job has no song_id (not stored for inpainting)")

    output_format = req.output_format or STATE.settings.output_format

    params: dict[str, Any] = {
        "source_job_id": req.source_job_id,
        "source_song_id": source_job.song_id,
        "composition_plan": req.composition_plan,
        "output_format": output_format,
        "provider": "elevenlabs",
    }

    # Build prompt from composition plan for logging
    prompt = f"Inpaint: {source_job.prompt[:100]}..."

    job_id = STATE.store.create_job(provider="elevenlabs", prompt=prompt, params=params, kind="inpaint", parent_job_id=req.source_job_id)

    asyncio.create_task(_run_inpaint(job_id=job_id, composition_plan=req.composition_plan, output_format=output_format))
    return {"job_id": job_id, "source_job_id": req.source_job_id, "source_song_id": source_job.song_id}


async def _run_job(*, job_id: str, prompt: str, params: dict[str, Any]) -> None:
    try:
        STATE.store.set_status(job_id, status="running")
        STATE.audio_dir.mkdir(parents=True, exist_ok=True)

        provider_name = str(params.get("provider") or "elevenlabs")
        duration_ms = int(params["duration_sec"]) * 1000
        vocals = bool(params["vocals"])
        provider_params = params.get("provider_params") or {}

        out_bytes: bytes
        out_ext = "mp3"
        song_id: str | None = None

        if provider_name == "elevenlabs":
            provider = ElevenLabsMusicProvider(
                api_key=STATE.settings.elevenlabs_api_key,
                base_url=STATE.settings.elevenlabs_base_url,
                timeout_s=STATE.settings.request_timeout_s,
            )
            composition_plan = _parse_composition_plan(provider_params)
            result = await provider.compose(
                prompt=(None if composition_plan is not None else prompt),
                composition_plan=composition_plan,
                music_length_ms=duration_ms,
                force_instrumental=(not vocals),
                seed=params.get("seed"),
                model_id=params.get("model_id"),
                output_format=str(params.get("output_format") or STATE.settings.output_format),
            )
            out_bytes = result.audio_bytes
            out_ext = "mp3"
            song_id = result.song_id  # Save for stems separation
        elif provider_name == "fal":
            client = FalQueueClient(
                key=STATE.settings.fal_key,
                queue_base_url=STATE.settings.fal_queue_base_url,
                timeout_s=STATE.settings.request_timeout_s,
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
            request_id = await client.submit(model_id=model_id, input_json=fal_input)
            result_json = await client.poll_until_done(
                model_id=model_id,
                request_id=request_id,
                poll_interval_s=float(provider_params.get("poll_interval_s") or 1.0),
                max_wait_s=300.0,
            )
            audio_url = client.extract_audio_url(result_json)
            async with httpx.AsyncClient(timeout=STATE.settings.request_timeout_s) as dl:
                r = await dl.get(audio_url)
                r.raise_for_status()
                out_bytes = r.content
            out_ext = "wav"
        elif provider_name == "replicate":
            client = ReplicateClient(
                api_token=STATE.settings.replicate_api_token,
                base_url=STATE.settings.replicate_base_url,
                timeout_s=STATE.settings.request_timeout_s,
            )
            version = str(provider_params.get("version") or "stability-ai/stable-audio-2.5")
            duration = provider_params.get("duration")
            if duration is None:
                duration = int(params["duration_sec"])
            inp: dict[str, Any] = {"prompt": prompt, "duration": int(duration)}
            seed = provider_params.get("seed", params.get("seed"))
            if seed is not None:
                inp["seed"] = int(seed)
            if provider_params.get("steps") is not None:
                inp["steps"] = int(provider_params["steps"])
            if provider_params.get("cfg_scale") is not None:
                inp["cfg_scale"] = float(provider_params["cfg_scale"])
            pid = await client.create_prediction(version=version, input_json=inp)
            pred = await client.poll_until_done(
                prediction_id=pid,
                poll_interval_s=float(provider_params.get("poll_interval_s") or 1.0),
                max_wait_s=300.0,
            )
            audio_url = client.extract_audio_url(pred)
            async with httpx.AsyncClient(timeout=STATE.settings.request_timeout_s) as dl:
                r = await dl.get(audio_url)
                r.raise_for_status()
                out_bytes = r.content
            out_ext = "wav"
        elif provider_name == "stability":
            client = StabilityAudioClient(
                api_key=STATE.settings.stability_api_key,
                base_url=STATE.settings.stability_base_url,
                timeout_s=STATE.settings.request_timeout_s,
            )
            endpoint_path = str(provider_params.get("endpoint_path") or "/v2beta/audio/stable-audio-2/text-to-audio")
            seconds_total = provider_params.get("seconds_total")
            if seconds_total is None:
                seconds_total = int(params["duration_sec"])
            seed = provider_params.get("seed", params.get("seed"))
            steps = provider_params.get("steps")
            cfg_scale = provider_params.get("cfg_scale")
            output_format = provider_params.get("output_format")
            res = await client.text_to_audio(
                endpoint_path=endpoint_path,
                prompt=prompt,
                seconds_total=int(seconds_total) if seconds_total is not None else None,
                seed=int(seed) if seed is not None else None,
                steps=int(steps) if steps is not None else None,
                cfg_scale=float(cfg_scale) if cfg_scale is not None else None,
                output_format=str(output_format) if output_format else None,
            )
            out_bytes = res.audio_bytes
            out_ext = "wav"
        else:
            raise RuntimeError(f"unknown provider: {provider_name}")

        out_path = STATE.audio_dir / f"{job_id}.{out_ext}"
        out_path.write_bytes(out_bytes)
        STATE.store.set_status(job_id, status="succeeded", output_path=str(out_path), song_id=song_id)
    except Exception as e:
        STATE.store.set_status(job_id, status="failed", error=str(e))


async def _run_job_store(*, job_id: str, prompt: str, params: dict[str, Any]) -> None:
    """Run a generate job with store_for_inpainting=True."""
    try:
        STATE.store.set_status(job_id, status="running")
        STATE.audio_dir.mkdir(parents=True, exist_ok=True)

        duration_ms = int(params["duration_sec"]) * 1000
        vocals = bool(params["vocals"])
        provider_params = params.get("provider_params") or {}
        store_for_inpainting = bool(params.get("store_for_inpainting", False))

        provider = ElevenLabsMusicProvider(
            api_key=STATE.settings.elevenlabs_api_key,
            base_url=STATE.settings.elevenlabs_base_url,
            timeout_s=STATE.settings.request_timeout_s,
        )
        composition_plan = _parse_composition_plan(provider_params)
        result = await provider.compose_detailed(
            prompt=(None if composition_plan is not None else prompt),
            composition_plan=composition_plan,
            music_length_ms=duration_ms,
            force_instrumental=(not vocals),
            seed=params.get("seed"),
            model_id=params.get("model_id"),
            output_format=str(params.get("output_format") or STATE.settings.output_format),
            store_for_inpainting=store_for_inpainting,
        )

        out_path = STATE.audio_dir / f"{job_id}.mp3"
        out_path.write_bytes(result.audio_bytes)
        STATE.store.set_status(job_id, status="succeeded", output_path=str(out_path), song_id=result.song_id)
    except Exception as e:
        STATE.store.set_status(job_id, status="failed", error=str(e))


async def _run_inpaint(*, job_id: str, composition_plan: dict[str, Any], output_format: str) -> None:
    """Run an inpaint job."""
    try:
        STATE.store.set_status(job_id, status="running")
        STATE.audio_dir.mkdir(parents=True, exist_ok=True)

        provider = ElevenLabsMusicProvider(
            api_key=STATE.settings.elevenlabs_api_key,
            base_url=STATE.settings.elevenlabs_base_url,
            timeout_s=STATE.settings.request_timeout_s,
        )
        result = await provider.inpaint(
            composition_plan=composition_plan,
            output_format=output_format,
        )

        out_path = STATE.audio_dir / f"{job_id}.mp3"
        out_path.write_bytes(result.audio_bytes)
        STATE.store.set_status(job_id, status="succeeded", output_path=str(out_path), song_id=result.song_id)
    except Exception as e:
        STATE.store.set_status(job_id, status="failed", error=str(e))


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("AI_MUSIC_HOST", "127.0.0.1")
    port = int(os.getenv("AI_MUSIC_PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)

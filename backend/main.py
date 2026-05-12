from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi import Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth import create_token, hash_password, verify_password
from providers.registry import providers_payload
from admin_config import load_local_config, redacted_config, save_local_config
from shared import (
    RANDOM_LYRICS_TEMPLATES,
    RANDOM_PROMPTS,
    generate_random_bpm,
    generate_random_duration_sec,
    generate_random_key_scale,
    generate_random_lyrics,
    generate_random_prompt,
)
from state import STATE
from deps import (
    _apply_provider_prompt_options,
    _auth_error_detail,
    _can_access_job,
    _is_admin,
    _media_type_for_path,
    _optional_current_user,
    _public_user,
    _resolve_output_format,
    _resolve_provider,
    _serialize_job,
    get_current_user,
    install_windows_asyncio_connection_reset_suppression,
    require_admin,
)
from user_store import UserRecord, UserRole
from workers import _job_worker_handler


class GenerateRequest(BaseModel):
    prompt: str = Field(default="", max_length=5000)
    lyrics: str | None = Field(default=None, max_length=12000)
    duration_sec: int = Field(ge=3, le=600)  # ACE-Step supports up to 600s
    vocals: bool = True
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    model_id: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=64)
    provider_params: dict[str, Any] | None = Field(default=None)


class GenerateManyRequest(GenerateRequest):
    count: int = Field(default=2, ge=1, le=4)


class ExtendRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)
    extra_sec: int = Field(ge=3, le=600)
    provider: str | None = Field(default=None, max_length=64)
    provider_params: dict[str, Any] | None = Field(default=None)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=72)
    invite_code: str = Field(min_length=1, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ProfileUpdateRequest(BaseModel):
    avatar_path: str | None = Field(default=None, max_length=500)


class PasswordUpdateRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=72)


class AdminUserUpdateRequest(BaseModel):
    role: UserRole | None = None
    daily_quota: int | None = Field(default=None, ge=0, le=100000)
    disabled: bool | None = None
    reset_password: str | None = Field(default=None, min_length=6, max_length=72)


class PublishRequest(BaseModel):
    share_permission: str = Field(default="listen_only", max_length=32)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    install_windows_asyncio_connection_reset_suppression()
    # Start provider worker pools.
    await STATE.start_workers(handler=_job_worker_handler)
    try:
        yield
    finally:
        # Stop provider workers and close shared httpx clients.
        await STATE.shutdown_workers()


app = FastAPI(title="you2music", version="0.1.0", lifespan=_lifespan)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))

@app.get("/admin", response_class=HTMLResponse)
def admin_page() -> HTMLResponse:
    return HTMLResponse((static_dir / "admin.html").read_text(encoding="utf-8"))


@app.post("/api/auth/register")
def auth_register(req: RegisterRequest) -> dict[str, Any]:
    username = req.username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username):
        raise HTTPException(status_code=400, detail="用户名只能包含字母、数字、点、短横线和下划线")
    try:
        user = STATE.user_store.create_user(
            username=username,
            password_hash=hash_password(req.password),
            invite_code=req.invite_code,
            daily_quota=STATE.settings.default_daily_quota,
        )
    except ValueError as e:
        msg = str(e)
        status = 409 if "exists" in msg or "used" in msg else 400
        raise HTTPException(status_code=status, detail=_auth_error_detail(msg)) from e
    return {"token": create_token(user=user, settings=STATE.settings), "user": _public_user(user)}


@app.post("/api/auth/login")
def auth_login(req: LoginRequest) -> dict[str, Any]:
    user = STATE.user_store.get_by_username(req.username)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.disabled:
        raise HTTPException(status_code=403, detail="账户已被禁用")
    return {"token": create_token(user=user, settings=STATE.settings), "user": _public_user(user)}


@app.get("/api/auth/me")
def auth_me(current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": _public_user(current_user)}


@app.put("/api/auth/me")
def auth_update_me(req: ProfileUpdateRequest, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    user = STATE.user_store.update_user(current_user.id, avatar_path=req.avatar_path)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return {"user": _public_user(user)}


@app.put("/api/auth/password")
def auth_update_password(req: PasswordUpdateRequest, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=403, detail="当前密码错误")
    try:
        password_hash = hash_password(req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    STATE.user_store.update_password(current_user.id, password_hash=password_hash)
    return {"ok": True}


@app.get("/api/providers")
def get_providers(current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    return providers_payload(STATE.settings)


def _sse_format(event: str, data: dict[str, Any]) -> bytes:
    # Minimal SSE format (UTF-8).
    # data must be one line; we JSON-dump to keep it compact.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


@app.get("/api/events")
async def events(current_user: UserRecord = Depends(get_current_user)) -> StreamingResponse:
    """Realtime event stream for multi-device/tab sync (FastAPI mode only)."""
    user_id = int(current_user.id)
    q = await STATE.event_hub.subscribe(user_id)

    async def gen():
        # Initial hello so client can mark stream as live.
        yield _sse_format("hello", {"ts_ms": int(time.time() * 1000)})
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15.0)
                    evt = str(item.get("type") or "message")
                    yield _sse_format(evt, item)
                except asyncio.TimeoutError:
                    yield _sse_format("ping", {"ts_ms": int(time.time() * 1000)})
        finally:
            await STATE.event_hub.unsubscribe(user_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream")


class AdminConfigRequest(BaseModel):
    config: dict[str, Any]


# ========================================
# Random Sample Generation (ACE-Step inspired)
# ========================================
@app.get("/api/random_sample")
def get_random_sample(current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    """Generate a random prompt and lyrics sample for quick inspiration."""
    # Prefer the new fine-grained generators backed by files under
    # `backend/random_content/`. Keep the legacy lists as fallback.
    prompt = generate_random_prompt() or random.choice(RANDOM_PROMPTS)
    lyrics = generate_random_lyrics() or random.choice(RANDOM_LYRICS_TEMPLATES)
    bpm = generate_random_bpm()
    key_scale = generate_random_key_scale()
    duration = generate_random_duration_sec()

    return {
        "prompt": prompt,
        "lyrics": lyrics,
        "bpm": bpm,
        "key_scale": key_scale,
        "duration": duration,
    }


_UPLOAD_MAX_BYTES = 20 * 1024 * 1024


def _audio_format_from_filename(name: str) -> str:
    n = (name or "").lower()
    if n.endswith(".wav"):
        return "wav"
    if n.endswith(".flac"):
        return "flac"
    return "mp3"


@app.post("/api/uploads/audio")
async def upload_audio(
    file: UploadFile = File(...),
    current_user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload an audio file for ACE-Step audio-input task types.

    Important: We store the file on disk and only keep a small upload_id in job
    params. Never persist base64 audio blobs in sqlite job params.
    """
    filename = str(file.filename or "").strip() or "audio"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="音频文件为空")
    if len(data) > _UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="音频文件不能超过 20MB")

    fmt = _audio_format_from_filename(filename)
    upload_id = uuid.uuid4().hex
    path = STATE.upload_dir / f"{current_user.id}-{upload_id}.{fmt}"
    path.write_bytes(data)
    return {"upload_id": upload_id, "filename": filename, "size_bytes": len(data), "format": fmt}


@app.get("/api/admin/config")
def admin_get_config(current_user: UserRecord = Depends(require_admin)) -> dict[str, Any]:
    cfg = load_local_config()
    return {"config": redacted_config(cfg)}


@app.get("/api/admin/providers")
def admin_get_providers(current_user: UserRecord = Depends(require_admin)) -> dict[str, Any]:
    # include_disabled=True so admin can enable/disable providers even when filtered
    return providers_payload(STATE.settings, include_disabled=True)


@app.post("/api/admin/config")
def admin_set_config(req: AdminConfigRequest, current_user: UserRecord = Depends(require_admin)) -> dict[str, Any]:
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

    for key in ("jwt_secret", "admin_password"):
        if new_cfg.get(key) == "********":
            new_cfg[key] = current.get(key, "")
    for section, keys in {
        "auth": ("jwt_secret", "admin_password"),
        "admin": ("password",),
    }.items():
        cur_obj = current.get(section) if isinstance(current.get(section), dict) else {}
        new_obj = new_cfg.get(section) if isinstance(new_cfg.get(section), dict) else {}
        if not isinstance(new_obj, dict):
            continue
        for key in keys:
            if new_obj.get(key) == "********":
                new_obj[key] = cur_obj.get(key, "")

    new_cfg.pop("admin_token", None)

    save_local_config(new_cfg)
    STATE.reload()
    return {"ok": True}


@app.post("/api/admin/reload")
def admin_reload(current_user: UserRecord = Depends(require_admin)) -> dict[str, Any]:
    STATE.reload()
    return {"ok": True}


@app.post("/api/admin/test")
async def admin_test(current_user: UserRecord = Depends(require_admin)) -> dict[str, Any]:
    # Run lightweight connectivity/auth checks. Avoid real generations by default.
    #
    # Notes:
    # - Prefer "whoami/account/balance" style endpoints.
    # - For fal queue we use a "dummy request_id status" probe so we don't enqueue jobs.
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
                if pid == "minimax":
                    # MiniMax API test - simple health check
                    attempts.append(
                        await _attempt_get(
                            client,
                            name="health",
                            url=f"{STATE.settings.minimax_base_url}/v1/music_generation",
                            headers={"Authorization": f"Bearer {STATE.settings.minimax_api_key}"},
                            ok_if_status=lambda s: s in (401, 403, 405, 400),  # These indicate the endpoint exists
                        )
                    )
                elif pid == "acestep":
                    # ACE-Step API test
                    attempts.append(
                        await _attempt_get(
                            client,
                            name="health",
                            url=f"{STATE.settings.acestep_base_url}/v1/models",
                            headers={"Authorization": f"Bearer {STATE.settings.acestep_api_key}"},
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


@app.get("/api/admin/users")
def admin_list_users(current_user: UserRecord = Depends(require_admin)) -> dict[str, Any]:
    return {"users": [_public_user(user) for user in STATE.user_store.list_users()]}


@app.put("/api/admin/users/{user_id}")
def admin_update_user(
    user_id: int,
    req: AdminUserUpdateRequest,
    current_user: UserRecord = Depends(require_admin),
) -> dict[str, Any]:
    # Handle password reset first (sets must_change_password flag)
    if req.reset_password:
        new_hash = hash_password(req.reset_password)
        STATE.user_store.update_password(user_id, password_hash=new_hash)
        STATE.user_store.set_must_change_password(user_id, True)
    try:
        user = STATE.user_store.update_user(
            user_id,
            role=req.role,
            daily_quota=req.daily_quota,
            disabled=req.disabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return {"user": _public_user(user)}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, current_user: UserRecord = Depends(require_admin)) -> dict[str, Any]:
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="cannot delete current user")
    try:
        ok = STATE.user_store.delete_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True}


@app.post("/api/admin/invite-codes")
def admin_create_invite_code(current_user: UserRecord = Depends(require_admin)) -> dict[str, Any]:
    code = STATE.user_store.create_invite_code(created_by=current_user.id)
    return {"invite_code": code.__dict__}


@app.get("/api/admin/invite-codes")
def admin_list_invite_codes(current_user: UserRecord = Depends(require_admin)) -> dict[str, Any]:
    return {"invite_codes": [code.__dict__ for code in STATE.user_store.list_invite_codes()]}


@app.get("/api/admin/jobs")
def admin_list_jobs(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None),
    current_user: UserRecord = Depends(require_admin),
) -> dict[str, Any]:
    total = STATE.store.count_jobs(include_all=True, status=status)
    records = STATE.store.list_page(offset=offset, limit=limit, include_all=True, status=status)
    user_map = {u.id: u.username for u in STATE.user_store.list_users()}
    jobs = []
    for rec in records:
        d = _serialize_job(rec)
        d["username"] = user_map.get(rec.user_id, str(rec.user_id) if rec.user_id else "-")
        jobs.append(d)
    return {"jobs": jobs, "total": total, "offset": offset, "limit": limit}


@app.get("/api/admin/api-logs")
def admin_get_api_logs(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    provider: str | None = Query(default=None),
    http_status: int | None = Query(default=None),
    http_status_family: int | None = Query(default=None, ge=1, le=9),
    current_user: UserRecord = Depends(require_admin),
) -> dict[str, Any]:
    http_status_min: int | None = None
    http_status_max: int | None = None
    if http_status is None and http_status_family is not None:
        # Typical families: 2xx / 4xx / 5xx
        http_status_min = int(http_status_family) * 100
        http_status_max = int(http_status_family) * 100 + 99
    logs = STATE.log_store.list_page(
        offset=offset,
        limit=limit,
        provider=provider,
        http_status=http_status,
        http_status_min=http_status_min,
        http_status_max=http_status_max,
    )
    total = STATE.log_store.count(
        provider=provider,
        http_status=http_status,
        http_status_min=http_status_min,
        http_status_max=http_status_max,
    )
    return {"logs": logs, "total": total, "offset": offset, "limit": limit}


@app.post("/api/admin/jobs/{job_id}/cancel")
def admin_cancel_job(
    job_id: str,
    current_user: UserRecord = Depends(require_admin),
) -> dict[str, Any]:
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if rec.status != "queued":
        raise HTTPException(status_code=409, detail="只能取消排队中的任务")
    provider_name = str(rec.provider) if rec.provider else "minimax"
    pq = STATE.provider_queues.get(provider_name)
    cancelled_from_queue = False
    if pq:
        cancelled_from_queue = pq.cancel(job_id)
    STATE.store.set_status(job_id, status="failed", error="管理员取消排队")
    if rec.user_id is not None:
        # Push realtime update to the owner.
        asyncio.create_task(
            STATE.event_hub.publish(int(rec.user_id), {"type": "job_updated", "job_id": job_id, "status": "failed"})
        )
    return {"ok": True, "cancelled_from_queue": cancelled_from_queue}


@app.delete("/api/admin/jobs/{job_id}")
def admin_delete_job(
    job_id: str,
    current_user: UserRecord = Depends(require_admin),
) -> dict[str, Any]:
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if rec.status == "running":
        raise HTTPException(status_code=409, detail="无法删除正在生成中的任务，请等待完成或失败后再删除")
    # Cancel from provider queue if still pending
    if rec.status == "queued":
        provider_name = str(rec.provider) if rec.provider else "minimax"
        pq = STATE.provider_queues.get(provider_name)
        if pq:
            pq.cancel(job_id)
    ok = STATE.store.delete(job_id)
    return {"ok": ok}


@app.post("/api/generate")
async def generate(req: GenerateRequest, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    provider_name = _resolve_provider(req.provider)
    if provider_name not in ("minimax", "acestep"):
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider_name}")

    provider_params = req.provider_params or {}
    # Never accept base64 audio blobs in provider_params; they would be persisted
    # into sqlite job params and quickly bloat the DB / leak user content.
    for k in ("src_audio_b64", "reference_audio_b64"):
        if provider_params.get(k):
            raise HTTPException(status_code=400, detail="请先上传音频文件（不要直接传 base64）")
    base_prompt = (req.prompt or "").strip()
    if not base_prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    params: dict[str, Any] = {
        "base_prompt": req.prompt,
        "duration_sec": req.duration_sec,
        "vocals": req.vocals,
        "seed": req.seed,
        "model_id": req.model_id,
        "output_format": _resolve_output_format(provider_params),
        "provider": provider_name,
        "provider_params": provider_params,
        "lyrics": req.lyrics,
    }

    prompt = _apply_provider_prompt_options(
        base_prompt=base_prompt,
        lyrics=req.lyrics,
        vocals=req.vocals,
        provider_params=provider_params,
    )
    try:
        quota = STATE.user_store.consume_quota(user_id=current_user.id, amount=1, daily_quota=current_user.daily_quota)
    except ValueError as e:
        msg = str(e)
        if msg == "daily quota exhausted":
            msg = "今日配额已用完"
        raise HTTPException(status_code=429, detail=msg) from e

    job_id = STATE.store.create_job(
        provider=provider_name,
        prompt=prompt,
        params=params,
        kind="generate",
        user_id=current_user.id,
    )

    await STATE.event_hub.publish(
        int(current_user.id),
        {"type": "job_created", "job_id": job_id, "status": "queued", "provider": provider_name},
    )

    # Submit to provider queue (job starts in "queued" status, worker picks it up)
    await STATE.provider_queues[provider_name].submit(job_id)
    return {"job_id": job_id, "quota": quota}


@app.post("/api/generate_many")
async def generate_many(req: GenerateManyRequest, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    provider_name = _resolve_provider(req.provider)
    if provider_name not in ("minimax", "acestep"):
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider_name}")

    provider_params = req.provider_params or {}
    for k in ("src_audio_b64", "reference_audio_b64"):
        if provider_params.get(k):
            raise HTTPException(status_code=400, detail="请先上传音频文件（不要直接传 base64）")
    base_prompt = (req.prompt or "").strip()
    if not base_prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    params: dict[str, Any] = {
        "base_prompt": req.prompt,
        "duration_sec": req.duration_sec,
        "vocals": req.vocals,
        "seed": req.seed,
        "model_id": req.model_id,
        "output_format": _resolve_output_format(provider_params),
        "provider": provider_name,
        "provider_params": provider_params,
        "lyrics": req.lyrics,
    }

    prompt = _apply_provider_prompt_options(
        base_prompt=base_prompt,
        lyrics=req.lyrics,
        vocals=req.vocals,
        provider_params=provider_params,
    )

    try:
        quota = STATE.user_store.consume_quota(user_id=current_user.id, amount=req.count, daily_quota=current_user.daily_quota)
    except ValueError as e:
        msg = str(e)
        if msg == "daily quota exhausted":
            msg = "今日配额已用完"
        raise HTTPException(status_code=429, detail=msg) from e

    job_ids: list[str] = []
    for _ in range(req.count):
        job_id = STATE.store.create_job(
            provider=provider_name,
            prompt=prompt,
            params=params,
            kind="variation",
            user_id=current_user.id,
        )
        job_ids.append(job_id)
        await STATE.event_hub.publish(
            int(current_user.id),
            {"type": "job_created", "job_id": job_id, "status": "queued", "provider": provider_name},
        )
        # Submit to provider queue (job starts in "queued" status, worker picks it up)
        await STATE.provider_queues[provider_name].submit(job_id)

    return {"job_ids": job_ids, "quota": quota}


@app.post("/api/extend")
async def extend(req: ExtendRequest, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    parent = STATE.store.get(req.job_id)
    if not parent:
        raise HTTPException(status_code=404, detail="job not found")
    if not (_is_admin(current_user) or parent.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="job is private")
    if parent.status != "succeeded":
        raise HTTPException(status_code=409, detail="job not ready")

    try:
        parent_params = json.loads(parent.params_json)
    except Exception:
        parent_params = {}

    duration_sec = int(parent_params.get("duration_sec") or 0)
    new_duration = duration_sec + int(req.extra_sec)
    if new_duration > 600:  # ACE-Step supports up to 600s
        raise HTTPException(status_code=400, detail="total duration exceeds 600 seconds")

    new_params = dict(parent_params)
    new_params["duration_sec"] = new_duration
    if req.provider:
        new_provider = _resolve_provider(req.provider)
        if new_provider not in ("minimax", "acestep"):
            raise HTTPException(status_code=400, detail=f"unknown provider: {new_provider}")
        new_params["provider"] = new_provider
    if req.provider_params:
        new_params["provider_params"] = req.provider_params
        new_params["output_format"] = _resolve_output_format(req.provider_params)

    try:
        quota = STATE.user_store.consume_quota(user_id=current_user.id, amount=1, daily_quota=current_user.daily_quota)
    except ValueError as e:
        msg = str(e)
        if msg == "daily quota exhausted":
            msg = "今日配额已用完"
        raise HTTPException(status_code=429, detail=msg) from e

    job_id = STATE.store.create_job(
        provider=str(new_params.get("provider") or parent.provider),
        prompt=parent.prompt,
        params=new_params,
        kind="extend",
        parent_job_id=parent.job_id,
        user_id=current_user.id,
    )

    # Submit to provider queue (job starts in "queued" status, worker picks it up)
    provider_name = str(new_params.get("provider") or parent.provider)
    await STATE.event_hub.publish(
        int(current_user.id),
        {"type": "job_created", "job_id": job_id, "status": "queued", "provider": provider_name},
    )
    await STATE.provider_queues[provider_name].submit(job_id)
    return {"job_id": job_id, "parent_job_id": parent.job_id, "quota": quota}


@app.get("/api/jobs/recent")
def get_recent_jobs(
    limit: int = Query(default=20, ge=1, le=50),
    current_user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    records = STATE.store.list_recent(limit=limit, user_id=current_user.id, include_all=False)
    return {"jobs": [_serialize_job(rec) for rec in records]}


@app.get("/api/jobs/history")
def get_jobs_history(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    current_user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    include_all = False  # Homepage only shows own jobs; admin job management is in the admin panel
    total = STATE.store.count_jobs(user_id=current_user.id, include_all=include_all)
    records = STATE.store.list_page(offset=offset, limit=limit, user_id=current_user.id, include_all=include_all)
    return {"jobs": [_serialize_job(rec) for rec in records], "total": total, "offset": offset, "limit": limit}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if not _can_access_job(rec, current_user):
        raise HTTPException(status_code=403, detail="job is private")
    return _serialize_job(rec)


@app.get("/api/jobs")
def get_jobs(ids: str = Query(default=""), current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    job_ids = [x for x in ids.split(",") if x][:20]
    out: list[dict[str, Any]] = []
    for job_id in job_ids:
        rec = STATE.store.get(job_id)
        if not rec:
            continue
        if not _can_access_job(rec, current_user):
            continue
        out.append(_serialize_job(rec))
    return {"jobs": out}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if not (_is_admin(current_user) or rec.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="job is private")
    if rec.status == "running":
        raise HTTPException(status_code=409, detail="无法删除正在生成中的任务，请等待完成或失败后再删除")
    # Cancel from provider queue if still pending
    if rec.status == "queued":
        provider_name = str(rec.provider) if rec.provider else "minimax"
        pq = STATE.provider_queues.get(provider_name)
        if pq:
            pq.cancel(job_id)
    ok = STATE.store.delete(job_id)
    return {"ok": ok}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    """Cancel a queued job. Only works for jobs still in 'queued' status."""
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if not (_is_admin(current_user) or rec.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="job is private")
    if rec.status != "queued":
        raise HTTPException(status_code=409, detail="只能取消排队中的任务")

    # Remove from provider queue's pending list
    provider_name = str(rec.provider) if rec.provider else "minimax"
    pq = STATE.provider_queues.get(provider_name)
    cancelled_from_queue = False
    if pq:
        cancelled_from_queue = pq.cancel(job_id)

    # Mark as failed in store
    STATE.store.set_status(job_id, status="failed", error="用户取消排队")
    if rec.user_id is not None:
        asyncio.create_task(
            STATE.event_hub.publish(int(rec.user_id), {"type": "job_updated", "job_id": job_id, "status": "failed"})
        )
    return {"ok": True, "cancelled_from_queue": cancelled_from_queue}


@app.delete("/api/jobs")
def delete_jobs(current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    if _is_admin(current_user):
        deleted = STATE.store.delete_all()
    else:
        deleted = STATE.store.delete_for_user(user_id=current_user.id)
    return {"ok": True, "deleted": deleted}


@app.post("/api/jobs/{job_id}/publish")
def publish_job(job_id: str, req: PublishRequest, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if rec.status != "succeeded":
        raise HTTPException(status_code=409, detail="job is not ready to publish")
    if not (_is_admin(current_user) or rec.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="job is private")
    permission = req.share_permission.strip()
    if permission not in ("listen_only", "downloadable"):
        raise HTTPException(status_code=400, detail="share_permission must be listen_only or downloadable")
    STATE.store.set_sharing(job_id, visibility="published", share_permission=permission)  # type: ignore[arg-type]
    updated = STATE.store.get(job_id)
    if not updated:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": _serialize_job(updated)}


@app.post("/api/jobs/{job_id}/unpublish")
def unpublish_job(job_id: str, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if not (_is_admin(current_user) or rec.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="job is private")
    STATE.store.set_sharing(job_id, visibility="private", share_permission="listen_only")
    updated = STATE.store.get(job_id)
    if not updated:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": _serialize_job(updated)}


@app.get("/api/community")
def list_community(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    records = STATE.store.list_published(offset=offset, limit=limit)
    # Use community-specific URLs so unauthenticated users can access audio.
    def _serialize_community(rec: Any) -> dict[str, Any]:
        d = _serialize_job(rec)
        if d.get("audio_url"):
            d["audio_url"] = f"/api/community/{rec.job_id}/audio"
        if d.get("download_url"):
            d["download_url"] = f"/api/community/{rec.job_id}/audio"
        return d
    return {"jobs": [_serialize_community(rec) for rec in records], "offset": offset, "limit": limit}


@app.get("/api/audio/{job_id}")
def get_audio(job_id: str, current_user: UserRecord | None = Depends(_optional_current_user)) -> FileResponse:
    rec = STATE.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if not _can_access_job(rec, current_user):
        raise HTTPException(status_code=403, detail="job is private")
    if rec.status != "succeeded" or not rec.output_path:
        raise HTTPException(status_code=404, detail="audio not ready")

    path = Path(rec.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio missing on disk")

    return FileResponse(str(path), media_type=_media_type_for_path(path), filename=path.name)


@app.get("/api/community/{job_id}/audio")
def get_community_audio(job_id: str) -> FileResponse:
    return get_audio(job_id, None)


@app.get("/api/audio/{job_id}.mp3")
def get_audio_mp3_compat(job_id: str, current_user: UserRecord | None = Depends(_optional_current_user)) -> FileResponse:
    # Backwards-compatible alias (older UI/clients).
    return get_audio(job_id, current_user)


if __name__ == "__main__":
    from cli import main
    main()

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi import Header, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app_state import AppState
from auth import create_token, extract_bearer_token, hash_password, verify_password, verify_token
from providers.registry import providers_payload
from providers.minimax import MiniMaxMusicClient
from providers.acestep import ACEStepClient
from admin_config import load_local_config, redacted_config, save_local_config
from user_store import UserRecord, UserRole


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


class PublishRequest(BaseModel):
    share_permission: str = Field(default="listen_only", max_length=32)


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
    p = (req_provider or STATE.settings.default_provider or "minimax").strip()
    return p or "minimax"


def _resolve_output_format(provider_params: dict[str, Any] | None) -> str:
    raw = (provider_params or {}).get("output_format")
    if raw and isinstance(raw, str) and raw.strip():
        return raw.strip()
    return STATE.settings.output_format


STATE = AppState.create()

app = FastAPI(title="you2music", version="0.1.0")

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _public_user(user: UserRecord) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "avatar_path": user.avatar_path,
        "daily_quota": user.daily_quota,
        "disabled": user.disabled,
        "created_at_ms": user.created_at_ms,
        "quota": STATE.user_store.quota_status(user_id=user.id, daily_quota=user.daily_quota),
    }


def _optional_current_user(authorization: str | None = Header(default=None)) -> UserRecord | None:
    if not authorization:
        return None
    token = extract_bearer_token(authorization)
    payload = verify_token(token=token, settings=STATE.settings)
    user = STATE.user_store.get_by_id(payload.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="user not found")
    if user.disabled:
        raise HTTPException(status_code=403, detail="user disabled")
    return user


def get_current_user(authorization: str | None = Header(default=None)) -> UserRecord:
    token = extract_bearer_token(authorization)
    payload = verify_token(token=token, settings=STATE.settings)
    user = STATE.user_store.get_by_id(payload.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="user not found")
    if user.disabled:
        raise HTTPException(status_code=403, detail="user disabled")
    return user


def require_admin(current_user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return current_user


def _is_admin(user: UserRecord) -> bool:
    return user.role == "admin"


def _can_access_job(rec: Any, user: UserRecord | None) -> bool:
    if rec.visibility == "published":
        return True
    if user is None:
        return False
    return _is_admin(user) or rec.user_id == user.id


def _serialize_job(rec: Any, *, include_download: bool = True) -> dict[str, Any]:
    audio_url = None
    download_url = None
    if rec.status == "succeeded" and rec.output_path:
        audio_url = f"/api/audio/{rec.job_id}"
        if include_download and rec.share_permission == "downloadable":
            download_url = audio_url
    return {
        "job_id": rec.job_id,
        "status": rec.status,
        "created_at_ms": rec.created_at_ms,
        "updated_at_ms": rec.updated_at_ms,
        "provider": rec.provider,
        "prompt": rec.prompt,
        "params": json.loads(rec.params_json),
        "audio_url": audio_url,
        "download_url": download_url,
        "error": rec.error,
        "song_id": rec.song_id,
        "user_id": rec.user_id,
        "visibility": rec.visibility,
        "share_permission": rec.share_permission,
    }


def _auth_error_detail(msg: str) -> str:
    mapping = {
        "username already exists": "用户名已存在",
        "invalid invite code": "邀请码无效",
        "invite code has already been used": "邀请码已被使用",
        "username is required": "请填写用户名",
        "password hash is required": "密码处理失败，请重试",
        "invite code is required": "请填写邀请码",
        "password must be at most 72 bytes for bcrypt": "密码过长，请控制在 72 字节以内",
    }
    return mapping.get(msg, msg)


def _install_windows_asyncio_connection_reset_suppression() -> None:
    """
    Suppress noisy Windows Proactor loop warnings on client disconnects.

    On Windows (ProactorEventLoop), a normal client disconnect during/after a response
    can surface as:
      - ConnectionResetError: [WinError 10054] ...
      - ConnectionAbortedError: [WinError 10053] ...
    via the event loop exception handler ("Exception in callback ..._call_connection_lost()").

    This is a local tool and these tracebacks are typically not actionable for users.
    We ignore only these specific network disconnect errors and let everything else through.
    """

    if os.name != "nt":
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop yet; called too early.
        return

    previous_handler = loop.get_exception_handler()

    def handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        msg = str(context.get("message") or "")

        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
            text = str(exc)
            if "WinError 10054" in text or "WinError 10053" in text or "_call_connection_lost" in msg:
                return

        if previous_handler is not None:
            previous_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def _spawn_job_task(coro: "asyncio.Future[Any] | asyncio.Task[Any] | Any") -> None:
    """
    Spawn a background job task and track it for shutdown cancellation.

    Uvicorn on Windows may appear to "not stop" on Ctrl+C if there are long-running
    background tasks. Tracking lets us cancel them promptly on shutdown.
    """
    task = asyncio.create_task(coro)

    tasks = getattr(app.state, "job_tasks", None)
    if tasks is None:
        tasks = set()
        setattr(app.state, "job_tasks", tasks)

    tasks.add(task)

    def _done(t: asyncio.Task[Any]) -> None:
        try:
            tasks.discard(t)
        except Exception:
            pass

    task.add_done_callback(_done)


@app.on_event("startup")
async def _startup_install_loop_handler() -> None:
    _install_windows_asyncio_connection_reset_suppression()
    if getattr(app.state, "job_tasks", None) is None:
        setattr(app.state, "job_tasks", set())


@app.on_event("shutdown")
async def _shutdown_cancel_jobs() -> None:
    tasks = getattr(app.state, "job_tasks", None)
    if not tasks:
        return

    # Cancel outstanding jobs quickly so Ctrl+C stops reliably in dev.
    snapshot = [t for t in list(tasks) if not t.done()]
    for t in snapshot:
        t.cancel()

    # Best effort: don't let cancellation errors block shutdown.
    # On Windows, cancellation of in-flight network IO can sometimes take longer than expected.
    # Keep shutdown bounded so dev iteration is reliable.
    timeout_s = float(os.getenv("AI_MUSIC_SHUTDOWN_CANCEL_TIMEOUT_S", "0.5"))
    try:
        await asyncio.wait_for(asyncio.gather(*snapshot, return_exceptions=True), timeout=timeout_s)
    except asyncio.TimeoutError:
        return


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
        raise HTTPException(status_code=403, detail="invalid current password")
    try:
        password_hash = hash_password(req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    STATE.user_store.update_password(current_user.id, password_hash=password_hash)
    return {"ok": True}


@app.get("/api/providers")
def get_providers(current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    return providers_payload(STATE.settings)


def _require_admin(token: str | None) -> None:
    raise HTTPException(status_code=410, detail="admin token authentication has been removed; use JWT admin role")


class AdminConfigRequest(BaseModel):
    config: dict[str, Any]


# ========================================
# Random Sample Generation (ACE-Step inspired)
# ========================================
RANDOM_PROMPTS = [
    "A dreamy electronic ambient track with soft synth pads and gentle arpeggios",
    "Upbeat pop song with catchy melody and energetic drums",
    "Melancholic piano ballad with emotional strings",
    "Funky dance track with groovy bass line and brass section",
    "Acoustic folk song with warm guitar strumming and heartfelt vocals",
    "Epic cinematic orchestral piece with dramatic crescendo",
    "Chill lo-fi hip hop beat with jazzy samples and vinyl crackle",
    "Energetic rock anthem with powerful electric guitars and driving rhythm",
    "Smooth R&B track with sultry vocals and lush harmonies",
    "Traditional Chinese-inspired piece with guzheng and erhu melodies",
    "Modern trap beat with heavy 808 bass and crisp hi-hats",
    "Reggae-inspired track with laid-back groove and offbeat guitar skanks",
    "Electronic dance music with buildups and drops",
    "Jazz standard with swing rhythm and improvisational solos",
    "New age meditation music with Tibetan singing bowls and nature sounds",
]

RANDOM_LYRICS_TEMPLATES = [
    """[Verse 1]
漫步在这城市的街头
霓虹灯映照着过往的梦
微风轻拂脸庞的感觉
让我想起了你的温柔

[Chorus]
时光如水静静流淌
记忆中的画面依然清晰
那些年我们一起追的梦
如今都变成了心底的歌""",
    """[Verse 1]
Standing on the edge of tomorrow
Looking back at yesterday
All the joy and all the sorrow
Led me to this moment today

[Chorus]
We're chasing dreams across the sky
No matter how far, we'll learn to fly
Together we'll make it through the night
Into the morning light""",
    """[Verse 1]
月光洒落在窗台
思绪随着夜风飘来
那些未曾说出口的话
在心中悄悄绽放

[Bridge]
时间是最温柔的答案
等待是最深情的告白

[Chorus]
让风带走所有遗憾
让梦点亮每个夜晚""",
    """[Verse 1]
踏遍千山万水
追寻心中的风景
一路上有风有雨
也有你温暖的笑容

[Chorus]
人生就像一场旅行
珍惜沿途的每一道风景
不管终点在哪里
重要的是与你同行""",
    """[Verse 1]
咖啡杯里倒映着午后阳光
书页翻动间时光悄然流淌
窗外的城市依旧繁忙
而我沉浸在这片刻的安详

[Chorus]
Simple moments, peaceful days
In this quiet space, my heart stays
Finding beauty in the ordinary
Living life extraordinary""",
]


@app.get("/api/random_sample")
def get_random_sample(current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    """Generate a random prompt and lyrics sample for quick inspiration."""
    prompt = random.choice(RANDOM_PROMPTS)
    lyrics = random.choice(RANDOM_LYRICS_TEMPLATES)
    bpm = random.choice([60, 70, 80, 90, 100, 110, 120, 128, 140])
    keys = ["C major", "G major", "D major", "A minor", "E minor", "F major"]
    key_scale = random.choice(keys)
    durations = [30, 45, 60, 90, 120, 180]
    duration = random.choice(durations)

    return {
        "prompt": prompt,
        "lyrics": lyrics,
        "bpm": bpm,
        "key_scale": key_scale,
        "duration": duration,
    }


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


@app.post("/api/generate")
async def generate(req: GenerateRequest, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    provider_name = _resolve_provider(req.provider)
    if provider_name not in ("minimax", "acestep"):
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider_name}")

    provider_params = req.provider_params or {}
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
        raise HTTPException(status_code=429, detail=str(e)) from e

    job_id = STATE.store.create_job(
        provider=provider_name,
        prompt=prompt,
        params=params,
        kind="generate",
        user_id=current_user.id,
    )

    _spawn_job_task(_run_job(job_id=job_id, prompt=prompt, params=params))
    return {"job_id": job_id, "quota": quota}


@app.post("/api/generate_many")
async def generate_many(req: GenerateManyRequest, current_user: UserRecord = Depends(get_current_user)) -> dict[str, Any]:
    provider_name = _resolve_provider(req.provider)
    if provider_name not in ("minimax", "acestep"):
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider_name}")

    provider_params = req.provider_params or {}
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
        raise HTTPException(status_code=429, detail=str(e)) from e

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
        _spawn_job_task(_run_job(job_id=job_id, prompt=prompt, params=params))

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
        raise HTTPException(status_code=429, detail=str(e)) from e

    job_id = STATE.store.create_job(
        provider=str(new_params.get("provider") or parent.provider),
        prompt=parent.prompt,
        params=new_params,
        kind="extend",
        parent_job_id=parent.job_id,
        user_id=current_user.id,
    )

    _spawn_job_task(_run_job(job_id=job_id, prompt=parent.prompt, params=new_params))
    return {"job_id": job_id, "parent_job_id": parent.job_id, "quota": quota}


@app.get("/api/jobs/recent")
def get_recent_jobs(
    limit: int = Query(default=20, ge=1, le=50),
    current_user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    records = STATE.store.list_recent(limit=limit, user_id=current_user.id, include_all=_is_admin(current_user))
    return {"jobs": [_serialize_job(rec) for rec in records]}


@app.get("/api/jobs/history")
def get_jobs_history(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    current_user: UserRecord = Depends(get_current_user),
) -> dict[str, Any]:
    include_all = _is_admin(current_user)
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
    ok = STATE.store.delete(job_id)
    return {"ok": ok}


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
    return {"jobs": [_serialize_job(rec) for rec in records], "offset": offset, "limit": limit}


def _media_type_for_path(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".mp3":
        return "audio/mpeg"
    if suf == ".wav":
        return "audio/wav"
    return "application/octet-stream"


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


async def _run_job(*, job_id: str, prompt: str, params: dict[str, Any]) -> None:
    try:
        STATE.store.set_status(job_id, status="running")
        STATE.audio_dir.mkdir(parents=True, exist_ok=True)

        provider_name = str(params.get("provider") or "minimax")
        duration_ms = int(params["duration_sec"]) * 1000
        vocals = bool(params["vocals"])
        provider_params = params.get("provider_params") or {}

        out_bytes: bytes
        out_ext = "mp3"
        song_id: str | None = None

        if provider_name == "minimax":
            # MiniMax official API (music-2.6)
            client = MiniMaxMusicClient(
                api_key=STATE.settings.minimax_api_key,
                base_url=STATE.settings.minimax_base_url,
                timeout_s=STATE.settings.request_timeout_s,
            )
            model = str(provider_params.get("model") or "music-2.6")
            lyrics_raw = params.get("lyrics") or provider_params.get("lyrics")
            lyrics_text = str(lyrics_raw).strip() if lyrics_raw is not None else ""
            sample_rate = int(provider_params.get("sample_rate") or 44100)
            bitrate = int(provider_params.get("bitrate") or 256000)
            audio_format = str(provider_params.get("format") or "mp3")

            # MiniMax requires lyrics unless:
            # - is_instrumental=true, or
            # - lyrics_optimizer=true with empty lyrics (auto-generate lyrics)
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

            result = await client.generate(
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
                out_bytes = await client.download_audio(result.audio_url)
            out_ext = audio_format
        elif provider_name == "acestep":
            # ACE-Step 1.5 via acemusic.ai (OpenAI-compatible API)
            client = ACEStepClient(
                api_key=STATE.settings.acestep_api_key,
                base_url=STATE.settings.acestep_base_url,
                timeout_s=STATE.settings.request_timeout_s,
            )
            model = str(provider_params.get("model") or "acemusic/acestep-v1.5-turbo")
            lyrics = params.get("lyrics") or provider_params.get("lyrics")
            audio_duration = provider_params.get("audio_duration")
            if audio_duration is None:
                audio_duration = float(params["duration_sec"])
            audio_format = str(provider_params.get("audio_format") or "mp3")

            result = await client.generate(
                prompt=prompt,
                lyrics=str(lyrics).strip() if lyrics else None,
                model=model,
                audio_duration=audio_duration,
                audio_format=audio_format,
            )

            out_bytes = result.audio_bytes
            out_ext = audio_format
        else:
            raise RuntimeError(f"unknown provider: {provider_name}")

        out_path = STATE.audio_dir / f"{job_id}.{out_ext}"
        out_path.write_bytes(out_bytes)
        STATE.store.set_status(job_id, status="succeeded", output_path=str(out_path), song_id=song_id)
    except asyncio.CancelledError:
        # Shutdown/dev stop: treat as a controlled failure to avoid leaving jobs "running".
        STATE.store.set_status(job_id, status="failed", error="cancelled")
        raise
    except Exception as e:
        STATE.store.set_status(job_id, status="failed", error=str(e))


class _SuppressUvicornShutdownTimeoutFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return "timeout graceful shutdown exceeded" not in (msg or "").lower()


if __name__ == "__main__":
    import uvicorn
    import uvicorn.config

    host = STATE.settings.host
    port = STATE.settings.port

    # On Windows + VSCode terminal, Ctrl+C can sometimes feel "stuck" when there are
    # long-running background tasks or half-open client connections. Keep graceful
    # shutdown short so dev iteration is reliable.
    # This is a maximum wait time. In normal cases the server exits much faster,
    # but on Windows the shutdown sequence can sometimes take a few seconds even
    # with no active requests. Use a slightly larger default to avoid noisy
    # "timeout graceful shutdown exceeded" logs.
    timeout_grace_s = float(os.getenv("AI_MUSIC_TIMEOUT_GRACEFUL_SHUTDOWN_S", "3.0"))
    timeout_keep_alive_s = int(os.getenv("AI_MUSIC_UVICORN_TIMEOUT_KEEP_ALIVE_S", "1"))

    log_config = uvicorn.config.LOGGING_CONFIG
    if os.getenv("AI_MUSIC_SUPPRESS_UVICORN_SHUTDOWN_TIMEOUT_LOG", "1").strip().lower() in ("1", "true", "yes", "on"):
        # Use uvicorn's built-in dictConfig hook so our filter survives uvicorn's logging setup.
        log_config = dict(log_config)
        log_config["filters"] = dict(log_config.get("filters") or {})
        log_config["filters"]["suppress_shutdown_timeout"] = {
            "()": "main._SuppressUvicornShutdownTimeoutFilter",
        }
        log_config["handlers"] = dict(log_config.get("handlers") or {})
        if "default" in log_config["handlers"] and isinstance(log_config["handlers"]["default"], dict):
            handler_cfg = dict(log_config["handlers"]["default"])
            handler_filters = list(handler_cfg.get("filters") or [])
            if "suppress_shutdown_timeout" not in handler_filters:
                handler_filters.append("suppress_shutdown_timeout")
            handler_cfg["filters"] = handler_filters
            log_config["handlers"]["default"] = handler_cfg

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        timeout_graceful_shutdown=timeout_grace_s,
        timeout_keep_alive=timeout_keep_alive_s,
        log_config=log_config,
    )

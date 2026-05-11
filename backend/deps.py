"""Auth dependencies and shared utility functions.

Extracted from main.py to avoid circular imports between main.py and route modules.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from fastapi import Depends, Header
from fastapi import HTTPException

from auth import extract_bearer_token, verify_token
from shared import build_prompt
from state import STATE
from user_store import UserRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _sanitize_filename(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "_", text.strip())[:80]
    return text or "audio"


def _resolve_provider(req_provider: str | None) -> str:
    p = (req_provider or STATE.settings.default_provider or "minimax").strip()
    return p or "minimax"


def _resolve_output_format(provider_params: dict[str, Any] | None) -> str:
    raw = (provider_params or {}).get("output_format")
    if raw and isinstance(raw, str) and raw.strip():
        return raw.strip()
    return STATE.settings.output_format


def _apply_provider_prompt_options(
    *,
    base_prompt: str,
    lyrics: str | None,
    vocals: bool,
    provider_params: dict[str, Any] | None,
) -> str:
    raw_prompt = bool((provider_params or {}).get("raw_prompt", False))
    if raw_prompt:
        parts = [base_prompt.strip()]
        if lyrics and lyrics.strip():
            parts.append(lyrics.strip())
        return "\n\n".join(parts).strip()
    return build_prompt(base_prompt=base_prompt, lyrics=lyrics, vocals=vocals)


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


def _media_type_for_path(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".mp3":
        return "audio/mpeg"
    if suf == ".wav":
        return "audio/wav"
    return "application/octet-stream"


# ---------------------------------------------------------------------------
# User serialization
# ---------------------------------------------------------------------------

def _public_user(user: UserRecord) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "avatar_path": user.avatar_path,
        "daily_quota": user.daily_quota,
        "disabled": user.disabled,
        "must_change_password": user.must_change_password,
        "created_at_ms": user.created_at_ms,
        "quota": STATE.user_store.quota_status(user_id=user.id, daily_quota=user.daily_quota),
    }


# ---------------------------------------------------------------------------
# Auth dependency callables (used by Depends())
# ---------------------------------------------------------------------------

def _optional_current_user(authorization: str | None = Header(default=None)) -> UserRecord | None:
    if not authorization:
        return None
    try:
        token = extract_bearer_token(authorization)
        payload = verify_token(token=token, settings=STATE.settings)
        user = STATE.user_store.get_by_id(payload.user_id)
        if not user:
            return None
        if user.disabled:
            return None
        return user
    except HTTPException:
        return None


def get_current_user(authorization: str | None = Header(default=None)) -> UserRecord:
    token = extract_bearer_token(authorization)
    payload = verify_token(token=token, settings=STATE.settings)
    user = STATE.user_store.get_by_id(payload.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已被删除")
    if user.disabled:
        raise HTTPException(status_code=403, detail="账户已被禁用")
    return user


def require_admin(current_user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return current_user


# ---------------------------------------------------------------------------
# Authorization helpers (non-dependency, callable directly)
# ---------------------------------------------------------------------------

def _is_admin(user: UserRecord) -> bool:
    return user.role == "admin"


def _can_access_job(rec: Any, user: UserRecord | None) -> bool:
    if rec.visibility == "published":
        return True
    if user is None:
        return False
    return _is_admin(user) or rec.user_id == user.id


# ---------------------------------------------------------------------------
# Job serialization
# ---------------------------------------------------------------------------

def _serialize_job(rec: Any, *, include_download: bool = True) -> dict[str, Any]:
    audio_url = None
    download_url = None
    if rec.status == "succeeded" and rec.output_path:
        audio_url = f"/api/audio/{rec.job_id}"
        if include_download and rec.share_permission == "downloadable":
            download_url = audio_url
    result = {
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
    if rec.status == "queued":
        provider_name = str(rec.provider) if rec.provider else "minimax"
        pq = STATE.provider_queues.get(provider_name)
        if pq:
            result["queue_position"] = pq.get_position(rec.job_id)
            result["queue_depth"] = pq.pending_count
    return result


# ---------------------------------------------------------------------------
# Windows asyncio noise suppression
# ---------------------------------------------------------------------------

def install_windows_asyncio_connection_reset_suppression() -> None:
    """Suppress noisy Windows Proactor loop warnings on client disconnects."""
    if os.name != "nt":
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
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

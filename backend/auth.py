from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from fastapi import HTTPException

from config import Settings
from user_store import UserRecord


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    username: str
    role: str


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > 72:
        raise ValueError("password must be at most 72 bytes for bcrypt")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(*, user: UserRecord, settings: Settings) -> str:
    secret = _require_jwt_secret(settings)
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(*, token: str, settings: Settings) -> TokenPayload:
    secret = _require_jwt_secret(settings)
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="invalid token") from e

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=401, detail="invalid token subject") from e

    username = str(payload.get("username") or "").strip()
    role = str(payload.get("role") or "").strip()
    if not username or role not in ("admin", "user"):
        raise HTTPException(status_code=401, detail="invalid token payload")
    return TokenPayload(user_id=user_id, username=username, role=role)


def extract_bearer_token(authorization: str | None) -> str:
    value = (authorization or "").strip()
    if not value:
        raise HTTPException(status_code=401, detail="authentication required")
    prefix = "Bearer "
    if not value.startswith(prefix):
        raise HTTPException(status_code=401, detail="invalid authorization header")
    token = value[len(prefix) :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="invalid authorization header")
    return token


def _require_jwt_secret(settings: Settings) -> str:
    secret = (settings.jwt_secret or "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="JWT secret not configured (set AI_MUSIC_JWT_SECRET)")
    return secret

from __future__ import annotations

import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal


UserRole = Literal["admin", "user"]


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    password_hash: str
    role: UserRole
    avatar_path: str | None
    daily_quota: int
    disabled: bool
    must_change_password: bool
    created_at_ms: int


@dataclass(frozen=True)
class InviteCodeRecord:
    code: str
    created_by: int | None
    used_by: int | None
    used_at_ms: int | None
    created_at_ms: int


class UserStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()

    def init(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL UNIQUE,
                  password_hash TEXT NOT NULL,
                  role TEXT NOT NULL DEFAULT 'user',
                  avatar_path TEXT,
                  daily_quota INTEGER NOT NULL DEFAULT 20,
                  disabled INTEGER NOT NULL DEFAULT 0,
                  created_at_ms INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS invite_codes (
                  code TEXT PRIMARY KEY,
                  created_by INTEGER,
                  used_by INTEGER,
                  used_at_ms INTEGER,
                  created_at_ms INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_quotas (
                  user_id INTEGER NOT NULL,
                  date TEXT NOT NULL,
                  used_count INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY (user_id, date)
                )
                """
            )
            self._migrate(conn)
            conn.commit()

    def ensure_admin(self, *, username: str, password_hash: str, daily_quota: int) -> UserRecord | None:
        username_clean = username.strip()
        if not username_clean or not password_hash:
            return None

        existing_admin_id: int | None = None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
                if row:
                    existing_admin_id = int(row[0])
                    conn.commit()
                else:
                    now = _now_ms()
                    cursor = conn.execute(
                        """
                        INSERT INTO users (username, password_hash, role, avatar_path, daily_quota, disabled, created_at_ms)
                        VALUES (?, ?, 'admin', NULL, ?, 0, ?)
                        """,
                        (username_clean, password_hash, int(daily_quota), now),
                    )
                    conn.commit()
                    existing_admin_id = int(cursor.lastrowid)

        return self.get_by_id(existing_admin_id)

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        invite_code: str,
        daily_quota: int,
    ) -> UserRecord:
        username_clean = username.strip()
        code_clean = invite_code.strip()
        if not username_clean:
            raise ValueError("username is required")
        if not password_hash:
            raise ValueError("password hash is required")
        if not code_clean:
            raise ValueError("invite code is required")

        with self._lock:
            with self._connect() as conn:
                invite = conn.execute(
                    "SELECT code, used_by FROM invite_codes WHERE code = ?",
                    (code_clean,),
                ).fetchone()
                if not invite:
                    raise ValueError("invalid invite code")
                if invite[1] is not None:
                    raise ValueError("invite code has already been used")

                now = _now_ms()
                try:
                    cursor = conn.execute(
                        """
                        INSERT INTO users (username, password_hash, role, avatar_path, daily_quota, disabled, created_at_ms)
                        VALUES (?, ?, 'user', NULL, ?, 0, ?)
                        """,
                        (username_clean, password_hash, int(daily_quota), now),
                    )
                except sqlite3.IntegrityError as e:
                    raise ValueError("username already exists") from e

                user_id = int(cursor.lastrowid)
                conn.execute(
                    "UPDATE invite_codes SET used_by = ?, used_at_ms = ? WHERE code = ?",
                    (user_id, now, code_clean),
                )
                conn.commit()

        user = self.get_by_id(user_id)
        if user is None:
            raise RuntimeError("created user not found")
        return user

    def get_by_id(self, user_id: int) -> UserRecord | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id, username, password_hash, role, avatar_path, daily_quota, disabled, must_change_password, created_at_ms
                    FROM users WHERE id = ?
                    """,
                    (int(user_id),),
                ).fetchone()
        return _row_to_user(row)

    def get_by_username(self, username: str) -> UserRecord | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id, username, password_hash, role, avatar_path, daily_quota, disabled, must_change_password, created_at_ms
                    FROM users WHERE username = ?
                    """,
                    (username.strip(),),
                ).fetchone()
        return _row_to_user(row)

    def list_users(self) -> list[UserRecord]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, username, password_hash, role, avatar_path, daily_quota, disabled, must_change_password, created_at_ms
                    FROM users ORDER BY created_at_ms DESC
                    """
                ).fetchall()
        return [u for u in (_row_to_user(row) for row in rows) if u is not None]

    def update_user(
        self,
        user_id: int,
        *,
        role: UserRole | None = None,
        daily_quota: int | None = None,
        disabled: bool | None = None,
        avatar_path: str | None = None,
    ) -> UserRecord | None:
        user = self.get_by_id(user_id)
        if user is None:
            return None

        next_role = role or user.role
        next_quota = int(daily_quota if daily_quota is not None else user.daily_quota)
        next_disabled = bool(disabled if disabled is not None else user.disabled)
        next_avatar = avatar_path if avatar_path is not None else user.avatar_path

        if next_role not in ("admin", "user"):
            raise ValueError("role must be admin or user")
        if next_quota < 0:
            raise ValueError("daily quota must be non-negative")

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE users
                    SET role = ?, daily_quota = ?, disabled = ?, avatar_path = ?
                    WHERE id = ?
                    """,
                    (next_role, next_quota, 1 if next_disabled else 0, next_avatar, int(user_id)),
                )
                conn.commit()
        return self.get_by_id(user_id)

    def update_password(self, user_id: int, *, password_hash: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                    (password_hash, int(user_id)),
                )
                conn.commit()
                return cursor.rowcount > 0

    def set_must_change_password(self, user_id: int, flag: bool) -> bool:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE users SET must_change_password = ? WHERE id = ?",
                    (1 if flag else 0, int(user_id)),
                )
                conn.commit()
                return cursor.rowcount > 0

    def delete_user(self, user_id: int) -> bool:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT role FROM users WHERE id = ?", (int(user_id),)).fetchone()
                if not row:
                    return False
                if str(row[0]) == "admin":
                    admins = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()
                    if int(admins[0] or 0) <= 1:
                        raise ValueError("cannot delete the last admin")
                cursor = conn.execute("DELETE FROM users WHERE id = ?", (int(user_id),))
                conn.commit()
                return cursor.rowcount > 0

    def create_invite_code(self, *, created_by: int | None) -> InviteCodeRecord:
        code = secrets.token_urlsafe(18)
        now = _now_ms()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO invite_codes (code, created_by, used_by, used_at_ms, created_at_ms) VALUES (?, ?, NULL, NULL, ?)",
                    (code, created_by, now),
                )
                conn.commit()
        return InviteCodeRecord(code=code, created_by=created_by, used_by=None, used_at_ms=None, created_at_ms=now)

    def list_invite_codes(self) -> list[InviteCodeRecord]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT code, created_by, used_by, used_at_ms, created_at_ms
                    FROM invite_codes ORDER BY created_at_ms DESC
                    """
                ).fetchall()
        return [_row_to_invite(row) for row in rows]

    def quota_status(self, *, user_id: int, daily_quota: int, date: str | None = None) -> dict[str, int | str]:
        date_key = date or today_key()
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT used_count FROM user_quotas WHERE user_id = ? AND date = ?",
                    (int(user_id), date_key),
                ).fetchone()
        used = int(row[0] or 0) if row else 0
        return {"date": date_key, "used": used, "limit": int(daily_quota), "remaining": max(0, int(daily_quota) - used)}

    def consume_quota(self, *, user_id: int, amount: int, daily_quota: int, date: str | None = None) -> dict[str, int | str]:
        date_key = date or today_key()
        amount_int = int(amount)
        if amount_int < 1:
            amount_int = 1

        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT used_count FROM user_quotas WHERE user_id = ? AND date = ?",
                    (int(user_id), date_key),
                ).fetchone()
                used = int(row[0] or 0) if row else 0
                limit = int(daily_quota)
                if used + amount_int > limit:
                    raise ValueError("daily quota exhausted")
                if row:
                    conn.execute(
                        "UPDATE user_quotas SET used_count = ? WHERE user_id = ? AND date = ?",
                        (used + amount_int, int(user_id), date_key),
                    )
                else:
                    conn.execute(
                        "INSERT INTO user_quotas (user_id, date, used_count) VALUES (?, ?, ?)",
                        (int(user_id), date_key, used + amount_int),
                    )
                conn.commit()
        return {"date": date_key, "used": used + amount_int, "limit": int(daily_quota), "remaining": max(0, int(daily_quota) - used - amount_int)}

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "disabled" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
        if "avatar_path" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN avatar_path TEXT")
        if "must_change_password" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")


def today_key() -> str:
    return datetime.now(UTC).date().isoformat()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _row_to_user(row: sqlite3.Row | tuple[object, ...] | None) -> UserRecord | None:
    if row is None:
        return None
    return UserRecord(
        id=int(row[0]),
        username=str(row[1]),
        password_hash=str(row[2]),
        role=str(row[3]),  # type: ignore[arg-type]
        avatar_path=str(row[4]) if row[4] is not None else None,
        daily_quota=int(row[5]),
        disabled=bool(row[6]),
        must_change_password=bool(row[7]),
        created_at_ms=int(row[8]),
    )


def _row_to_invite(row: sqlite3.Row | tuple[object, ...]) -> InviteCodeRecord:
    return InviteCodeRecord(
        code=str(row[0]),
        created_by=int(row[1]) if row[1] is not None else None,
        used_by=int(row[2]) if row[2] is not None else None,
        used_at_ms=int(row[3]) if row[3] is not None else None,
        created_at_ms=int(row[4]),
    )

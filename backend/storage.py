from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


JobStatus = Literal["queued", "running", "succeeded", "failed"]
JobVisibility = Literal["private", "published"]
SharePermission = Literal["listen_only", "downloadable"]


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    status: JobStatus
    created_at_ms: int
    updated_at_ms: int
    provider: str
    prompt: str
    params_json: str
    output_path: str | None
    error: str | None
    song_id: str | None = None  # For ElevenLabs Music API, used for stems separation
    user_id: int | None = None
    visibility: JobVisibility = "private"
    share_permission: SharePermission = "listen_only"


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()

    def init(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  job_id TEXT PRIMARY KEY,
                  parent_job_id TEXT,
                  kind TEXT NOT NULL DEFAULT 'generate',
                  status TEXT NOT NULL,
                  created_at_ms INTEGER NOT NULL,
                  updated_at_ms INTEGER NOT NULL,
                  provider TEXT NOT NULL,
                  prompt TEXT NOT NULL,
                  params_json TEXT NOT NULL,
                  output_path TEXT,
                  error TEXT,
                  song_id TEXT,
                  user_id INTEGER,
                  visibility TEXT NOT NULL DEFAULT 'private',
                  share_permission TEXT NOT NULL DEFAULT 'listen_only'
                )
                """
            )
            self._migrate(conn)
            conn.commit()

    def create_job(
        self,
        *,
        provider: str,
        prompt: str,
        params: dict[str, Any],
        kind: str = "generate",
        parent_job_id: str | None = None,
        user_id: int | None = None,
    ) -> str:
        job_id = uuid.uuid4().hex
        now = int(time.time() * 1000)
        params_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO jobs (job_id, parent_job_id, kind, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, user_id, visibility, share_permission)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'private', 'listen_only')
                    """,
                    (
                        job_id,
                        parent_job_id,
                        kind,
                        "queued",
                        now,
                        now,
                        provider,
                        prompt,
                        params_json,
                        None,
                        None,
                        user_id,
                    ),
                )
                conn.commit()
        return job_id

    def set_status(
        self,
        job_id: str,
        *,
        status: JobStatus,
        output_path: str | None = None,
        error: str | None = None,
        song_id: str | None = None,
    ) -> None:
        now = int(time.time() * 1000)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = ?, updated_at_ms = ?, output_path = COALESCE(?, output_path), error = ?, song_id = COALESCE(?, song_id)
                    WHERE job_id = ?
                    """,
                    (status, now, output_path, error, song_id, job_id),
                )
                conn.commit()

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT job_id, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, song_id, user_id, visibility, share_permission
                    FROM jobs WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
        if not row:
            return None
        return _row_to_job(row)

    def list_recent(self, *, limit: int = 20, user_id: int | None = None, include_all: bool = False) -> list[JobRecord]:
        limit_int = int(limit)
        if limit_int < 1:
            limit_int = 1
        if limit_int > 50:
            limit_int = 50

        with self._lock:
            with self._connect() as conn:
                if include_all:
                    rows = conn.execute(
                        """
                        SELECT job_id, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, song_id, user_id, visibility, share_permission
                        FROM jobs
                        ORDER BY created_at_ms DESC, job_id DESC
                        LIMIT ?
                        """,
                        (limit_int,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT job_id, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, song_id, user_id, visibility, share_permission
                        FROM jobs
                        WHERE user_id = ?
                        ORDER BY created_at_ms DESC, job_id DESC
                        LIMIT ?
                        """,
                        (user_id, limit_int),
                    ).fetchall()

        return [_row_to_job(row) for row in rows]

    def count_jobs(self, *, user_id: int | None = None, include_all: bool = False, status: str | None = None) -> int:
        conditions: list[str] = []
        params: list[object] = []
        if not include_all and user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(f"SELECT COUNT(*) FROM jobs {where}", params).fetchone()
        if not row:
            return 0
        return int(row[0] or 0)

    def list_page(self, *, offset: int = 0, limit: int = 20, user_id: int | None = None, include_all: bool = False, status: str | None = None) -> list[JobRecord]:
        off = int(offset)
        lim = int(limit)
        if off < 0:
            off = 0
        if lim < 1:
            lim = 1
        if lim > 200:
            lim = 200

        conditions: list[str] = []
        params: list[object] = []
        if not include_all and user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([lim, off])

        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT job_id, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, song_id, user_id, visibility, share_permission
                    FROM jobs
                    {where}
                    ORDER BY created_at_ms DESC, job_id DESC
                    LIMIT ? OFFSET ?
                    """,
                    params,
                ).fetchall()

        return [_row_to_job(row) for row in rows]

    def list_published(self, *, offset: int = 0, limit: int = 50) -> list[JobRecord]:
        off = max(0, int(offset))
        lim = min(100, max(1, int(limit)))
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT job_id, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, song_id, user_id, visibility, share_permission
                    FROM jobs
                    WHERE visibility = 'published' AND status = 'succeeded'
                    ORDER BY updated_at_ms DESC, job_id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (lim, off),
                ).fetchall()
        return [_row_to_job(row) for row in rows]

    def set_sharing(self, job_id: str, *, visibility: JobVisibility, share_permission: SharePermission) -> bool:
        if visibility not in ("private", "published"):
            raise ValueError("visibility must be private or published")
        if share_permission not in ("listen_only", "downloadable"):
            raise ValueError("share_permission must be listen_only or downloadable")
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    UPDATE jobs
                    SET visibility = ?, share_permission = ?, updated_at_ms = ?
                    WHERE job_id = ?
                    """,
                    (visibility, share_permission, int(time.time() * 1000), job_id),
                )
                conn.commit()
                return cursor.rowcount > 0

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "parent_job_id" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN parent_job_id TEXT")
        if "kind" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'generate'")
        if "song_id" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN song_id TEXT")
        if "user_id" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN user_id INTEGER")
        if "visibility" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private'")
        if "share_permission" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN share_permission TEXT NOT NULL DEFAULT 'listen_only'")

    def delete(self, job_id: str) -> bool:
        """Delete a single job record. Returns True if found and deleted."""
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
                conn.commit()
                return cursor.rowcount > 0

    def delete_all(self) -> int:
        """Delete all job records. Returns count of deleted rows."""
        with self._lock:
            with self._connect() as conn:
                count = int(
                    conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] or 0
                )
                conn.execute("DELETE FROM jobs")
                conn.commit()
        return count

    def delete_for_user(self, *, user_id: int) -> int:
        """Delete all job records for one user. Returns count of deleted rows."""
        with self._lock:
            with self._connect() as conn:
                count = int(
                    conn.execute("SELECT COUNT(*) FROM jobs WHERE user_id = ?", (int(user_id),)).fetchone()[0] or 0
                )
                conn.execute("DELETE FROM jobs WHERE user_id = ?", (int(user_id),))
                conn.commit()
        return count


def _row_to_job(row: sqlite3.Row | tuple[object, ...]) -> JobRecord:
    return JobRecord(
        job_id=str(row[0]),
        status=str(row[1]),  # type: ignore[arg-type]
        created_at_ms=int(row[2]),
        updated_at_ms=int(row[3]),
        provider=str(row[4]),
        prompt=str(row[5]),
        params_json=str(row[6]),
        output_path=str(row[7]) if row[7] is not None else None,
        error=str(row[8]) if row[8] is not None else None,
        song_id=str(row[9]) if len(row) > 9 and row[9] is not None else None,
        user_id=int(row[10]) if len(row) > 10 and row[10] is not None else None,
        visibility=str(row[11]) if len(row) > 11 and row[11] is not None else "private",  # type: ignore[arg-type]
        share_permission=str(row[12]) if len(row) > 12 and row[12] is not None else "listen_only",  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# ApiLogStore - HTTP API call log (for debugging / admin inspection)
# ---------------------------------------------------------------------------

_MAX_REQUEST_BODY_LEN = 2000
_MAX_RESPONSE_BODY_LEN = 4000


class ApiLogStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()

    def init(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_logs (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id           TEXT,
                    provider         TEXT NOT NULL,
                    method           TEXT,
                    endpoint         TEXT,
                    request_body     TEXT,
                    response_body    TEXT,
                    http_status      INTEGER,
                    elapsed_ms       INTEGER,
                    api_key_hint     TEXT,
                    error            TEXT,
                    created_at_ms    INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_logs_job_id "
                "ON api_logs(job_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_logs_created "
                "ON api_logs(created_at_ms DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_logs_provider_created "
                "ON api_logs(provider, created_at_ms DESC)"
            )
            conn.commit()

    def log(
        self,
        *,
        job_id: str | None,
        provider: str,
        method: str,
        endpoint: str,
        request_body: str | None,
        response_body: str | None,
        http_status: int | None,
        elapsed_ms: int,
        api_key_hint: str | None,
        error: str | None,
    ) -> None:
        now = int(time.time() * 1000)
        req = (request_body or "")[:_MAX_REQUEST_BODY_LEN]
        resp = (response_body or "")[:_MAX_RESPONSE_BODY_LEN]
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO api_logs
                    (job_id, provider, method, endpoint, request_body, response_body,
                     http_status, elapsed_ms, api_key_hint, error, created_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (job_id, provider, method, endpoint, req, resp,
                     http_status, elapsed_ms, api_key_hint, error, now),
                )
                conn.commit()

    def list_page(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        provider: str | None = None,
        job_id: str | None = None,
        http_status: int | None = None,
        http_status_min: int | None = None,
        http_status_max: int | None = None,
    ) -> list[dict[str, Any]]:
        off = max(0, int(offset))
        lim = min(200, max(1, int(limit)))

        conditions: list[str] = []
        params: list[object] = []
        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        if job_id:
            conditions.append("job_id = ?")
            params.append(job_id)
        if http_status is not None:
            conditions.append("http_status = ?")
            params.append(http_status)
        else:
            if http_status_min is not None:
                conditions.append("http_status >= ?")
                params.append(int(http_status_min))
            if http_status_max is not None:
                conditions.append("http_status <= ?")
                params.append(int(http_status_max))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        params.extend([lim, off])
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT id, job_id, provider, method, endpoint,
                           request_body, response_body, http_status,
                           elapsed_ms, api_key_hint, error, created_at_ms
                    FROM api_logs
                    {where}
                    ORDER BY created_at_ms DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    params,
                ).fetchall()
        return [_row_to_api_log(row) for row in rows]

    def count(
        self,
        *,
        provider: str | None = None,
        job_id: str | None = None,
        http_status: int | None = None,
        http_status_min: int | None = None,
        http_status_max: int | None = None,
    ) -> int:
        conditions: list[str] = []
        params: list[object] = []
        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        if job_id:
            conditions.append("job_id = ?")
            params.append(job_id)
        if http_status is not None:
            conditions.append("http_status = ?")
            params.append(http_status)
        else:
            if http_status_min is not None:
                conditions.append("http_status >= ?")
                params.append(int(http_status_min))
            if http_status_max is not None:
                conditions.append("http_status <= ?")
                params.append(int(http_status_max))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(f"SELECT COUNT(*) FROM api_logs {where}", params).fetchone()
        return int(row[0] or 0) if row else 0

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn


def _row_to_api_log(row: sqlite3.Row | tuple[object, ...]) -> dict[str, Any]:
    return {
        "id": int(row[0]),
        "job_id": str(row[1]) if row[1] is not None else None,
        "provider": str(row[2]),
        "method": str(row[3]) if row[3] is not None else None,
        "endpoint": str(row[4]) if row[4] is not None else None,
        "request_body": str(row[5]) if row[5] is not None else None,
        "response_body": str(row[6]) if row[6] is not None else None,
        "http_status": int(row[7]) if row[7] is not None else None,
        "elapsed_ms": int(row[8]) if row[8] is not None else None,
        "api_key_hint": str(row[9]) if row[9] is not None else None,
        "error": str(row[10]) if row[10] is not None else None,
        "created_at_ms": int(row[11]),
    }

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
                        ORDER BY created_at_ms DESC
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
                        ORDER BY created_at_ms DESC
                        LIMIT ?
                        """,
                        (user_id, limit_int),
                    ).fetchall()

        return [_row_to_job(row) for row in rows]

    def count_jobs(self, *, user_id: int | None = None, include_all: bool = False) -> int:
        with self._lock:
            with self._connect() as conn:
                if include_all:
                    row = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
                else:
                    row = conn.execute("SELECT COUNT(*) FROM jobs WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return 0
        return int(row[0] or 0)

    def list_page(self, *, offset: int = 0, limit: int = 20, user_id: int | None = None, include_all: bool = False) -> list[JobRecord]:
        off = int(offset)
        lim = int(limit)
        if off < 0:
            off = 0
        if lim < 1:
            lim = 1
        if lim > 200:
            lim = 200

        with self._lock:
            with self._connect() as conn:
                if include_all:
                    rows = conn.execute(
                        """
                        SELECT job_id, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, song_id, user_id, visibility, share_permission
                        FROM jobs
                        ORDER BY created_at_ms DESC
                        LIMIT ? OFFSET ?
                        """,
                        (lim, off),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT job_id, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, song_id, user_id, visibility, share_permission
                        FROM jobs
                        WHERE user_id = ?
                        ORDER BY created_at_ms DESC
                        LIMIT ? OFFSET ?
                        """,
                        (user_id, lim, off),
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
                    ORDER BY updated_at_ms DESC
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

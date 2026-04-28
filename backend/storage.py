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
                  error TEXT
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
    ) -> str:
        job_id = uuid.uuid4().hex
        now = int(time.time() * 1000)
        params_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO jobs (job_id, parent_job_id, kind, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    SELECT job_id, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, song_id
                    FROM jobs WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
        if not row:
            return None
        return JobRecord(
            job_id=row[0],
            status=row[1],
            created_at_ms=int(row[2]),
            updated_at_ms=int(row[3]),
            provider=row[4],
            prompt=row[5],
            params_json=row[6],
            output_path=row[7],
            error=row[8],
            song_id=row[9] if len(row) > 9 else None,
        )

    def list_recent(self, *, limit: int = 20) -> list[JobRecord]:
        limit_int = int(limit)
        if limit_int < 1:
            limit_int = 1
        if limit_int > 50:
            limit_int = 50

        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT job_id, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, song_id
                    FROM jobs
                    ORDER BY created_at_ms DESC
                    LIMIT ?
                    """,
                    (limit_int,),
                ).fetchall()

        out: list[JobRecord] = []
        for row in rows:
            out.append(
                JobRecord(
                    job_id=row[0],
                    status=row[1],
                    created_at_ms=int(row[2]),
                    updated_at_ms=int(row[3]),
                    provider=row[4],
                    prompt=row[5],
                    params_json=row[6],
                    output_path=row[7],
                    error=row[8],
                    song_id=row[9] if len(row) > 9 else None,
                )
            )
        return out

    def count_jobs(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
        if not row:
            return 0
        return int(row[0] or 0)

    def list_page(self, *, offset: int = 0, limit: int = 20) -> list[JobRecord]:
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
                rows = conn.execute(
                    """
                    SELECT job_id, status, created_at_ms, updated_at_ms, provider, prompt, params_json, output_path, error, song_id
                    FROM jobs
                    ORDER BY created_at_ms DESC
                    LIMIT ? OFFSET ?
                    """,
                    (lim, off),
                ).fetchall()

        out: list[JobRecord] = []
        for row in rows:
            out.append(
                JobRecord(
                    job_id=row[0],
                    status=row[1],
                    created_at_ms=int(row[2]),
                    updated_at_ms=int(row[3]),
                    provider=row[4],
                    prompt=row[5],
                    params_json=row[6],
                    output_path=row[7],
                    error=row[8],
                    song_id=row[9] if len(row) > 9 else None,
                )
            )
        return out

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

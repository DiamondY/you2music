"""Test fixtures for backend tests."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the backend directory is on sys.path so we can import storage, user_store, etc.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from storage import JobStore  # noqa: E402
from user_store import UserStore  # noqa: E402


@pytest.fixture
def tmp_db_path() -> Path:
    """Create a temporary file path for SQLite databases.

    Uses ignore_cleanup_errors=True to handle Windows WAL file locking
    (test.db-wal / test.db-shm may still be open when tempfile tries to
    remove the directory).
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        yield Path(td) / "test.db"


@pytest.fixture
def job_store(tmp_db_path: Path) -> JobStore:
    """Create a fresh JobStore with an initialized database."""
    store = JobStore(tmp_db_path)
    store.init()
    return store


@pytest.fixture
def user_store(tmp_db_path: Path) -> UserStore:
    """Create a fresh UserStore with an initialized database."""
    store = UserStore(tmp_db_path)
    store.init()
    return store

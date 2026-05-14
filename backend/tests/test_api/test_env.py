"""Test environment bootstrap for API/E2E tests.

This module must be imported before any backend modules that would trigger
`STATE = AppState.create()` at import time.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_ENV: dict[str, str] = {
    "AI_MUSIC_JWT_SECRET": "test-jwt-secret-for-testing-only",
    "AI_MUSIC_ADMIN_USERNAME": "admin",
    "AI_MUSIC_ADMIN_PASSWORD": "adminpw",
    "AI_MUSIC_DEFAULT_DAILY_QUOTA": "999",
    "ACESTEP_API_KEY": "test-key",
    "ACESTEP_BASE_URL": "http://localhost:0",
    "AI_MUSIC_TEST_MODE": "1",
}

# First layer: ensure defaults are set at import time.
os.environ.setdefault(
    "AI_MUSIC_DATA_DIR",
    str(Path(tempfile.gettempdir()) / "you2music_test_default"),
)
for _k, _v in TEST_ENV.items():
    os.environ.setdefault(_k, _v)


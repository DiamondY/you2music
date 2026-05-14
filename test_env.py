"""Repo-root shim so `import test_env` works from any pytest invocation.

The authoritative env constants live in `backend/tests/test_api/test_env.py`.
"""

from __future__ import annotations

from backend.tests.test_api.test_env import TEST_ENV as TEST_ENV  # noqa: F401
from backend.tests.test_api import test_env as _test_env  # noqa: F401


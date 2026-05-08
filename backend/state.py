"""Application state singleton.

Provides a single module-level STATE instance that can be imported by
main.py, route modules, workers, and dependency functions without
circular import issues.
"""

from __future__ import annotations

from app_state import AppState

STATE = AppState.create()

"""
Opt-in workaround for an environment-specific issue on Windows where Python 3.14's
tempfile-created directories can become non-writable (PermissionError) when created
with restrictive POSIX-like modes (e.g. 0o700).

This file is loaded automatically by Python at startup *if* it is on sys.path.
We use it as a scoped monkeypatch for tooling that relies on tempfile, such as:
- `python -m pip install ...`
- `python -m venv ...` (ensurepip)

Usage (PowerShell):
  $env:PYTHONPATH="C:\\...\\ai-music-tool\\tools\\py314_tempfile_fix"
  $env:PY_TEMP_BASE="C:\\...\\ai-music-tool\\.tmp_python"
  python -m pip install -r backend\\requirements.txt
"""

from __future__ import annotations

import os
import secrets
import tempfile
import shutil
import weakref
from pathlib import Path
from typing import Any, Optional


def _get_base_dir() -> str:
    base = os.getenv("PY_TEMP_BASE", "").strip()
    if base:
        Path(base).mkdir(parents=True, exist_ok=True)
        return base

    # Fall back to the normal TEMP/TMP. Even when the base is writable,
    # the problem in this environment is the *mode* passed to mkdir.
    return tempfile.gettempdir()


def _mkdtemp_fixed(
    suffix: Optional[str] = None,
    prefix: Optional[str] = None,
    dir: Optional[str] = None,
) -> str:
    # Keep signature compatible with tempfile.mkdtemp
    if suffix is None:
        suffix = ""
    if prefix is None:
        prefix = "tmp"
    base_dir = dir or _get_base_dir()

    for _ in range(100):
        name = f"{prefix}{secrets.token_hex(8)}{suffix}"
        path = os.path.join(base_dir, name)
        try:
            # Key workaround: avoid creating with mode 0o700 on Windows,
            # which can yield an ACL that denies writes in this environment.
            if os.name == "nt":
                os.mkdir(path, 0o777)
            else:
                os.mkdir(path, 0o700)
            return path
        except FileExistsError:
            continue
        except PermissionError:
            # As a last resort, try a less restrictive mode.
            try:
                os.mkdir(path, 0o777)
                return path
            except Exception:
                continue

    raise FileExistsError("Could not create a temporary directory (mkdtemp_fixed exhausted retries).")


def _cleanup(name: str, warn_message: str, ignore_errors: bool) -> None:
    try:
        shutil.rmtree(name, ignore_errors=ignore_errors)
    except Exception:
        if not ignore_errors:
            raise


class _TemporaryDirectoryFixed:
    """
    A minimal replacement for tempfile.TemporaryDirectory that uses our mkdtemp
    function and a weakref finalizer (no private stdlib APIs).
    """

    def __init__(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,
        ignore_cleanup_errors: bool = False,
    ) -> None:
        self.name = _mkdtemp_fixed(suffix=suffix, prefix=prefix, dir=dir)
        self._ignore_cleanup_errors = ignore_cleanup_errors
        self._finalizer = weakref.finalize(
            self,
            _cleanup,
            self.name,
            f"Implicitly cleaning up {self!r}",
            ignore_cleanup_errors,
        )

    def __repr__(self) -> str:
        return f"<_TemporaryDirectoryFixed {self.name!r}>"

    def cleanup(self) -> None:
        self._finalizer()

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc, value, tb) -> None:
        self.cleanup()


def _apply_patch() -> None:
    tempfile.mkdtemp = _mkdtemp_fixed  # type: ignore[assignment]
    tempfile.TemporaryDirectory = _TemporaryDirectoryFixed  # type: ignore[assignment]


_apply_patch()

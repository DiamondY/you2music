from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from config import Settings, load_settings
from storage import JobStore


@dataclass
class AppState:
    """
    Holds live runtime state that may need to be reloaded when config changes:
    - settings (keys, endpoints, proxy, defaults)
    - data_dir / audio_dir
    - sqlite job store

    Thread-safety: a simple lock is enough for this small-scope tool.
    """

    settings: Settings
    data_dir: Path
    audio_dir: Path
    db_path: Path
    store: JobStore
    _lock: threading.Lock

    @classmethod
    def create(cls) -> "AppState":
        settings = load_settings()
        data_dir = settings.data_dir
        audio_dir = data_dir / "audio"
        db_path = data_dir / "app.db"
        store = JobStore(db_path)
        store.init()
        st = cls(
            settings=settings,
            data_dir=data_dir,
            audio_dir=audio_dir,
            db_path=db_path,
            store=store,
            _lock=threading.Lock(),
        )
        st.apply_proxy_env()
        return st

    def apply_proxy_env(self) -> None:
        """
        Apply proxy settings to environment variables so httpx/urllib can use them.

        Empty string means "unset".
        """
        http_proxy = (self.settings.proxy_http or "").strip()
        https_proxy = (self.settings.proxy_https or "").strip()
        no_proxy = (self.settings.proxy_no or "").strip()

        def set_or_unset(key: str, value: str) -> None:
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

        set_or_unset("HTTP_PROXY", http_proxy)
        set_or_unset("http_proxy", http_proxy)
        set_or_unset("HTTPS_PROXY", https_proxy)
        set_or_unset("https_proxy", https_proxy)
        set_or_unset("NO_PROXY", no_proxy)
        set_or_unset("no_proxy", no_proxy)

    def reload(self) -> None:
        """
        Reload settings from config/env. If the data_dir changed, re-init store.
        Proxy env is always updated to match new settings.
        """
        with self._lock:
            new_settings = load_settings()
            new_data_dir = new_settings.data_dir
            new_audio_dir = new_data_dir / "audio"
            new_db_path = new_data_dir / "app.db"

            self.settings = new_settings
            self.apply_proxy_env()

            if new_db_path != self.db_path:
                self.data_dir = new_data_dir
                self.audio_dir = new_audio_dir
                self.db_path = new_db_path
                self.store = JobStore(self.db_path)
                self.store.init()


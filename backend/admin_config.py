from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def config_dir() -> Path:
    return repo_root() / "config"


def local_config_path() -> Path:
    return config_dir() / "providers.local.json"


def load_local_config() -> dict[str, Any]:
    path = local_config_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_local_config(cfg: dict[str, Any]) -> None:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = local_config_path()

    tmp = path.with_suffix(f".tmp.{int(time.time())}.{secrets.token_hex(4)}.json")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def redacted_config(cfg: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(cfg)) if cfg else {}
    secrets_obj = out.get("secrets")
    if isinstance(secrets_obj, dict):
        for k, v in list(secrets_obj.items()):
            if isinstance(v, str) and v:
                secrets_obj[k] = "********"
    if isinstance(out.get("admin_token"), str) and out.get("admin_token"):
        out["admin_token"] = "********"
    return out

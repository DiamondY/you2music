from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    acestep_api_key: str
    acestep_api_keys: list[str]
    acestep_base_url: str
    provider_ui_defaults: dict[str, dict[str, Any]]
    jwt_secret: str
    admin_username: str
    admin_password: str
    default_daily_quota: int
    proxy_http: str
    proxy_https: str
    proxy_no: str
    data_dir: Path
    output_format: str
    request_timeout_s: float
    host: str
    port: int
    concurrency_config: dict[str, Any]
    audio_upload_ttl_hours: int


ACESTEP_BASE_URL_DEFAULT = "https://api.acemusic.ai"


def _parse_keys(raw: Any) -> list[str]:
    """Parse API keys from a string or array of strings/objects.

    Backward-compatible: a single string becomes a one-element list.
    Arrays may contain plain strings or dicts with a ``key`` field.
    """
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        keys: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                keys.append(item.strip())
            elif isinstance(item, dict):
                k = str(item.get("key") or "").strip()
                if k:
                    keys.append(k)
        return keys
    return []


def _parse_key_single(raw: Any) -> str:
    """Extract the first key from a string or array for backward compat."""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, str):
            return first.strip()
        if isinstance(first, dict):
            return str(first.get("key") or "").strip()
    return ""


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"Failed to read config JSON: {path} ({e})")


def load_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[1]
    config_dir = repo_root / "config"
    # Prefer local (gitignored) config, fall back to none.
    cfg = _read_json_if_exists(config_dir / "providers.local.json") or _read_json_if_exists(config_dir / "providers.json") or {}

    acestep_api_key = os.getenv("ACESTEP_API_KEY", "").strip()
    acestep_base_url = os.getenv("ACESTEP_BASE_URL", ACESTEP_BASE_URL_DEFAULT).strip().rstrip("/")
    jwt_secret = os.getenv("AI_MUSIC_JWT_SECRET", "").strip()
    admin_username = os.getenv("AI_MUSIC_ADMIN_USERNAME", "").strip()
    admin_password = os.getenv("AI_MUSIC_ADMIN_PASSWORD", "").strip()
    daily_quota_env = os.getenv("AI_MUSIC_DEFAULT_DAILY_QUOTA")
    default_daily_quota = int((daily_quota_env or "20").strip() or "20")

    data_dir_raw = os.getenv(
        "AI_MUSIC_DATA_DIR",
        str(Path(__file__).resolve().parents[1] / "data"),
    )
    data_dir = Path(data_dir_raw).expanduser().resolve()

    output_format = os.getenv("AI_MUSIC_OUTPUT_FORMAT", "mp3_44100_192").strip()
    timeout_s = float(os.getenv("AI_MUSIC_REQUEST_TIMEOUT_S", "120"))
    audio_upload_ttl_hours = int(os.getenv("AI_MUSIC_AUDIO_UPLOAD_TTL_HOURS", "24").strip() or "24")

    # Apply JSON config values as defaults (env vars override)
    acestep_api_keys_raw: Any = None
    if isinstance(cfg, dict):
        secrets = cfg.get("secrets") if isinstance(cfg.get("secrets"), dict) else {}
        endpoints = cfg.get("endpoints") if isinstance(cfg.get("endpoints"), dict) else {}
        proxy = cfg.get("proxy") if isinstance(cfg.get("proxy"), dict) else {}
        auth_cfg = cfg.get("auth") if isinstance(cfg.get("auth"), dict) else {}
        admin_cfg = cfg.get("admin") if isinstance(cfg.get("admin"), dict) else {}

        if not acestep_api_key:
            raw = secrets.get("acestep_api_key")
            acestep_api_keys_raw = raw
            acestep_api_key = _parse_key_single(raw)
        else:
            acestep_api_keys_raw = acestep_api_key
        if acestep_base_url == ACESTEP_BASE_URL_DEFAULT:
            acestep_base_url = str(endpoints.get("acestep_base_url") or acestep_base_url).strip().rstrip("/")

        if not jwt_secret:
            jwt_secret = str(auth_cfg.get("jwt_secret") or cfg.get("jwt_secret") or "").strip()
        if not admin_username:
            admin_username = str(
                admin_cfg.get("username") or auth_cfg.get("admin_username") or cfg.get("admin_username") or ""
            ).strip()
        if not admin_password:
            admin_password = str(
                admin_cfg.get("password") or auth_cfg.get("admin_password") or cfg.get("admin_password") or ""
            ).strip()
        if daily_quota_env is None:
            quota_raw = admin_cfg.get("default_daily_quota", auth_cfg.get("default_daily_quota", cfg.get("default_daily_quota")))
            if isinstance(quota_raw, int):
                default_daily_quota = quota_raw
            elif isinstance(quota_raw, str) and quota_raw.strip():
                default_daily_quota = int(quota_raw.strip())
        # Proxy values (env overrides file)
        if not os.getenv("HTTP_PROXY") and not os.getenv("http_proxy"):
            p = proxy.get("http")
            if isinstance(p, str) and p.strip():
                os.environ["HTTP_PROXY"] = p.strip()
        if not os.getenv("HTTPS_PROXY") and not os.getenv("https_proxy"):
            p = proxy.get("https")
            if isinstance(p, str) and p.strip():
                os.environ["HTTPS_PROXY"] = p.strip()
        if not os.getenv("NO_PROXY") and not os.getenv("no_proxy"):
            p = proxy.get("no_proxy")
            if isinstance(p, str) and p.strip():
                os.environ["NO_PROXY"] = p.strip()

    provider_ui_defaults: dict[str, dict[str, Any]] = {}
    if isinstance(cfg, dict):
        ud = cfg.get("ui_defaults")
        if isinstance(ud, dict):
            for k, v in ud.items():
                if isinstance(k, str) and isinstance(v, dict):
                    provider_ui_defaults[k] = v

    proxy_http = (os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "").strip()
    proxy_https = (os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "").strip()
    proxy_no = (os.getenv("NO_PROXY") or os.getenv("no_proxy") or "").strip()

    # ACE-Step base_url should point to the API origin, not the marketing website.
    # The API is OpenAI-compatible and lives under https://api.acemusic.ai/v1/...
    try:
        acestep_split = urlsplit(acestep_base_url)
        acestep_host = (acestep_split.netloc or "").lower()
        acestep_path = acestep_split.path or ""
    except Exception:
        acestep_host = ""
        acestep_path = ""

    if acestep_host in ("acemusic.ai", "www.acemusic.ai"):
        if (acestep_path or "").strip("/"):
            raise RuntimeError(
                f"Invalid ACESTEP_BASE_URL={acestep_base_url!r}: expected the API origin only. "
                "Use 'https://api.acemusic.ai'."
            )
        acestep_base_url = "https://api.acemusic.ai"
        acestep_path = ""

    acestep_path_parts = [p for p in (acestep_path or "").split("/") if p]
    if any(p.lower() == "v1" for p in acestep_path_parts):
        raise RuntimeError(
            f"Invalid ACESTEP_BASE_URL={acestep_base_url!r}: base_url must not include '/v1'. "
            "Use 'https://api.acemusic.ai'."
        )

    # Host / Port: env overrides config file, config file overrides defaults.
    cfg_host = ""
    cfg_port: int | None = None
    if isinstance(cfg, dict):
        server = cfg.get("server") if isinstance(cfg.get("server"), dict) else {}
        if isinstance(server.get("host"), str) and server["host"].strip():
            cfg_host = server["host"].strip()
        if isinstance(server.get("port"), int) and 1 <= server["port"] <= 65535:
            cfg_port = server["port"]

    host = os.getenv("AI_MUSIC_HOST", cfg_host or "127.0.0.1").strip()
    raw_port = os.getenv("AI_MUSIC_PORT", str(cfg_port or 8000)).strip()
    port = int(raw_port)

    # Concurrency config (merged with defaults)
    from concurrency import _merge_concurrency
    concurrency_raw = cfg.get("concurrency") if isinstance(cfg, dict) else None
    concurrency_config = _merge_concurrency(concurrency_raw if isinstance(concurrency_raw, dict) else None)

    # Resolve multi-key lists from the raw config values.
    acestep_api_keys = _parse_keys(acestep_api_keys_raw)
    # Ensure the single-key fallback has something if the list is populated but
    # the single didn't get parsed (e.g. env var was empty, config had an array).
    if not acestep_api_key and acestep_api_keys:
        acestep_api_key = acestep_api_keys[0]

    return Settings(
        acestep_api_key=acestep_api_key,
        acestep_api_keys=acestep_api_keys,
        acestep_base_url=acestep_base_url,
        provider_ui_defaults=provider_ui_defaults,
        jwt_secret=jwt_secret,
        admin_username=admin_username,
        admin_password=admin_password,
        default_daily_quota=default_daily_quota,
        proxy_http=proxy_http,
        proxy_https=proxy_https,
        proxy_no=proxy_no,
        data_dir=data_dir,
        output_format=output_format,
        request_timeout_s=timeout_s,
        host=host,
        port=port,
        concurrency_config=concurrency_config,
        audio_upload_ttl_hours=audio_upload_ttl_hours,
    )

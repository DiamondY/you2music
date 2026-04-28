from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    default_provider: str
    minimax_api_key: str
    minimax_base_url: str
    acestep_api_key: str
    acestep_base_url: str
    enabled_providers: list[str] | None
    provider_ui_defaults: dict[str, dict[str, Any]]
    admin_token: str
    proxy_http: str
    proxy_https: str
    proxy_no: str
    data_dir: Path
    output_format: str
    request_timeout_s: float


MINIMAX_BASE_URL_DEFAULT = "https://api.minimaxi.com"
ACESTEP_BASE_URL_DEFAULT = "https://api.acemusic.ai"


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

    minimax_api_key = os.getenv("MINIMAX_API_KEY", "").strip()
    minimax_base_url = os.getenv("MINIMAX_BASE_URL", MINIMAX_BASE_URL_DEFAULT).strip().rstrip("/")
    acestep_api_key = os.getenv("ACESTEP_API_KEY", "").strip()
    acestep_base_url = os.getenv("ACESTEP_BASE_URL", ACESTEP_BASE_URL_DEFAULT).strip().rstrip("/")
    admin_token = os.getenv("AI_MUSIC_ADMIN_TOKEN", "").strip()

    data_dir_raw = os.getenv(
        "AI_MUSIC_DATA_DIR",
        str(Path(__file__).resolve().parents[1] / "data"),
    )
    data_dir = Path(data_dir_raw).expanduser().resolve()

    output_format = os.getenv("AI_MUSIC_OUTPUT_FORMAT", "mp3_44100_192").strip()
    default_provider = os.getenv("AI_MUSIC_PROVIDER_DEFAULT", "minimax").strip() or "minimax"
    timeout_s = float(os.getenv("AI_MUSIC_REQUEST_TIMEOUT_S", "120"))

    # Apply JSON config values as defaults (env vars override)
    if isinstance(cfg, dict):
        secrets = cfg.get("secrets") if isinstance(cfg.get("secrets"), dict) else {}
        endpoints = cfg.get("endpoints") if isinstance(cfg.get("endpoints"), dict) else {}
        proxy = cfg.get("proxy") if isinstance(cfg.get("proxy"), dict) else {}

        if not minimax_api_key:
            minimax_api_key = str(secrets.get("minimax_api_key") or "").strip()
        if minimax_base_url == MINIMAX_BASE_URL_DEFAULT:
            minimax_base_url = str(endpoints.get("minimax_base_url") or minimax_base_url).strip().rstrip("/")

        if not acestep_api_key:
            acestep_api_key = str(secrets.get("acestep_api_key") or "").strip()
        if acestep_base_url == ACESTEP_BASE_URL_DEFAULT:
            acestep_base_url = str(endpoints.get("acestep_base_url") or acestep_base_url).strip().rstrip("/")

        dp = cfg.get("default_provider")
        if isinstance(dp, str) and dp.strip():
            default_provider = dp.strip()
        if not admin_token:
            at = cfg.get("admin_token")
            if isinstance(at, str) and at.strip():
                admin_token = at.strip()

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

    enabled_providers: list[str] | None = None
    provider_ui_defaults: dict[str, dict[str, Any]] = {}
    if isinstance(cfg, dict):
        ep = cfg.get("enabled_providers")
        if isinstance(ep, list) and all(isinstance(x, str) for x in ep):
            enabled_providers = [x.strip() for x in ep if x.strip()]
        ud = cfg.get("ui_defaults")
        if isinstance(ud, dict):
            for k, v in ud.items():
                if isinstance(k, str) and isinstance(v, dict):
                    provider_ui_defaults[k] = v

    proxy_http = (os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "").strip()
    proxy_https = (os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "").strip()
    proxy_no = (os.getenv("NO_PROXY") or os.getenv("no_proxy") or "").strip()

    # MiniMax base_url should be a domain root; the client will append `/v1/music_generation`.
    try:
        minimax_path = urlsplit(minimax_base_url).path or ""
    except Exception:
        minimax_path = ""
    minimax_path_parts = [p for p in minimax_path.split("/") if p]
    if any(p.lower() == "v1" for p in minimax_path_parts):
        raise RuntimeError(
            f"Invalid MINIMAX_BASE_URL={minimax_base_url!r}: base_url must not include '/v1'. "
            "Use 'https://api.minimaxi.com' (CN) or 'https://api.minimax.io' (INTL)."
        )

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

    return Settings(
        default_provider=default_provider,
        minimax_api_key=minimax_api_key,
        minimax_base_url=minimax_base_url,
        acestep_api_key=acestep_api_key,
        acestep_base_url=acestep_base_url,
        enabled_providers=enabled_providers,
        provider_ui_defaults=provider_ui_defaults,
        admin_token=admin_token,
        proxy_http=proxy_http,
        proxy_https=proxy_https,
        proxy_no=proxy_no,
        data_dir=data_dir,
        output_format=output_format,
        request_timeout_s=timeout_s,
    )

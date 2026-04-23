from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    elevenlabs_api_key: str
    elevenlabs_base_url: str
    default_provider: str
    fal_key: str
    fal_queue_base_url: str
    fal_platform_base_url: str
    replicate_api_token: str
    replicate_base_url: str
    stability_api_key: str
    stability_base_url: str
    suno_api_key: str
    suno_base_url: str
    enabled_providers: list[str] | None
    provider_ui_defaults: dict[str, dict[str, Any]]
    admin_token: str
    proxy_http: str
    proxy_https: str
    proxy_no: str
    data_dir: Path
    output_format: str
    request_timeout_s: float


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

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    base_url = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").strip().rstrip("/")
    fal_key = os.getenv("FAL_KEY", "").strip()
    fal_queue_base_url = os.getenv("FAL_QUEUE_BASE_URL", "https://queue.fal.run").strip().rstrip("/")
    fal_platform_base_url = os.getenv("FAL_PLATFORM_BASE_URL", "https://api.fal.ai").strip().rstrip("/")
    replicate_api_token = os.getenv("REPLICATE_API_TOKEN", "").strip()
    replicate_base_url = os.getenv("REPLICATE_BASE_URL", "https://api.replicate.com").strip().rstrip("/")
    stability_api_key = os.getenv("STABILITY_API_KEY", "").strip()
    stability_base_url = os.getenv("STABILITY_BASE_URL", "https://api.stability.ai").strip().rstrip("/")
    suno_api_key = os.getenv("SUNO_API_KEY", "").strip()
    suno_base_url = os.getenv("SUNO_BASE_URL", "https://api.musicapi.ai").strip().rstrip("/")
    admin_token = os.getenv("AI_MUSIC_ADMIN_TOKEN", "").strip()

    data_dir_raw = os.getenv(
        "AI_MUSIC_DATA_DIR",
        str(Path(__file__).resolve().parents[1] / "data"),
    )
    data_dir = Path(data_dir_raw).expanduser().resolve()

    # ElevenLabs Music API expects format strings like "mp3_44100_192".
    # Keep a sane default so the out-of-box ElevenLabs flow works.
    output_format = os.getenv("AI_MUSIC_OUTPUT_FORMAT", "mp3_44100_192").strip()
    default_provider = os.getenv("AI_MUSIC_PROVIDER_DEFAULT", "elevenlabs").strip() or "elevenlabs"
    timeout_s = float(os.getenv("AI_MUSIC_REQUEST_TIMEOUT_S", "120"))

    # Apply JSON config values as defaults (env vars override)
    if isinstance(cfg, dict):
        secrets = cfg.get("secrets") if isinstance(cfg.get("secrets"), dict) else {}
        endpoints = cfg.get("endpoints") if isinstance(cfg.get("endpoints"), dict) else {}
        proxy = cfg.get("proxy") if isinstance(cfg.get("proxy"), dict) else {}
        if not api_key:
            api_key = str(secrets.get("elevenlabs_api_key") or "").strip()
        if base_url == "https://api.elevenlabs.io":
            base_url = str(endpoints.get("elevenlabs_base_url") or base_url).strip().rstrip("/")

        if not fal_key:
            fal_key = str(secrets.get("fal_key") or "").strip()
        if fal_queue_base_url == "https://queue.fal.run":
            fal_queue_base_url = str(endpoints.get("fal_queue_base_url") or fal_queue_base_url).strip().rstrip("/")
        if fal_platform_base_url == "https://api.fal.ai":
            fal_platform_base_url = str(endpoints.get("fal_platform_base_url") or fal_platform_base_url).strip().rstrip("/")

        if not replicate_api_token:
            replicate_api_token = str(secrets.get("replicate_api_token") or "").strip()
        if replicate_base_url == "https://api.replicate.com":
            replicate_base_url = str(endpoints.get("replicate_base_url") or replicate_base_url).strip().rstrip("/")

        if not stability_api_key:
            stability_api_key = str(secrets.get("stability_api_key") or "").strip()
        if stability_base_url == "https://api.stability.ai":
            stability_base_url = str(endpoints.get("stability_base_url") or stability_base_url).strip().rstrip("/")

        if not suno_api_key:
            suno_api_key = str(secrets.get("suno_api_key") or "").strip()
        if suno_base_url == "https://api.musicapi.ai":
            suno_base_url = str(endpoints.get("suno_base_url") or suno_base_url).strip().rstrip("/")

        if default_provider == "elevenlabs":
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

    return Settings(
        elevenlabs_api_key=api_key,
        elevenlabs_base_url=base_url,
        default_provider=default_provider,
        fal_key=fal_key,
        fal_queue_base_url=fal_queue_base_url,
        fal_platform_base_url=fal_platform_base_url,
        replicate_api_token=replicate_api_token,
        replicate_base_url=replicate_base_url,
        stability_api_key=stability_api_key,
        stability_base_url=stability_base_url,
        suno_api_key=suno_api_key,
        suno_base_url=suno_base_url,
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

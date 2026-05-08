"""CLI entry point for the you2music server.

Extracted from main.py. Starts uvicorn with appropriate Windows-friendly defaults.
"""

from __future__ import annotations

import logging
import os

from state import STATE


class _SuppressUvicornShutdownTimeoutFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return "timeout graceful shutdown exceeded" not in (msg or "").lower()


def main() -> None:
    import uvicorn
    import uvicorn.config

    host = STATE.settings.host
    port = STATE.settings.port

    # On Windows + VSCode terminal, Ctrl+C can sometimes feel "stuck" when there are
    # long-running background tasks or half-open client connections. Keep graceful
    # shutdown short so dev iteration is reliable.
    timeout_grace_s = float(os.getenv("AI_MUSIC_TIMEOUT_GRACEFUL_SHUTDOWN_S", "3.0"))
    timeout_keep_alive_s = int(os.getenv("AI_MUSIC_UVICORN_TIMEOUT_KEEP_ALIVE_S", "1"))

    log_config = uvicorn.config.LOGGING_CONFIG
    if os.getenv("AI_MUSIC_SUPPRESS_UVICORN_SHUTDOWN_TIMEOUT_LOG", "1").strip().lower() in ("1", "true", "yes", "on"):
        log_config = dict(log_config)
        log_config["filters"] = dict(log_config.get("filters") or {})
        log_config["filters"]["suppress_shutdown_timeout"] = {
            "()": "cli._SuppressUvicornShutdownTimeoutFilter",
        }
        log_config["handlers"] = dict(log_config.get("handlers") or {})
        if "default" in log_config["handlers"] and isinstance(log_config["handlers"]["default"], dict):
            handler_cfg = dict(log_config["handlers"]["default"])
            handler_filters = list(handler_cfg.get("filters") or [])
            if "suppress_shutdown_timeout" not in handler_filters:
                handler_filters.append("suppress_shutdown_timeout")
            handler_cfg["filters"] = handler_filters
            log_config["handlers"]["default"] = handler_cfg

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        timeout_graceful_shutdown=timeout_grace_s,
        timeout_keep_alive=timeout_keep_alive_s,
        log_config=log_config,
    )


if __name__ == "__main__":
    main()

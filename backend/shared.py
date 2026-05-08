"""Shared data and utility functions used by both main.py and stdlib_server.py."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


# ========================================
# Random Sample Data (shared)
# ========================================


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _pick(seq: list[Any]) -> Any:
    if not seq:
        return ""
    return random.choice(seq)


def _format_template(tpl: str, mapping: dict[str, Any]) -> str:
    out = str(tpl)
    for k, v in mapping.items():
        out = out.replace("{" + str(k) + "}", str(v))
    return out


def generate_random_prompt() -> str:
    """Generate a richer prompt by combining smaller building blocks.

    Source content lives in `backend/random_content/prompt_parts.v1.json`.
    """
    pack = _load_json(_repo_root() / "backend" / "random_content" / "prompt_parts.v1.json") or {}
    templates = pack.get("templates") if isinstance(pack.get("templates"), list) else []

    mapping = {
        "genre": _pick(pack.get("genres", [])),
        "subgenre": _pick(pack.get("subgenres", [])),
        "mood": _pick(pack.get("moods", [])),
        "vibe": _pick(pack.get("vibes", [])),
        "era": _pick(pack.get("eras", [])),
        "tempo": _pick(pack.get("tempos", [])),
        "time_signature": _pick(pack.get("time_signatures", [])),
        "key_scale": _pick(pack.get("key_scales", [])),
        "vocals_hint": _pick(pack.get("vocals_hints", [])),
        "arrangement": _pick(pack.get("arrangements", [])),
        "structure": _pick(pack.get("structures", [])),
        "lead_instruments": _pick(pack.get("lead_instruments", [])),
        "support_instruments": _pick(pack.get("support_instruments", [])),
        "sound_design": _pick(pack.get("sound_design", [])),
        "mixing": _pick(pack.get("mixing", [])),
        "focus": _pick(pack.get("focus", [])),
    }

    tpl = _pick(templates) if templates else "{genre}，{mood}，{vibe}。{vocals_hint}"
    text = _format_template(str(tpl), mapping)
    return " ".join(text.split()).strip()


def generate_random_lyrics() -> str:
    """Generate lyrics from templates and placeholder vocabularies.

    Source content lives in `backend/random_content/lyrics_templates.v1.json`.
    """
    pack = _load_json(_repo_root() / "backend" / "random_content" / "lyrics_templates.v1.json") or {}
    placeholders = pack.get("placeholders") if isinstance(pack.get("placeholders"), dict) else {}
    templates = pack.get("templates") if isinstance(pack.get("templates"), list) else []
    if not templates:
        return ""

    tpl_obj = _pick(templates)
    if not isinstance(tpl_obj, dict):
        return ""
    text = str(tpl_obj.get("text") or "").strip()
    lang = str(tpl_obj.get("lang") or "zh").strip().lower()

    mapping: dict[str, Any] = {}
    if lang == "en":
        mapping["theme"] = _pick(placeholders.get("themes_en", []))
        mapping["scene"] = _pick(placeholders.get("scenes_en", []))
        mapping["emotion"] = _pick(placeholders.get("emotions_en", []))
        mapping["hook"] = _pick(placeholders.get("hooks_en", []))
    else:
        mapping["theme"] = _pick(placeholders.get("themes_zh", []))
        mapping["scene"] = _pick(placeholders.get("scenes_zh", []))
        mapping["emotion"] = _pick(placeholders.get("emotions_zh", []))
        mapping["hook"] = _pick(placeholders.get("hooks_zh", []))

    return _format_template(text, mapping).strip()


def generate_random_duration_sec() -> int:
    # Keep durations short-ish for iteration speed; UI clamps anyway.
    return int(_pick([25, 30, 35, 45, 60, 75, 90, 120, 150, 180]))


def generate_random_bpm() -> int:
    return int(_pick([60, 70, 80, 90, 100, 110, 120, 128, 136, 140, 150, 160, 174]))


def generate_random_key_scale() -> str:
    v = str(_pick(["C major", "G major", "D major", "A minor", "E minor", "F major"])).strip()
    return v or "C major"


# Backwards-compat exports. Call sites that used to do random.choice on these lists
# still work, but the lists are now generated from the external packs above.
RANDOM_PROMPTS: list[str] = [generate_random_prompt() for _ in range(24)]
RANDOM_LYRICS_TEMPLATES: list[str] = [generate_random_lyrics() for _ in range(12)]


# ========================================
# Prompt building (shared)
# ========================================


def build_prompt(*, base_prompt: str, lyrics: str | None, vocals: bool) -> str:
    """Build the full prompt string sent to music generation providers."""
    parts: list[str] = [base_prompt.strip()]
    if vocals:
        parts.append("with vocals, singing (do not be instrumental-only)")
    else:
        parts.append("instrumental only (no vocals)")
    if lyrics and lyrics.strip():
        parts.append("Lyrics:\n" + lyrics.strip())
    return "\n\n".join(parts).strip()


# ========================================
# Job serialization helpers (shared)
# ========================================


def serialize_job_dict(
    *,
    job_id: str,
    status: str,
    created_at_ms: int,
    updated_at_ms: int,
    provider: str,
    prompt: str,
    params: dict[str, Any],
    error: str | None,
    song_id: str | None,
    audio_url: str | None = None,
    download_url: str | None = None,
    user_id: int | None = None,
    visibility: str = "private",
    share_permission: str = "listen_only",
) -> dict[str, Any]:
    """Serialize a job record into the standard API response dict.

    This is the shared serialization format used by both main.py (FastAPI)
    and stdlib_server.py (stdlib HTTP server).
    """
    return {
        "job_id": job_id,
        "status": status,
        "created_at_ms": created_at_ms,
        "updated_at_ms": updated_at_ms,
        "provider": provider,
        "prompt": prompt,
        "params": params,
        "audio_url": audio_url,
        "download_url": download_url,
        "error": error,
        "song_id": song_id,
        "user_id": user_id,
        "visibility": visibility,
        "share_permission": share_permission,
    }

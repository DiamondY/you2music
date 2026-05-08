"""Shared data and utility functions used by both main.py and stdlib_server.py."""

from __future__ import annotations

from typing import Any

# ========================================
# Random Sample Data (shared)
# ========================================

RANDOM_PROMPTS: list[str] = [
    "A dreamy electronic ambient track with soft synth pads and gentle arpeggios",
    "Upbeat pop song with catchy melody and energetic drums",
    "Melancholic piano ballad with emotional strings",
    "Funky dance track with groovy bass line and brass section",
    "Acoustic folk song with warm guitar strumming and heartfelt vocals",
    "Epic cinematic orchestral piece with dramatic crescendo",
    "Chill lo-fi hip hop beat with jazzy samples and vinyl crackle",
    "Energetic rock anthem with powerful electric guitars and driving rhythm",
    "Smooth R&B track with sultry vocals and lush harmonies",
    "Traditional Chinese-inspired piece with guzheng and erhu melodies",
    "Modern trap beat with heavy 808 bass and crisp hi-hats",
    "Reggae-inspired track with laid-back groove and offbeat guitar skanks",
    "Electronic dance music with buildups and drops",
    "Jazz standard with swing rhythm and improvisational solos",
    "New age meditation music with Tibetan singing bowls and nature sounds",
]

RANDOM_LYRICS_TEMPLATES: list[str] = [
    """[Verse 1]
漫步在这城市的街头
霓虹灯映照着过往的梦
微风轻拂脸庞的感觉
让我想起了你的温柔

[Chorus]
时光如水静静流淌
记忆中的画面依然清晰
那些年我们一起追的梦
如今都变成了心底的歌""",
    """[Verse 1]
Standing on the edge of tomorrow
Looking back at yesterday
All the joy and all the sorrow
Led me to this moment today

[Chorus]
We're chasing dreams across the sky
No matter how far, we'll learn to fly
Together we'll make it through the night
Into the morning light""",
    """[Verse 1]
月光洒落在窗台
思绪随着夜风飘来
那些未曾说出口的话
在心中惄惄绽放

[Bridge]
时间是最温柔的答案
等待是最深情的告白

[Chorus]
让风带走所有遗憾
让梦点亮每个夜晚""",
    """[Verse 1]
踏遍千山万水
追寻心中的风景
一路上有风有雨
也有你温暖的笑容

[Chorus]
人生就像一场旅行
珍惜沿途的每一道风景
不管终点在哪里
重要的是与你同行""",
    """[Verse 1]
咖啡杯里倒映着午后阳光
书页翻动间时光悄然流淌
窗外的城市依旧繁忙
而我沉浸在这片刻的安详

[Chorus]
Simple moments, peaceful days
In this quiet space, my heart stays
Finding beauty in the ordinary
Living life extraordinary""",
]


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

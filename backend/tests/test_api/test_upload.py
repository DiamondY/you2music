from __future__ import annotations

import io
import wave

import test_env  # noqa: F401


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * 800)
    return buf.getvalue()


def test_upload_audio_requires_auth(client) -> None:
    resp = client.post("/api/uploads/audio", files={"file": ("a.wav", _wav_bytes(), "audio/wav")})
    assert resp.status_code == 401


def test_upload_audio_accepts_wav(client, auth_headers) -> None:
    resp = client.post("/api/uploads/audio", headers=auth_headers, files={"file": ("a.wav", _wav_bytes(), "audio/wav")})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["upload_id"]
    assert data["format"] in ("wav", "mp3", "flac")


def test_upload_audio_rejects_non_audio(client, auth_headers) -> None:
    resp = client.post(
        "/api/uploads/audio",
        headers=auth_headers,
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_audio_rejects_oversized_file(client, auth_headers, monkeypatch) -> None:
    import main

    monkeypatch.setattr(main, "_UPLOAD_MAX_BYTES", 10)
    resp = client.post(
        "/api/uploads/audio",
        headers=auth_headers,
        files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
    )
    assert resp.status_code == 413

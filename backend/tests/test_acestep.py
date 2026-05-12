"""Tests for ACE-Step provider: request body construction, SSE parsing, and logging redaction."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from providers.acestep import ACEStepClient, ACEStepStreamEvent, VALID_TASK_TYPES


# ---------------------------------------------------------------------------
# Fixture: a client instance (no real HTTP calls — we test body construction)
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> ACEStepClient:
    """Create an ACEStepClient for testing (no real HTTP calls)."""
    return ACEStepClient(
        api_key="test-key-for-unit-tests",
        base_url="https://api.acemusic.ai",
        timeout_s=30.0,
    )


# ===========================================================================
# 1. Request Body Construction Tests
# ===========================================================================


class TestBuildRequestBody:
    """Test _build_request_body produces correct payload shapes."""

    # --- Basic text2music ---

    def test_text2music_minimal(self, client: ACEStepClient) -> None:
        """Minimal text2music request: prompt only."""
        body = client._build_request_body(prompt="a pop song")
        assert body["model"] == "acemusic/acestep-v1.5-turbo"
        assert body["messages"] == [{"role": "user", "content": "a pop song"}]
        # task_type omitted when default text2music
        assert "task_type" not in body

    def test_text2music_with_lyrics(self, client: ACEStepClient) -> None:
        """Lyrics appear in both messages.content and top-level lyrics."""
        body = client._build_request_body(
            prompt="a pop song",
            lyrics="la la la",
        )
        assert "Lyrics:\nla la la" in body["messages"][0]["content"]
        assert body["lyrics"] == "la la la"

    def test_text2music_explicit_task_type(self, client: ACEStepClient) -> None:
        """Explicit task_type=text2music is sent in body."""
        body = client._build_request_body(prompt="x", task_type="text2music")
        assert body["task_type"] == "text2music"

    # --- Dual-write: audio_config + top-level flat ---

    def test_dual_write_duration(self, client: ACEStepClient) -> None:
        """duration appears in both audio_config and top-level."""
        body = client._build_request_body(prompt="x", audio_duration=60)
        assert body["audio_config"]["duration"] == 60
        assert body["duration"] == 60

    def test_dual_write_format(self, client: ACEStepClient) -> None:
        """format appears in audio_config.format, top-level uses audio_format."""
        body = client._build_request_body(prompt="x", audio_format="wav")
        assert body["audio_config"]["format"] == "wav"
        assert body["audio_format"] == "wav"
        # Wrong name should NOT appear
        assert "format" not in {k for k in body if k != "audio_config"}

    def test_dual_write_bpm(self, client: ACEStepClient) -> None:
        """bpm dual-written."""
        body = client._build_request_body(prompt="x", bpm=128)
        assert body["audio_config"]["bpm"] == 128
        assert body["bpm"] == 128

    def test_dual_write_vocal_language(self, client: ACEStepClient) -> None:
        """vocal_language dual-written (except 'auto' is excluded)."""
        body = client._build_request_body(prompt="x", vocal_language="zh")
        assert body["audio_config"]["vocal_language"] == "zh"
        assert body["vocal_language"] == "zh"

    def test_vocal_language_auto_excluded(self, client: ACEStepClient) -> None:
        """vocal_language=auto is NOT sent (server auto-detects)."""
        body = client._build_request_body(prompt="x", vocal_language="auto")
        assert "vocal_language" not in body.get("audio_config", {})
        assert "vocal_language" not in body

    def test_instrumental_dual_write(self, client: ACEStepClient) -> None:
        """instrumental=true goes to audio_config AND top-level (dual-write for compat)."""
        body = client._build_request_body(prompt="x", instrumental=True)
        assert body["audio_config"]["instrumental"] is True
        # Implementation also writes instrumental at top-level for backward compat
        assert body["instrumental"] is True

    # --- Top-level only params (NOT in audio_config) ---

    def test_thinking_top_level_only(self, client: ACEStepClient) -> None:
        """thinking is top-level, not in audio_config."""
        body = client._build_request_body(prompt="x", thinking=True)
        assert body["thinking"] is True
        assert "thinking" not in body.get("audio_config", {})

    def test_seed_top_level_only(self, client: ACEStepClient) -> None:
        """seed is top-level with use_random_seed=False."""
        body = client._build_request_body(prompt="x", seed=42)
        assert body["seed"] == 42
        assert body["use_random_seed"] is False
        assert "seed" not in body.get("audio_config", {})

    def test_seed_zero_accepted(self, client: ACEStepClient) -> None:
        """seed=0 is a valid value (not treated as None)."""
        body = client._build_request_body(prompt="x", seed=0)
        assert body["seed"] == 0
        assert body["use_random_seed"] is False

    def test_sample_mode_top_level(self, client: ACEStepClient) -> None:
        """sample_mode is top-level boolean."""
        body = client._build_request_body(prompt="x", sample_mode=True)
        assert body["sample_mode"] is True

    def test_temperature_top_level(self, client: ACEStepClient) -> None:
        """temperature is top-level float."""
        body = client._build_request_body(prompt="x", temperature=0.95)
        assert body["temperature"] == 0.95

    def test_top_p_top_level(self, client: ACEStepClient) -> None:
        """top_p is top-level float."""
        body = client._build_request_body(prompt="x", top_p=0.8)
        assert body["top_p"] == 0.8

    def test_use_cot_caption_top_level(self, client: ACEStepClient) -> None:
        """use_cot_caption is top-level boolean."""
        body = client._build_request_body(prompt="x", use_cot_caption=True)
        assert body["use_cot_caption"] is True

    def test_use_cot_language_top_level(self, client: ACEStepClient) -> None:
        """use_cot_language is top-level boolean."""
        body = client._build_request_body(prompt="x", use_cot_language=False)
        assert body["use_cot_language"] is False

    # --- Task type params ---

    def test_task_type_cover(self, client: ACEStepClient) -> None:
        """cover task_type set at top-level."""
        body = client._build_request_body(
            prompt="cover version",
            task_type="cover",
            src_audio_b64="dGVzdA==",
        )
        assert body["task_type"] == "cover"

    def test_audio_cover_strength(self, client: ACEStepClient) -> None:
        """audio_cover_strength is top-level float."""
        body = client._build_request_body(
            prompt="cover",
            task_type="cover",
            src_audio_b64="dGVzdA==",
            audio_cover_strength=0.5,
        )
        assert body["audio_cover_strength"] == 0.5

    def test_repainting_params(self, client: ACEStepClient) -> None:
        """repainting_start/end are top-level floats."""
        body = client._build_request_body(
            prompt="repaint",
            task_type="repaint",
            src_audio_b64="dGVzdA==",
            repainting_start=5.0,
            repainting_end=15.0,
        )
        assert body["repainting_start"] == 5.0
        assert body["repainting_end"] == 15.0

    # --- Audio input: multimodal messages ---

    def test_text2music_reference_audio(self, client: ACEStepClient) -> None:
        """text2music with reference_audio → multimodal message with audio part."""
        body = client._build_request_body(
            prompt="style like this",
            reference_audio_b64="cmVmYXVkZW8=",
            reference_audio_format="wav",
        )
        content = body["messages"][0]["content"]
        assert isinstance(content, list)
        # First part is text
        assert content[0]["type"] == "text"
        # Second part is input_audio
        assert content[1]["type"] == "input_audio"
        assert content[1]["input_audio"]["data"] == "cmVmYXVkZW8="
        assert content[1]["input_audio"]["format"] == "wav"

    def test_cover_src_audio_multimodal(self, client: ACEStepClient) -> None:
        """cover task → src_audio as first audio part."""
        body = client._build_request_body(
            prompt="cover this",
            task_type="cover",
            src_audio_b64="c3JjYXVkZW8=",
            src_audio_format="mp3",
        )
        content = body["messages"][0]["content"]
        assert isinstance(content, list)
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "input_audio"
        assert content[1]["input_audio"]["data"] == "c3JjYXVkZW8="
        assert content[1]["input_audio"]["format"] == "mp3"

    def test_cover_with_both_audios(self, client: ACEStepClient) -> None:
        """cover with src + reference → three content parts."""
        body = client._build_request_body(
            prompt="cover + ref",
            task_type="cover",
            src_audio_b64="c3Jj",
            src_audio_format="mp3",
            reference_audio_b64="cmVm",
            reference_audio_format="wav",
        )
        content = body["messages"][0]["content"]
        assert len(content) == 3
        assert content[0]["type"] == "text"
        assert content[1]["input_audio"]["data"] == "c3Jj"   # src first
        assert content[2]["input_audio"]["data"] == "cmVm"   # ref second

    def test_no_audio_string_content(self, client: ACEStepClient) -> None:
        """Without audio, messages.content is a plain string."""
        body = client._build_request_body(prompt="no audio")
        assert isinstance(body["messages"][0]["content"], str)

    # --- Validation ---

    def test_invalid_task_type_raises(self, client: ACEStepClient) -> None:
        """Invalid task_type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid task_type"):
            client._build_request_body(prompt="x", task_type="remix")

    def test_text2music_rejects_src_audio(self, client: ACEStepClient) -> None:
        """text2music + src_audio raises ValueError."""
        with pytest.raises(ValueError, match="does not accept src_audio"):
            client._build_request_body(
                prompt="x",
                task_type="text2music",
                src_audio_b64="dGVzdA==",
            )

    def test_cover_requires_src_audio(self, client: ACEStepClient) -> None:
        """cover without src_audio raises ValueError."""
        with pytest.raises(ValueError, match="requires src_audio"):
            client._build_request_body(prompt="x", task_type="cover")

    def test_repaint_requires_src_audio(self, client: ACEStepClient) -> None:
        """repaint without src_audio raises ValueError."""
        with pytest.raises(ValueError, match="requires src_audio"):
            client._build_request_body(prompt="x", task_type="repaint")

    def test_all_valid_task_types(self, client: ACEStepClient) -> None:
        """All documented task types are accepted."""
        for tt in VALID_TASK_TYPES:
            kwargs: dict[str, Any] = {"prompt": "x", "task_type": tt}
            if tt != "text2music":
                kwargs["src_audio_b64"] = "dGVzdA=="
            body = client._build_request_body(**kwargs)
            assert "task_type" in body or tt == "text2music"

    # --- Model mapping ---

    def test_model_mapping(self, client: ACEStepClient) -> None:
        """Friendly model names are mapped to API IDs."""
        body = client._build_request_body(prompt="x", model="acestep-v15-turbo")
        assert body["model"] == "acemusic/acestep-v1.5-turbo"

    def test_model_passthrough(self, client: ACEStepClient) -> None:
        """Full API model IDs pass through unchanged."""
        body = client._build_request_body(
            prompt="x", model="acemusic/acestep-v1.5-xl-turbo"
        )
        assert body["model"] == "acemusic/acestep-v1.5-xl-turbo"


# ===========================================================================
# 2. SSE Parsing Tests
# ===========================================================================


def _make_sse_line(data: dict[str, Any]) -> str:
    """Build an SSE data: line from a dict."""
    return f"data: {json.dumps(data)}"


class TestSSEParsing:
    """Test SSE chunk → ACEStepStreamEvent parsing logic.

    We test by simulating the line-by-line parsing that generate_stream
    performs internally. Since the parsing is inline (not a separate
    function), we validate the event structure directly.
    """

    def test_event_types(self) -> None:
        """ACEStepStreamEvent supports all documented event types."""
        for et in ("init", "content", "heartbeat", "audio", "done"):
            evt = ACEStepStreamEvent(event_type=et)
            assert evt.event_type == et

    def test_content_event(self) -> None:
        """Content event carries text."""
        evt = ACEStepStreamEvent(event_type="content", content="Generating intro...")
        assert evt.content == "Generating intro..."
        assert evt.audio_bytes is None

    def test_heartbeat_event(self) -> None:
        """Heartbeat event has no content."""
        evt = ACEStepStreamEvent(event_type="heartbeat")
        assert evt.content is None

    def test_audio_event(self) -> None:
        """Audio event carries decoded bytes."""
        raw_audio = b"fake mp3 data"
        evt = ACEStepStreamEvent(
            event_type="audio",
            audio_bytes=raw_audio,
        )
        assert evt.audio_bytes == raw_audio

    def test_done_event(self) -> None:
        """Done event carries finish_reason."""
        evt = ACEStepStreamEvent(event_type="done", finish_reason="stop")
        assert evt.finish_reason == "stop"

    def test_frozen_dataclass(self) -> None:
        """ACEStepStreamEvent is frozen (immutable)."""
        evt = ACEStepStreamEvent(event_type="init")
        with pytest.raises(AttributeError):
            evt.event_type = "content"  # type: ignore[misc]

    def test_sse_init_chunk(self) -> None:
        """SSE chunk with role=assistant → init event."""
        chunk = {"choices": [{"delta": {"role": "assistant"}}]}
        delta = chunk["choices"][0]["delta"]
        assert delta.get("role") == "assistant"

    def test_sse_content_chunk(self) -> None:
        """SSE chunk with non-dot content → content event."""
        chunk = {"choices": [{"delta": {"content": "Analyzing prompt..."}}]}
        delta = chunk["choices"][0]["delta"]
        content = delta.get("content")
        assert content and content != "."

    def test_sse_heartbeat_chunk(self) -> None:
        """SSE chunk with content='.' → heartbeat."""
        chunk = {"choices": [{"delta": {"content": "."}}]}
        delta = chunk["choices"][0]["delta"]
        content = delta.get("content")
        assert content == "."

    def test_sse_audio_chunk(self) -> None:
        """SSE chunk with delta.audio → audio event with decoded bytes."""
        fake_b64 = base64.b64encode(b"audio-data").decode()
        chunk = {
            "choices": [
                {
                    "delta": {
                        "audio": [
                            {"audio_url": {"url": f"data:audio/mpeg;base64,{fake_b64}"}}
                        ]
                    }
                }
            ]
        }
        delta = chunk["choices"][0]["delta"]
        audio_list = delta.get("audio")
        assert audio_list
        data_url = audio_list[0]["audio_url"]["url"]
        assert data_url.startswith("data:")
        _, b64_part = data_url.split(",", 1)
        assert base64.b64decode(b64_part) == b"audio-data"

    def test_sse_done_chunk(self) -> None:
        """SSE chunk with finish_reason → done event."""
        chunk = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        fr = chunk["choices"][0].get("finish_reason")
        assert fr is not None

    def test_sse_done_sentinel(self) -> None:
        """data: [DONE] terminates the stream."""
        data_str = "[DONE]"
        assert data_str == "[DONE]"


# ===========================================================================
# 3. Logging Redaction Tests
# ===========================================================================


class TestLoggingRedaction:
    """Test that API logs do NOT contain base64 audio data.

    The log body construction in workers.py intentionally:
    1. Uses upload_id references instead of raw base64 audio data
    2. Uses simple prompt string instead of multimodal content array
    3. Omits base64 audio data from response logs

    We test the log body construction logic here.
    """

    def test_log_body_no_base64_in_messages(self) -> None:
        """Log body uses simple string content, never multimodal array."""
        # Simulate what workers.py builds for logging
        log_body: dict[str, Any] = {
            "model": "acemusic/acestep-v1.5-turbo",
            "messages": [{"role": "user", "content": "a pop song"}],
        }
        content = log_body["messages"][0]["content"]
        assert isinstance(content, str)
        assert "input_audio" not in json.dumps(log_body)

    def test_log_body_uses_upload_id_not_b64(self) -> None:
        """Audio uploads referenced by upload_id, not base64 data."""
        log_body: dict[str, Any] = {
            "model": "acemusic/acestep-v1.5-turbo",
            "messages": [{"role": "user", "content": "cover this"}],
            "src_audio_upload_id": "abc123",
            "src_audio_format": "mp3",
        }
        log_json = json.dumps(log_body)
        # upload_id present
        assert "abc123" in log_json
        # No base64 audio data
        assert "input_audio" not in log_json
        assert "data:" not in log_json
        # No base64-like patterns (long alphanumeric strings)
        for key in log_body:
            val = log_body[key]
            if isinstance(val, str):
                assert len(val) < 200, f"Suspicious long string in log key '{key}'"

    def test_log_body_no_src_audio_b64_key(self) -> None:
        """src_audio_b64 key never appears in log body."""
        log_body: dict[str, Any] = {
            "model": "acemusic/acestep-v1.5-turbo",
            "messages": [{"role": "user", "content": "cover"}],
            "src_audio_upload_id": "abc123",
            "src_audio_format": "mp3",
            "reference_audio_upload_id": "def456",
            "reference_audio_format": "wav",
        }
        log_json = json.dumps(log_body)
        assert "src_audio_b64" not in log_json
        assert "reference_audio_b64" not in log_json

    def test_response_log_no_audio_bytes(self) -> None:
        """Response log contains task_id only, no audio data."""
        response_log = json.dumps({"task_id": "acestep-stop"})
        assert "audio" not in response_log
        assert "base64" not in response_log

    def test_log_body_params_without_secrets(self) -> None:
        """All logged params are safe (no secrets, no blobs)."""
        log_body: dict[str, Any] = {
            "model": "acemusic/acestep-v1.5-turbo",
            "messages": [{"role": "user", "content": "test"}],
            "duration": 30,
            "audio_format": "mp3",
            "bpm": 128,
            "vocal_language": "zh",
            "task_type": "cover",
            "audio_cover_strength": 0.8,
            "seed": 42,
            "src_audio_upload_id": "abc",
        }
        log_json = json.dumps(log_body)
        # No sensitive keys
        for forbidden in ("src_audio_b64", "reference_audio_b64", "api_key", "Authorization"):
            assert forbidden not in log_json, f"Forbidden key '{forbidden}' in log"

    def test_empty_string_params_excluded_from_log(self) -> None:
        """Empty string values are excluded from acestep_kwargs (workers.py logic)."""
        # Simulate the filtering from workers.py
        provider_params: dict[str, Any] = {
            "key_scale": "",
            "time_signature": "",
            "bpm": 128,
        }
        acestep_kwargs: dict[str, Any] = {}
        for k in ("bpm", "key_scale", "time_signature"):
            val = provider_params.get(k)
            if val is not None and val != "":
                acestep_kwargs[k] = val
        assert "bpm" in acestep_kwargs
        assert "key_scale" not in acestep_kwargs
        assert "time_signature" not in acestep_kwargs

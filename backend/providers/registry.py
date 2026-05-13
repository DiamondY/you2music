from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import Settings


@dataclass(frozen=True)
class ProviderField:
    key: str
    label: str
    kind: str  # "string" | "number" | "integer" | "boolean" | "enum" | "json"
    required: bool = False
    advanced: bool = False
    default: Any | None = None
    enum: list[str] | None = None
    help: str | None = None
    visible_if: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    description: str
    capabilities: dict[str, Any]
    fields: list[ProviderField]
    config_secret_key: str | None = None
    env_secret_name: str | None = None
    config_endpoint_key: str | None = None
    env_endpoint_name: str | None = None


def get_providers(settings: Settings, *, include_disabled: bool = False) -> list[ProviderInfo]:
    """Return the list of supported providers.

    Project policy: ACE-Step is the only provider.
    """
    ui_defaults = getattr(settings, "provider_ui_defaults", {}) or {}

    def _def(provider_id: str, key: str, fallback: Any) -> Any:
        v = ui_defaults.get(provider_id, {}).get(key, None)
        return fallback if v is None else v

    # ACE-Step fields - optimized for OpenAI-compatible API
    acestep_fields: list[ProviderField] = [
        # Basic settings
        ProviderField(
            key="model",
            label="Model",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("acestep", "model", "acemusic/acestep-v1.5-turbo"),
            enum=[
                "acemusic/acestep-v1.5-turbo",
                "acemusic/acestep-v1.5-xl-turbo",
            ],
            help="Turbo is faster; XL is higher quality.",
        ),
        ProviderField(
            key="audio_format",
            label="Audio Format",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("acestep", "audio_format", "mp3"),
            enum=["mp3", "wav", "flac"],
            help="Output audio container/codec.",
        ),
        ProviderField(
            key="vocal_language",
            label="Vocal Language",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("acestep", "vocal_language", "zh"),
            enum=["zh", "en", "ja", "ko", "auto"],
            help="Primary lyrics language; auto lets server detect.",
        ),
        ProviderField(
            key="task_type",
            label="Task Type",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("acestep", "task_type", "text2music"),
            enum=["text2music", "cover", "repaint", "lego", "extract", "complete"],
            help="text2music or audio-edit tasks.",
        ),
        # Music attributes (optional)
        ProviderField(
            key="bpm",
            label="BPM",
            kind="integer",
            required=False,
            advanced=False,
            default=_def("acestep", "bpm", None),
            help="30–300; leave empty for auto.",
        ),
        ProviderField(
            key="key_scale",
            label="Key / Scale",
            kind="string",
            required=False,
            advanced=False,
            default=_def("acestep", "key_scale", ""),
            help="Example: C major, D minor. Leave empty for auto.",
        ),
        ProviderField(
            key="time_signature",
            label="Time Signature",
            kind="string",
            required=False,
            advanced=False,
            default=_def("acestep", "time_signature", ""),
            help="Example: 4/4, 3/4, 6/8. Leave empty for auto.",
        ),
        ProviderField(
            key="thinking",
            label="Thinking",
            kind="boolean",
            required=False,
            advanced=True,
            default=bool(_def("acestep", "thinking", False)),
            help="Enable enhanced reasoning mode (server-side).",
        ),
        ProviderField(
            key="use_format",
            label="Use Format",
            kind="boolean",
            required=False,
            advanced=True,
            default=bool(_def("acestep", "use_format", False)),
            help="Enable format-enhancement for prompt/lyrics.",
        ),
        ProviderField(
            key="inference_steps",
            label="Inference Steps",
            kind="integer",
            required=False,
            advanced=True,
            default=_def("acestep", "inference_steps", None),
            help="Model inference steps; leave empty for server default.",
        ),
        ProviderField(
            key="guidance_scale",
            label="Guidance Scale",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "guidance_scale", None),
            help="Prompt guidance scale; leave empty for server default.",
        ),
        ProviderField(
            key="seed",
            label="Seed",
            kind="integer",
            required=False,
            advanced=True,
            default=_def("acestep", "seed", None),
            help="Reproducibility seed (0+).",
        ),
        ProviderField(
            key="temperature",
            label="Temperature",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "temperature", None),
            help="LM sampling temperature.",
        ),
        ProviderField(
            key="top_p",
            label="Top P",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "top_p", None),
            help="Nucleus sampling top_p.",
        ),
        ProviderField(
            key="use_cot_caption",
            label="Use CoT Caption",
            kind="boolean",
            required=False,
            advanced=True,
            default=_def("acestep", "use_cot_caption", None),
            help="Rewrite/expand music description via LM.",
        ),
        ProviderField(
            key="use_cot_language",
            label="Use CoT Language",
            kind="boolean",
            required=False,
            advanced=True,
            default=_def("acestep", "use_cot_language", None),
            help="Auto-detect lyrics language via LM.",
        ),
        ProviderField(
            key="audio_cover_strength",
            label="Cover Strength",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "audio_cover_strength", None),
            help="cover task strength 0.0–1.0.",
            visible_if={"task_type": "cover"},
        ),
        ProviderField(
            key="repainting_start",
            label="Repaint Start (sec)",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "repainting_start", None),
            help="repaint start time (seconds).",
            visible_if={"task_type": "repaint"},
        ),
        ProviderField(
            key="repainting_end",
            label="Repaint End (sec)",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "repainting_end", None),
            help="repaint end time (seconds).",
            visible_if={"task_type": "repaint"},
        ),
        # Audio upload references (worker loads them from uploads dir)
        ProviderField(
            key="src_audio_upload_id",
            label="Source Audio Upload ID",
            kind="string",
            required=False,
            advanced=True,
            default="",
            help="Required for cover/repaint/lego/extract/complete.",
            visible_if={"task_type": ["cover", "repaint", "lego", "extract", "complete"]},
        ),
        ProviderField(
            key="src_audio_format",
            label="Source Audio Format",
            kind="enum",
            required=False,
            advanced=True,
            default="mp3",
            enum=["mp3", "wav", "flac"],
            help="Format for source audio file.",
            visible_if={"task_type": ["cover", "repaint", "lego", "extract", "complete"]},
        ),
        ProviderField(
            key="reference_audio_upload_id",
            label="Reference Audio Upload ID",
            kind="string",
            required=False,
            advanced=True,
            default="",
            help="Optional reference audio for any task.",
        ),
        ProviderField(
            key="reference_audio_format",
            label="Reference Audio Format",
            kind="enum",
            required=False,
            advanced=True,
            default="mp3",
            enum=["mp3", "wav", "flac"],
            help="Format for reference audio file.",
        ),
    ]

    return [
        ProviderInfo(
            id="acestep",
            name="ACE-Step 1.5 (acemusic.ai)",
            description="ACE-Step 1.5 open-source music generation model served via acemusic.ai (OpenAI-compatible API).",
            capabilities={
                "supports_vocals": True,
                "supports_true_extend": False,
                "supports_audio_input": True,
                "max_duration_sec": 600,
            },
            fields=acestep_fields,
            config_secret_key="acestep_api_key",
            env_secret_name="ACESTEP_API_KEY",
            config_endpoint_key="acestep_base_url",
            env_endpoint_name="ACESTEP_BASE_URL",
        )
    ]


def providers_payload(settings: Settings, *, include_disabled: bool = False) -> dict[str, Any]:
    providers = get_providers(settings, include_disabled=include_disabled)
    missing_by_provider = {
        "acestep": (["ACESTEP_API_KEY"] if not getattr(settings, "acestep_api_key", None) else []),
    }
    return {
        "default_provider": "acestep",
        "providers": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "capabilities": p.capabilities,
                "ready": len(missing_by_provider.get(p.id, [])) == 0,
                "missing_env": missing_by_provider.get(p.id, []),
                "config_secret_key": p.config_secret_key,
                "env_secret_name": p.env_secret_name,
                "config_endpoint_key": p.config_endpoint_key,
                "env_endpoint_name": p.env_endpoint_name,
                "endpoints": (
                    [
                        {
                            "key": p.config_endpoint_key,
                            "env": p.env_endpoint_name,
                            "label": "Base URL",
                        }
                    ]
                    if p.config_endpoint_key
                    else []
                ),
                "fields": [
                    {
                        "key": f.key,
                        "label": f.label,
                        "kind": f.kind,
                        "required": f.required,
                        "advanced": f.advanced,
                        "default": f.default,
                        "enum": f.enum,
                        "help": f.help,
                        "visible_if": f.visible_if,
                    }
                    for f in p.fields
                ],
            }
            for p in providers
        ],
    }

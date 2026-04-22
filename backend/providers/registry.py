from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

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
    # Keep this minimal and explicit. Add more providers by appending ProviderInfo
    # and implementing them in main/stdlib_server job runner.
    ui_defaults = getattr(settings, "provider_ui_defaults", {}) or {}

    def _def(provider_id: str, key: str, fallback: Any) -> Any:
        v = ui_defaults.get(provider_id, {}).get(key, None)
        return fallback if v is None else v

    eleven_fields: list[ProviderField] = [
        ProviderField(
            key="output_format",
            label="输出格式",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("elevenlabs", "output_format", settings.output_format),
            enum=[
                "mp3_128kbps",
                "mp3_192kbps",
                "pcm_44100",
            ],
            help="传给 ElevenLabs `output_format`。不同账号/套餐支持的格式可能不同。",
        ),
        ProviderField(
            key="raw_prompt",
            label="原始 Prompt 模式",
            kind="boolean",
            required=False,
            advanced=True,
            default=bool(_def("elevenlabs", "raw_prompt", False)),
            help="开启后不再自动注入 'with vocals' 或 Lyrics 前缀，完全按你的 prompt 发送。",
        ),
        ProviderField(
            key="use_composition_plan",
            label="使用 Composition Plan",
            kind="boolean",
            required=False,
            advanced=True,
            default=bool(_def("elevenlabs", "use_composition_plan", False)),
            help="开启后使用 composition_plan_json 作为输入（高级用法）。",
        ),
        ProviderField(
            key="composition_plan_json",
            label="Composition Plan JSON",
            kind="json",
            required=False,
            advanced=True,
            default=None,
            help="粘贴 ElevenLabs 的 composition plan JSON（将作为 `composition_plan` 发送）。",
            visible_if={"use_composition_plan": True},
        ),
    ]

    fal_fields: list[ProviderField] = [
        ProviderField(
            key="model_id",
            label="fal 模型 ID",
            kind="string",
            required=True,
            advanced=False,
            default=_def("fal", "model_id", "fal-ai/stable-audio-25/text-to-audio"),
            help="示例：fal-ai/stable-audio-25/text-to-audio",
        ),
        ProviderField(
            key="seconds_total",
            label="时长（秒）",
            kind="integer",
            required=False,
            advanced=False,
            default=None,
            help="留空则用通用 duration_sec。",
        ),
        ProviderField(
            key="num_inference_steps",
            label="Steps",
            kind="integer",
            required=False,
            advanced=True,
            default=_def("fal", "num_inference_steps", 28),
        ),
        ProviderField(
            key="guidance_scale",
            label="Guidance Scale",
            kind="number",
            required=False,
            advanced=True,
            default=_def("fal", "guidance_scale", 7.0),
        ),
        ProviderField(
            key="seed",
            label="Seed（覆盖通用 seed）",
            kind="integer",
            required=False,
            advanced=True,
            default=None,
        ),
        ProviderField(
            key="poll_interval_s",
            label="轮询间隔（秒）",
            kind="number",
            required=False,
            advanced=True,
            default=_def("fal", "poll_interval_s", 1.0),
        ),
    ]

    replicate_fields: list[ProviderField] = [
        ProviderField(
            key="version",
            label="Replicate version/model",
            kind="string",
            required=True,
            advanced=False,
            default=_def("replicate", "version", "stability-ai/stable-audio-2.5"),
            help="通常写模型名即可；也可填具体 version id（更稳定但需自行维护）。",
        ),
        ProviderField(
            key="duration",
            label="时长（秒）",
            kind="integer",
            required=False,
            advanced=False,
            default=None,
            help="留空则用通用 duration_sec。",
        ),
        ProviderField(
            key="steps",
            label="Steps",
            kind="integer",
            required=False,
            advanced=True,
            default=_def("replicate", "steps", 150),
        ),
        ProviderField(
            key="cfg_scale",
            label="CFG Scale",
            kind="number",
            required=False,
            advanced=True,
            default=_def("replicate", "cfg_scale", 7.0),
        ),
        ProviderField(
            key="seed",
            label="Seed（覆盖通用 seed）",
            kind="integer",
            required=False,
            advanced=True,
            default=None,
        ),
        ProviderField(
            key="poll_interval_s",
            label="轮询间隔（秒）",
            kind="number",
            required=False,
            advanced=True,
            default=_def("replicate", "poll_interval_s", 1.0),
        ),
    ]

    stability_fields: list[ProviderField] = [
        ProviderField(
            key="endpoint_path",
            label="Endpoint Path",
            kind="string",
            required=True,
            advanced=True,
            default=_def("stability", "endpoint_path", "/v2beta/audio/stable-audio-2/text-to-audio"),
            help="Stability 的 Stable Audio endpoint 可能变化；可在此覆盖。",
        ),
        ProviderField(
            key="seconds_total",
            label="时长（秒）",
            kind="integer",
            required=False,
            advanced=False,
            default=None,
            help="留空则用通用 duration_sec。",
        ),
        ProviderField(
            key="steps",
            label="Steps",
            kind="integer",
            required=False,
            advanced=True,
            default=_def("stability", "steps", 150),
        ),
        ProviderField(
            key="cfg_scale",
            label="CFG Scale",
            kind="number",
            required=False,
            advanced=True,
            default=_def("stability", "cfg_scale", 7.0),
        ),
        ProviderField(
            key="seed",
            label="Seed（覆盖通用 seed）",
            kind="integer",
            required=False,
            advanced=True,
            default=None,
        ),
        ProviderField(
            key="output_format",
            label="输出格式（provider）",
            kind="string",
            required=False,
            advanced=True,
            default=None,
            help="如果 Stability endpoint 支持 output_format，可在此传入。",
        ),
    ]

    providers: list[ProviderInfo] = [
        ProviderInfo(
            id="elevenlabs",
            name="ElevenLabs Music",
            description="ElevenLabs Music API（支持人声/器乐）。",
            capabilities={
                "supports_vocals": True,
                "supports_true_extend": False,
                "max_duration_sec": 300,
                "supports_composition_plan": True,
            },
            fields=eleven_fields,
            config_secret_key="elevenlabs_api_key",
            env_secret_name="ELEVENLABS_API_KEY",
            config_endpoint_key="elevenlabs_base_url",
            env_endpoint_name="ELEVENLABS_BASE_URL",
        )
    ]

    providers.extend(
        [
            ProviderInfo(
                id="fal",
                name="fal.ai (Stable Audio)",
                description="通过 fal queue 调用 Stable Audio（通常为器乐/音效）。",
                capabilities={
                    "supports_vocals": False,
                    "supports_true_extend": False,
                    "max_duration_sec": 180,
                },
                fields=fal_fields,
                config_secret_key="fal_key",
                env_secret_name="FAL_KEY",
                config_endpoint_key="fal_queue_base_url",
                env_endpoint_name="FAL_QUEUE_BASE_URL",
            ),
            ProviderInfo(
                id="replicate",
                name="Replicate (Stable Audio)",
                description="通过 Replicate predictions 调用 Stable Audio（通常为器乐/音效）。",
                capabilities={
                    "supports_vocals": False,
                    "supports_true_extend": False,
                    "max_duration_sec": 180,
                },
                fields=replicate_fields,
                config_secret_key="replicate_api_token",
                env_secret_name="REPLICATE_API_TOKEN",
                config_endpoint_key="replicate_base_url",
                env_endpoint_name="REPLICATE_BASE_URL",
            ),
            ProviderInfo(
                id="stability",
                name="Stability (Official API)",
                description="Stability 官方 API（实验性接入；endpoint 可能变化）。",
                capabilities={
                    "supports_vocals": False,
                    "supports_true_extend": False,
                    "max_duration_sec": 180,
                },
                fields=stability_fields,
                config_secret_key="stability_api_key",
                env_secret_name="STABILITY_API_KEY",
                config_endpoint_key="stability_base_url",
                env_endpoint_name="STABILITY_BASE_URL",
            ),
        ]
    )

    if not include_disabled:
        enabled = getattr(settings, "enabled_providers", None)
        if enabled:
            allowed = set(enabled)
            providers = [p for p in providers if p.id in allowed]

    return providers


def providers_payload(settings: Settings, *, include_disabled: bool = False) -> dict[str, Any]:
    providers = get_providers(settings, include_disabled=include_disabled)
    # readiness (env present) - used for UI hints/disablement
    missing_by_provider = {
        "elevenlabs": (["ELEVENLABS_API_KEY"] if not settings.elevenlabs_api_key else []),
        "fal": (["FAL_KEY"] if not settings.fal_key else []),
        "replicate": (["REPLICATE_API_TOKEN"] if not settings.replicate_api_token else []),
        "stability": (["STABILITY_API_KEY"] if not settings.stability_api_key else []),
    }
    return {
        "default_provider": getattr(settings, "default_provider", "elevenlabs"),
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
                            "key": "fal_queue_base_url",
                            "env": "FAL_QUEUE_BASE_URL",
                            "label": "Queue Base URL",
                        },
                        {
                            "key": "fal_platform_base_url",
                            "env": "FAL_PLATFORM_BASE_URL",
                            "label": "Platform Base URL",
                        },
                    ]
                    if p.id == "fal"
                    else (
                        [
                            {
                                "key": p.config_endpoint_key,
                                "env": p.env_endpoint_name,
                                "label": "Base URL",
                            }
                        ]
                        if p.config_endpoint_key
                        else []
                    )
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

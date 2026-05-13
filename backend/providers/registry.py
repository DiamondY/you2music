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
            label="模型",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("acestep", "model", "acemusic/acestep-v1.5-turbo"),
            enum=[
                "acemusic/acestep-v1.5-turbo",
                "acemusic/acestep-v1.5-xl-turbo",
            ],
            help="Turbo 更快；XL 质量更高。",
        ),
        ProviderField(
            key="audio_format",
            label="音频格式",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("acestep", "audio_format", "mp3"),
            enum=["mp3", "wav", "flac"],
            help="输出音频格式（容器/编码）。",
        ),
        ProviderField(
            key="vocal_language",
            label="歌词语言",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("acestep", "vocal_language", "zh"),
            enum=["zh", "en", "ja", "ko", "auto"],
            help="主要歌词语言；auto 为自动识别。",
        ),
        ProviderField(
            key="task_type",
            label="任务类型",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("acestep", "task_type", "text2music"),
            enum=["text2music", "cover", "repaint", "lego", "extract", "complete"],
            help="text2music 为文本生曲；其余为音频编辑类任务。",
        ),
        # Music attributes (optional)
        ProviderField(
            key="bpm",
            label="BPM",
            kind="integer",
            required=False,
            advanced=False,
            default=_def("acestep", "bpm", None),
            help="范围 30–300；留空自动推断。",
        ),
        ProviderField(
            key="key_scale",
            label="调性",
            kind="string",
            required=False,
            advanced=False,
            default=_def("acestep", "key_scale", ""),
            help="示例：C major、D minor；留空自动推断。",
        ),
        ProviderField(
            key="time_signature",
            label="拍号",
            kind="string",
            required=False,
            advanced=False,
            default=_def("acestep", "time_signature", ""),
            help="示例：4/4、3/4、6/8；留空自动推断。",
        ),
        ProviderField(
            key="thinking",
            label="深度思考",
            kind="boolean",
            required=False,
            advanced=True,
            default=bool(_def("acestep", "thinking", False)),
            help="开启增强推理模式（服务端）。",
        ),
        ProviderField(
            key="use_format",
            label="格式增强",
            kind="boolean",
            required=False,
            advanced=True,
            default=bool(_def("acestep", "use_format", False)),
            help="对 Prompt/歌词做格式增强。",
        ),
        ProviderField(
            key="inference_steps",
            label="推理步数",
            kind="integer",
            required=False,
            advanced=True,
            default=_def("acestep", "inference_steps", None),
            help="推理步数；留空使用服务端默认值。",
        ),
        ProviderField(
            key="guidance_scale",
            label="引导强度",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "guidance_scale", None),
            help="Prompt 引导强度；留空使用服务端默认值。",
        ),
        ProviderField(
            key="seed",
            label="随机种子",
            kind="integer",
            required=False,
            advanced=True,
            default=_def("acestep", "seed", None),
            help="复现用随机种子（>= 0）。",
        ),
        ProviderField(
            key="temperature",
            label="温度",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "temperature", None),
            help="采样温度（影响随机性）。",
        ),
        ProviderField(
            key="top_p",
            label="Top P",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "top_p", None),
            help="核采样 top_p。",
        ),
        ProviderField(
            key="use_cot_caption",
            label="描述增强",
            kind="boolean",
            required=False,
            advanced=True,
            default=_def("acestep", "use_cot_caption", None),
            help="用语言模型重写/扩写音乐描述。",
        ),
        ProviderField(
            key="use_cot_language",
            label="歌词语言识别",
            kind="boolean",
            required=False,
            advanced=True,
            default=_def("acestep", "use_cot_language", None),
            help="用语言模型自动识别歌词语言。",
        ),
        ProviderField(
            key="audio_cover_strength",
            label="Cover 强度",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "audio_cover_strength", None),
            help="仅 cover：范围 0.0–1.0。",
            visible_if={"task_type": "cover"},
        ),
        ProviderField(
            key="repainting_start",
            label="重绘起点(秒)",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "repainting_start", None),
            help="仅重绘：起始时间（秒）。",
            visible_if={"task_type": "repaint"},
        ),
        ProviderField(
            key="repainting_end",
            label="重绘终点(秒)",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "repainting_end", None),
            help="仅重绘：结束时间（秒）。",
            visible_if={"task_type": "repaint"},
        ),
        # Audio upload references (worker loads them from uploads dir)
        ProviderField(
            key="src_audio_upload_id",
            label="源音频ID",
            kind="string",
            required=False,
            advanced=True,
            default="",
            help="cover/repaint/lego/extract/complete 需要。",
            visible_if={"task_type": ["cover", "repaint", "lego", "extract", "complete"]},
        ),
        ProviderField(
            key="src_audio_format",
            label="源音频格式",
            kind="enum",
            required=False,
            advanced=True,
            default="mp3",
            enum=["mp3", "wav", "flac"],
            help="源音频文件格式。",
            visible_if={"task_type": ["cover", "repaint", "lego", "extract", "complete"]},
        ),
        ProviderField(
            key="reference_audio_upload_id",
            label="参考音频ID",
            kind="string",
            required=False,
            advanced=True,
            default="",
            help="可选：参考音频（任意任务可用）。",
        ),
        ProviderField(
            key="reference_audio_format",
            label="参考音频格式",
            kind="enum",
            required=False,
            advanced=True,
            default="mp3",
            enum=["mp3", "wav", "flac"],
            help="参考音频文件格式。",
        ),
    ]

    return [
        ProviderInfo(
            id="acestep",
            name="ACE-Step 1.5 (acemusic.ai)",
            description="ACE-Step 1.5 开源音乐生成模型（通过 acemusic.ai 云服务调用，OpenAI 兼容 API）。",
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
                            "label": "接口地址",
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

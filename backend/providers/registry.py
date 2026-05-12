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
    # Keep this minimal and explicit. Add more providers by appending ProviderInfo
    # and implementing them in main/stdlib_server job runner.
    ui_defaults = getattr(settings, "provider_ui_defaults", {}) or {}

    def _def(provider_id: str, key: str, fallback: Any) -> Any:
        v = ui_defaults.get(provider_id, {}).get(key, None)
        return fallback if v is None else v

    # MiniMax fields - optimized for the official API
    minimax_fields: list[ProviderField] = [
        # Basic settings
        ProviderField(
            key="model",
            label="模型",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("minimax", "model", "music-2.6"),
            enum=["music-2.6"],
            help="MiniMax 音乐生成模型。",
        ),
        ProviderField(
            key="lyrics_optimizer",
            label="自动生成歌词",
            kind="boolean",
            required=False,
            advanced=False,
            default=False,
            help="开启后，MiniMax 会自动为你的提示词生成歌词（适合没有歌词时使用）。",
        ),
        # Advanced settings
        ProviderField(
            key="sample_rate",
            label="采样率",
            kind="enum",
            required=False,
            advanced=True,
            default=str(_def("minimax", "sample_rate", 44100)),
            enum=["44100", "48000"],
            help="音频采样率，越高音质越好。",
        ),
        ProviderField(
            key="bitrate",
            label="比特率",
            kind="enum",
            required=False,
            advanced=True,
            default=str(_def("minimax", "bitrate", 256000)),
            enum=["128000", "192000", "256000", "320000"],
            help="音频比特率，越高音质越好、文件越大。",
        ),
        ProviderField(
            key="format",
            label="输出格式",
            kind="enum",
            required=False,
            advanced=True,
            default=_def("minimax", "format", "mp3"),
            enum=["mp3", "wav"],
            help="MP3 文件更小，WAV 无损但文件大。",
        ),
    ]

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
            help="Turbo 速度快，XL 质量更高（4B DiT）。",
        ),
        ProviderField(
            key="vocal_language",
            label="歌词语言",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("acestep", "vocal_language", "zh"),
            enum=["zh", "en", "ja", "ko", "auto"],
            help="歌词主要语言，auto 自动检测。",
        ),
        ProviderField(
            key="bpm",
            label="BPM",
            kind="integer",
            required=False,
            advanced=False,
            default=_def("acestep", "bpm", None),
            help="节拍速度 30–300，留空自动推断。",
        ),
        ProviderField(
            key="key_scale",
            label="调性",
            kind="string",
            required=False,
            advanced=False,
            default=_def("acestep", "key_scale", ""),
            help="例如 C Major, Am, D minor。留空自动推断。",
        ),
        # Advanced settings
        ProviderField(
            key="audio_format",
            label="输出格式",
            kind="enum",
            required=False,
            advanced=True,
            default=_def("acestep", "audio_format", "mp3"),
            enum=["mp3", "wav", "flac"],
            help="MP3 最小，WAV 无损，FLAC 无损压缩。",
        ),
        ProviderField(
            key="time_signature",
            label="拍号",
            kind="enum",
            required=False,
            advanced=True,
            default=_def("acestep", "time_signature", ""),
            enum=["", "2/4", "3/4", "4/4", "6/8"],
            help="留空自动推断。",
        ),
        ProviderField(
            key="thinking",
            label="思考模式",
            kind="boolean",
            required=False,
            advanced=True,
            default=_def("acestep", "thinking", False),
            help="使用 5Hz LM 增强质量（更慢但更好）。",
        ),
        ProviderField(
            key="use_format",
            label="格式增强",
            kind="boolean",
            required=False,
            advanced=True,
            default=_def("acestep", "use_format", False),
            help="让 LM 优化描述和歌词结构。",
        ),
        ProviderField(
            key="request_timeout_s",
            label="请求超时 (秒)",
            kind="integer",
            required=False,
            advanced=True,
            default=_def("acestep", "request_timeout_s", 180),
            help="API 请求超时时间。思考模式建议 ≥180，批量生成建议 ≥240。",
        ),
        # Advanced generation control parameters
        ProviderField(
            key="inference_steps",
            label="推理步数",
            kind="integer",
            required=False,
            advanced=True,
            default=_def("acestep", "inference_steps", None),
            help="Turbo 模型 1-20（推荐 8），留空使用服务端默认值。",
        ),
        ProviderField(
            key="guidance_scale",
            label="引导系数",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "guidance_scale", None),
            help="Prompt 引导强度，默认 7.0。仅 base 模型有效。",
        ),
        ProviderField(
            key="shift",
            label="时间偏移",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "shift", None),
            help="时间步偏移因子 1.0-5.0，默认 3.0。仅 base 模型有效。",
        ),
        ProviderField(
            key="infer_method",
            label="推理方法",
            kind="enum",
            required=False,
            advanced=True,
            default=_def("acestep", "infer_method", ""),
            enum=["", "ode", "sde"],
            help="ode=确定性（更快），sde=随机性。留空使用默认。",
        ),
        ProviderField(
            key="timesteps",
            label="自定义时间步",
            kind="string",
            required=False,
            advanced=True,
            default=_def("acestep", "timesteps", ""),
            help="逗号分隔值，如 0.97,0.76,... 覆盖推理步数。留空自动。",
        ),
        ProviderField(
            key="seed",
            label="随机种子",
            kind="integer",
            required=False,
            advanced=True,
            default=_def("acestep", "seed", None),
            help="固定种子（可复现结果）。留空随机。支持 0。",
        ),
        ProviderField(
            key="task_type",
            label="任务类型",
            kind="enum",
            required=False,
            advanced=False,
            default=_def("acestep", "task_type", "text2music"),
            enum=["text2music", "cover", "repaint", "lego", "extract", "complete"],
            help="text2music=文本生乐，cover=翻唱，repaint=局部重绘，lego=拼接，extract=提取，complete=续写。cover/repaint/lego/extract/complete 需要上传音频。",
        ),
        ProviderField(
            key="sample_mode",
            label="自然语言模式",
            kind="boolean",
            required=False,
            advanced=False,
            default=_def("acestep", "sample_mode", False),
            help="开启后，输入自然语言描述，由 LLM 自动生成 prompt 和歌词。",
        ),
        ProviderField(
            key="temperature",
            label="采样温度",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "temperature", None),
            help="LM 采样温度，默认 0.85。越高越随机。",
        ),
        ProviderField(
            key="top_p",
            label="Top-p 采样",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "top_p", None),
            help="Nucleus sampling，默认 0.9。",
        ),
        ProviderField(
            key="use_cot_caption",
            label="CoT 改写描述",
            kind="boolean",
            required=False,
            advanced=True,
            default=_def("acestep", "use_cot_caption", None),
            help="通过思维链改写/增强音乐描述。默认开启。",
        ),
        ProviderField(
            key="use_cot_language",
            label="CoT 语言检测",
            kind="boolean",
            required=False,
            advanced=True,
            default=_def("acestep", "use_cot_language", None),
            help="通过思维链自动检测歌词语言。默认开启。",
        ),
        ProviderField(
            key="audio_cover_strength",
            label="翻唱强度",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "audio_cover_strength", None),
            help="cover 任务翻唱强度 0.0~1.0，默认 1.0。",
        ),
        ProviderField(
            key="repainting_start",
            label="重绘起始 (秒)",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "repainting_start", None),
            help="repaint 任务重绘区域起始位置（秒）。",
        ),
        ProviderField(
            key="repainting_end",
            label="重绘结束 (秒)",
            kind="number",
            required=False,
            advanced=True,
            default=_def("acestep", "repainting_end", None),
            help="repaint 任务重绘区域结束位置（秒）。",
        ),
    ]

    providers: list[ProviderInfo] = [
        ProviderInfo(
            id="minimax",
            name="MiniMax Music (官方 API)",
            description="MiniMax 官方音乐生成 API（music-2.6），支持人声+中英文歌词，国内可访问。最长 240 秒。",
            capabilities={
                "supports_vocals": True,
                "supports_true_extend": False,
                "max_duration_sec": 240,
            },
            fields=minimax_fields,
            config_secret_key="minimax_api_key",
            env_secret_name="MINIMAX_API_KEY",
            config_endpoint_key="minimax_base_url",
            env_endpoint_name="MINIMAX_BASE_URL",
        ),
        ProviderInfo(
            id="acestep",
            name="ACE-Step 1.5 (acemusic.ai)",
            description="ACE-Step 1.5 开源音乐生成模型，质量介于 Suno v4.5 和 v5 之间，支持人声+50+语言歌词，100% 免费。最长 600 秒。",
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
        ),
    ]

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
        "minimax": (["MINIMAX_API_KEY"] if not settings.minimax_api_key else []),
        "acestep": (["ACESTEP_API_KEY"] if not getattr(settings, "acestep_api_key", None) else []),
    }
    return {
        "default_provider": getattr(settings, "default_provider", "minimax"),
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

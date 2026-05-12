"""ACE-Step 1.5 Music API Provider (stdlib version - no httpx).

ACE-Step 1.5 开源音乐生成模型，通过 acemusic.ai 云服务调用。
支持人声 + 50+ 语言歌词，100% 免费。

API 端点: https://api.acemusic.ai/v1/chat/completions (OpenAI 兼容)
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

VALID_TASK_TYPES = {"text2music", "cover", "repaint", "lego", "extract", "complete"}


@dataclass(frozen=True)
class ACEStepStdlibResult:
    """ACE-Step generation result."""

    audio_bytes: bytes
    task_id: str
    audio_url: str | None = None
    metadata: dict[str, Any] | None = None
    extra_audios: list[bytes] | None = None


class ACEStepClientStdlib:
    """ACE-Step 1.5 API client using stdlib only (OpenAI-compatible)."""

    # Model ID mapping for acemusic.ai
    MODEL_MAP = {
        "acestep-v15-turbo": "acemusic/acestep-v1.5-turbo",
        "acestep-v15-xl-turbo": "acemusic/acestep-v1.5-xl-turbo",
        "ACE-Step V1.5 Turbo": "acemusic/acestep-v1.5-turbo",
        "ACE-Step V1.5 XL Turbo": "acemusic/acestep-v1.5-xl-turbo",
    }

    def __init__(self, *, api_key: str, base_url: str, timeout_s: float) -> None:
        if not api_key:
            raise ValueError("ACESTEP_API_KEY is required for acestep provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def _get_model_id(self, model: str) -> str:
        """Map friendly model names to API model IDs."""
        return self.MODEL_MAP.get(model, model)

    @staticmethod
    def _build_audio_part(audio_b64: str, audio_format: str) -> dict[str, Any]:
        """
        构建音频片段的 content part
        :param audio_b64: base64 编码的音频数据
        :param audio_format: 音频格式，如 "mp3", "wav"
        :return: OpenAI 兼容的 audio content part 字典
        """
        return {
            "type": "input_audio",
            "input_audio": {
                "data": audio_b64,
                "format": audio_format,
            },
        }

    def _build_request_body(
        self,
        *,
        prompt: str,
        lyrics: str | None = None,
        model: str = "acemusic/acestep-v1.5-turbo",
        audio_duration: float | None = None,
        audio_format: str = "mp3",
        bpm: int | None = None,
        key_scale: str | None = None,
        time_signature: str | None = None,
        vocal_language: str | None = None,
        instrumental: bool = False,
        thinking: bool = False,
        use_format: bool = False,
        batch_size: int = 1,
        inference_steps: int | None = None,
        guidance_scale: float | None = None,
        seed: int | None = None,
        shift: float | None = None,
        infer_method: str | None = None,
        timesteps: str | None = None,
        task_type: str | None = None,
        sample_mode: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        use_cot_caption: bool | None = None,
        use_cot_language: bool | None = None,
        audio_cover_strength: float | None = None,
        repainting_start: float | None = None,
        repainting_end: float | None = None,
        src_audio_b64: str | None = None,
        src_audio_format: str | None = None,
        reference_audio_b64: str | None = None,
        reference_audio_format: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        构建请求体字典，供 generate 共用
        :return: OpenAI Chat Completions 格式的请求体
        """
        model_id = self._get_model_id(model)

        # 构建消息内容
        text_content = f"{prompt}\n\nLyrics:\n{lyrics}" if lyrics else prompt

        effective_task_type = task_type or "text2music"
        if effective_task_type not in VALID_TASK_TYPES:
            raise ValueError(f"Invalid task_type '{effective_task_type}', must be one of {sorted(VALID_TASK_TYPES)}")

        # Audio input validation (same contract as async client)
        has_audio = bool(src_audio_b64 or reference_audio_b64)
        if effective_task_type == "text2music":
            if src_audio_b64:
                raise ValueError("task_type=text2music does not accept src_audio; use reference_audio instead.")
        else:
            if not src_audio_b64:
                raise ValueError(f"task_type={effective_task_type} requires src_audio.")

        if has_audio:
            content_parts = [{"type": "text", "text": text_content}]

            # Routing per Openrouter_API_DOC (same as async client)
            if effective_task_type == "text2music":
                if reference_audio_b64:
                    fmt = reference_audio_format or "mp3"
                    content_parts.append(self._build_audio_part(reference_audio_b64, fmt))
            else:
                fmt = src_audio_format or "mp3"
                content_parts.append(self._build_audio_part(src_audio_b64 or "", fmt))
                if reference_audio_b64:
                    fmt2 = reference_audio_format or "mp3"
                    content_parts.append(self._build_audio_part(reference_audio_b64, fmt2))

            messages = [{"role": "user", "content": content_parts}]
        else:
            messages = [{"role": "user", "content": text_content}]

        body: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
        }

        # audio_config 嵌套对象（OpenRouter 格式）
        audio_config: dict[str, Any] = {}
        if audio_duration is not None:
            audio_config["duration"] = int(audio_duration)
        if audio_format:
            audio_config["format"] = audio_format
        if bpm is not None:
            audio_config["bpm"] = int(bpm)
        if key_scale:
            audio_config["key_scale"] = key_scale
        if time_signature:
            audio_config["time_signature"] = time_signature
        if vocal_language and vocal_language != "auto":
            audio_config["vocal_language"] = vocal_language
        if instrumental:
            audio_config["instrumental"] = True
        if audio_config:
            body["audio_config"] = audio_config

        # Dual-write 平展参数（兼容旧版与新版 API）
        if audio_duration is not None:
            body["duration"] = int(audio_duration)
        if audio_format:
            body["audio_format"] = audio_format
        if bpm is not None:
            body["bpm"] = int(bpm)
        if key_scale:
            body["key_scale"] = key_scale
        if time_signature:
            body["time_signature"] = time_signature
        if vocal_language and vocal_language != "auto":
            body["vocal_language"] = vocal_language
        if instrumental:
            body["instrumental"] = True

        # 歌词（顶层，OpenRouter 格式）
        if lyrics:
            body["lyrics"] = str(lyrics).strip()

        # 生成控制（顶层）
        if thinking:
            body["thinking"] = True
        if use_format:
            body["use_format"] = True
        if batch_size and batch_size > 1:
            body["batch_size"] = int(batch_size)

        # 高级参数（顶层）
        if inference_steps is not None:
            body["inference_steps"] = int(inference_steps)
        if guidance_scale is not None:
            body["guidance_scale"] = float(guidance_scale)
        if seed is not None and seed >= 0:
            body["seed"] = int(seed)
            body["use_random_seed"] = False
        if shift is not None:
            body["shift"] = float(shift)
        if infer_method:
            body["infer_method"] = infer_method
        if timesteps:
            body["timesteps"] = timesteps

        # 新 OpenRouter 参数
        if effective_task_type != "text2music":
            body["task_type"] = effective_task_type
        elif task_type is not None:
            body["task_type"] = "text2music"

        if sample_mode:
            body["sample_mode"] = True

        if temperature is not None:
            body["temperature"] = float(temperature)
        if top_p is not None:
            body["top_p"] = float(top_p)
        if use_cot_caption is not None:
            body["use_cot_caption"] = bool(use_cot_caption)
        if use_cot_language is not None:
            body["use_cot_language"] = bool(use_cot_language)
        if audio_cover_strength is not None:
            body["audio_cover_strength"] = float(audio_cover_strength)
        if repainting_start is not None:
            body["repainting_start"] = float(repainting_start)
        if repainting_end is not None:
            body["repainting_end"] = float(repainting_end)

        # kwargs 透传（排除 poll_interval_s, max_wait_s 等内部参数）
        for k, v in kwargs.items():
            if v is not None and k not in ("poll_interval_s", "max_wait_s"):
                body[k] = v

        return body

    def _request_json(
        self, method: str, url: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make HTTP request and return JSON response."""
        data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _DEFAULT_USER_AGENT,
        }

        req = urllib.request.Request(url=url, method=method, data=data_bytes, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            if int(getattr(e, "code", 0) or 0) == 403 and "error code: 1010" in text.lower():
                raise RuntimeError(
                    "ACE-Step API HTTP 403 (Cloudflare error code: 1010). "
                    "Check that ACESTEP_BASE_URL is set to 'https://api.acemusic.ai' (API domain), "
                    "not 'https://acemusic.ai' (website domain)."
                ) from e
            if int(getattr(e, "code", 0) or 0) == 504:
                raise RuntimeError(
                    "ACE-Step API 超时 (HTTP 504 Gateway Timeout)。"
                    "服务器处理时间过长，通常是因为开启了「思考模式」或生成长音频。"
                    "建议：缩短时长、关闭思考模式、或稍后重试。"
                ) from e
            try:
                data = json.loads(text)
                error_msg = data.get("error", {}).get("message") or data.get("error") or text
                raise RuntimeError(f"ACE-Step API HTTP {e.code}: {error_msg}") from e
            except json.JSONDecodeError:
                raise RuntimeError(f"ACE-Step API HTTP {e.code}: {text}") from e

    def generate(
        self,
        *,
        prompt: str,
        lyrics: str | None = None,
        model: str = "acemusic/acestep-v1.5-turbo",
        audio_duration: float | None = None,
        audio_format: str = "mp3",
        bpm: int | None = None,
        key_scale: str | None = None,
        time_signature: str | None = None,
        vocal_language: str | None = None,
        instrumental: bool = False,
        thinking: bool = False,
        use_format: bool = False,
        batch_size: int = 1,
        inference_steps: int | None = None,
        guidance_scale: float | None = None,
        seed: int | None = None,
        shift: float | None = None,
        infer_method: str | None = None,
        timesteps: str | None = None,
        task_type=None,
        sample_mode: bool = False,
        temperature=None,
        top_p=None,
        use_cot_caption=None,
        use_cot_language=None,
        audio_cover_strength=None,
        repainting_start=None,
        repainting_end=None,
        src_audio_b64=None,
        src_audio_format=None,
        reference_audio_b64=None,
        reference_audio_format=None,
        **kwargs: Any,
    ) -> ACEStepStdlibResult:
        """Generate music using ACE-Step 1.5 model (OpenAI-compatible API).

        Args:
            prompt: 音乐描述
            lyrics: 歌词文本 (支持50+语言)
            model: 模型名称
            audio_duration: 时长(秒)
            audio_format: 输出格式 (mp3, wav, flac)
            bpm: 节拍速度 (30-300, None=auto)
            key_scale: 调性 (e.g. "C Major", "Am")
            time_signature: 拍号 (e.g. "4/4")
            vocal_language: 歌词语言 (en, zh, ja, ko, auto)
            instrumental: 纯音乐模式（无人声）
            thinking: 使用 5Hz LM 增强质量
            use_format: 让 LM 优化描述和歌词
            batch_size: 同时生成多个候选 (1-4)
            inference_steps: 推理步数 (Turbo 1-20, Base 1-200)
            guidance_scale: Prompt 引导系数 (仅 base 模型)
            seed: 固定种子 (可复现结果)
            shift: 时间步偏移因子 1.0-5.0 (仅 base 模型)
            infer_method: 推理方法 "ode" 或 "sde"
            timesteps: 自定义时间步 (逗号分隔)
            task_type: 任务类型 (text2music, cover, repaint, lego, extract, complete)
            sample_mode: 采样模式
            temperature: 采样温度
            top_p: Top-p 采样
            use_cot_caption: 使用思维链标题
            use_cot_language: 使用思维链语言
            audio_cover_strength: 音频覆盖强度
            repainting_start: 重绘开始时间
            repainting_end: 重绘结束时间
            src_audio_b64: 源音频 base64
            src_audio_format: 源音频格式
            reference_audio_b64: 参考音频 base64
            reference_audio_format: 参考音频格式

        Returns:
            ACEStepStdlibResult with audio_bytes
        """
        url = f"{self._base}/v1/chat/completions"

        body = self._build_request_body(
            prompt=prompt,
            lyrics=lyrics,
            model=model,
            audio_duration=audio_duration,
            audio_format=audio_format,
            bpm=bpm,
            key_scale=key_scale,
            time_signature=time_signature,
            vocal_language=vocal_language,
            instrumental=instrumental,
            thinking=thinking,
            use_format=use_format,
            batch_size=batch_size,
            inference_steps=inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            shift=shift,
            infer_method=infer_method,
            timesteps=timesteps,
            task_type=task_type,
            sample_mode=sample_mode,
            temperature=temperature,
            top_p=top_p,
            use_cot_caption=use_cot_caption,
            use_cot_language=use_cot_language,
            audio_cover_strength=audio_cover_strength,
            repainting_start=repainting_start,
            repainting_end=repainting_end,
            src_audio_b64=src_audio_b64,
            src_audio_format=src_audio_format,
            reference_audio_b64=reference_audio_b64,
            reference_audio_format=reference_audio_format,
            **kwargs,
        )

        data = self._request_json("POST", url, body)

        # Parse the OpenAI-style response
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"ACE-Step API returned no choices: {data}")

        message = choices[0].get("message", {})
        audio_list = message.get("audio", [])

        if not audio_list:
            raise RuntimeError(f"ACE-Step API returned no audio: {data}")

        # 解析第一个音频块（data URL 格式: data:audio/mpeg;base64,...）
        first_audio = audio_list[0]
        audio_data_url = first_audio.get("audio_url", {}).get("url", "")
        if not audio_data_url:
            raise RuntimeError(f"ACE-Step API returned no audio URL: {first_audio}")
        if not audio_data_url.startswith("data:"):
            raise RuntimeError(f"ACE-Step returned non-data URL: {audio_data_url[:50]}...")
        _, b64_part = audio_data_url.split(",", 1)
        audio_bytes = base64.b64decode(b64_part)

        # 提取额外音频（如果有，如批量生成）
        extra_audios: list[bytes] | None = None
        if len(audio_list) > 1:
            extra_audios = []
            for audio_item in audio_list[1:]:
                data_url = audio_item.get("audio_url", {}).get("url", "")
                if data_url and "," in data_url:
                    _, b64 = data_url.split(",", 1)
                    extra_audios.append(base64.b64decode(b64))
                elif data_url:
                    extra_audios.append(base64.b64decode(data_url))

        # 任务 ID
        task_id = data.get("id", "acestep-sync")

        # metadata
        metadata = {
            "model": data.get("model", model),
            "usage": data.get("usage", {}),
            "finish_reason": choices[0].get("finish_reason"),
        }

        return ACEStepStdlibResult(
            audio_bytes=audio_bytes,
            task_id=task_id,
            audio_url=None,
            metadata=metadata,
            extra_audios=extra_audios,
        )

    def generate_and_wait(
        self,
        *,
        prompt: str,
        lyrics: str | None = None,
        model: str = "acemusic/acestep-v1.5-turbo",
        audio_duration: float | None = None,
        audio_format: str = "mp3",
        bpm: int | None = None,
        key_scale: str | None = None,
        time_signature: str | None = None,
        vocal_language: str | None = None,
        instrumental: bool = False,
        thinking: bool = False,
        use_format: bool = False,
        batch_size: int = 1,
        inference_steps: int | None = None,
        guidance_scale: float | None = None,
        seed: int | None = None,
        shift: float | None = None,
        infer_method: str | None = None,
        timesteps: str | None = None,
        task_type=None,
        sample_mode: bool = False,
        temperature=None,
        top_p=None,
        use_cot_caption=None,
        use_cot_language=None,
        audio_cover_strength=None,
        repainting_start=None,
        repainting_end=None,
        src_audio_b64=None,
        src_audio_format=None,
        reference_audio_b64=None,
        reference_audio_format=None,
        **kwargs: Any,
    ) -> ACEStepStdlibResult:
        """Generate music and return result (synchronous API)."""
        return self.generate(
            prompt=prompt,
            lyrics=lyrics,
            model=model,
            audio_duration=audio_duration,
            audio_format=audio_format,
            bpm=bpm,
            key_scale=key_scale,
            time_signature=time_signature,
            vocal_language=vocal_language,
            instrumental=instrumental,
            thinking=thinking,
            use_format=use_format,
            batch_size=batch_size,
            inference_steps=inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            shift=shift,
            infer_method=infer_method,
            timesteps=timesteps,
            task_type=task_type,
            sample_mode=sample_mode,
            temperature=temperature,
            top_p=top_p,
            use_cot_caption=use_cot_caption,
            use_cot_language=use_cot_language,
            audio_cover_strength=audio_cover_strength,
            repainting_start=repainting_start,
            repainting_end=repainting_end,
            src_audio_b64=src_audio_b64,
            src_audio_format=src_audio_format,
            reference_audio_b64=reference_audio_b64,
            reference_audio_format=reference_audio_format,
            **kwargs,
        )

    def download_audio(self, audio_url: str) -> bytes:
        """Download audio from URL (not used for OpenAI-compatible API)."""
        with urllib.request.urlopen(audio_url, timeout=self._timeout) as resp:
            return resp.read()

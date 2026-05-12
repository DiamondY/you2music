"""ACE-Step 1.5 music provider (OpenAI/OpenRouter-compatible).

Upstream endpoint (acemusic.ai cloud):
- POST /v1/chat/completions
- Supports audio_config, lyrics, multimodal input_audio, task_type, and stream:true (SSE).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

VALID_TASK_TYPES = {"text2music", "cover", "repaint", "lego", "extract", "complete"}


@dataclass(frozen=True)
class ACEStepResult:
    """ACE-Step generation result."""

    audio_bytes: bytes
    task_id: str
    audio_url: str | None = None
    metadata: dict[str, Any] | None = None
    extra_audios: list[bytes] | None = None


@dataclass(frozen=True)
class ACEStepStreamEvent:
    """ACE-Step streaming event (derived from SSE chunks)."""

    event_type: str
    content: str | None = None
    audio_bytes: bytes | None = None
    finish_reason: str | None = None
    raw: dict | None = None


class ACEStepClient:
    """ACE-Step 1.5 API client (async/httpx)."""

    MODEL_MAP = {
        "acestep-v15-turbo": "acemusic/acestep-v1.5-turbo",
        "acestep-v15-xl-turbo": "acemusic/acestep-v1.5-xl-turbo",
        "ACE-Step V1.5 Turbo": "acemusic/acestep-v1.5-turbo",
        "ACE-Step V1.5 XL Turbo": "acemusic/acestep-v1.5-xl-turbo",
    }

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_s: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not str(api_key or "").strip():
            raise ValueError("ACESTEP_API_KEY is required for acestep provider.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = float(timeout_s)
        self._shared_client = http_client

    def _get_model_id(self, model: str) -> str:
        """将友好模型名称映射到 API 模型 ID"""
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
        **kwargs,
    ) -> dict[str, Any]:
        """
        构建请求体字典，供 generate 和 generate_stream 共用
        :return: OpenAI Chat Completions 格式的请求体
        """
        model_id = self._get_model_id(model)

        # 构建消息内容
        text_content = f"{prompt}\n\nLyrics:\n{lyrics}" if lyrics else prompt

        # Normalize + validate task type early so we can enforce audio rules.
        effective_task_type = task_type or "text2music"
        if effective_task_type not in VALID_TASK_TYPES:
            raise ValueError(f"Invalid task_type '{effective_task_type}', must be one of {sorted(VALID_TASK_TYPES)}")

        # Audio input: validate against task_type contract.
        has_audio = bool(src_audio_b64 or reference_audio_b64)
        if effective_task_type == "text2music":
            # text2music: src_audio is not meaningful; only reference_audio is allowed.
            if src_audio_b64:
                raise ValueError("task_type=text2music does not accept src_audio; use reference_audio instead.")
        else:
            # Audio-edit tasks require src_audio.
            if not src_audio_b64:
                raise ValueError(f"task_type={effective_task_type} requires src_audio.")

        if has_audio:
            content_parts = [{"type": "text", "text": text_content}]

            # Routing per Openrouter_API_DOC:
            # - text2music: audio[0] => reference_audio
            # - cover/repaint/lego/extract/complete: audio[0] => src_audio, audio[1] => reference_audio (optional)
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
            # Be explicit if caller asked for task_type=text2music.
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

    async def generate(
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
        **kwargs,
    ) -> ACEStepResult:
        """发起非流式生成请求并解析返回的音频数据"""
        url = f"{self._base}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _DEFAULT_USER_AGENT,
        }

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

        if self._shared_client is not None:
            client = self._shared_client
        else:
            client = httpx.AsyncClient(timeout=self._timeout)

        try:
            resp = await client.post(url, headers=headers, json=body)
        finally:
            if self._shared_client is None:
                await client.aclose()

        self._check_response(resp)

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("ACE-Step API returned no choices")

        message = choices[0].get("message", {})
        audio_list = message.get("audio", [])

        if not audio_list:
            raise ValueError("ACE-Step API returned no audio")

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
        task_id = data.get("id", "")

        # metadata
        metadata = {
            "model": data.get("model", model),
            "usage": data.get("usage", {}),
            "finish_reason": choices[0].get("finish_reason"),
        }

        return ACEStepResult(
            audio_bytes=audio_bytes,
            task_id=task_id,
            audio_url=None,
            metadata=metadata,
            extra_audios=extra_audios,
        )

    async def generate_stream(
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
        **kwargs,
    ) -> AsyncIterator[ACEStepStreamEvent]:
        """
        流式生成，通过 SSE 逐块解析 delta 并 yield 事件
        :yields: ACEStepStreamEvent 事件对象
        """
        url = f"{self._base}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": _DEFAULT_USER_AGENT,
        }

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

        # 流式标志
        body["stream"] = True

        if self._shared_client is not None:
            client = self._shared_client
        else:
            client = httpx.AsyncClient(timeout=self._timeout)

        try:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                self._check_response(resp)

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue

                    # SSE data 行
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        delta = chunk.get("choices", [{}])[0].get("delta", {})

                        # init 事件：assistant 角色首次出现
                        if delta.get("role") == "assistant":
                            yield ACEStepStreamEvent(
                                event_type="init",
                                raw=chunk,
                            )

                        # content 事件
                        content = delta.get("content")
                        if content and content != ".":
                            yield ACEStepStreamEvent(
                                event_type="content",
                                content=content,
                                raw=chunk,
                            )

                        # heartbeat 事件：心跳占位符
                        if content == ".":
                            yield ACEStepStreamEvent(
                                event_type="heartbeat",
                                raw=chunk,
                            )

                        # audio 事件
                        audio_list = delta.get("audio")
                        if audio_list:
                            for audio_item in audio_list:
                                data_url = audio_item.get("audio_url", {}).get("url", "")
                                if not data_url:
                                    continue
                                if not data_url.startswith("data:"):
                                    continue
                                _, b64_part = data_url.split(",", 1)
                                audio_bytes = base64.b64decode(b64_part)

                                yield ACEStepStreamEvent(
                                    event_type="audio",
                                    audio_bytes=audio_bytes,
                                    raw=chunk,
                                )

                        # done event (finish_reason)
                        if chunk.get("choices") and chunk["choices"][0].get("finish_reason") is not None:
                            yield ACEStepStreamEvent(
                                event_type="done",
                                finish_reason=str(chunk["choices"][0].get("finish_reason") or ""),
                                raw=chunk,
                            )
        finally:
            if self._shared_client is None:
                await client.aclose()

    async def generate_and_wait(
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
        **kwargs,
    ) -> ACEStepResult:
        """
        同步生成接口，内部直接调用 generate
        （ACE-Step 后端已同步返回结果，无需额外轮询）
        """
        return await self.generate(
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

    async def download_audio(self, audio_url: str) -> bytes:
        """从音频 URL 下载音频数据"""
        if self._shared_client is not None:
            client = self._shared_client
        else:
            client = httpx.AsyncClient(timeout=self._timeout)

        try:
            resp = await client.get(audio_url)
            resp.raise_for_status()
            return resp.content
        finally:
            if self._shared_client is None:
                await client.aclose()

    def _check_response(self, resp: httpx.Response) -> None:
        """检查 HTTP 响应，检测 Cloudflare 1010、504 超时等错误"""
        if resp.status_code == 403:
            body = resp.text
            if "Cloudflare" in body and "1010" in body:
                raise RuntimeError(
                    "Cloudflare 1010 error: blocked by bot detection. "
                    "Check your API key or proxy settings."
                )
        if resp.status_code == 504:
            raise TimeoutError(
                f"Gateway timeout (504) from ACE-Step API: {resp.text}"
            )

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"ACE-Step API error {e.response.status_code}: {e.response.text}"
            ) from e

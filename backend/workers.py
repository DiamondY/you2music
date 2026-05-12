"""Job worker functions.

Extracted from main.py. Handles dequeuing jobs from provider queues,
applying rate limits, executing API calls with retry, and updating job status.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from concurrency import run_with_retry
from providers.minimax import MiniMaxMusicClient
from providers.acestep import ACEStepClient
from state import STATE

logger = logging.getLogger(__name__)

# Keep in sync with shared.build_prompt() vocals tags. We strip these when building
# ACE-Step prompt because ACE-Step has separate vocals/lyrics handling.
_VOCALS_TAG_WITH = "with vocals, singing (do not be instrumental-only)"
_VOCALS_TAG_INSTR = "instrumental only (no vocals)"


@asynccontextmanager
async def _log_api_call(
    job_id: str | None,
    provider: str,
    endpoint: str,
    request_body: str,
    api_key_hint: str | None,
) -> AsyncIterator[dict[str, Any]]:
    """Context manager that times an API call and records it to the log store.

    After the block completes (success or failure), caller should populate
    the returned dict with 'http_status', 'response_body', and 'error' if
    applicable.  The dict is then written to the db.
    """
    t0 = time.monotonic()
    info: dict[str, Any] = {
        "job_id": job_id,
        "provider": provider,
        "endpoint": endpoint,
        "request_body": request_body,
        "api_key_hint": api_key_hint,
        "http_status": None,
        "response_body": None,
        "error": None,
    }
    try:
        yield info
    finally:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        STATE.log_store.log(
            job_id=info["job_id"],
            provider=info["provider"],
            method="POST",
            endpoint=info["endpoint"],
            request_body=info["request_body"],
            response_body=info.get("response_body"),
            http_status=info.get("http_status"),
            elapsed_ms=elapsed_ms,
            api_key_hint=info.get("api_key_hint"),
            error=info.get("error"),
        )


def _extract_http_status(error_message: str) -> int | None:
    """Best-effort extract HTTP status code from an exception string.

    We intentionally keep this lightweight: providers may raise plain RuntimeError
    with text containing patterns like "HTTP 429", "HTTP 401", etc.
    """
    import re

    m = re.search(r"HTTP\s+(\d{3})", error_message)
    return int(m.group(1)) if m else None


async def _publish_job_status(
    *,
    user_id: int | None,
    job_id: str,
    status: str,
    provider: str | None = None,
    error: str | None = None,
) -> None:
    if user_id is None:
        return
    payload: dict[str, Any] = {"type": "job_updated", "job_id": job_id, "status": status}
    if provider:
        payload["provider"] = provider
    if error:
        payload["error"] = error
    await STATE.event_hub.publish(int(user_id), payload)


async def _job_worker_handler(job_id: str) -> None:
    """Worker handler: called by ProviderQueue workers for each job.

    Sets job status from 'queued' → 'running', acquires a rate-limit token,
    then executes the job with retry support. Includes queue timeout check:
    if a job waited too long (in queue + rate-limit wait), it is marked as failed.
    """
    rec = STATE.store.get(job_id)
    if not rec:
        return

    # If the job was cancelled while in queue, its status is no longer "queued"
    # — skip it entirely.
    if rec.status != "queued":
        return

    try:
        params = json.loads(rec.params_json)
    except Exception:
        params = {}

    provider_name = str(params.get("provider") or "minimax")

    execution_lock = STATE.provider_execution_locks.get(provider_name)
    if execution_lock is None:
        await _execute_queued_job(job_id=job_id, rec=rec, params=params)
        return

    async with execution_lock:
        latest = STATE.store.get(job_id)
        if not latest or latest.status != "queued":
            return
        await _execute_queued_job(job_id=job_id, rec=latest, params=params)


async def _execute_queued_job(*, job_id: str, rec: Any, params: dict[str, Any]) -> None:
    provider_name = str(params.get("provider") or "minimax")

    await _wait_provider_cooldown(provider_name)

    # Acquire rate-limit token before starting work
    bucket = STATE.rate_limiters.get(provider_name)
    if bucket:
        await bucket.acquire()

    # Check queue timeout: if the job waited too long (queue wait + rate-limit wait), fail it
    queue_timeout_sec = float(STATE.settings.concurrency_config.get("queue_timeout_sec", 300))
    if queue_timeout_sec > 0:
        elapsed_sec = (time.time() * 1000 - rec.created_at_ms) / 1000.0
        if elapsed_sec > queue_timeout_sec:
            STATE.store.set_status(
                job_id,
                status="failed",
                error=f"排队超时：等待了 {elapsed_sec:.0f} 秒，超过上限 {queue_timeout_sec:.0f} 秒",
            )
            await _publish_job_status(
                user_id=getattr(rec, "user_id", None),
                job_id=job_id,
                status="failed",
                provider=provider_name,
                error="排队超时",
            )
            logger.warning("Job %s queue timeout: waited %.0fs (limit %ds)", job_id, elapsed_sec, int(queue_timeout_sec))
            return

    # Set status to running only when a real provider execution slot is available.
    STATE.store.set_status(job_id, status="running")
    await _publish_job_status(
        user_id=getattr(rec, "user_id", None),
        job_id=job_id,
        status="running",
        provider=provider_name,
    )

    # Execute with retry
    retry_cfg = STATE.settings.concurrency_config.get("retry", {}) if isinstance(STATE.settings.concurrency_config.get("retry"), dict) else {}
    max_retries = int(retry_cfg.get("max_retries", 3))
    base_delay = float(retry_cfg.get("base_delay_sec", 2.0))
    retryable_statuses = retry_cfg.get("retryable_statuses", [429, 502, 503, 504])

    try:
        await run_with_retry(
            lambda: _run_job(job_id=job_id, prompt=rec.prompt, params=params),
            max_retries=max_retries,
            retryable_statuses=retryable_statuses,
            base_delay=base_delay,
            retry_logger=logging.getLogger(__name__),
        )
    except asyncio.CancelledError:
        # Shutdown: mark job as failed so it doesn't stay "running" forever.
        STATE.store.set_status(job_id, status="failed", error="cancelled")
        await _publish_job_status(
            user_id=getattr(rec, "user_id", None),
            job_id=job_id,
            status="failed",
            provider=provider_name,
            error="cancelled",
        )
        raise
    except Exception as e:
        # run_with_retry exhausted retries or non-retryable error
        STATE.store.set_status(job_id, status="failed", error=str(e))
        await _publish_job_status(
            user_id=getattr(rec, "user_id", None),
            job_id=job_id,
            status="failed",
            provider=provider_name,
            error=str(e),
        )
    finally:
        if _provider_cooldown_seconds(provider_name) > 0:
            STATE.provider_last_finished_at[provider_name] = time.monotonic()


def _provider_cooldown_seconds(provider_name: str) -> float:
    provider_cfg = STATE.settings.concurrency_config.get(provider_name)
    if not isinstance(provider_cfg, dict):
        return 0.0
    try:
        return max(0.0, float(provider_cfg.get("cooldown_sec") or 0.0))
    except (TypeError, ValueError):
        return 0.0


async def _wait_provider_cooldown(provider_name: str) -> None:
    cooldown_sec = _provider_cooldown_seconds(provider_name)
    if cooldown_sec <= 0:
        return
    last_finished_at = float(STATE.provider_last_finished_at.get(provider_name) or 0.0)
    if last_finished_at <= 0:
        return
    wait_sec = cooldown_sec - (time.monotonic() - last_finished_at)
    if wait_sec > 0:
        await asyncio.sleep(wait_sec)


async def _run_job(*, job_id: str, prompt: str, params: dict[str, Any]) -> None:
    """Execute a single music generation job. Called by _job_worker_handler via run_with_retry."""
    provider_name = str(params.get("provider") or "minimax")
    key_pool = STATE.key_pools.get(provider_name)
    api_key: str | None = None
    job_rec = STATE.store.get(job_id)
    owner_user_id = int(job_rec.user_id) if job_rec and job_rec.user_id is not None else None
    try:
        STATE.audio_dir.mkdir(parents=True, exist_ok=True)

        vocals = bool(params["vocals"])
        provider_params = params.get("provider_params") or {}

        # Acquire a key from the pool (or fall back to the single-key setting).
        if key_pool:
            api_key = await key_pool.acquire()
            key_hint = key_pool.last_hint
        else:
            api_key = STATE.settings.minimax_api_key if provider_name == "minimax" else STATE.settings.acestep_api_key
            key_hint = None

        out_bytes: bytes
        out_ext = "mp3"
        song_id: str | None = None

        if provider_name == "minimax":
            endpoint = "/v1/music_generation"
            shared_client = STATE.http_clients.get("minimax")
            client = MiniMaxMusicClient(
                api_key=api_key,
                base_url=STATE.settings.minimax_base_url,
                timeout_s=STATE.settings.request_timeout_s,
                http_client=shared_client,
            )
            model = str(provider_params.get("model") or "music-2.6")
            lyrics_raw = params.get("lyrics") or provider_params.get("lyrics")
            lyrics_text = str(lyrics_raw).strip() if lyrics_raw is not None else ""
            audio_format = str(provider_params.get("format") or "mp3")
            sample_rate = int(provider_params.get("sample_rate") or 44100)
            bitrate = int(provider_params.get("bitrate") or 256000)

            lyrics_optimizer_val = provider_params.get("lyrics_optimizer")
            lyrics_optimizer = (
                bool(lyrics_optimizer_val)
                if isinstance(lyrics_optimizer_val, bool)
                else (True if vocals and not lyrics_text else False)
            )
            is_instrumental = not vocals
            if is_instrumental:
                lyrics_to_send: str | None = None
                lyrics_optimizer = False
            elif lyrics_text:
                lyrics_to_send = lyrics_text
            else:
                lyrics_to_send = ""
                lyrics_optimizer = True

            req_body = json.dumps({
                "model": model,
                "prompt": prompt,
                "audio_setting": {
                    "sample_rate": sample_rate,
                    "bitrate": bitrate,
                    "format": audio_format,
                },
            }, ensure_ascii=False)
            async with _log_api_call(
                job_id=job_id,
                provider=provider_name,
                endpoint=endpoint,
                request_body=req_body,
                api_key_hint=key_hint,
            ) as log_info:
                try:
                    result = await client.generate(
                        prompt=prompt,
                        lyrics=lyrics_to_send,
                        model=model,
                        sample_rate=sample_rate,
                        bitrate=bitrate,
                        format=audio_format,
                        lyrics_optimizer=lyrics_optimizer,
                        is_instrumental=is_instrumental,
                    )
                    log_info["http_status"] = 200
                    log_info["response_body"] = json.dumps({
                        "audio_url": result.audio_url,
                        "task_id": result.task_id,
                    }, ensure_ascii=False) if result else None
                    if result.audio_bytes is not None:
                        out_bytes = result.audio_bytes
                    else:
                        if not result.audio_url:
                            raise RuntimeError("MiniMax response missing audio_url")
                        out_bytes = await client.download_audio(result.audio_url)
                    out_ext = audio_format
                except Exception as e:
                    log_info["http_status"] = _extract_http_status(str(e))
                    log_info["error"] = str(e)
                    raise

        elif provider_name == "acestep":
            endpoint = "/v1/chat/completions"
            shared_client = STATE.http_clients.get("acestep")
            client = ACEStepClient(
                api_key=api_key,
                base_url=STATE.settings.acestep_base_url,
                timeout_s=STATE.settings.request_timeout_s,
                http_client=shared_client,
            )
            model = str(provider_params.get("model") or "acemusic/acestep-v1.5-turbo")
            lyrics = params.get("lyrics") or provider_params.get("lyrics")
            audio_duration = provider_params.get("audio_duration")
            if audio_duration is None:
                audio_duration = float(params["duration_sec"])
            audio_format = str(provider_params.get("audio_format") or "mp3")
            instrumental = not vocals

            # Extract base_prompt (strip vocals tag and lyrics embedded by build_prompt)
            acestep_prompt = str(params.get("base_prompt") or prompt).split("\n\nLyrics:\n")[0]
            for _tag in (_VOCALS_TAG_WITH, _VOCALS_TAG_INSTR):
                acestep_prompt = acestep_prompt.replace("\n\n" + _tag, "").replace(_tag, "")
            acestep_prompt = acestep_prompt.strip()

            # Collect all ACE-Step params from provider_params
            acestep_kwargs: dict[str, Any] = {}
            for k in ("bpm", "key_scale", "time_signature", "vocal_language",
                       "thinking", "use_format", "inference_steps", "guidance_scale",
                       "shift", "infer_method", "timesteps", "task_type", "sample_mode",
                       "temperature", "top_p", "use_cot_caption", "use_cot_language",
                       "audio_cover_strength", "repainting_start", "repainting_end"):
                val = provider_params.get(k)
                if val is not None and val != "":
                    acestep_kwargs[k] = val

            # seed: prefer global params, fallback to provider_params
            seed_val = params.get("seed")
            if seed_val is None:
                seed_val = provider_params.get("seed")
            if seed_val is not None and seed_val != "":
                # allow seed=0, reject empty string
                acestep_kwargs["seed"] = int(seed_val)

            # Audio input: use upload_id references (never persist base64 blobs).
            def _load_upload_b64(*, user_id: int, upload_id: str, fmt: str) -> str:
                safe_id = str(upload_id or "").strip()
                if not safe_id:
                    raise RuntimeError("缺少上传的音频文件 (upload_id)")
                safe_fmt = (fmt or "mp3").strip().lower()
                if safe_fmt not in ("mp3", "wav", "flac"):
                    safe_fmt = "mp3"
                path = STATE.upload_dir / f"{user_id}-{safe_id}.{safe_fmt}"
                if not path.exists():
                    raise RuntimeError("上传的音频文件不存在或已过期，请重新上传")
                raw = path.read_bytes()
                return base64.b64encode(raw).decode("ascii")

            src_upload_id = provider_params.get("src_audio_upload_id")
            src_audio_format = str(provider_params.get("src_audio_format") or "mp3")
            ref_upload_id = provider_params.get("reference_audio_upload_id")
            reference_audio_format = str(provider_params.get("reference_audio_format") or "mp3")
            if src_upload_id:
                if owner_user_id is None:
                    raise RuntimeError("job missing owner user_id for audio upload")
                acestep_kwargs["src_audio_b64"] = _load_upload_b64(
                    user_id=owner_user_id,
                    upload_id=str(src_upload_id),
                    fmt=src_audio_format,
                )
                acestep_kwargs["src_audio_format"] = src_audio_format
            if ref_upload_id:
                if owner_user_id is None:
                    raise RuntimeError("job missing owner user_id for audio upload")
                acestep_kwargs["reference_audio_b64"] = _load_upload_b64(
                    user_id=owner_user_id,
                    upload_id=str(ref_upload_id),
                    fmt=reference_audio_format,
                )
                acestep_kwargs["reference_audio_format"] = reference_audio_format

            # Build log body (audio_config + dual-write flat params)
            log_body: dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": acestep_prompt}],
            }
            if lyrics:
                log_body["lyrics"] = str(lyrics).strip()
            log_audio_config: dict[str, Any] = {}
            if audio_duration is not None:
                log_audio_config["duration"] = int(audio_duration)
            if audio_format:
                log_audio_config["format"] = audio_format
            if instrumental:
                log_audio_config["instrumental"] = True
            for k in ("bpm", "key_scale", "time_signature", "vocal_language"):
                val = acestep_kwargs.get(k)
                if val is not None:
                    log_audio_config[k] = val
            if log_audio_config:
                log_body["audio_config"] = log_audio_config
            # Dual-write flat params in log
            if audio_duration is not None:
                log_body["duration"] = int(audio_duration)
            if audio_format:
                log_body["audio_format"] = audio_format
            for k in ("bpm", "key_scale", "time_signature", "vocal_language",
                       "thinking", "use_format", "inference_steps", "guidance_scale",
                       "seed", "shift", "infer_method", "timesteps", "task_type",
                       "sample_mode", "temperature", "top_p", "use_cot_caption",
                       "use_cot_language", "audio_cover_strength", "repainting_start",
                       "repainting_end"):
                val = acestep_kwargs.get(k)
                if val is not None:
                    log_body[k] = val
            # Audio upload references (never log base64)
            if src_upload_id:
                log_body["src_audio_upload_id"] = str(src_upload_id)
                log_body["src_audio_format"] = src_audio_format
            if ref_upload_id:
                log_body["reference_audio_upload_id"] = str(ref_upload_id)
                log_body["reference_audio_format"] = reference_audio_format
            # Task type indicator in log
            task_type = acestep_kwargs.get("task_type", "text2music")
            if task_type != "text2music":
                log_body["task_type"] = task_type
            req_body = json.dumps(log_body, ensure_ascii=False)

            async with _log_api_call(
                job_id=job_id,
                provider=provider_name,
                endpoint=endpoint,
                request_body=req_body,
                api_key_hint=key_hint,
            ) as log_info:
                try:
                    _stream_task_id = "acestep-stream"
                    _stream_bytes: bytes | None = None
                    _stream_ex: Exception | None = None
                    _got_audio = False
                    last_emit = 0.0
                    last_content = ""
                    try:
                        async for evt in client.generate_stream(
                            prompt=acestep_prompt,
                            lyrics=str(lyrics).strip() if lyrics else None,
                            model=model,
                            audio_duration=audio_duration,
                            audio_format=audio_format,
                            instrumental=instrumental,
                            **acestep_kwargs,
                        ):
                            if evt.event_type == "content" and evt.content:
                                # Publish progress (throttled) to frontend via event hub.
                                if owner_user_id is not None:
                                    now = time.monotonic()
                                    last_content = evt.content
                                    if (now - last_emit) >= 0.25:
                                        last_emit = now
                                        await STATE.event_hub.publish(
                                            owner_user_id,
                                            {
                                                "type": "job_progress",
                                                "job_id": job_id,
                                                "provider": "acestep",
                                                "content": last_content,
                                            },
                                        )
                            elif evt.event_type == "audio" and evt.audio_bytes:
                                _stream_bytes = evt.audio_bytes
                                _got_audio = True
                            elif evt.event_type == "done":
                                if evt.finish_reason:
                                    _stream_task_id = f"acestep-{evt.finish_reason}"
                    except Exception as stream_ex:
                        _stream_ex = stream_ex
                        logger.warning("ACE-Step stream failed, falling back to non-stream: %s", stream_ex)
                    finally:
                        if owner_user_id is not None and last_content:
                            try:
                                await STATE.event_hub.publish(
                                    owner_user_id,
                                    {
                                        "type": "job_progress",
                                        "job_id": job_id,
                                        "provider": "acestep",
                                        "content": last_content,
                                    },
                                )
                            except Exception:
                                pass

                    # Fallback to non-streaming if streaming produced no audio
                    if not _got_audio:
                        result = await client.generate(
                            prompt=acestep_prompt,
                            lyrics=str(lyrics).strip() if lyrics else None,
                            model=model,
                            audio_duration=audio_duration,
                            audio_format=audio_format,
                            instrumental=instrumental,
                            **acestep_kwargs,
                        )
                        _stream_bytes = result.audio_bytes
                        _stream_task_id = result.task_id

                    if _stream_ex and not _stream_bytes:
                        raise _stream_ex

                    log_info["http_status"] = 200
                    log_info["response_body"] = json.dumps({
                        "task_id": _stream_task_id,
                    }, ensure_ascii=False)
                    out_bytes = _stream_bytes
                    out_ext = audio_format
                except Exception as e:
                    log_info["http_status"] = _extract_http_status(str(e))
                    log_info["error"] = str(e)
                    raise
        else:
            raise RuntimeError(f"unknown provider: {provider_name}")

        out_path = STATE.audio_dir / f"{job_id}.{out_ext}"
        out_path.write_bytes(out_bytes)
        STATE.store.set_status(job_id, status="succeeded", output_path=str(out_path), song_id=song_id)
        rec = STATE.store.get(job_id)
        await _publish_job_status(
            user_id=(rec.user_id if rec else None),
            job_id=job_id,
            status="succeeded",
            provider=str(params.get("provider") or "minimax"),
        )
        # Report success to key pool so health tracking resets.
        if key_pool and api_key:
            key_pool.report_result(api_key, success=True)
    except asyncio.CancelledError:
        # Shutdown/dev stop: treat as a controlled failure to avoid leaving jobs "running".
        STATE.store.set_status(job_id, status="failed", error="cancelled")
        rec = STATE.store.get(job_id)
        await _publish_job_status(
            user_id=(rec.user_id if rec else None),
            job_id=job_id,
            status="failed",
            provider=provider_name,
            error="cancelled",
        )
        if key_pool and api_key:
            key_pool.report_result(api_key, success=False)
        raise
    except Exception as e:
        # Ensure failures are reported to key pool as well. This is essential for:
        # - 429 rate-limit cooldown
        # - 401/403 disabling a bad key
        if key_pool and api_key:
            http_status = _extract_http_status(str(e))
            key_pool.report_result(api_key, success=False, http_status=http_status)
        raise

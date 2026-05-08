"""Job worker functions.

Extracted from main.py. Handles dequeuing jobs from provider queues,
applying rate limits, executing API calls with retry, and updating job status.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from concurrency import run_with_retry
from providers.minimax import MiniMaxMusicClient
from providers.acestep import ACEStepClient
from state import STATE

logger = logging.getLogger(__name__)


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
    try:
        STATE.audio_dir.mkdir(parents=True, exist_ok=True)

        provider_name = str(params.get("provider") or "minimax")
        duration_ms = int(params["duration_sec"]) * 1000
        vocals = bool(params["vocals"])
        provider_params = params.get("provider_params") or {}

        out_bytes: bytes
        out_ext = "mp3"
        song_id: str | None = None

        if provider_name == "minimax":
            # MiniMax official API (music-2.6)
            # Use shared httpx client for connection pooling
            shared_client = STATE.http_clients.get("minimax")
            client = MiniMaxMusicClient(
                api_key=STATE.settings.minimax_api_key,
                base_url=STATE.settings.minimax_base_url,
                timeout_s=STATE.settings.request_timeout_s,
                http_client=shared_client,
            )
            model = str(provider_params.get("model") or "music-2.6")
            lyrics_raw = params.get("lyrics") or provider_params.get("lyrics")
            lyrics_text = str(lyrics_raw).strip() if lyrics_raw is not None else ""
            sample_rate = int(provider_params.get("sample_rate") or 44100)
            bitrate = int(provider_params.get("bitrate") or 256000)
            audio_format = str(provider_params.get("format") or "mp3")

            # MiniMax requires lyrics unless:
            # - is_instrumental=true, or
            # - lyrics_optimizer=true with empty lyrics (auto-generate lyrics)
            lyrics_optimizer_val = provider_params.get("lyrics_optimizer")
            lyrics_optimizer = (
                bool(lyrics_optimizer_val)
                if isinstance(lyrics_optimizer_val, bool)
                else (True if vocals and not lyrics_text else False)
            )
            is_instrumental = not vocals
            lyrics_to_send: str | None
            if is_instrumental:
                lyrics_to_send = None
                lyrics_optimizer = False
            elif lyrics_text:
                lyrics_to_send = lyrics_text
            else:
                lyrics_to_send = ""
                lyrics_optimizer = True

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
            if result.audio_bytes is not None:
                out_bytes = result.audio_bytes
            else:
                if not result.audio_url:
                    raise RuntimeError("MiniMax response missing audio_url")
                out_bytes = await client.download_audio(result.audio_url)
            out_ext = audio_format
        elif provider_name == "acestep":
            # ACE-Step 1.5 via acemusic.ai (OpenAI-compatible API)
            # Use shared httpx client for connection pooling
            shared_client = STATE.http_clients.get("acestep")
            client = ACEStepClient(
                api_key=STATE.settings.acestep_api_key,
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

            result = await client.generate(
                prompt=prompt,
                lyrics=str(lyrics).strip() if lyrics else None,
                model=model,
                audio_duration=audio_duration,
                audio_format=audio_format,
            )

            out_bytes = result.audio_bytes
            out_ext = audio_format
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
    except asyncio.CancelledError:
        # Shutdown/dev stop: treat as a controlled failure to avoid leaving jobs "running".
        STATE.store.set_status(job_id, status="failed", error="cancelled")
        rec = STATE.store.get(job_id)
        await _publish_job_status(
            user_id=(rec.user_id if rec else None),
            job_id=job_id,
            status="failed",
            provider=str(params.get("provider") or "minimax"),
            error="cancelled",
        )
        raise

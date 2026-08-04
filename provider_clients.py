#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request


@dataclass
class AttemptResult:
    provider: str
    model: str
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    log_path: Path
    timed_out: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def extract_retry_after_seconds(text: str) -> int | None:
    match = re.search(r"please retry in\s+([0-9]+(?:\.[0-9]+)?)s", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(float(match.group(1)))
    except ValueError:
        return None


def is_hard_quota_exhausted_message(text: str) -> bool:
    lowered = text.lower()
    return (
        "terminalquotaerror" in lowered
        or "daily quota" in lowered
        or "limit: 0" in lowered
        or "generate_content_free_tier_input_token_count, limit: 0" in lowered
        or "generate_content_free_tier_requests, limit: 0" in lowered
    )


def _write_attempt_log(log_path: Path, lines: list[str]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(lines), encoding="utf-8")


def run_gemini_attempt(
    *,
    model_name: str,
    prompt_text: str,
    env: dict[str, str],
    timeout_seconds: int,
    heartbeat_seconds: int,
    attempt_index: int,
    debug_log_dir: Path,
    log_prefix: str = "attempt",
    max_429_lines_before_fallback: int = 0,
    rate_limit_grace_seconds: int = 0,
    max_retry_after_seconds_before_fallback: int = 0,
    emit_live_output: bool = True,
) -> AttemptResult:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = debug_log_dir / f"{log_prefix}-{attempt_index:02d}-{model_name}-{timestamp}.log"

    command = [
        "gemini",
        "--skip-trust",
        "--model",
        model_name,
        "--prompt",
        prompt_text,
    ]

    start = time.monotonic()

    if not shutil.which("gemini"):
        stderr_text = "'gemini' CLI not found on PATH."
        _write_attempt_log(
            log_path,
            [
                f"provider=gemini",
                f"model={model_name}",
                f"attempt={attempt_index}",
                "return_code=127",
                "elapsed_seconds=0.00",
                "timed_out=False",
                "aborted_for_rate_limit=False",
                "--- STDOUT ---",
                "",
                "--- STDERR ---",
                stderr_text,
            ],
        )
        return AttemptResult(
            provider="gemini",
            model=model_name,
            returncode=127,
            stdout="",
            stderr=stderr_text,
            elapsed_seconds=0.0,
            log_path=log_path,
        )

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=env,
        start_new_session=True,
    )

    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Failed to capture Gemini subprocess output pipes.")

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stream_lock = threading.Lock()
    stream_stats: dict[str, Any] = {
        "stdout_lines": 0,
        "stderr_lines": 0,
        "rate_limit_events": 0,
        "hard_quota_events": 0,
        "max_retry_after_seconds": None,
        "last_output_at": None,
    }

    def stream_reader(pipe, sink: list[str], sink_name: str, emit_stream, stat_key: str) -> None:
        try:
            for line in iter(pipe.readline, ""):
                with stream_lock:
                    sink.append(line)
                    stream_stats[stat_key] = int(stream_stats[stat_key]) + 1
                    lowered = line.lower()
                    if (
                        "status 429" in lowered
                        or "\"code\":429" in lowered
                        or "resource_exhausted" in lowered
                        or "quota exceeded" in lowered
                    ):
                        stream_stats["rate_limit_events"] = int(stream_stats["rate_limit_events"]) + 1
                    if is_hard_quota_exhausted_message(lowered):
                        stream_stats["hard_quota_events"] = int(stream_stats["hard_quota_events"]) + 1
                    retry_after = extract_retry_after_seconds(line)
                    if retry_after is not None:
                        previous = stream_stats["max_retry_after_seconds"]
                        if previous is None or retry_after > int(previous):
                            stream_stats["max_retry_after_seconds"] = retry_after
                    stream_stats["last_output_at"] = time.monotonic()

                if emit_live_output:
                    emit_stream.write(f"[{sink_name}] {line}")
                    emit_stream.flush()
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    stdout_thread = threading.Thread(
        target=stream_reader,
        args=(process.stdout, stdout_chunks, "gemini stdout", sys.stdout, "stdout_lines"),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=stream_reader,
        args=(process.stderr, stderr_chunks, "gemini stderr", sys.stderr, "stderr_lines"),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    aborted_for_rate_limit = False
    if emit_live_output:
        print(
            f"Attempt {attempt_index}: launched Gemini PID {process.pid} for model {model_name}",
            file=sys.stderr,
            flush=True,
        )

    while process.poll() is None:
        elapsed = time.monotonic() - start
        if elapsed >= timeout_seconds:
            timed_out = True
            if emit_live_output:
                print(
                    f"Attempt {attempt_index}: timeout reached ({timeout_seconds}s). Killing process group for PID {process.pid}.",
                    file=sys.stderr,
                    flush=True,
                )
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
            break

        wait_seconds = min(heartbeat_seconds, max(timeout_seconds - elapsed, 0))
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        elapsed = time.monotonic() - start
        with stream_lock:
            stdout_lines = int(stream_stats["stdout_lines"])
            stderr_lines = int(stream_stats["stderr_lines"])
            rate_limit_events = int(stream_stats["rate_limit_events"])
            hard_quota_events = int(stream_stats["hard_quota_events"])
            max_retry_after_seconds = stream_stats["max_retry_after_seconds"]
            last_output_at = stream_stats["last_output_at"]

        if last_output_at is None:
            activity = "no output yet"
        else:
            quiet_for = int(time.monotonic() - float(last_output_at))
            activity = f"last output {quiet_for}s ago"

        if emit_live_output:
            print(
                f"Attempt {attempt_index}: waiting on Gemini model {model_name} "
                f"({int(elapsed)}s elapsed, stdout lines: {stdout_lines}, stderr lines: {stderr_lines}, "
                f"rate-limit events: {rate_limit_events}, hard-quota events: {hard_quota_events}, {activity})...",
                file=sys.stderr,
                flush=True,
            )

        if (
            max_429_lines_before_fallback > 0
            and elapsed >= rate_limit_grace_seconds
            and rate_limit_events >= max_429_lines_before_fallback
            and stdout_lines == 0
            and process.poll() is None
        ):
            aborted_for_rate_limit = True
            if emit_live_output:
                print(
                    f"Attempt {attempt_index}: detected repeated rate-limit errors ({rate_limit_events}) "
                    f"with no stdout after {int(elapsed)}s. Aborting this model attempt to trigger fallback.",
                    file=sys.stderr,
                    flush=True,
                )
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
            break

        if (
            max_retry_after_seconds_before_fallback > 0
            and max_retry_after_seconds is not None
            and int(max_retry_after_seconds) > max_retry_after_seconds_before_fallback
            and stdout_lines == 0
            and process.poll() is None
        ):
            aborted_for_rate_limit = True
            if emit_live_output:
                print(
                    f"Attempt {attempt_index}: provider asked to retry in {int(max_retry_after_seconds)}s "
                    f"(threshold: {max_retry_after_seconds_before_fallback}s). Aborting this model attempt to trigger fallback.",
                    file=sys.stderr,
                    flush=True,
                )
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
            break

    return_code = process.wait()
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)

    stdout_text = "".join(stdout_chunks)
    stderr_text = "".join(stderr_chunks)
    if aborted_for_rate_limit:
        stderr_text = (
            f"{stderr_text}\n"
            "[provider-client] aborted attempt after repeated rate-limit/quota errors to allow fallback.\n"
        )

    elapsed = time.monotonic() - start
    if return_code is None:
        return_code = 1

    _write_attempt_log(
        log_path,
        [
            "provider=gemini",
            f"model={model_name}",
            f"attempt={attempt_index}",
            f"pid={process.pid}",
            f"command={' '.join(command[:4])} <prompt elided>",
            f"return_code={return_code}",
            f"elapsed_seconds={elapsed:.2f}",
            f"timed_out={timed_out}",
            f"aborted_for_rate_limit={aborted_for_rate_limit}",
            f"stdout_lines={stream_stats['stdout_lines']}",
            f"stderr_lines={stream_stats['stderr_lines']}",
            f"rate_limit_events={stream_stats['rate_limit_events']}",
            f"hard_quota_events={stream_stats['hard_quota_events']}",
            f"max_retry_after_seconds={stream_stats['max_retry_after_seconds']}",
            "--- STDOUT ---",
            stdout_text,
            "--- STDERR ---",
            stderr_text,
        ],
    )

    return AttemptResult(
        provider="gemini",
        model=model_name,
        returncode=return_code,
        stdout=stdout_text,
        stderr=stderr_text,
        elapsed_seconds=elapsed,
        log_path=log_path,
        timed_out=timed_out,
        metadata={
            "abortedForRateLimit": aborted_for_rate_limit,
            "rateLimitEvents": stream_stats["rate_limit_events"],
            "hardQuotaEvents": stream_stats["hard_quota_events"],
            "maxRetryAfterSeconds": stream_stats["max_retry_after_seconds"],
        },
    )


def _extract_hf_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()

    generated_text = payload.get("generated_text")
    if isinstance(generated_text, str) and generated_text.strip():
        return generated_text.strip()

    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        item_text = payload[0].get("generated_text")
        if isinstance(item_text, str) and item_text.strip():
            return item_text.strip()

    return ""


def _extract_hf_error_details(body_text: str) -> tuple[str, str]:
    message = ""
    guidance = ""
    parsed: dict[str, Any] | None = None

    try:
        decoded = json.loads(body_text) if body_text else {}
        if isinstance(decoded, dict):
            parsed = decoded
    except Exception:
        parsed = None

    if parsed:
        top_error = parsed.get("error")
        if isinstance(top_error, str):
            message = top_error
        elif isinstance(top_error, dict):
            nested = top_error.get("message")
            if isinstance(nested, str):
                message = nested
    if not message:
        message = (body_text or "").strip()[:1000]

    lowered = message.lower()
    if "depleted your monthly included credits" in lowered:
        guidance = (
            "Hugging Face router rejected the request due to depleted included credits. "
            "Purchase inference credits, upgrade plan, or switch provider/model."
        )
    elif "not a chat model" in lowered or "model_not_supported" in lowered:
        guidance = (
            "Selected model is not compatible with chat completions at this endpoint. "
            "Pick a chat-capable model for /v1/chat/completions."
        )

    return message, guidance


def _is_hf_retryable_http_status(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _is_hf_retryable_exception_message(message: str) -> bool:
    lowered = message.lower()
    return (
        "remote end closed connection without response" in lowered
        or "connection reset by peer" in lowered
        or "timed out" in lowered
        or "temporarily unavailable" in lowered
        or "service unavailable" in lowered
        or "connection aborted" in lowered
        or "connection refused" in lowered
    )


def run_huggingface_attempt(
    *,
    model_name: str,
    prompt_text: str,
    env: dict[str, str],
    timeout_seconds: int,
    heartbeat_seconds: int,
    attempt_index: int,
    debug_log_dir: Path,
    log_prefix: str = "attempt",
    emit_live_output: bool = True,
) -> AttemptResult:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = model_name.replace("/", "_")
    log_path = debug_log_dir / f"{log_prefix}-{attempt_index:02d}-{safe_model}-{timestamp}.log"

    token = (env.get("HF_API_TOKEN") or env.get("HUGGINGFACE_API_TOKEN") or "").strip()
    if not token:
        stderr_text = "Missing HF_API_TOKEN (or HUGGINGFACE_API_TOKEN) for Hugging Face provider."
        _write_attempt_log(
            log_path,
            [
                "provider=huggingface",
                f"model={model_name}",
                f"attempt={attempt_index}",
                "return_code=401",
                "elapsed_seconds=0.00",
                "timed_out=False",
                "--- STDOUT ---",
                "",
                "--- STDERR ---",
                stderr_text,
            ],
        )
        return AttemptResult(
            provider="huggingface",
            model=model_name,
            returncode=401,
            stdout="",
            stderr=stderr_text,
            elapsed_seconds=0.0,
            log_path=log_path,
        )

    api_url = (
        env.get("HUGGINGFACE_API_URL")
        or "https://router.huggingface.co/v1/chat/completions"
    ).strip()

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": 0.2,
    }
    payload_json = json.dumps(payload)
    payload_bytes = payload_json.encode("utf-8")
    prompt_chars = len(prompt_text)
    payload_size_bytes = len(payload_bytes)

    max_retries = max(0, int((env.get("HUGGINGFACE_MAX_RETRIES") or "2").strip() or "2"))
    initial_backoff_seconds = max(1, int((env.get("HUGGINGFACE_INITIAL_BACKOFF_SECONDS") or "2").strip() or "2"))

    timed_out = False
    stdout_text = ""
    stderr_text = ""
    return_code = 1
    total_start = time.monotonic()
    retry_count = 0
    final_exception_type = ""

    if emit_live_output:
        print(
            f"Attempt {attempt_index}: invoking Hugging Face model {model_name} via {api_url} "
            f"(prompt chars: {prompt_chars}, payload bytes: {payload_size_bytes})",
            file=sys.stderr,
            flush=True,
        )

    for inner_attempt in range(1, max_retries + 2):
        inner_result: dict[str, Any] = {
            "done": False,
            "status": 1,
            "stdout": "",
            "stderr": "",
            "retryable": False,
            "exceptionType": "",
            "traceback": "",
        }

        req = request.Request(
            api_url,
            data=payload_bytes,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        def do_request() -> None:
            try:
                with request.urlopen(req, timeout=timeout_seconds) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    parsed = json.loads(body)
                    text = _extract_hf_text(parsed)
                    if not text:
                        inner_result["status"] = 1
                        inner_result["stderr"] = (
                            "Hugging Face response did not include usable text. "
                            f"Raw body: {body[:1000]}"
                        )
                    else:
                        inner_result["status"] = 0
                        inner_result["stdout"] = text
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                status = int(exc.code or 1)
                inner_result["status"] = status
                inner_result["retryable"] = _is_hf_retryable_http_status(status)
                inner_result["exceptionType"] = type(exc).__name__
                message, guidance = _extract_hf_error_details(body)
                lines = [f"HTTP {status}: {message}"]
                if status == 401:
                    lines.append(
                        "Authentication failed. Verify HF_API_TOKEN/HUGGINGFACE_API_TOKEN is valid and has inference access.",
                    )
                elif status == 402 and not guidance:
                    lines.append(
                        "Payment/credit issue from Hugging Face inference router. Check plan/credits.",
                    )
                if guidance:
                    lines.append(f"Guidance: {guidance}")
                inner_result["stderr"] = "\n".join(lines).strip()
            except Exception as exc:
                message = str(exc)
                inner_result["status"] = 1
                inner_result["retryable"] = _is_hf_retryable_exception_message(message)
                inner_result["exceptionType"] = type(exc).__name__
                inner_result["traceback"] = traceback.format_exc(limit=4)
                inner_result["stderr"] = f"{type(exc).__name__}: {message}".strip()
            finally:
                inner_result["done"] = True

        inner_start = time.monotonic()
        thread = threading.Thread(target=do_request, daemon=True)
        thread.start()

        while thread.is_alive():
            elapsed_inner = time.monotonic() - inner_start
            if elapsed_inner >= timeout_seconds:
                timed_out = True
                break
            wait = min(heartbeat_seconds, max(timeout_seconds - elapsed_inner, 0))
            if wait > 0:
                thread.join(timeout=wait)
            if emit_live_output and thread.is_alive():
                print(
                    f"Attempt {attempt_index}.{inner_attempt}: waiting on Hugging Face model {model_name} "
                    f"({int(time.monotonic() - inner_start)}s elapsed)...",
                    file=sys.stderr,
                    flush=True,
                )

        if timed_out:
            break

        stdout_text = str(inner_result.get("stdout", ""))
        stderr_text = str(inner_result.get("stderr", ""))
        return_code = int(inner_result.get("status", 1))
        final_exception_type = str(inner_result.get("exceptionType", ""))

        if return_code == 0 and stdout_text.strip():
            break

        retryable = bool(inner_result.get("retryable", False))
        has_more_retries = inner_attempt <= max_retries
        if retryable and has_more_retries:
            retry_count += 1
            backoff = initial_backoff_seconds * (2 ** (inner_attempt - 1))
            if emit_live_output:
                print(
                    f"Attempt {attempt_index}.{inner_attempt}: transient Hugging Face failure; "
                    f"retrying in {backoff}s. Error: {stderr_text[:240]}",
                    file=sys.stderr,
                    flush=True,
                )
            time.sleep(backoff)
            continue

        break

    elapsed = time.monotonic() - total_start
    if timed_out:
        stderr_text = f"Timed out waiting for Hugging Face response after {timeout_seconds}s."
        _write_attempt_log(
            log_path,
            [
                "provider=huggingface",
                f"model={model_name}",
                f"attempt={attempt_index}",
                "return_code=124",
                f"elapsed_seconds={elapsed:.2f}",
                "timed_out=True",
                f"api_url={api_url}",
                f"prompt_chars={prompt_chars}",
                f"payload_bytes={payload_size_bytes}",
                f"retries_used={retry_count}",
                "--- STDOUT ---",
                "",
                "--- STDERR ---",
                stderr_text,
            ],
        )
        return AttemptResult(
            provider="huggingface",
            model=model_name,
            returncode=124,
            stdout="",
            stderr=stderr_text,
            elapsed_seconds=elapsed,
            log_path=log_path,
            timed_out=True,
        )

    _write_attempt_log(
        log_path,
        [
            "provider=huggingface",
            f"model={model_name}",
            f"attempt={attempt_index}",
            f"return_code={return_code}",
            f"elapsed_seconds={elapsed:.2f}",
            "timed_out=False",
            f"api_url={api_url}",
            f"prompt_chars={prompt_chars}",
            f"payload_bytes={payload_size_bytes}",
            f"retries_used={retry_count}",
            f"exception_type={final_exception_type or 'none'}",
            "--- STDOUT ---",
            stdout_text,
            "--- STDERR ---",
            stderr_text,
        ],
    )

    return AttemptResult(
        provider="huggingface",
        model=model_name,
        returncode=return_code,
        stdout=stdout_text,
        stderr=stderr_text,
        elapsed_seconds=elapsed,
        log_path=log_path,
        timed_out=False,
        metadata={
            "promptChars": prompt_chars,
            "payloadBytes": payload_size_bytes,
            "retriesUsed": retry_count,
            "exceptionType": final_exception_type,
        },
    )


def run_swiftlet_attempt(
    *,
    model_name: str,
    prompt_text: str,
    env: dict[str, str],
    timeout_seconds: int,
    heartbeat_seconds: int,
    attempt_index: int,
    debug_log_dir: Path,
    log_prefix: str = "attempt",
    emit_live_output: bool = True,
) -> AttemptResult:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = model_name.replace("/", "_")
    log_path = debug_log_dir / f"{log_prefix}-{attempt_index:02d}-{safe_model}-{timestamp}.log"

    api_url = (
        env.get("SWIFTLET_API_URL")
        or "http://127.0.0.1:8080/v1/chat/completions"
    ).strip()

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": 0.2,
    }
    payload_json = json.dumps(payload)
    payload_bytes = payload_json.encode("utf-8")
    prompt_chars = len(prompt_text)
    payload_size_bytes = len(payload_bytes)

    max_retries = max(0, int((env.get("SWIFTLET_MAX_RETRIES") or "2").strip() or "2"))
    initial_backoff_seconds = max(
        1,
        int((env.get("SWIFTLET_INITIAL_BACKOFF_SECONDS") or "2").strip() or "2"),
    )

    timed_out = False
    stdout_text = ""
    stderr_text = ""
    return_code = 1
    total_start = time.monotonic()
    retry_count = 0
    final_exception_type = ""

    if emit_live_output:
        print(
            f"Attempt {attempt_index}: invoking Swiftlet model {model_name} via {api_url} "
            f"(prompt chars: {prompt_chars}, payload bytes: {payload_size_bytes})",
            file=sys.stderr,
            flush=True,
        )

    for inner_attempt in range(1, max_retries + 2):
        inner_result: dict[str, Any] = {
            "done": False,
            "status": 1,
            "stdout": "",
            "stderr": "",
            "retryable": False,
            "exceptionType": "",
            "traceback": "",
        }

        req = request.Request(
            api_url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        def do_request() -> None:
            try:
                with request.urlopen(req, timeout=timeout_seconds) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    parsed = json.loads(body)
                    text = _extract_hf_text(parsed)
                    if not text:
                        inner_result["status"] = 1
                        inner_result["stderr"] = (
                            "Swiftlet response did not include usable text. "
                            f"Raw body: {body[:1000]}"
                        )
                    else:
                        inner_result["status"] = 0
                        inner_result["stdout"] = text
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                status = int(exc.code or 1)
                inner_result["status"] = status
                inner_result["exceptionType"] = type(exc).__name__
                message, _guidance = _extract_hf_error_details(body)
                lowered = message.lower()
                deterministic_model_error = "missingtensor(" in lowered or "missingfile(" in lowered
                inner_result["retryable"] = _is_hf_retryable_http_status(status) and not deterministic_model_error
                lines = [f"HTTP {status}: {message}"]
                if status == 404:
                    lines.append(
                        "Check SWIFTLET_API_URL path. Swiftlet expects /v1/chat/completions.",
                    )
                if deterministic_model_error:
                    lines.append(
                        "Swiftlet reported a model/container mismatch. Verify the --model path points to a valid Swiftlet .qpack container.",
                    )
                inner_result["stderr"] = "\n".join(lines).strip()
            except Exception as exc:
                message = str(exc)
                inner_result["status"] = 1
                inner_result["retryable"] = _is_hf_retryable_exception_message(message)
                inner_result["exceptionType"] = type(exc).__name__
                inner_result["traceback"] = traceback.format_exc(limit=4)
                lines = [f"{type(exc).__name__}: {message}".strip()]
                lowered = message.lower()
                if "connection refused" in lowered:
                    lines.append(
                        "Swiftlet server appears unavailable. Start it, for example: "
                        "cd /Volumes/SSD3/AI/Swiftlet && .build/release/swiftlet-server --model ./models/qwen3.6-35b.qpack --port 8080",
                    )
                inner_result["stderr"] = "\n".join(lines)
            finally:
                inner_result["done"] = True

        inner_start = time.monotonic()
        thread = threading.Thread(target=do_request, daemon=True)
        thread.start()

        while thread.is_alive():
            elapsed_inner = time.monotonic() - inner_start
            if elapsed_inner >= timeout_seconds:
                timed_out = True
                break
            wait = min(heartbeat_seconds, max(timeout_seconds - elapsed_inner, 0))
            if wait > 0:
                thread.join(timeout=wait)
            if emit_live_output and thread.is_alive():
                print(
                    f"Attempt {attempt_index}.{inner_attempt}: waiting on Swiftlet model {model_name} "
                    f"({int(time.monotonic() - inner_start)}s elapsed)...",
                    file=sys.stderr,
                    flush=True,
                )

        if timed_out:
            break

        stdout_text = str(inner_result.get("stdout", ""))
        stderr_text = str(inner_result.get("stderr", ""))
        return_code = int(inner_result.get("status", 1))
        final_exception_type = str(inner_result.get("exceptionType", ""))

        if return_code == 0 and stdout_text.strip():
            break

        retryable = bool(inner_result.get("retryable", False))
        has_more_retries = inner_attempt <= max_retries
        if retryable and has_more_retries:
            retry_count += 1
            backoff = initial_backoff_seconds * (2 ** (inner_attempt - 1))
            if emit_live_output:
                print(
                    f"Attempt {attempt_index}.{inner_attempt}: transient Swiftlet failure; "
                    f"retrying in {backoff}s. Error: {stderr_text[:240]}",
                    file=sys.stderr,
                    flush=True,
                )
            time.sleep(backoff)
            continue

        break

    elapsed = time.monotonic() - total_start
    if timed_out:
        stderr_text = f"Timed out waiting for Swiftlet response after {timeout_seconds}s."
        _write_attempt_log(
            log_path,
            [
                "provider=swiftlet",
                f"model={model_name}",
                f"attempt={attempt_index}",
                "return_code=124",
                f"elapsed_seconds={elapsed:.2f}",
                "timed_out=True",
                f"api_url={api_url}",
                f"prompt_chars={prompt_chars}",
                f"payload_bytes={payload_size_bytes}",
                f"retries_used={retry_count}",
                "--- STDOUT ---",
                "",
                "--- STDERR ---",
                stderr_text,
            ],
        )
        return AttemptResult(
            provider="swiftlet",
            model=model_name,
            returncode=124,
            stdout="",
            stderr=stderr_text,
            elapsed_seconds=elapsed,
            log_path=log_path,
            timed_out=True,
        )

    _write_attempt_log(
        log_path,
        [
            "provider=swiftlet",
            f"model={model_name}",
            f"attempt={attempt_index}",
            f"return_code={return_code}",
            f"elapsed_seconds={elapsed:.2f}",
            "timed_out=False",
            f"api_url={api_url}",
            f"prompt_chars={prompt_chars}",
            f"payload_bytes={payload_size_bytes}",
            f"retries_used={retry_count}",
            f"exception_type={final_exception_type or 'none'}",
            "--- STDOUT ---",
            stdout_text,
            "--- STDERR ---",
            stderr_text,
        ],
    )

    return AttemptResult(
        provider="swiftlet",
        model=model_name,
        returncode=return_code,
        stdout=stdout_text,
        stderr=stderr_text,
        elapsed_seconds=elapsed,
        log_path=log_path,
        timed_out=False,
        metadata={
            "promptChars": prompt_chars,
            "payloadBytes": payload_size_bytes,
            "retriesUsed": retry_count,
            "exceptionType": final_exception_type,
        },
    )


def _extract_openai_error_details(body_text: str) -> tuple[str, str]:
    message = ""
    guidance = ""
    parsed: dict[str, Any] | None = None

    try:
        decoded = json.loads(body_text) if body_text else {}
        if isinstance(decoded, dict):
            parsed = decoded
    except Exception:
        parsed = None

    if parsed:
        top_error = parsed.get("error")
        if isinstance(top_error, str):
            message = top_error
        elif isinstance(top_error, dict):
            nested = top_error.get("message")
            if isinstance(nested, str):
                message = nested
    if not message:
        message = (body_text or "").strip()[:1000]

    lowered = message.lower()
    if "incorrect api key" in lowered or "invalid_api_key" in lowered:
        guidance = "OpenAI API key appears invalid. Verify OPENAI_API_KEY."
    elif "rate limit" in lowered or "quota" in lowered or "insufficient_quota" in lowered:
        guidance = "OpenAI rate/credit limit reached. Check usage limits and billing, then retry."

    return message, guidance


def run_openai_attempt(
    *,
    model_name: str,
    prompt_text: str,
    env: dict[str, str],
    timeout_seconds: int,
    heartbeat_seconds: int,
    attempt_index: int,
    debug_log_dir: Path,
    log_prefix: str = "attempt",
    emit_live_output: bool = True,
) -> AttemptResult:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = model_name.replace("/", "_")
    log_path = debug_log_dir / f"{log_prefix}-{attempt_index:02d}-{safe_model}-{timestamp}.log"

    token = (env.get("OPENAI_API_KEY") or env.get("OPENAI_TOKEN") or "").strip()
    if not token:
        stderr_text = "Missing OPENAI_API_KEY (or OPENAI_TOKEN) for OpenAI provider."
        _write_attempt_log(
            log_path,
            [
                "provider=openai",
                f"model={model_name}",
                f"attempt={attempt_index}",
                "return_code=401",
                "elapsed_seconds=0.00",
                "timed_out=False",
                "--- STDOUT ---",
                "",
                "--- STDERR ---",
                stderr_text,
            ],
        )
        return AttemptResult(
            provider="openai",
            model=model_name,
            returncode=401,
            stdout="",
            stderr=stderr_text,
            elapsed_seconds=0.0,
            log_path=log_path,
        )

    api_url = (env.get("OPENAI_API_URL") or "https://api.openai.com/v1/chat/completions").strip()

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": 0.2,
    }
    payload_json = json.dumps(payload)
    payload_bytes = payload_json.encode("utf-8")
    prompt_chars = len(prompt_text)
    payload_size_bytes = len(payload_bytes)

    max_retries = max(0, int((env.get("OPENAI_MAX_RETRIES") or "2").strip() or "2"))
    initial_backoff_seconds = max(1, int((env.get("OPENAI_INITIAL_BACKOFF_SECONDS") or "2").strip() or "2"))

    timed_out = False
    stdout_text = ""
    stderr_text = ""
    return_code = 1
    total_start = time.monotonic()
    retry_count = 0
    final_exception_type = ""

    if emit_live_output:
        print(
            f"Attempt {attempt_index}: invoking OpenAI model {model_name} via {api_url} "
            f"(prompt chars: {prompt_chars}, payload bytes: {payload_size_bytes})",
            file=sys.stderr,
            flush=True,
        )

    for inner_attempt in range(1, max_retries + 2):
        inner_result: dict[str, Any] = {
            "done": False,
            "status": 1,
            "stdout": "",
            "stderr": "",
            "retryable": False,
            "exceptionType": "",
            "traceback": "",
        }

        req = request.Request(
            api_url,
            data=payload_bytes,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        def do_request() -> None:
            try:
                with request.urlopen(req, timeout=timeout_seconds) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    parsed = json.loads(body)
                    text = _extract_hf_text(parsed)
                    if not text:
                        inner_result["status"] = 1
                        inner_result["stderr"] = (
                            "OpenAI response did not include usable text. "
                            f"Raw body: {body[:1000]}"
                        )
                    else:
                        inner_result["status"] = 0
                        inner_result["stdout"] = text
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                status = int(exc.code or 1)
                inner_result["status"] = status
                inner_result["retryable"] = _is_hf_retryable_http_status(status)
                inner_result["exceptionType"] = type(exc).__name__
                message, guidance = _extract_openai_error_details(body)
                lines = [f"HTTP {status}: {message}"]
                if status == 401:
                    lines.append("Authentication failed. Verify OPENAI_API_KEY is valid.")
                if guidance:
                    lines.append(f"Guidance: {guidance}")
                inner_result["stderr"] = "\n".join(lines).strip()
            except Exception as exc:
                message = str(exc)
                inner_result["status"] = 1
                inner_result["retryable"] = _is_hf_retryable_exception_message(message)
                inner_result["exceptionType"] = type(exc).__name__
                inner_result["traceback"] = traceback.format_exc(limit=4)
                inner_result["stderr"] = f"{type(exc).__name__}: {message}".strip()
            finally:
                inner_result["done"] = True

        inner_start = time.monotonic()
        thread = threading.Thread(target=do_request, daemon=True)
        thread.start()

        while thread.is_alive():
            elapsed_inner = time.monotonic() - inner_start
            if elapsed_inner >= timeout_seconds:
                timed_out = True
                break
            wait = min(heartbeat_seconds, max(timeout_seconds - elapsed_inner, 0))
            if wait > 0:
                thread.join(timeout=wait)
            if emit_live_output and thread.is_alive():
                print(
                    f"Attempt {attempt_index}.{inner_attempt}: waiting on OpenAI model {model_name} "
                    f"({int(time.monotonic() - inner_start)}s elapsed)...",
                    file=sys.stderr,
                    flush=True,
                )

        if timed_out:
            break

        stdout_text = str(inner_result.get("stdout", ""))
        stderr_text = str(inner_result.get("stderr", ""))
        return_code = int(inner_result.get("status", 1))
        final_exception_type = str(inner_result.get("exceptionType", ""))

        if return_code == 0 and stdout_text.strip():
            break

        retryable = bool(inner_result.get("retryable", False))
        has_more_retries = inner_attempt <= max_retries
        if retryable and has_more_retries:
            retry_count += 1
            backoff = initial_backoff_seconds * (2 ** (inner_attempt - 1))
            if emit_live_output:
                print(
                    f"Attempt {attempt_index}.{inner_attempt}: transient OpenAI failure; "
                    f"retrying in {backoff}s. Error: {stderr_text[:240]}",
                    file=sys.stderr,
                    flush=True,
                )
            time.sleep(backoff)
            continue

        break

    elapsed = time.monotonic() - total_start
    if timed_out:
        stderr_text = f"Timed out waiting for OpenAI response after {timeout_seconds}s."
        _write_attempt_log(
            log_path,
            [
                "provider=openai",
                f"model={model_name}",
                f"attempt={attempt_index}",
                "return_code=124",
                f"elapsed_seconds={elapsed:.2f}",
                "timed_out=True",
                f"api_url={api_url}",
                f"prompt_chars={prompt_chars}",
                f"payload_bytes={payload_size_bytes}",
                f"retries_used={retry_count}",
                "--- STDOUT ---",
                "",
                "--- STDERR ---",
                stderr_text,
            ],
        )
        return AttemptResult(
            provider="openai",
            model=model_name,
            returncode=124,
            stdout="",
            stderr=stderr_text,
            elapsed_seconds=elapsed,
            log_path=log_path,
            timed_out=True,
        )

    _write_attempt_log(
        log_path,
        [
            "provider=openai",
            f"model={model_name}",
            f"attempt={attempt_index}",
            f"return_code={return_code}",
            f"elapsed_seconds={elapsed:.2f}",
            "timed_out=False",
            f"api_url={api_url}",
            f"prompt_chars={prompt_chars}",
            f"payload_bytes={payload_size_bytes}",
            f"retries_used={retry_count}",
            f"exception_type={final_exception_type or 'none'}",
            "--- STDOUT ---",
            stdout_text,
            "--- STDERR ---",
            stderr_text,
        ],
    )

    return AttemptResult(
        provider="openai",
        model=model_name,
        returncode=return_code,
        stdout=stdout_text,
        stderr=stderr_text,
        elapsed_seconds=elapsed,
        log_path=log_path,
        timed_out=False,
        metadata={
            "promptChars": prompt_chars,
            "payloadBytes": payload_size_bytes,
            "retriesUsed": retry_count,
            "exceptionType": final_exception_type,
        },
    )

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

    req = request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    result_box: dict[str, Any] = {"done": False, "status": 1, "stdout": "", "stderr": ""}

    def do_request() -> None:
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(body)
                text = _extract_hf_text(parsed)
                if not text:
                    result_box["status"] = 1
                    result_box["stderr"] = f"Hugging Face response did not include usable text. Raw body: {body[:1000]}"
                else:
                    result_box["status"] = 0
                    result_box["stdout"] = text
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            result_box["status"] = int(exc.code or 1)
            result_box["stderr"] = f"HTTP {exc.code}: {body}".strip()
        except Exception as exc:
            result_box["status"] = 1
            result_box["stderr"] = str(exc)
        finally:
            result_box["done"] = True

    start = time.monotonic()
    thread = threading.Thread(target=do_request, daemon=True)
    thread.start()

    timed_out = False
    if emit_live_output:
        print(
            f"Attempt {attempt_index}: invoking Hugging Face model {model_name} via {api_url}",
            file=sys.stderr,
            flush=True,
        )

    while thread.is_alive():
        elapsed = time.monotonic() - start
        if elapsed >= timeout_seconds:
            timed_out = True
            break
        wait = min(heartbeat_seconds, max(timeout_seconds - elapsed, 0))
        if wait > 0:
            thread.join(timeout=wait)
        if emit_live_output and thread.is_alive():
            print(
                f"Attempt {attempt_index}: waiting on Hugging Face model {model_name} ({int(time.monotonic() - start)}s elapsed)...",
                file=sys.stderr,
                flush=True,
            )

    elapsed = time.monotonic() - start
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

    stdout_text = str(result_box.get("stdout", ""))
    stderr_text = str(result_box.get("stderr", ""))
    return_code = int(result_box.get("status", 1))

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
    )

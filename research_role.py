#!/usr/bin/env python3
import argparse
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from provider_catalog import load_provider_catalog, provider_map
from provider_clients import (
    AttemptResult,
    run_gemini_attempt,
    run_huggingface_attempt,
    run_openai_attempt,
    run_swiftlet_attempt,
    run_vscodebridge_attempt,
)

CV_FILE = Path("CV.md")
JOBSPEC_FILE = Path("jobspec.txt")
PROMPT_FILE = Path("research_prompt.md")
PROMPT_DEFAULT_FILE = Path("research_prompt.default.md")
ENV_FILE = Path(".env")
URLS_FILE = Path("research_urls.txt")
COMPANY_FILE = Path("research_company.txt")
OUTPUT_MD = Path("research_output.md")
OUTPUT_JSON = Path("research_output.json")
OUTPUT_PROMPT = Path("research_prompt.built.txt")
DEBUG_LOG_DIR = Path("gemini_debug_logs")
RESEARCH_GEMINI_TIMEOUT_SECONDS = 300
RESEARCH_HEARTBEAT_SECONDS = 15
RESEARCH_MAX_429_LINES_BEFORE_FALLBACK = 3
RESEARCH_429_GRACE_SECONDS = 20
RESEARCH_MAX_RETRY_AFTER_SECONDS_BEFORE_FALLBACK = 10
RESEARCH_MAX_CONSECUTIVE_HARD_QUOTA_MODELS = 3
DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite-001",
    "gemini-2.0-flash-001",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]
DEFAULT_HUGGINGFACE_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
DEFAULT_HUGGINGFACE_FALLBACK_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "google/gemma-2-9b-it",
]
HUGGINGFACE_TIMEOUT_SECONDS = 180
OPENAI_TIMEOUT_SECONDS = 180
DEFAULT_SWIFTLET_MODEL = "qwen3_5_moe_text"
DEFAULT_SWIFTLET_FALLBACK_MODELS = []
SWIFTLET_TIMEOUT_SECONDS = 240
DEFAULT_VSCODE_BRIDGE_MODEL = "copilot-vscode"
DEFAULT_VSCODE_BRIDGE_FALLBACK_MODELS = []
VSCODE_BRIDGE_TIMEOUT_SECONDS = 240
DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_OPENAI_FALLBACK_MODELS = [
    "gpt-5.6-terra",
    "gpt-5.6-sol",
    "gpt-5.5",
    "gpt-4.1-mini",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_now_to_second() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_retryable_model_error(stderr_text: str) -> bool:
    lowered = stderr_text.lower()
    return (
        "429" in stderr_text
        or "quota exceeded" in lowered
        or "terminalquotaerror" in lowered
        or "rate limit" in lowered
        or "high demand" in lowered
        or "service unavailable" in lowered
        or "modelnotfounderror" in lowered
        or "model is not found" in lowered
        or "no longer available" in lowered
    )


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


def extract_full_report_path(stderr_text: str) -> str | None:
    match = re.search(r"full report available at:\s*(\S+)", stderr_text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def load_full_report_content(report_path: str) -> str | None:
    path = Path(report_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def print_attempt_summary(attempt_results: list[tuple[str, str]], stream) -> None:
    if not attempt_results:
        return
    print("Model attempt summary:", file=stream)
    for model_name, outcome in attempt_results:
        print(f"- {model_name}: {outcome}", file=stream)


def parse_positive_int(process_env: dict[str, str], key: str, default: int) -> int:
    raw = (process_env.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def run_gemini_with_diagnostics(
    command: list[str],
    env: dict[str, str],
    timeout_seconds: int,
    heartbeat_seconds: int,
    model_name: str,
    attempt_index: int,
    max_429_lines_before_fallback: int,
    rate_limit_grace_seconds: int,
    max_retry_after_seconds_before_fallback: int,
) -> tuple[subprocess.CompletedProcess[str], float, Path]:
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = DEBUG_LOG_DIR / f"research-attempt-{attempt_index:02d}-{model_name}-{timestamp}.log"

    start = time.monotonic()
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
    stream_stats = {
        "stdout_lines": 0,
        "stderr_lines": 0,
        "rate_limit_events": 0,
        "hard_quota_events": 0,
        "max_retry_after_seconds": None,
        "last_output_at": None,
    }

    def stream_reader(
        pipe,
        sink: list[str],
        sink_name: str,
        emit_stream,
        stat_key: str,
    ) -> None:
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

                # Relay raw subprocess output immediately so hangs/failures are visible in real time.
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
    print(
        f"Attempt {attempt_index}: launched Gemini PID {process.pid} for model {model_name}",
        file=sys.stderr,
        flush=True,
    )

    while process.poll() is None:
        elapsed = time.monotonic() - start
        if elapsed >= timeout_seconds:
            timed_out = True
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

        print(
            f"Attempt {attempt_index}: waiting on Gemini model {model_name} "
            f"({int(elapsed)}s elapsed, stdout lines: {stdout_lines}, stderr lines: {stderr_lines}, "
            f"rate-limit events: {rate_limit_events}, hard-quota events: {hard_quota_events}, {activity})...",
            file=sys.stderr,
            flush=True,
        )

        if (
            elapsed >= rate_limit_grace_seconds
            and rate_limit_events >= max_429_lines_before_fallback
            and stdout_lines == 0
            and process.poll() is None
        ):
            aborted_for_rate_limit = True
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
            max_retry_after_seconds is not None
            and int(max_retry_after_seconds) > max_retry_after_seconds_before_fallback
            and stdout_lines == 0
            and process.poll() is None
        ):
            aborted_for_rate_limit = True
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
            "[wrapper] aborted attempt after repeated 429/quota errors to allow model fallback.\n"
        )

    end_elapsed = time.monotonic() - start
    if return_code is None:
        return_code = 1

    log_path.write_text(
        "\n".join(
            [
                f"model={model_name}",
                f"attempt={attempt_index}",
                f"pid={process.pid}",
                f"command={' '.join(command[:4])} <prompt elided>",
                f"return_code={return_code}",
                f"elapsed_seconds={end_elapsed:.2f}",
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
            ]
        ),
        encoding="utf-8",
    )

    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout_seconds, output=stdout_text, stderr=stderr_text)

    completed = subprocess.CompletedProcess(
        args=command,
        returncode=return_code,
        stdout=stdout_text,
        stderr=stderr_text,
    )
    return completed, end_elapsed, log_path


def build_model_sequence(
    process_env: dict[str, str],
    provider: str,
    explicit_model: str | None = None,
) -> list[str]:
    explicit = (explicit_model or "").strip()
    if explicit:
        return [explicit]

    if provider == "huggingface":
        primary = process_env.get("HUGGINGFACE_MODEL", "").strip() or DEFAULT_HUGGINGFACE_MODEL
        fallback_raw = process_env.get("HUGGINGFACE_MODEL_FALLBACKS", "").strip()
        env_fallbacks = [item.strip() for item in fallback_raw.split(",") if item.strip()]
        defaults = DEFAULT_HUGGINGFACE_FALLBACK_MODELS
    elif provider == "openai":
        primary = process_env.get("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
        fallback_raw = process_env.get("OPENAI_MODEL_FALLBACKS", "").strip()
        env_fallbacks = [item.strip() for item in fallback_raw.split(",") if item.strip()]
        defaults = DEFAULT_OPENAI_FALLBACK_MODELS
    elif provider == "swiftlet":
        primary = process_env.get("SWIFTLET_MODEL", "").strip() or DEFAULT_SWIFTLET_MODEL
        fallback_raw = process_env.get("SWIFTLET_MODEL_FALLBACKS", "").strip()
        env_fallbacks = [item.strip() for item in fallback_raw.split(",") if item.strip()]
        defaults = DEFAULT_SWIFTLET_FALLBACK_MODELS
    elif provider == "vscodebridge":
        primary = process_env.get("VSCODE_BRIDGE_MODEL", "").strip() or DEFAULT_VSCODE_BRIDGE_MODEL
        fallback_raw = process_env.get("VSCODE_BRIDGE_MODEL_FALLBACKS", "").strip()
        env_fallbacks = [item.strip() for item in fallback_raw.split(",") if item.strip()]
        defaults = DEFAULT_VSCODE_BRIDGE_FALLBACK_MODELS
    else:
        primary = process_env.get("GEMINI_MODEL", "").strip()
        if not primary:
            primary = DEFAULT_MODEL
        fallback_raw = process_env.get("GEMINI_MODEL_FALLBACKS", "").strip()
        env_fallbacks = [item.strip() for item in fallback_raw.split(",") if item.strip()]
        defaults = DEFAULT_FALLBACK_MODELS

    ordered: list[str] = []
    for model in [primary, *env_fallbacks, *defaults]:
        if model and model not in ordered:
            ordered.append(model)

    return ordered


def load_dotenv_file(path: Path) -> dict[str, str]:
    env_vars: dict[str, str] = {}
    if not path.exists():
        return env_vars

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        env_vars[key] = value

    return env_vars


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered


def read_company_name(company_file: Path) -> str:
    if not company_file.exists():
        return ""
    return company_file.read_text(encoding="utf-8").strip()


def persist_inputs(company_file: Path, company_name: str, urls_file: Path, urls: list[str]) -> None:
    company_file.write_text(company_name.strip() + "\n", encoding="utf-8")
    if urls:
        urls_file.write_text("\n".join(urls) + "\n", encoding="utf-8")


def reset_prompt_file(prompt_default_path: Path, prompt_path: Path) -> None:
    if not prompt_default_path.exists():
        raise FileNotFoundError(f"Default prompt file not found: {prompt_default_path}")
    prompt_path.write_text(prompt_default_path.read_text(encoding="utf-8"), encoding="utf-8")


def read_urls(urls_file: Path, inline_urls: list[str]) -> list[str]:
    inline_clean = dedupe_keep_order(inline_urls)
    if inline_clean:
        # When URLs are provided explicitly (CLI/web request), treat that list as
        # authoritative to avoid accidental accumulation from persisted test URLs.
        return inline_clean

    file_urls: list[str] = []
    if urls_file.exists():
        for raw_line in urls_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            file_urls.append(line)
    return dedupe_keep_order(file_urls)


def format_urls_block(urls: list[str]) -> str:
    if not urls:
        return "(none provided)"
    return "\n".join(f"- {url}" for url in urls)


def build_prompt(
    prompt_template: str,
    company_name: str,
    cv_content: str,
    jobspec_content: str,
    urls: list[str],
) -> str:
    urls_block = format_urls_block(urls)
    if any(
        token in prompt_template
        for token in ["{company_name}", "{cv_content}", "{jobspec_content}", "{urls_block}"]
    ):
        return prompt_template.format(
            company_name=company_name,
            cv_content=cv_content,
            jobspec_content=jobspec_content,
            urls_block=urls_block,
        )

    return (
        f"{prompt_template.strip()}\n\n"
        f"=== COMPANY NAME ===\n{company_name}\n\n"
        f"=== URLS ===\n{urls_block}\n\n"
        f"=== JOB SPECIFICATION ===\n{jobspec_content}\n\n"
        f"=== CV ===\n{cv_content}\n"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Research a target company/role context and produce interview prep notes.",
    )
    parser.add_argument("--company-name", default="", help="Target company name")
    parser.add_argument(
        "--company-file",
        default=str(COMPANY_FILE),
        help="Path to persisted company name file",
    )
    parser.add_argument("--cv", default=str(CV_FILE), help="Path to CV file (default: CV.md)")
    parser.add_argument("--jobspec", default=str(JOBSPEC_FILE), help="Path to job spec file (default: jobspec.txt)")
    parser.add_argument("--prompt", default=str(PROMPT_FILE), help="Path to editable research prompt")
    parser.add_argument(
        "--prompt-default",
        default=str(PROMPT_DEFAULT_FILE),
        help="Path to immutable default research prompt",
    )
    parser.add_argument("--urls-file", default=str(URLS_FILE), help="Path to newline-delimited URL list")
    parser.add_argument("--url", action="append", default=[], help="Additional URL (repeatable)")
    parser.add_argument("--output-md", default=str(OUTPUT_MD), help="Markdown output path")
    parser.add_argument("--output-json", default=str(OUTPUT_JSON), help="JSON output path")
    parser.add_argument(
        "--provider",
        default="",
        help="Model provider override (gemini, huggingface, openai, swiftlet, or vscodebridge)",
    )
    parser.add_argument("--model", default="", help="Model name (optional override)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build prompt and save JSON envelope without calling Gemini",
    )
    parser.add_argument(
        "--reset-prompt",
        action="store_true",
        help="Reset editable prompt from immutable default prompt and exit",
    )
    parser.add_argument(
        "--no-persist-inputs",
        action="store_true",
        help="Do not persist company name and URL list to disk",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    cv_path = Path(args.cv)
    jobspec_path = Path(args.jobspec)
    prompt_path = Path(args.prompt)
    prompt_default_path = Path(args.prompt_default)
    urls_file = Path(args.urls_file)
    company_file = Path(args.company_file)
    output_md = Path(args.output_md)
    output_json = Path(args.output_json)

    if args.reset_prompt:
        try:
            reset_prompt_file(prompt_default_path, prompt_path)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        print(f"Reset prompt from {prompt_default_path} to {prompt_path}")
        return

    if not prompt_path.exists() and prompt_default_path.exists():
        reset_prompt_file(prompt_default_path, prompt_path)
        print(f"Prompt file missing; restored from default: {prompt_default_path}")

    missing = [str(path) for path in [cv_path, jobspec_path, prompt_path] if not path.exists()]
    if missing:
        print(f"Missing required file(s): {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    company_name = args.company_name.strip() or read_company_name(company_file)
    if not company_name:
        print("Company name is required. Provide --company-name or set company file.", file=sys.stderr)
        sys.exit(1)

    cv_content = cv_path.read_text(encoding="utf-8")
    jobspec_content = jobspec_path.read_text(encoding="utf-8")
    prompt_template = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt_template:
        print(f"Prompt file is empty: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    urls = read_urls(urls_file, args.url)
    if not args.no_persist_inputs and not args.dry_run:
        persist_inputs(company_file, company_name, urls_file, urls)

    print("Building research prompt...", flush=True)
    prompt_text = build_prompt(prompt_template, company_name, cv_content, jobspec_content, urls)
    OUTPUT_PROMPT.write_text(prompt_text, encoding="utf-8")
    print(
        f"Prepared prompt for '{company_name}' with {len(urls)} URL(s). Saved to: {OUTPUT_PROMPT.resolve()}",
        flush=True,
    )

    process_env = os.environ.copy()
    process_env.update(load_dotenv_file(ENV_FILE))
    process_env.setdefault("GEMINI_CLI_TRUST_WORKSPACE", "true")
    catalog = load_provider_catalog(Path("model_providers.json"))
    providers = provider_map(catalog)
    default_provider = str(catalog.get("defaultProvider") or "gemini").strip() or "gemini"
    selected_provider = (args.provider or process_env.get("MODEL_PROVIDER") or default_provider).strip().lower()
    if selected_provider not in providers:
        print(f"Unsupported provider: {selected_provider}", file=sys.stderr)
        sys.exit(1)

    timeout_seconds = parse_positive_int(
        process_env,
        "RESEARCH_GEMINI_TIMEOUT_SECONDS",
        RESEARCH_GEMINI_TIMEOUT_SECONDS,
    )
    heartbeat_seconds = parse_positive_int(
        process_env,
        "RESEARCH_GEMINI_HEARTBEAT_SECONDS",
        RESEARCH_HEARTBEAT_SECONDS,
    )
    max_429_lines_before_fallback = parse_positive_int(
        process_env,
        "RESEARCH_GEMINI_MAX_429_LINES_BEFORE_FALLBACK",
        RESEARCH_MAX_429_LINES_BEFORE_FALLBACK,
    )
    rate_limit_grace_seconds = parse_positive_int(
        process_env,
        "RESEARCH_GEMINI_429_GRACE_SECONDS",
        RESEARCH_429_GRACE_SECONDS,
    )
    max_retry_after_seconds_before_fallback = parse_positive_int(
        process_env,
        "RESEARCH_GEMINI_MAX_RETRY_AFTER_SECONDS_BEFORE_FALLBACK",
        RESEARCH_MAX_RETRY_AFTER_SECONDS_BEFORE_FALLBACK,
    )
    max_consecutive_hard_quota_models = parse_positive_int(
        process_env,
        "RESEARCH_GEMINI_MAX_CONSECUTIVE_HARD_QUOTA_MODELS",
        RESEARCH_MAX_CONSECUTIVE_HARD_QUOTA_MODELS,
    )
    model_sequence = build_model_sequence(process_env, selected_provider, explicit_model=args.model)

    envelope: dict[str, object] = {
        "companyName": company_name,
        "provider": selected_provider,
        "model": model_sequence[0] if model_sequence else DEFAULT_MODEL,
        "urls": urls,
        "generatedAt": utc_now_iso(),
        "dryRun": bool(args.dry_run),
        "output": "",
    }

    if args.dry_run:
        envelope["output"] = "[dry-run] prompt built successfully"
        envelope["promptPreview"] = prompt_text[:6000]
        envelope["modelAttempts"] = []
        output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        print(f"Dry run complete. JSON written to: {output_json.resolve()}")
        return

    if selected_provider == "gemini" and not shutil.which("gemini"):
        print("'gemini' CLI not found on PATH.", file=sys.stderr)
        sys.exit(1)
    if selected_provider == "huggingface":
        hf_token = (process_env.get("HF_API_TOKEN") or process_env.get("HUGGINGFACE_API_TOKEN") or "").strip()
        if not hf_token:
            print("HF_API_TOKEN (or HUGGINGFACE_API_TOKEN) is required for provider=huggingface.", file=sys.stderr)
            sys.exit(1)
    if selected_provider == "openai":
        openai_token = (process_env.get("OPENAI_API_KEY") or process_env.get("OPENAI_TOKEN") or "").strip()
        if not openai_token:
            print("OPENAI_API_KEY (or OPENAI_TOKEN) is required for provider=openai.", file=sys.stderr)
            sys.exit(1)

    print(
        f"Diagnostics enabled. Per-attempt logs at: {DEBUG_LOG_DIR.resolve()}",
        flush=True,
    )
    print(f"Selected provider: {selected_provider}", flush=True)
    print(
        f"Research Gemini timeout: {timeout_seconds}s (heartbeat every {heartbeat_seconds}s)",
        flush=True,
    )
    print(
        "Rate-limit fallback trigger: "
        f">= {max_429_lines_before_fallback} detected 429/quota lines after {rate_limit_grace_seconds}s",
        flush=True,
    )
    print(
        "Retry-after fallback trigger: "
        f"> {max_retry_after_seconds_before_fallback}s requested backoff with no stdout",
        flush=True,
    )
    print(
        "Hard quota circuit-breaker: "
        f"stop after {max_consecutive_hard_quota_models} consecutive hard quota models",
        flush=True,
    )

    model_attempts: list[dict[str, object]] = []
    proc: AttemptResult | None = None
    selected_model: str | None = None
    attempt_results: list[tuple[str, str]] = []
    consecutive_hard_quota_models = 0

    for idx, model_name in enumerate(model_sequence, start=1):
        print(
            f"Invoking {selected_provider} model ({idx}/{len(model_sequence)}): {model_name}",
            flush=True,
        )

        try:
            if selected_provider == "huggingface":
                proc = run_huggingface_attempt(
                    model_name=model_name,
                    prompt_text=prompt_text,
                    env=process_env,
                    timeout_seconds=HUGGINGFACE_TIMEOUT_SECONDS,
                    heartbeat_seconds=heartbeat_seconds,
                    attempt_index=idx,
                    debug_log_dir=DEBUG_LOG_DIR,
                    log_prefix="research-attempt",
                    emit_live_output=True,
                )
            elif selected_provider == "openai":
                proc = run_openai_attempt(
                    model_name=model_name,
                    prompt_text=prompt_text,
                    env=process_env,
                    timeout_seconds=OPENAI_TIMEOUT_SECONDS,
                    heartbeat_seconds=heartbeat_seconds,
                    attempt_index=idx,
                    debug_log_dir=DEBUG_LOG_DIR,
                    log_prefix="research-attempt",
                    emit_live_output=True,
                )
            elif selected_provider == "swiftlet":
                proc = run_swiftlet_attempt(
                    model_name=model_name,
                    prompt_text=prompt_text,
                    env=process_env,
                    timeout_seconds=SWIFTLET_TIMEOUT_SECONDS,
                    heartbeat_seconds=heartbeat_seconds,
                    attempt_index=idx,
                    debug_log_dir=DEBUG_LOG_DIR,
                    log_prefix="research-attempt",
                    emit_live_output=True,
                )
            elif selected_provider == "vscodebridge":
                proc = run_vscodebridge_attempt(
                    model_name=model_name,
                    prompt_text=prompt_text,
                    env=process_env,
                    timeout_seconds=VSCODE_BRIDGE_TIMEOUT_SECONDS,
                    heartbeat_seconds=heartbeat_seconds,
                    attempt_index=idx,
                    debug_log_dir=DEBUG_LOG_DIR,
                    log_prefix="research-attempt",
                    emit_live_output=True,
                )
            else:
                proc = run_gemini_attempt(
                    model_name=model_name,
                    prompt_text=prompt_text,
                    env=process_env,
                    timeout_seconds=timeout_seconds,
                    heartbeat_seconds=heartbeat_seconds,
                    attempt_index=idx,
                    debug_log_dir=DEBUG_LOG_DIR,
                    log_prefix="research-attempt",
                    max_429_lines_before_fallback=max_429_lines_before_fallback,
                    rate_limit_grace_seconds=rate_limit_grace_seconds,
                    max_retry_after_seconds_before_fallback=max_retry_after_seconds_before_fallback,
                    emit_live_output=True,
                )
            print(
                f"Attempt {idx} completed in {proc.elapsed_seconds:.1f}s. Debug log: {proc.log_path}",
                flush=True,
            )
        except Exception as exc:
            excerpt = str(exc)[:500]
            model_attempts.append(
                {
                    "model": model_name,
                    "exitCode": "timeout",
                    "retryable": True,
                }
            )
            attempt_results.append((model_name, f"provider exception: {exc}"))
            print(
                f"Attempt {idx} failed unexpectedly. Model: {model_name}",
                file=sys.stderr,
                flush=True,
            )
            if excerpt:
                print(f"Stderr excerpt: {excerpt}", file=sys.stderr)

            envelope["model"] = model_name
            envelope["modelAttempts"] = model_attempts
            envelope["output"] = ""
            envelope["stderr"] = "Model attempt failed unexpectedly. See per-attempt debug log."
            output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
            print_attempt_summary(attempt_results, sys.stderr)
            sys.exit(1)

        stderr_text = (proc.stderr or "").strip()
        stdout_text = (proc.stdout or "").strip()
        if is_hard_quota_exhausted_message(stderr_text):
            consecutive_hard_quota_models += 1
        else:
            consecutive_hard_quota_models = 0
        model_attempts.append(
            {
                "model": model_name,
                "exitCode": proc.returncode,
                "retryable": bool(proc.returncode != 0 and is_retryable_model_error(stderr_text)),
                "hardQuota": is_hard_quota_exhausted_message(stderr_text),
            }
        )

        if proc.returncode == 0:
            selected_model = model_name
            attempt_results.append((model_name, "success"))
            break

        if is_retryable_model_error(stderr_text) and idx < len(model_sequence):
            attempt_results.append((model_name, "retryable error"))
            print(
                f"Model {model_name} hit a transient/quota condition. Trying next fallback model...",
                file=sys.stderr,
                flush=True,
            )
            if consecutive_hard_quota_models >= max_consecutive_hard_quota_models:
                print(
                    "Detected consecutive hard quota failures across models. "
                    "Stopping early instead of trying additional models.",
                    file=sys.stderr,
                    flush=True,
                )
                envelope["model"] = model_name
                envelope["modelAttempts"] = model_attempts
                envelope["output"] = ""
                envelope["stderr"] = (
                    "Aborted remaining model attempts after consecutive hard quota failures. "
                    "Check billing/quota, then retry later."
                )
                output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
                print_attempt_summary(attempt_results, sys.stderr)
                sys.exit(1)
            continue

        attempt_results.append((model_name, "fatal error"))
        print("Gemini CLI call failed.", file=sys.stderr)
        if stderr_text:
            print(stderr_text, file=sys.stderr)
        report_path = extract_full_report_path(stderr_text)
        report_content = None
        if report_path:
            print(f"Gemini fatal report: {report_path}", file=sys.stderr)
            report_content = load_full_report_content(report_path)
            if report_content:
                print("--- Gemini fatal report content ---", file=sys.stderr)
                print(report_content, file=sys.stderr)
                print("--- End Gemini fatal report content ---", file=sys.stderr)
            else:
                print("Unable to read Gemini fatal report content.", file=sys.stderr)
        envelope["model"] = model_name
        envelope["modelAttempts"] = model_attempts
        envelope["output"] = stdout_text
        envelope["stderr"] = stderr_text
        if report_path:
            envelope["fatalReportPath"] = report_path
        if report_content:
            envelope["fatalReportContent"] = report_content
        output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        print_attempt_summary(attempt_results, sys.stderr)
        sys.exit(proc.returncode)

    if proc is None or proc.returncode != 0:
        print("Gemini API failed across all configured models due to load/quota limits.", file=sys.stderr)
        envelope["model"] = model_sequence[0] if model_sequence else DEFAULT_MODEL
        envelope["modelAttempts"] = model_attempts
        envelope["output"] = ""
        envelope["stderr"] = "All model attempts failed. See modelAttempts for details."
        output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        print_attempt_summary(attempt_results, sys.stderr)
        sys.exit(1)

    output_text = (proc.stdout or "").strip()
    if not output_text:
        print("Gemini returned empty output.", file=sys.stderr)
        envelope["model"] = selected_model or model_sequence[0]
        envelope["modelAttempts"] = model_attempts
        envelope["output"] = ""
        output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        sys.exit(1)

    print("Gemini completed. Writing research outputs...", flush=True)
    generated_at = local_now_to_second()
    stamped_output = f"Generated At: {generated_at}\n\n{output_text.strip()}\n"
    output_md.write_text(stamped_output, encoding="utf-8")
    envelope["model"] = selected_model or model_sequence[0]
    envelope["modelAttempts"] = model_attempts
    envelope["output"] = output_text
    envelope["generatedAt"] = generated_at
    output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")

    print(f"Research markdown written to: {output_md.resolve()}")
    print(f"Research metadata written to: {output_json.resolve()}")


if __name__ == "__main__":
    main()

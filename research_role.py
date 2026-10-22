#!/usr/bin/env python3
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend_registry import get_backend_or_raise
from provider_catalog import load_provider_catalog, provider_map
from settings_env import SettingsError, one_shot_env
from pipe_io import RequestError, optional_text, require_text, run_json_io
from provider_clients import AttemptResult, track_provider_process, untrack_provider_process

INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")

CV_FILE = INPUT_DIR / "CV.md"
JOBSPEC_FILE = INPUT_DIR / "jobspec.txt"
PROMPT_FILE = INPUT_DIR / "research_prompt.md"
PROMPT_DEFAULT_FILE = INPUT_DIR / "research_prompt.default.md"
URLS_FILE = INPUT_DIR / "research_urls.txt"
COMPANY_FILE = INPUT_DIR / "research_company.txt"
OUTPUT_MD = OUTPUT_DIR / "research_output.md"
OUTPUT_JSON = OUTPUT_DIR / "research_output.json"
OUTPUT_PROMPT = OUTPUT_DIR / "research_prompt.built.txt"
DEBUG_LOG_DIR = OUTPUT_DIR / "gemini_debug_logs"
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
DEFAULT_SWIFTLET_MODEL = "qwen3_5_moe_text"
DEFAULT_SWIFTLET_FALLBACK_MODELS = []
DEFAULT_VSCODE_BRIDGE_MODEL = "copilot-vscode"
DEFAULT_VSCODE_BRIDGE_FALLBACK_MODELS = []
DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_OPENAI_FALLBACK_MODELS = [
    "gpt-5.6-terra",
    "gpt-5.6-sol",
    "gpt-5.5",
    "gpt-4.1-mini",
]


def utc_now_iso() -> str:
    """Purpose: Execute utc now iso for this module's workflow.
    
    Inputs:
    - None.
    
    Returns:
    - `str` value representing the operation result.
    """
    return datetime.now(timezone.utc).isoformat()


def local_now_to_second() -> str:
    """Purpose: Execute local now to second for this module's workflow.
    
    Inputs:
    - None.
    
    Returns:
    - `str` value representing the operation result.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_retryable_model_error(stderr_text: str) -> bool:
    """Purpose: Evaluate whether retryable model error is true.
    
    Inputs:
    - stderr_text: Captured stderr text used for retry/failure classification.
    
    Returns:
    - `bool` value representing the operation result.
    """
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
    """Purpose: Execute extract retry after seconds for this module's workflow.
    
    Inputs:
    - text: Input text content being parsed, normalized, or inspected.
    
    Returns:
    - `int | None` value representing the operation result.
    """
    match = re.search(r"please retry in\s+([0-9]+(?:\.[0-9]+)?)s", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(float(match.group(1)))
    except ValueError:
        return None


def is_hard_quota_exhausted_message(text: str) -> bool:
    """Purpose: Evaluate whether hard quota exhausted message is true.
    
    Inputs:
    - text: Input text content being parsed, normalized, or inspected.
    
    Returns:
    - `bool` value representing the operation result.
    """
    lowered = text.lower()
    return (
        "terminalquotaerror" in lowered
        or "daily quota" in lowered
        or "limit: 0" in lowered
        or "generate_content_free_tier_input_token_count, limit: 0" in lowered
        or "generate_content_free_tier_requests, limit: 0" in lowered
    )


def extract_full_report_path(stderr_text: str) -> str | None:
    """Purpose: Execute extract full report path for this module's workflow.
    
    Inputs:
    - stderr_text: Captured stderr text used for retry/failure classification.
    
    Returns:
    - `str | None` value representing the operation result.
    """
    match = re.search(r"full report available at:\s*(\S+)", stderr_text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def load_full_report_content(report_path: str) -> str | None:
    """Purpose: Load full report content from configured source(s).
    
    Inputs:
    - report_path: Path to a provider-generated full diagnostic report.
    
    Returns:
    - `str | None` value representing the operation result.
    """
    path = Path(report_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def print_attempt_summary(attempt_results: list[tuple[str, str]], stream) -> None:
    """Purpose: Execute print attempt summary for this module's workflow.
    
    Inputs:
    - attempt_results: Ordered list of model attempt outcomes for summary reporting.
    - stream: Writable output stream used for human-readable summary lines.
    
    Returns:
    - None. This function performs side effects only.
    """
    if not attempt_results:
        return
    print("Model attempt summary:", file=stream)
    for model_name, outcome in attempt_results:
        print(f"- {model_name}: {outcome}", file=stream)


def parse_positive_int(process_env: dict[str, str], key: str, default: int) -> int:
    """Purpose: Parse and validate positive int for downstream use.
    
    Inputs:
    - process_env: Runtime environment dictionary (the resolved settings environment).
    - key: Environment variable key to read and parse.
    - default: Default integer returned when the configured value is missing/invalid.
    
    Returns:
    - `int` value representing the operation result.
    """
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
    """Purpose: Run gemini with diagnostics and return its outcome.
    
    Inputs:
    - command: Command argument vector used to launch the model subprocess.
    - env: Process environment variables used for subprocesses or HTTP calls.
    - timeout_seconds: Maximum seconds allowed before timing out the attempt.
    - heartbeat_seconds: Interval in seconds between progress heartbeat checks/logs.
    - model_name: Model identifier to invoke for this provider attempt.
    - attempt_index: 1-based index of the current model attempt.
    - max_429_lines_before_fallback: Count threshold of detected 429/quota lines before aborting and falling back.
    - rate_limit_grace_seconds: Grace period in seconds before rate-limit fallback checks are enforced.
    - max_retry_after_seconds_before_fallback: Maximum provider-requested retry delay tolerated before forcing fallback.
    
    Returns:
    - `tuple[subprocess.CompletedProcess[str], float, Path]` value representing the operation result.
    """
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
    track_provider_process(process)

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
        """Purpose: Execute stream reader for this module's workflow.
        
        Inputs:
        - pipe: Readable stream (stdout/stderr or HTTP worker stream) consumed line-by-line.
        - sink: Mutable list used to accumulate streamed output lines.
        - sink_name: Human-readable label for the stream source in emitted output.
        - emit_stream: Output stream where mirrored live lines are written.
        - stat_key: Key in the stream statistics map to increment for each line.
        
        Returns:
        - None. This function performs side effects only.
        """
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
    untrack_provider_process(process)
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
    """Purpose: Build model sequence from current inputs and state.
    
    Inputs:
    - process_env: Runtime environment dictionary (the resolved settings environment).
    - provider: Selected provider backend identifier.
    - explicit_model: Optional explicit model override to prioritize in sequence building.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
    backend = get_backend_or_raise(provider, process_env)
    return backend.backend.model_sequence(process_env, explicit_model or "")


def dedupe_keep_order(items: list[str]) -> list[str]:
    """Purpose: Execute dedupe keep order for this module's workflow.
    
    Inputs:
    - items: Input list that will be deduplicated while preserving order.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
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
    """Purpose: Read company name from file or runtime state.
    
    Inputs:
    - company_file: Path to persisted company-name input file.
    
    Returns:
    - `str` value representing the operation result.
    """
    if not company_file.exists():
        return ""
    return company_file.read_text(encoding="utf-8").strip()


def persist_inputs(company_file: Path, company_name: str, urls_file: Path, urls: list[str]) -> None:
    """Purpose: Execute persist inputs for this module's workflow.
    
    Inputs:
    - company_file: Path to persisted company-name input file.
    - company_name: Company name used to contextualize research prompt generation.
    - urls_file: Path to persisted newline-delimited URL input file.
    - urls: URL list used as research context sources.
    
    Returns:
    - None. This function performs side effects only.
    """
    company_file.parent.mkdir(parents=True, exist_ok=True)
    urls_file.parent.mkdir(parents=True, exist_ok=True)
    company_file.write_text(company_name.strip() + "\n", encoding="utf-8")
    if urls:
        urls_file.write_text("\n".join(urls) + "\n", encoding="utf-8")


def reset_prompt_file(prompt_default_path: Path, prompt_path: Path) -> None:
    """Purpose: Execute reset prompt file for this module's workflow.
    
    Inputs:
    - prompt_default_path: Path to immutable default research prompt source file.
    - prompt_path: Path to editable prompt file used for runtime prompt composition.
    
    Returns:
    - None. This function performs side effects only.
    """
    if not prompt_default_path.exists():
        raise FileNotFoundError(f"Default prompt file not found: {prompt_default_path}")
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt_default_path.read_text(encoding="utf-8"), encoding="utf-8")


def read_urls(urls_file: Path, inline_urls: list[str]) -> list[str]:
    """Purpose: Read urls from file or runtime state.
    
    Inputs:
    - urls_file: Path to persisted newline-delimited URL input file.
    - inline_urls: URL values provided directly via CLI/request input.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
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
    """Purpose: Execute format urls block for this module's workflow.
    
    Inputs:
    - urls: URL list used as research context sources.
    
    Returns:
    - `str` value representing the operation result.
    """
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
    """Purpose: Build prompt from current inputs and state.
    
    Inputs:
    - prompt_template: Prompt template text that may include replacement tokens.
    - company_name: Company name used to contextualize research prompt generation.
    - cv_content: CV markdown content inserted into the research prompt.
    - jobspec_content: Job specification text inserted into the research prompt.
    - urls: URL list used as research context sources.
    
    Returns:
    - `str` value representing the operation result.
    """
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
    """Purpose: Parse and validate args for downstream use.
    
    Inputs:
    - None.
    
    Returns:
    - `argparse.Namespace` value representing the operation result.
    """
    parser = argparse.ArgumentParser(
        description="Research a target company/role context and produce interview prep notes.",
    )
    parser.add_argument("--company-name", default="", help="Target company name")
    parser.add_argument(
        "--company-file",
        default=str(COMPANY_FILE),
        help="Path to persisted company name file",
    )
    parser.add_argument("--cv", default=str(CV_FILE), help="Path to CV file (default: input/CV.md)")
    parser.add_argument(
        "--jobspec",
        default=str(JOBSPEC_FILE),
        help="Path to job spec file (default: input/jobspec.txt)",
    )
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
    parser.add_argument("--provider", default="", help="Model provider override (any discovered backend id)")
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
    parser.add_argument("--db", default=None, help="Settings DB (default: cv_web/resumator.db)")
    parser.add_argument(
        "--io",
        choices=["files", "json"],
        default="files",
        help="files: read input/, write output/ (default). json: one request on stdin, one result on stdout, "
        "progress on stderr, no files (multi-role runs)",
    )
    return parser.parse_args()


@dataclass
class ResearchOutcome:
    """What a research run produced: the JSON envelope (None when it stopped before one), the stamped markdown
    (success only), the exit code and, on failure, a short error."""

    envelope: dict[str, object] | None
    markdown: str | None
    exit_code: int
    error: str | None = None


def run_research(request: dict, *, files: bool, env: dict | None = None) -> ResearchOutcome:
    """Run the research pipeline on request = {cv, jobspec, prompt, company, urls, provider, model, dry_run}.

    files=True is the one-shot mode: it saves the built prompt and per-attempt logs under output/ (the caller writes
    the outputs). files=False (`--io json`) writes nothing: attempt logs go to stderr.

    env is the process environment for the run (default `os.environ`); no `.env` file is read.
    """
    company_name = request["company"]
    urls = request["urls"]
    print("Building research prompt...", flush=True)
    prompt_text = build_prompt(request["prompt"], company_name, request["cv"], request["jobspec"], urls)
    if files:
        OUTPUT_PROMPT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PROMPT.write_text(prompt_text, encoding="utf-8")
        print(
            f"Prepared prompt for '{company_name}' with {len(urls)} URL(s). Saved to: {OUTPUT_PROMPT.resolve()}",
            flush=True,
        )
    else:
        print(f"Prepared prompt for '{company_name}' with {len(urls)} URL(s).", flush=True)

    process_env = dict(os.environ if env is None else env)
    process_env.setdefault("GEMINI_CLI_TRUST_WORKSPACE", "true")
    catalog = load_provider_catalog(process_env)
    providers = provider_map(catalog)
    default_provider = str(catalog.get("defaultProvider") or "gemini").strip() or "gemini"
    requested_provider = request.get("provider") or ""
    selected_provider = (requested_provider or process_env.get("MODEL_PROVIDER") or default_provider).strip().lower()
    if selected_provider not in providers:
        print(f"Unsupported provider: {selected_provider}", file=sys.stderr)
        return ResearchOutcome(None, None, 1, f"unsupported provider '{selected_provider}'")
    selected_backend = get_backend_or_raise(selected_provider, process_env)
    if not selected_backend.status.enabled:
        reason = selected_backend.status.reason or "provider is disabled"
        print(f"Provider '{selected_provider}' is disabled: {reason}", file=sys.stderr)
        return ResearchOutcome(None, None, 1, f"provider '{selected_provider}' is disabled: {reason}")

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
    model_sequence = build_model_sequence(process_env, selected_provider, explicit_model=request.get("model") or "")

    envelope: dict[str, object] = {
        "companyName": company_name,
        "provider": selected_provider,
        "model": model_sequence[0] if model_sequence else DEFAULT_MODEL,
        "urls": urls,
        "generatedAt": utc_now_iso(),
        "dryRun": bool(request.get("dry_run")),
        "output": "",
    }

    if request.get("dry_run"):
        envelope["output"] = "[dry-run] prompt built successfully"
        envelope["promptPreview"] = prompt_text[:6000]
        envelope["modelAttempts"] = []
        return ResearchOutcome(envelope, None, 0)

    debug_log_dir = DEBUG_LOG_DIR if files else None
    if debug_log_dir:
        print(
            f"Diagnostics enabled. Per-attempt logs at: {debug_log_dir.resolve()}",
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
            proc = selected_backend.backend.run_attempt(
                model_name=model_name,
                prompt_text=prompt_text,
                env=process_env,
                timeout_seconds=int(getattr(selected_backend.backend, "timeout_seconds", timeout_seconds)),
                heartbeat_seconds=heartbeat_seconds,
                attempt_index=idx,
                debug_log_dir=debug_log_dir,
                log_prefix="research-attempt",
                emit_live_output=True,
                max_429_lines_before_fallback=max_429_lines_before_fallback,
                rate_limit_grace_seconds=rate_limit_grace_seconds,
                max_retry_after_seconds_before_fallback=max_retry_after_seconds_before_fallback,
            )
            log_text = f" Debug log: {proc.log_path}" if proc.log_path else ""
            print(f"Attempt {idx} completed in {proc.elapsed_seconds:.1f}s.{log_text}", flush=True)
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
            print_attempt_summary(attempt_results, sys.stderr)
            return ResearchOutcome(envelope, None, 1, f"model attempt failed unexpectedly: {excerpt}")

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
                print_attempt_summary(attempt_results, sys.stderr)
                return ResearchOutcome(envelope, None, 1, "stopped after consecutive hard quota failures")
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
        print_attempt_summary(attempt_results, sys.stderr)
        return ResearchOutcome(envelope, None, proc.returncode, f"provider call failed on model {model_name}")

    if proc is None or proc.returncode != 0:
        print("Gemini API failed across all configured models due to load/quota limits.", file=sys.stderr)
        envelope["model"] = model_sequence[0] if model_sequence else DEFAULT_MODEL
        envelope["modelAttempts"] = model_attempts
        envelope["output"] = ""
        envelope["stderr"] = "All model attempts failed. See modelAttempts for details."
        print_attempt_summary(attempt_results, sys.stderr)
        return ResearchOutcome(envelope, None, 1, "all model attempts failed")

    output_text = (proc.stdout or "").strip()
    if not output_text:
        print("Gemini returned empty output.", file=sys.stderr)
        envelope["model"] = selected_model or model_sequence[0]
        envelope["modelAttempts"] = model_attempts
        envelope["output"] = ""
        return ResearchOutcome(envelope, None, 1, "the model returned empty output")

    print("Gemini completed. Writing research outputs...", flush=True)
    generated_at = local_now_to_second()
    stamped_output = f"Generated At: {generated_at}\n\n{output_text.strip()}\n"
    envelope["model"] = selected_model or model_sequence[0]
    envelope["modelAttempts"] = model_attempts
    envelope["output"] = output_text
    envelope["generatedAt"] = generated_at
    return ResearchOutcome(envelope, stamped_output, 0)


def handle_json_request(request: dict) -> dict:
    """`--io json`: check the request's fields, run research without files, and shape the result."""
    urls = request.get("urls") or []
    if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
        raise RequestError("request field 'urls' must be a list of strings")
    checked = {
        "cv": require_text(request, "cv"),
        "jobspec": optional_text(request, "jobspec"),
        "prompt": require_text(request, "prompt").strip(),
        "company": require_text(request, "company").strip(),
        "urls": dedupe_keep_order(urls),
        "provider": optional_text(request, "provider"),
        "model": optional_text(request, "model"),
        "dry_run": bool(request.get("dry_run")),
    }
    outcome = run_research(checked, files=False)
    envelope = outcome.envelope or {}
    return {
        "success": outcome.exit_code == 0,
        "provider": envelope.get("provider", ""),
        "model": envelope.get("model", ""),
        "output_json": outcome.envelope,
        "output_md": outcome.markdown,
        "error": outcome.error,
    }


def main() -> None:
    """Run one research job: one-shot from input/ to output/, or `--io json` over pipes (no files)."""
    args = parse_args()
    if args.io == "json":
        sys.exit(run_json_io(handle_json_request))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)

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

    prompt_template = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt_template:
        print(f"Prompt file is empty: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    urls = read_urls(urls_file, args.url)
    if not args.no_persist_inputs and not args.dry_run:
        persist_inputs(company_file, company_name, urls_file, urls)

    try:
        env = one_shot_env(args.db, "" if args.dry_run else args.provider)
    except SettingsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    outcome = run_research(
        {
            "cv": cv_path.read_text(encoding="utf-8"),
            "jobspec": jobspec_path.read_text(encoding="utf-8"),
            "prompt": prompt_template,
            "company": company_name,
            "urls": urls,
            "provider": args.provider,
            "model": args.model,
            "dry_run": args.dry_run,
        },
        files=True,
        env=env,
    )
    if outcome.markdown is not None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(outcome.markdown, encoding="utf-8")
    if outcome.envelope is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(outcome.envelope, indent=2) + "\n", encoding="utf-8")
    if outcome.exit_code != 0:
        sys.exit(outcome.exit_code)

    if args.dry_run:
        print(f"Dry run complete. JSON written to: {output_json.resolve()}")
        return
    print(f"Research markdown written to: {output_md.resolve()}")
    print(f"Research metadata written to: {output_json.resolve()}")


if __name__ == "__main__":
    main()

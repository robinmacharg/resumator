#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from cv_convert import convert_markdown_outputs

# File paths in current working directory
CV_FILE = Path("CV.md")
JOBSPEC_FILE = Path("jobspec.txt")
PROMPT_FILE = Path("prompt.md")
ENV_FILE = Path(".env")
TAILORED_MD = Path("tailored.md")
OUTPUT_PDF = Path("tailored_dev.pdf")
OUTPUT_DOCX = Path("tailored_dev.docx")
GEMINI_TIMEOUT_SECONDS = 300
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_FALLBACK_MODELS = ["gemini-2.5-pro"]
GEMINI_HEARTBEAT_SECONDS = 15
DEBUG_LOG_DIR = Path("gemini_debug_logs")
DEFAULT_FAST_MODEL = "gemini-2.5-flash-lite"
DEFAULT_FAST_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]
MAX_FAST_CV_CHARS = 18000


def is_high_load_error(stderr_text: str) -> bool:
    lowered = stderr_text.lower()
    return (
        "503" in stderr_text
        or "429" in stderr_text
        or "404" in stderr_text
        or "high demand" in lowered
        or "unavailable" in lowered
        or "service unavailable" in lowered
        or "quota exceeded" in lowered
        or "terminalquotaerror" in lowered
        or "rate limit" in lowered
        or "modelnotfounderror" in lowered
        or "no longer available" in lowered
        or "model is not found" in lowered
    )


def build_model_sequence(process_env: dict) -> list[str]:
    """Build model attempt order from environment with sensible fallbacks."""
    fast_mode = process_env.get("CV_FAST_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}
    default_primary = DEFAULT_FAST_MODEL if fast_mode else DEFAULT_GEMINI_MODEL
    primary = process_env.get("GEMINI_MODEL", default_primary).strip()
    fallback_raw = process_env.get("GEMINI_MODEL_FALLBACKS", "")
    fallback_from_env = [
        item.strip() for item in fallback_raw.split(",") if item.strip()
    ]

    fallback_defaults = DEFAULT_FAST_FALLBACK_MODELS if fast_mode else DEFAULT_FALLBACK_MODELS

    ordered: list[str] = []
    for model in [primary, *fallback_from_env, *fallback_defaults]:
        if model and model not in ordered:
            ordered.append(model)

    return ordered


def classify_error_reason(stderr_text: str) -> str:
    """Return a short, human-readable error category for diagnostics."""
    lowered = stderr_text.lower()
    if "503" in stderr_text or "high demand" in lowered or "service unavailable" in lowered:
        return "503 high-demand"
    if "429" in stderr_text or "quota exceeded" in lowered or "terminalquotaerror" in lowered:
        return "429 quota"
    if "404" in stderr_text or "modelnotfounderror" in lowered or "no longer available" in lowered:
        return "model unavailable"
    if "rate limit" in lowered:
        return "rate limit"
    if "unauthorized" in lowered or "permission denied" in lowered:
        return "auth/policy"
    return "other error"


def print_attempt_summary(attempt_results: list[tuple[str, str]], stream) -> None:
    """Print a compact per-model summary for easier post-run diagnosis."""
    if not attempt_results:
        return
    print("Model attempt summary:", file=stream)
    for model_name, outcome in attempt_results:
        print(f"- {model_name}: {outcome}", file=stream)


def run_gemini_with_diagnostics(
    command: list[str],
    env: dict,
    timeout_seconds: int,
    model_name: str,
    attempt_index: int,
) -> tuple[subprocess.CompletedProcess, float, Path]:
    """Run Gemini with heartbeat logging and persist full attempt logs."""
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = DEBUG_LOG_DIR / f"attempt-{attempt_index:02d}-{model_name}-{timestamp}.log"

    start = time.monotonic()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    stdout_text = ""
    stderr_text = ""
    timed_out = False

    while True:
        elapsed = time.monotonic() - start
        remaining = timeout_seconds - elapsed
        if remaining <= 0:
            timed_out = True
            process.kill()
            stdout_text, stderr_text = process.communicate()
            break

        try:
            stdout_text, stderr_text = process.communicate(
                timeout=min(GEMINI_HEARTBEAT_SECONDS, remaining)
            )
            break
        except subprocess.TimeoutExpired:
            print(
                f"Attempt {attempt_index}: still waiting on Gemini model "
                f"{model_name} ({int(elapsed)}s elapsed)...",
                file=sys.stderr,
            )

    end_elapsed = time.monotonic() - start
    return_code = process.returncode if process.returncode is not None else 1

    log_path.write_text(
        "\n".join(
            [
                f"model={model_name}",
                f"attempt={attempt_index}",
                f"return_code={return_code}",
                f"elapsed_seconds={end_elapsed:.2f}",
                f"timed_out={timed_out}",
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

def load_dotenv_file(path: Path) -> dict:
    """Load key/value pairs from a simple .env file without extra dependencies."""
    env_vars: dict[str, str] = {}
    if not path.exists():
        return env_vars

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export "):].strip()

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


def build_prompt(prompt_text: str, cv_content: str, jobspec_content: str) -> str:
    """Create the final prompt, supporting either placeholders or auto-appended inputs."""
    if "{cv_content}" in prompt_text or "{jobspec_content}" in prompt_text:
        return prompt_text.format(
            cv_content=cv_content,
            jobspec_content=jobspec_content,
        )

    return (
        f"{prompt_text.strip()}\n\n"
        f"=== MASTER CV ===\n{cv_content}\n\n"
        f"=== JOB SPECIFICATION ===\n{jobspec_content}"
    )


def is_fast_mode_enabled(process_env: dict) -> bool:
    return process_env.get("CV_FAST_MODE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def prepare_cv_content_for_mode(cv_content: str, fast_mode: bool) -> str:
    """Trim CV input for faster iteration mode while preserving recency bias."""
    if not fast_mode or len(cv_content) <= MAX_FAST_CV_CHARS:
        return cv_content

    print(
        f"FAST_MODE: truncating CV input from {len(cv_content)} to ~{MAX_FAST_CV_CHARS} chars "
        "for quicker iteration."
    )
    return cv_content[:MAX_FAST_CV_CHARS]


def apply_fast_mode_prompt_rules(full_prompt: str, fast_mode: bool) -> str:
    if not fast_mode:
        return full_prompt

    fast_instructions = (
        "\n\n=== FAST MODE INSTRUCTIONS ===\n"
        "You are in FAST MODE for formatting iteration.\n"
        "Prioritize speed and deterministic structure over prose richness.\n"
        "Keep bullets concise and avoid unnecessary verbosity.\n"
        "Still obey all semantic tag and markdown output contract requirements.\n"
    )
    return full_prompt + fast_instructions


def main() -> None:
    # 1. Verify input files exist
    missing = [str(path) for path in (CV_FILE, JOBSPEC_FILE, PROMPT_FILE) if not path.exists()]
    if missing:
        print(f"Error: Missing required file(s): {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    # 2. Verify gemini CLI is installed
    if not shutil.which("gemini"):
        print(
            "Error: 'gemini' CLI tool not found. Install via: npm install -g @google/gemini-cli",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Reading inputs...")
    cv_content = CV_FILE.read_text(encoding="utf-8")
    jobspec_content = JOBSPEC_FILE.read_text(encoding="utf-8")
    prompt_text = PROMPT_FILE.read_text(encoding="utf-8").strip()
    if not prompt_text:
        print(f"Error: {PROMPT_FILE} is empty.", file=sys.stderr)
        sys.exit(1)

    # 3. Build process environment from current env + .env file
    process_env = os.environ.copy()
    process_env.update(load_dotenv_file(ENV_FILE))
    # Headless automation: allow Gemini CLI to run in this workspace without
    # interactive trust prompts.
    process_env.setdefault("GEMINI_CLI_TRUST_WORKSPACE", "true")

    # 4. Formulate prompt and invoke Gemini non-interactively via stdin/stdout
    fast_mode = is_fast_mode_enabled(process_env)
    if fast_mode:
        print("FAST_MODE enabled.")

    mode_cv_content = prepare_cv_content_for_mode(cv_content, fast_mode)
    full_prompt = build_prompt(prompt_text, mode_cv_content, jobspec_content)
    full_prompt = apply_fast_mode_prompt_rules(full_prompt, fast_mode)

    print("Invoking Gemini CLI to project CV...")
    models_to_try = build_model_sequence(process_env)
    print("Model attempt order: " + ", ".join(models_to_try))
    print(
        f"Diagnostics enabled. Per-attempt logs will be written to: {DEBUG_LOG_DIR.resolve()}"
    )

    process: subprocess.CompletedProcess | None = None
    last_error = ""
    attempt_results: list[tuple[str, str]] = []
    for index, model_name in enumerate(models_to_try, start=1):
        print(f"Gemini attempt {index}/{len(models_to_try)} with model: {model_name}")
        command = [
            "gemini",
            "--skip-trust",
            "--model",
            model_name,
            "--prompt",
            full_prompt,
        ]
        try:
            completed, elapsed, log_path = run_gemini_with_diagnostics(
                command=command,
                env=process_env,
                timeout_seconds=GEMINI_TIMEOUT_SECONDS,
                model_name=model_name,
                attempt_index=index,
            )
            if completed.returncode != 0:
                raise subprocess.CalledProcessError(
                    returncode=completed.returncode,
                    cmd=completed.args,
                    output=completed.stdout,
                    stderr=completed.stderr,
                )

            process = completed
            print(
                f"Attempt {index} completed in {elapsed:.1f}s. "
                f"Debug log: {log_path}"
            )
            attempt_results.append((model_name, "success"))
            break
        except subprocess.TimeoutExpired as exc:
            stderr_excerpt = (exc.stderr or "").strip()
            excerpt = stderr_excerpt[:500] + ("..." if len(stderr_excerpt) > 500 else "")
            attempt_results.append((model_name, f"timeout after {GEMINI_TIMEOUT_SECONDS}s"))
            print(
                f"Attempt {index} timed out after {GEMINI_TIMEOUT_SECONDS}s. "
                f"Model: {model_name}",
                file=sys.stderr,
            )
            if excerpt:
                print(f"Stderr excerpt: {excerpt}", file=sys.stderr)
            print_attempt_summary(attempt_results, sys.stderr)
            sys.exit(1)
        except subprocess.CalledProcessError as exc:
            stderr_text = (exc.stderr or "").strip() or "(no stderr output)"
            last_error = stderr_text
            reason = classify_error_reason(stderr_text)

            if is_high_load_error(stderr_text):
                attempt_results.append((model_name, reason))
                print(
                    f"Attempt {index} hit transient load/quota limits. "
                    "Trying next fallback model if available...",
                    file=sys.stderr,
                )
                continue

            attempt_results.append((model_name, reason))
            print(f"Gemini CLI execution failed on model {model_name}:", file=sys.stderr)
            print(stderr_text, file=sys.stderr)
            print_attempt_summary(attempt_results, sys.stderr)
            sys.exit(1)

    if process is None:
        print(
            "Gemini API failed across all configured models due to load/quota limits.",
            file=sys.stderr,
        )
        print_attempt_summary(attempt_results, sys.stderr)
        if last_error:
            print("Last error details:", file=sys.stderr)
            print(last_error, file=sys.stderr)
        print(
            "Set GEMINI_MODEL and GEMINI_MODEL_FALLBACKS in .env to customize retries.",
            file=sys.stderr,
        )
        sys.exit(1)

    tailored_markdown = (process.stdout or "").strip()
    if not tailored_markdown:
        print("Gemini CLI returned empty output.", file=sys.stderr)
        sys.exit(1)

    TAILORED_MD.write_text(tailored_markdown + "\n", encoding="utf-8")
    print(f"Generated intermediate markdown: {TAILORED_MD}")

    # 5. Compile markdown outputs
    print("Compiling PDF and DOCX...")
    conversion_result = convert_markdown_outputs(
        markdown_path=TAILORED_MD,
        output_pdf=OUTPUT_PDF,
        output_docx=OUTPUT_DOCX,
        sanitized_markdown_path=Path("tailored.export.md"),
    )

    if conversion_result.used_sanitized_markdown:
        print(
            f"Detected YAML frontmatter; using sanitized export file: "
            f"{conversion_result.export_markdown_path}"
        )

    pdf_ok = conversion_result.pdf_ok
    docx_ok = conversion_result.docx_ok

    if not pdf_ok and not docx_ok:
        print("Warning: Unable to compile PDF or DOCX from generated markdown.")
        print(f"Find your generated markdown at: {TAILORED_MD.resolve()}")
        sys.exit(0)

    if pdf_ok:
        print(f"Success! PDF created at: {OUTPUT_PDF.resolve()}")
    else:
        print("PDF generation failed.", file=sys.stderr)

    if docx_ok:
        print(f"Success! DOCX created at: {OUTPUT_DOCX.resolve()}")
    else:
        print("DOCX generation failed.", file=sys.stderr)


if __name__ == "__main__":
    main()

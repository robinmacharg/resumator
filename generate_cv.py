#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cv_convert import convert_markdown_outputs

# File paths in current working directory
CV_FILE = Path("CV.md")
JOBSPEC_FILE = Path("jobspec.txt")
PROMPT_FILE = Path("prompt.md")
ENV_FILE = Path(".env")
TAILORED_MD = Path("tailored.md")
OUTPUT_PDF = Path("tailored.pdf")
OUTPUT_DOCX = Path("tailored.docx")
GEMINI_TIMEOUT_SECONDS = 300
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_FALLBACK_MODELS = ["gemini-2.5-pro"]


def is_high_load_error(stderr_text: str) -> bool:
    lowered = stderr_text.lower()
    return (
        "503" in stderr_text
        or "429" in stderr_text
        or "high demand" in lowered
        or "unavailable" in lowered
        or "service unavailable" in lowered
        or "quota exceeded" in lowered
        or "terminalquotaerror" in lowered
        or "rate limit" in lowered
    )


def build_model_sequence(process_env: dict) -> list[str]:
    """Build model attempt order from environment with sensible fallbacks."""
    primary = process_env.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    fallback_raw = process_env.get("GEMINI_MODEL_FALLBACKS", "")
    fallback_from_env = [
        item.strip() for item in fallback_raw.split(",") if item.strip()
    ]

    ordered: list[str] = []
    for model in [primary, *fallback_from_env, *DEFAULT_FALLBACK_MODELS]:
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
    full_prompt = build_prompt(prompt_text, cv_content, jobspec_content)

    print("Invoking Gemini CLI to project CV...")
    models_to_try = build_model_sequence(process_env)
    print("Model attempt order: " + ", ".join(models_to_try))

    process: subprocess.CompletedProcess | None = None
    last_error = ""
    attempt_results: list[tuple[str, str]] = []
    for index, model_name in enumerate(models_to_try, start=1):
        print(f"Gemini attempt {index}/{len(models_to_try)} with model: {model_name}")
        try:
            process = subprocess.run(
                [
                    "gemini",
                    "--skip-trust",
                    "--model",
                    model_name,
                    "--prompt",
                    full_prompt,
                ],
                capture_output=True,
                text=True,
                check=True,
                env=process_env,
                timeout=GEMINI_TIMEOUT_SECONDS,
            )
            attempt_results.append((model_name, "success"))
            break
        except subprocess.TimeoutExpired:
            attempt_results.append((model_name, f"timeout after {GEMINI_TIMEOUT_SECONDS}s"))
            print(
                f"Attempt {index} timed out after {GEMINI_TIMEOUT_SECONDS}s.",
                file=sys.stderr,
            )
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

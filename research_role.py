#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CV_FILE = Path("CV.md")
JOBSPEC_FILE = Path("jobspec.txt")
PROMPT_FILE = Path("research_prompt.md")
PROMPT_DEFAULT_FILE = Path("research_prompt.default.md")
ENV_FILE = Path(".env")
URLS_FILE = Path("research_urls.txt")
COMPANY_FILE = Path("research_company.txt")
OUTPUT_MD = Path("research_output.md")
OUTPUT_JSON = Path("research_output.json")
DEFAULT_MODEL = "gemini-2.5-flash"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    file_urls: list[str] = []
    if urls_file.exists():
        for raw_line in urls_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            file_urls.append(line)
    return dedupe_keep_order([*file_urls, *inline_urls])


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
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model name")
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
    if not args.no_persist_inputs:
        persist_inputs(company_file, company_name, urls_file, urls)

    prompt_text = build_prompt(prompt_template, company_name, cv_content, jobspec_content, urls)

    envelope: dict[str, object] = {
        "companyName": company_name,
        "model": args.model,
        "urls": urls,
        "generatedAt": utc_now_iso(),
        "dryRun": bool(args.dry_run),
        "output": "",
    }

    if args.dry_run:
        envelope["output"] = "[dry-run] prompt built successfully"
        envelope["promptPreview"] = prompt_text[:6000]
        output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        print(f"Dry run complete. JSON written to: {output_json.resolve()}")
        return

    if not shutil.which("gemini"):
        print("'gemini' CLI not found on PATH.", file=sys.stderr)
        sys.exit(1)

    process_env = os.environ.copy()
    process_env.update(load_dotenv_file(ENV_FILE))
    process_env.setdefault("GEMINI_CLI_TRUST_WORKSPACE", "true")

    command = [
        "gemini",
        "--skip-trust",
        "--model",
        args.model,
        "--prompt",
        prompt_text,
    ]

    proc = subprocess.run(
        command,
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        env=process_env,
    )

    if proc.returncode != 0:
        print("Gemini CLI call failed.", file=sys.stderr)
        if proc.stderr:
            print(proc.stderr.strip(), file=sys.stderr)
        envelope["output"] = proc.stdout.strip()
        envelope["stderr"] = proc.stderr.strip()
        output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        sys.exit(proc.returncode)

    output_text = (proc.stdout or "").strip()
    if not output_text:
        print("Gemini returned empty output.", file=sys.stderr)
        envelope["output"] = ""
        output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        sys.exit(1)

    output_md.write_text(output_text + "\n", encoding="utf-8")
    envelope["output"] = output_text
    output_json.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")

    print(f"Research markdown written to: {output_md.resolve()}")
    print(f"Research metadata written to: {output_json.resolve()}")


if __name__ == "__main__":
    main()

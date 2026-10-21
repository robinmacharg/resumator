#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from cv_convert import convert_markdown_outputs
from backend_registry import get_backend_or_raise
from provider_catalog import load_provider_catalog, provider_map
from provider_clients import AttemptResult

INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")

CV_FILE = INPUT_DIR / "CV.md"
JOBSPEC_FILE = INPUT_DIR / "jobspec.txt"
PROMPT_FILE = INPUT_DIR / "prompt.md"
ENV_FILE = Path(".env")
TAILORED_MD = OUTPUT_DIR / "tailored.md"
RAW_MODEL_OUTPUT_FILE = OUTPUT_DIR / "tailored.model-output.txt"
RAW_MODEL_JSON_FILE = OUTPUT_DIR / "tailored.model.json"
OUTPUT_PDF = OUTPUT_DIR / "tailored_dev.pdf"
OUTPUT_DOCX = OUTPUT_DIR / "tailored_dev.docx"
GEMINI_HEARTBEAT_SECONDS = 15
DEBUG_LOG_DIR = OUTPUT_DIR / "gemini_debug_logs"
MAX_FAST_CV_CHARS = 18000
MONTH_ABBREVIATIONS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_LOOKUP = {
    **{name.lower(): index for index, name in enumerate(MONTH_ABBREVIATIONS, start=1)},
    **{
        name: index
        for index, name in enumerate(
            ["january", "february", "march", "april", "may", "june", "july", "august",
             "september", "october", "november", "december"],
            start=1,
        )
    },
    "sept": 9,
}


def is_high_load_error(stderr_text: str) -> bool:
    """Purpose: Evaluate whether high load error is true.
    
    Inputs:
    - stderr_text: See type hints and call site for expected value.
    
    Returns:
    - `bool` value representing the operation result.
    """
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


def build_model_sequence(process_env: dict[str, str], provider: str, explicit_model: str = "") -> list[str]:
    """Purpose: Build model sequence from current inputs and state.
    
    Inputs:
    - process_env: See type hints and call site for expected value.
    - provider: See type hints and call site for expected value.
    - explicit_model: See type hints and call site for expected value.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
    backend = get_backend_or_raise(provider, process_env)
    return backend.backend.model_sequence(process_env, explicit_model)


def parse_args() -> argparse.Namespace:
    """Purpose: Parse and validate args for downstream use.
    
    Inputs:
    - None.
    
    Returns:
    - `argparse.Namespace` value representing the operation result.
    """
    parser = argparse.ArgumentParser(description="Generate a tailored CV via Gemini CLI")
    parser.add_argument(
        "--provider",
        default="",
        help="Model provider override (any discovered backend id)",
    )
    parser.add_argument("--model", default="", help="Explicit model override")
    return parser.parse_args()


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


def extract_json_payload(raw_text: str) -> str:
    """Extract a JSON object payload, tolerating optional fenced wrappers."""
    stripped = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, flags=re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    first = stripped.find("{")
    last = stripped.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise ValueError("Could not locate a JSON object in model output.")
    return stripped[first : last + 1]


def require_non_empty_string(value, field_name: str) -> str:
    """Purpose: Execute require non empty string for this module's workflow.
    
    Inputs:
    - value: See type hints and call site for expected value.
    - field_name: See type hints and call site for expected value.
    
    Returns:
    - `str` value representing the operation result.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def require_list_of_strings(value, field_name: str, *, min_items: int = 0, max_items: int | None = None) -> list[str]:
    """Purpose: Execute require list of strings for this module's workflow.
    
    Inputs:
    - value: See type hints and call site for expected value.
    - field_name: See type hints and call site for expected value.
    - min_items: See type hints and call site for expected value.
    - max_items: See type hints and call site for expected value.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings.")
    cleaned: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{idx}] must be a non-empty string.")
        cleaned.append(item.strip())

    if len(cleaned) < min_items:
        raise ValueError(f"{field_name} must include at least {min_items} item(s).")
    if max_items is not None and len(cleaned) > max_items:
        raise ValueError(f"{field_name} must include at most {max_items} item(s).")
    return cleaned


def normalize_optional_http_url(value, field_name: str) -> str | None:
    """Purpose: Execute normalize optional http url for this module's workflow.
    
    Inputs:
    - value: See type hints and call site for expected value.
    - field_name: See type hints and call site for expected value.
    
    Returns:
    - `str | None` value representing the operation result.
    """
    if value is None:
        return None
    url = require_non_empty_string(value, field_name)
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        raise ValueError(f"{field_name} must be an http(s) URL.")
    return url


DATE_RANGE_SEPARATOR = re.compile(r"\s*(?:-|–|—|\bto\b)\s*", flags=re.IGNORECASE)
DATE_POINT = re.compile(r"^(?:([A-Za-z]+)\.?\s+)?((?:19|20)\d{2})$")
BOLD_LEAD_IN = re.compile(r"^\*\*[^*]+\*\*")


def parse_date_point(text: str) -> tuple[int, int | None] | None:
    """Parse 'Mon YYYY', 'Month YYYY' or 'YYYY' into (year, month or None). 'Present' gives None."""
    cleaned = text.strip()
    if cleaned.lower() == "present":
        return None
    match = DATE_POINT.match(cleaned)
    month = MONTH_LOOKUP.get(match.group(1).lower()) if match and match.group(1) else None
    if not match or (match.group(1) and month is None):
        raise ValueError(f"unrecognised date '{cleaned}'")
    return int(match.group(2)), month


def format_date_point(point: tuple[int, int | None] | None) -> str:
    """Format a parsed date point as 'Mon YYYY', 'YYYY' or 'Present' (D7)."""
    if point is None:
        return "Present"
    year, month = point
    return f"{MONTH_ABBREVIATIONS[month - 1]} {year}" if month else str(year)


def earliest_month(point: tuple[int, int | None]) -> tuple[int, int]:
    """First (year, month) a date point can mean."""
    return point[0], point[1] or 1


def latest_month(point: tuple[int, int | None] | None) -> tuple[int, int]:
    """Last (year, month) a date point can mean. Present sorts after every date."""
    if point is None:
        return 9999, 12
    return point[0], point[1] or 12


def split_date_range(value, field_name: str) -> tuple[tuple[int, int | None], tuple[int, int | None] | None]:
    """Parse a date range into (start, end) points; end is None for Present."""
    date_range = require_non_empty_string(value, field_name)
    parts = DATE_RANGE_SEPARATOR.split(date_range)
    if len(parts) != 2:
        raise ValueError(
            f"{field_name} must be a range such as 'Jan 2019 - Mar 2021' or 'Jun 2020 - Present'."
        )
    try:
        start, end = parse_date_point(parts[0]), parse_date_point(parts[1])
    except ValueError as exc:
        raise ValueError(f"{field_name}: {exc}; use 'Mon YYYY', 'YYYY' or 'Present'.") from exc
    if start is None:
        raise ValueError(f"{field_name} cannot start at Present.")
    if latest_month(end) < earliest_month(start):
        raise ValueError(f"{field_name} ends before it starts.")
    return start, end


def normalize_date_range(value, field_name: str) -> str:
    """Validate a date range and rewrite it as 'Mon YYYY - Mon YYYY' or '... - Present' (D7)."""
    start, end = split_date_range(value, field_name)
    return f"{format_date_point(start)} - {format_date_point(end)}"


def earlier_career_span(items: list[dict]) -> str:
    """The 'YYYY - YYYY' (or 'YYYY - Present') span covered by normalised earlier-career items."""
    ranges = [split_date_range(item["date_range"], "date_range") for item in items]
    start = min((start for start, _ in ranges), key=earliest_month)
    end = max((end for _, end in ranges), key=latest_month)
    return f"{start[0]} - {end[0] if end else 'Present'}"


def require_bold_lead_in(items: list[str], field_name: str) -> list[str]:
    """Check that every item opens with a **bold phrase**."""
    for idx, item in enumerate(items):
        if not BOLD_LEAD_IN.match(item):
            raise ValueError(f"{field_name}[{idx}] must open with a **bold phrase**.")
    return items


def validate_and_normalize_payload(
    payload: dict,
    *,
    role_cutoff: tuple[int, int] | None = None,
    warnings: list[str] | None = None,
) -> dict:
    """Validate the v2 contract and normalise it for deterministic rendering.

    Contract breaches raise ValueError. Rule breaches that still leave renderable output are
    appended to warnings instead, so the caller can show them (D17).

    role_cutoff is the earliest (year, month) a selected key role should start in. A role whose
    start month is unknown passes if any month of its start year would.
    """
    if warnings is None:
        warnings = []
    if not isinstance(payload, dict):
        raise ValueError("Top-level JSON value must be an object.")

    for key in ["candidate", "document"]:
        if key not in payload:
            raise ValueError(f"Missing required top-level key: {key}")

    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object.")
    payload["metadata"] = metadata

    candidate = payload["candidate"]
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object.")
    normalized_candidate = {
        key: require_non_empty_string(candidate.get(key), f"candidate.{key}")
        for key in ["name", "phone", "email"]
    }
    for key in ["linkedin", "github", "stackoverflow", "website"]:
        value = candidate.get(key)
        normalized_candidate[key] = normalize_optional_http_url(value or None, f"candidate.{key}")
    normalized_candidate["subheader_lines"] = require_list_of_strings(
        candidate.get("subheader_lines", []),
        "candidate.subheader_lines",
    )
    payload["candidate"] = normalized_candidate

    document = payload["document"]
    if not isinstance(document, dict):
        raise ValueError("document must be an object.")

    document["headline"] = require_non_empty_string(document.get("headline"), "document.headline")

    document["professional_summary"] = require_bold_lead_in(
        require_list_of_strings(
            document.get("professional_summary"),
            "document.professional_summary",
            min_items=4,
            max_items=5,
        ),
        "document.professional_summary",
    )

    role_requirements = document.get("role_requirements")
    if not isinstance(role_requirements, dict):
        raise ValueError("document.role_requirements must be an object.")
    requirement_items = require_list_of_strings(
        role_requirements.get("items"),
        "document.role_requirements.items",
        min_items=4,
        max_items=6,
    )
    document["role_requirements"] = {
        "role_title": require_non_empty_string(
            role_requirements.get("role_title"),
            "document.role_requirements.role_title",
        ),
        "items": require_bold_lead_in(
            [clean_bullet_text(item) for item in requirement_items],
            "document.role_requirements.items",
        ),
    }

    document["education_credentials"] = require_list_of_strings(
        document.get("education_credentials"),
        "document.education_credentials",
        min_items=1,
        max_items=3,
    )

    selected_roles = document.get("selected_key_roles")
    if not isinstance(selected_roles, list) or not selected_roles:
        raise ValueError("document.selected_key_roles must be a non-empty list.")
    if len(selected_roles) > 5:
        raise ValueError("document.selected_key_roles must contain at most 5 roles.")
    normalized_roles: list[dict] = []
    for idx, role in enumerate(selected_roles):
        field = f"document.selected_key_roles[{idx}]"
        if not isinstance(role, dict):
            raise ValueError(f"{field} must be an object.")
        start, _ = split_date_range(role.get("date_range"), f"{field}.date_range")
        if role_cutoff and latest_month(start) < role_cutoff:
            warnings.append(
                f"{field} ({role.get('title')} | {role.get('company')}) starts {format_date_point(start)}, "
                f"before the selected-roles cutoff {format_date_point(role_cutoff)}."
            )
        normalized_roles.append(
            {
                "title": require_non_empty_string(role.get("title"), f"{field}.title"),
                "company": require_non_empty_string(role.get("company"), f"{field}.company"),
                "date_range": normalize_date_range(role.get("date_range"), f"{field}.date_range"),
                "app_store_url": normalize_optional_http_url(
                    role.get("app_store_url") or None,
                    f"{field}.app_store_url",
                ),
                "keywords": require_list_of_strings(role.get("keywords", []), f"{field}.keywords"),
                "bullets": [
                    clean_bullet_text(item)
                    for item in require_list_of_strings(
                        role.get("bullets"),
                        f"{field}.bullets",
                        min_items=1,
                        max_items=5,
                    )
                ],
            }
        )
    document["selected_key_roles"] = normalized_roles

    earlier_career = document.get("earlier_career")
    if not isinstance(earlier_career, dict):
        raise ValueError("document.earlier_career must be an object.")
    earlier_items = earlier_career.get("items")
    if not isinstance(earlier_items, list) or not earlier_items:
        raise ValueError("document.earlier_career.items must be a non-empty list.")
    normalized_earlier_items: list[dict] = []
    for idx, item in enumerate(earlier_items):
        field = f"document.earlier_career.items[{idx}]"
        if not isinstance(item, dict):
            raise ValueError(f"{field} must be an object.")
        normalized_earlier_items.append(
            {
                "role_title": require_non_empty_string(item.get("role_title"), f"{field}.role_title"),
                "company": require_non_empty_string(item.get("company"), f"{field}.company"),
                "technologies": require_list_of_strings(item.get("technologies", []), f"{field}.technologies"),
                "date_range": normalize_date_range(item.get("date_range"), f"{field}.date_range"),
            }
        )
    document["earlier_career"] = {
        "sectors": require_list_of_strings(
            earlier_career.get("sectors"),
            "document.earlier_career.sectors",
            min_items=1,
        ),
        "items": normalized_earlier_items,
    }

    document["open_source_contributions"] = [
        clean_bullet_text(item)
        for item in require_list_of_strings(
            document.get("open_source_contributions"),
            "document.open_source_contributions",
            min_items=3,
            max_items=4,
        )
    ]

    technical_skills = document.get("technical_skills")
    if not isinstance(technical_skills, list) or not technical_skills:
        raise ValueError("document.technical_skills must be a non-empty list.")
    normalized_skills: list[dict] = []
    for idx, group in enumerate(technical_skills):
        if not isinstance(group, dict):
            raise ValueError(f"document.technical_skills[{idx}] must be an object.")
        group_name = require_non_empty_string(group.get("group"), f"document.technical_skills[{idx}].group")
        items = require_list_of_strings(
            group.get("items"),
            f"document.technical_skills[{idx}].items",
            min_items=1,
        )
        normalized_skills.append({"group": group_name, "items": items})
    document["technical_skills"] = normalized_skills

    return payload


def parse_and_validate_json_output(
    raw_text: str,
    *,
    role_cutoff: tuple[int, int] | None = None,
    warnings: list[str] | None = None,
) -> dict:
    """Extract the JSON object from model output and validate it (see validate_and_normalize_payload)."""
    payload_text = extract_json_payload(raw_text)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model output JSON parsing failed: {exc}") from exc
    return validate_and_normalize_payload(payload, role_cutoff=role_cutoff, warnings=warnings)


def yaml_scalar(value) -> str:
    """Purpose: Execute yaml scalar for this module's workflow.
    
    Inputs:
    - value: See type hints and call site for expected value.
    
    Returns:
    - `str` value representing the operation result.
    """
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise ValueError(f"Unsupported YAML scalar type: {type(value)}")


def render_yaml_block(value, indent: int) -> list[str]:
    """Purpose: Execute render yaml block for this module's workflow.
    
    Inputs:
    - value: See type hints and call site for expected value.
    - indent: See type hints and call site for expected value.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
    space = " " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.extend(render_yaml_block(item, indent + 2))
            else:
                lines.append(f"{space}{key}: {yaml_scalar(item)}")
        return lines

    if isinstance(value, list):
        if not value:
            lines.append(f"{space}[]")
            return lines
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.extend(render_yaml_block(item, indent + 2))
            else:
                lines.append(f"{space}- {yaml_scalar(item)}")
        return lines

    lines.append(f"{space}{yaml_scalar(value)}")
    return lines


def clean_bullet_text(text: str) -> str:
    """Purpose: Execute clean bullet text for this module's workflow.
    
    Inputs:
    - text: See type hints and call site for expected value.
    
    Returns:
    - `str` value representing the operation result.
    """
    cleaned = text.strip()
    if cleaned.startswith("- ") or cleaned.startswith("* "):
        return cleaned[2:].strip()
    return cleaned


def join_naturally(items: list[str]) -> str:
    """Join 'a', 'b', 'c' as 'a, b and c'."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def render_tagged_markdown(payload: dict, *, directives: dict | None = None) -> str:
    """Render a validated v2 payload as tagged markdown for cv_convert.

    Section order, headings and fixed phrases live here. directives takes the
    cv_source shape ({omit: [...], contact_links: bool}); the defaults print everything.
    """
    directives = directives or {}
    omit = {name.lower() for name in directives.get("omit", [])}
    candidate = payload["candidate"]
    document = payload["document"]

    frontmatter_lines = ["---"]
    for key in ["candidate", "metadata"]:
        frontmatter_lines.append(f"{key}:")
        frontmatter_lines.extend(render_yaml_block(payload[key], 2) or ["  {}"])
    frontmatter_lines.append("---")

    lines: list[str] = [*frontmatter_lines, ""]
    lines.append(f"[candidate_name] {candidate['name']}")
    lines.append(f"[candidate_title] {document['headline']}")
    lines.append(f"[candidate_contact] {candidate['phone']} - [{candidate['email']}](mailto:{candidate['email']})")

    if directives.get("contact_links", True):
        social_parts = [
            f"[{label}]({candidate[key]})"
            for key, label in [
                ("linkedin", "LinkedIn"),
                ("github", "GitHub"),
                ("stackoverflow", "StackOverflow"),
                ("website", "Website"),
            ]
            if candidate.get(key)
        ]
        if social_parts:
            lines.append("[candidate_contact] " + " | ".join(social_parts))

    for subheader_line in candidate.get("subheader_lines", []):
        lines.append(f"[candidate_subheader] {subheader_line}")

    lines.append("")
    lines.append("[section_heading] # Professional Summary")
    lines.append("")
    for item in document["professional_summary"]:
        lines.append(f"[summary_paragraph] {item}")

    role_requirements = document["role_requirements"]
    lines.append("")
    lines.append(
        f"[role_requirements_heading] ### Targeted Requirements Match for {role_requirements['role_title']}"
    )
    for item in role_requirements["items"]:
        lines.append(f"[role_requirements_item] - {item}")

    lines.append("")
    lines.append("[section_heading] # Education, Certifications & Credentials")
    lines.append("")
    for item in document["education_credentials"]:
        lines.append(f"[education_item] * {clean_bullet_text(item)}")

    lines.append("")
    lines.append("[section_heading] # Selected Key Roles")
    lines.append("")
    for role in document["selected_key_roles"]:
        lines.append(f"[role_heading] ## {role['title']} | {role['company']}")
        role_dates = role["date_range"]
        if role.get("app_store_url"):
            role_dates = f"{role_dates} ([AppStore]({role['app_store_url']}))"
        lines.append(f"[date_range] {role_dates}")
        if role["keywords"] and "keywords" not in omit:
            lines.append(f"[keywords] Keywords: [{', '.join(role['keywords'])}]")
        for item in role["bullets"]:
            lines.append(f"[role_bullet] * {item}")
        lines.append("")

    earlier_career = document["earlier_career"]
    lines.append("[section_heading] # Earlier Career Highlights")
    lines.append("")
    lines.append(
        f"[earlier_intro] **{earlier_career_span(earlier_career['items'])}** Positions across "
        f"{join_naturally(earlier_career['sectors'])}."
    )
    lines.append("")
    for item in earlier_career["items"]:
        tech_text = f" ({', '.join(item['technologies'])})" if item["technologies"] else ""
        lines.append(
            f"[earlier_role] * **{item['role_title']}** | _{item['company']}_{tech_text} - {item['date_range']}"
        )

    lines.append("")
    lines.append("[section_heading] # Open Source Contributions")
    lines.append("")
    for item in document["open_source_contributions"]:
        lines.append(f"[project_item] * {item}")

    lines.append("")
    lines.append("[section_heading] # Technical Skills and Expertise")
    lines.append("")
    for group in document["technical_skills"]:
        lines.append(f"[skills_group] **{group['group']}** - {', '.join(group['items'])}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def is_fast_mode_enabled(process_env: dict) -> bool:
    """Purpose: Evaluate whether fast mode enabled is true.
    
    Inputs:
    - process_env: See type hints and call site for expected value.
    
    Returns:
    - `bool` value representing the operation result.
    """
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
    """Purpose: Execute apply fast mode prompt rules for this module's workflow.
    
    Inputs:
    - full_prompt: See type hints and call site for expected value.
    - fast_mode: See type hints and call site for expected value.
    
    Returns:
    - `str` value representing the operation result.
    """
    if not fast_mode:
        return full_prompt

    fast_instructions = (
        "\n\n=== FAST MODE INSTRUCTIONS ===\n"
        "You are in FAST MODE for formatting iteration.\n"
        "Prioritize speed and deterministic JSON structure over prose richness.\n"
        "Keep bullets concise and avoid unnecessary verbosity.\n"
        "Still obey the full JSON output contract exactly.\n"
    )
    return full_prompt + fast_instructions


def main() -> None:
    """Purpose: Execute main for this module's workflow.
    
    Inputs:
    - None.
    
    Returns:
    - None. This function performs side effects only.
    """
    args = parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Verify input files exist
    missing = [str(path) for path in (CV_FILE, JOBSPEC_FILE, PROMPT_FILE) if not path.exists()]
    if missing:
        print(f"Error: Missing required file(s): {', '.join(missing)}", file=sys.stderr)
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
    catalog = load_provider_catalog(Path("model_providers.json"))
    providers = provider_map(catalog)
    default_provider = str(catalog.get("defaultProvider") or "gemini").strip() or "gemini"

    selected_provider = (args.provider or process_env.get("MODEL_PROVIDER") or default_provider).strip().lower()
    if selected_provider not in providers:
        print(f"Error: Unsupported provider '{selected_provider}'.", file=sys.stderr)
        sys.exit(1)
    selected_backend = get_backend_or_raise(selected_provider, process_env)
    if not selected_backend.status.enabled:
        reason = selected_backend.status.reason or "provider is disabled"
        print(f"Error: Provider '{selected_provider}' is disabled: {reason}", file=sys.stderr)
        sys.exit(1)

    # 4. Formulate prompt and invoke Gemini non-interactively via stdin/stdout
    fast_mode = is_fast_mode_enabled(process_env)
    if fast_mode:
        print("FAST_MODE enabled.")

    mode_cv_content = prepare_cv_content_for_mode(cv_content, fast_mode)
    full_prompt = build_prompt(prompt_text, mode_cv_content, jobspec_content)
    full_prompt = apply_fast_mode_prompt_rules(full_prompt, fast_mode)

    print(f"Invoking provider '{selected_provider}' to project CV...")
    models_to_try = build_model_sequence(process_env, provider=selected_provider, explicit_model=args.model)
    print("Model attempt order: " + ", ".join(models_to_try))
    print(
        f"Diagnostics enabled. Per-attempt logs will be written to: {DEBUG_LOG_DIR.resolve()}"
    )

    process: AttemptResult | None = None
    last_error = ""
    attempt_results: list[tuple[str, str]] = []
    for index, model_name in enumerate(models_to_try, start=1):
        print(f"{selected_provider} attempt {index}/{len(models_to_try)} with model: {model_name}")
        completed = selected_backend.backend.run_attempt(
            model_name=model_name,
            prompt_text=full_prompt,
            env=process_env,
            timeout_seconds=int(getattr(selected_backend.backend, "timeout_seconds", 240)),
            heartbeat_seconds=GEMINI_HEARTBEAT_SECONDS,
            attempt_index=index,
            debug_log_dir=DEBUG_LOG_DIR,
            log_prefix="cv-attempt",
            emit_live_output=True,
        )

        if completed.returncode != 0:
            stderr_text = (completed.stderr or "").strip() or "(no stderr output)"
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
            print(f"Provider call failed on model {model_name}:", file=sys.stderr)
            print(stderr_text, file=sys.stderr)
            print_attempt_summary(attempt_results, sys.stderr)
            sys.exit(1)

        process = completed
        print(
            f"Attempt {index} completed in {completed.elapsed_seconds:.1f}s. "
            f"Debug log: {completed.log_path}"
        )
        attempt_results.append((model_name, "success"))
        break

    if process is None:
        print(
            "Provider call failed across all configured models due to load/quota or model errors.",
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

    raw_model_output = process.stdout or ""
    RAW_MODEL_OUTPUT_FILE.write_text(raw_model_output, encoding="utf-8")
    print(f"Saved raw model output to: {RAW_MODEL_OUTPUT_FILE}")

    if not raw_model_output.strip():
        print("Gemini CLI returned empty output.", file=sys.stderr)
        sys.exit(1)

    try:
        extracted_json_payload = extract_json_payload(raw_model_output)
        RAW_MODEL_JSON_FILE.write_text(extracted_json_payload + "\n", encoding="utf-8")
        print(f"Saved extracted model JSON to: {RAW_MODEL_JSON_FILE}")
    except ValueError:
        print(
            "Could not extract JSON payload from raw model output; "
            f"inspect {RAW_MODEL_OUTPUT_FILE}.",
            file=sys.stderr,
        )

    validation_warnings: list[str] = []
    try:
        structured_payload = parse_and_validate_json_output(raw_model_output, warnings=validation_warnings)
    except ValueError as exc:
        print(f"Generated output failed JSON contract validation: {exc}", file=sys.stderr)
        print(
            f"Inspect {RAW_MODEL_OUTPUT_FILE} and {RAW_MODEL_JSON_FILE} for raw output details.",
            file=sys.stderr,
        )
        sys.exit(1)

    for warning in validation_warnings:
        print(f"Warning: model output breaks a rule: {warning}", file=sys.stderr)

    tailored_markdown = render_tagged_markdown(structured_payload)
    TAILORED_MD.write_text(tailored_markdown, encoding="utf-8")
    print(f"Generated intermediate markdown: {TAILORED_MD}")

    # 5. Compile markdown outputs
    print("Compiling PDF and DOCX...")
    conversion_result = convert_markdown_outputs(
        markdown_path=TAILORED_MD,
        output_pdf=OUTPUT_PDF,
        output_docx=OUTPUT_DOCX,
        sanitized_markdown_path=OUTPUT_DIR / "tailored.export.md",
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

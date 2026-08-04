#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from cv_convert import convert_markdown_outputs
from provider_catalog import load_provider_catalog, provider_map
from provider_clients import (
    AttemptResult,
    run_gemini_attempt,
    run_huggingface_attempt,
    run_openai_attempt,
    run_swiftlet_attempt,
    run_vscodebridge_attempt,
)

# File paths in current working directory
CV_FILE = Path("CV.md")
JOBSPEC_FILE = Path("jobspec.txt")
PROMPT_FILE = Path("prompt.md")
ENV_FILE = Path(".env")
TAILORED_MD = Path("tailored.md")
RAW_MODEL_OUTPUT_FILE = Path("tailored.model-output.txt")
RAW_MODEL_JSON_FILE = Path("tailored.model.json")
OUTPUT_PDF = Path("tailored_dev.pdf")
OUTPUT_DOCX = Path("tailored_dev.docx")
GEMINI_TIMEOUT_SECONDS = 300
HUGGINGFACE_TIMEOUT_SECONDS = 180
OPENAI_TIMEOUT_SECONDS = 180
SWIFTLET_TIMEOUT_SECONDS = 240
VSCODE_BRIDGE_TIMEOUT_SECONDS = 240
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
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
GEMINI_HEARTBEAT_SECONDS = 15
DEBUG_LOG_DIR = Path("gemini_debug_logs")
DEFAULT_FAST_MODEL = "gemini-2.5-flash-lite"
DEFAULT_FAST_FALLBACK_MODELS = DEFAULT_FALLBACK_MODELS
DEFAULT_HUGGINGFACE_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
DEFAULT_HUGGINGFACE_FALLBACK_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "google/gemma-2-9b-it",
]
DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_OPENAI_FALLBACK_MODELS = [
    "gpt-5.6-terra",
    "gpt-5.6-sol",
    "gpt-5.5",
    "gpt-4.1-mini",
]
DEFAULT_SWIFTLET_MODEL = "qwen3_5_moe_text"
DEFAULT_SWIFTLET_FALLBACK_MODELS = []
DEFAULT_VSCODE_BRIDGE_MODEL = "copilot-vscode"
DEFAULT_VSCODE_BRIDGE_FALLBACK_MODELS = []
MAX_FAST_CV_CHARS = 18000
REQUIRED_SEMANTIC_TAG_KEYS = [
    "candidate_name",
    "candidate_title",
    "candidate_contact",
    "section_heading",
    "role_heading",
    "date_range",
    "keywords",
    "bullet_primary",
    "bullet_secondary",
    "project_item",
    "education_item",
    "summary_paragraph",
    "role_requirements_heading",
    "role_requirements_item",
]


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


def build_model_sequence(process_env: dict, provider: str, explicit_model: str = "") -> list[str]:
    """Build model attempt order from environment with sensible fallbacks."""
    explicit = explicit_model.strip()
    if explicit:
        return [explicit]

    fast_mode = process_env.get("CV_FAST_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}
    if provider == "huggingface":
        primary = process_env.get("HUGGINGFACE_MODEL", DEFAULT_HUGGINGFACE_MODEL).strip()
        fallback_raw = process_env.get("HUGGINGFACE_MODEL_FALLBACKS", "")
        fallback_from_env = [item.strip() for item in fallback_raw.split(",") if item.strip()]
        fallback_defaults = DEFAULT_HUGGINGFACE_FALLBACK_MODELS
    elif provider == "openai":
        primary = process_env.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip()
        fallback_raw = process_env.get("OPENAI_MODEL_FALLBACKS", "")
        fallback_from_env = [item.strip() for item in fallback_raw.split(",") if item.strip()]
        fallback_defaults = DEFAULT_OPENAI_FALLBACK_MODELS
    elif provider == "swiftlet":
        primary = process_env.get("SWIFTLET_MODEL", DEFAULT_SWIFTLET_MODEL).strip()
        fallback_raw = process_env.get("SWIFTLET_MODEL_FALLBACKS", "")
        fallback_from_env = [item.strip() for item in fallback_raw.split(",") if item.strip()]
        fallback_defaults = DEFAULT_SWIFTLET_FALLBACK_MODELS
    elif provider == "vscodebridge":
        primary = process_env.get("VSCODE_BRIDGE_MODEL", DEFAULT_VSCODE_BRIDGE_MODEL).strip()
        fallback_raw = process_env.get("VSCODE_BRIDGE_MODEL_FALLBACKS", "")
        fallback_from_env = [item.strip() for item in fallback_raw.split(",") if item.strip()]
        fallback_defaults = DEFAULT_VSCODE_BRIDGE_FALLBACK_MODELS
    else:
        default_primary = DEFAULT_FAST_MODEL if fast_mode else DEFAULT_GEMINI_MODEL
        primary = process_env.get("GEMINI_MODEL", default_primary).strip()
        fallback_raw = process_env.get("GEMINI_MODEL_FALLBACKS", "")
        fallback_from_env = [item.strip() for item in fallback_raw.split(",") if item.strip()]
        fallback_defaults = DEFAULT_FAST_FALLBACK_MODELS if fast_mode else DEFAULT_FALLBACK_MODELS

    ordered: list[str] = []
    for model in [primary, *fallback_from_env, *fallback_defaults]:
        if model and model not in ordered:
            ordered.append(model)

    return ordered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a tailored CV via Gemini CLI")
    parser.add_argument(
        "--provider",
        default="",
        help="Model provider override (gemini, huggingface, openai, swiftlet, or vscodebridge)",
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
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def require_list_of_strings(value, field_name: str, *, min_items: int = 0, max_items: int | None = None) -> list[str]:
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
    if value is None:
        return None
    url = require_non_empty_string(value, field_name)
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        raise ValueError(f"{field_name} must be an http(s) URL.")
    return url


def normalize_month_year_range(value, field_name: str) -> str:
    """Validate date ranges that should include month/year boundaries."""
    date_range = require_non_empty_string(value, field_name)
    has_year = re.search(r"\b(19|20)\d{2}\b", date_range) is not None
    has_separator = "-" in date_range or "to" in date_range.lower()
    if not has_year or not has_separator:
        raise ValueError(
            f"{field_name} must include a month/year range, for example 'Jan 2019 - Mar 2021'."
        )
    return date_range


def validate_and_normalize_payload(payload: dict) -> dict:
    """Validate schema and normalize key sections for deterministic rendering."""
    if not isinstance(payload, dict):
        raise ValueError("Top-level JSON value must be an object.")

    for key in ["candidate", "metadata", "semantic_tags", "skills_raw", "document"]:
        if key not in payload:
            raise ValueError(f"Missing required top-level key: {key}")

    candidate = payload["candidate"]
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object.")
    candidate["name"] = require_non_empty_string(candidate.get("name"), "candidate.name")
    candidate["title"] = require_non_empty_string(candidate.get("title"), "candidate.title")
    candidate["phone"] = require_non_empty_string(candidate.get("phone"), "candidate.phone")
    candidate["email"] = require_non_empty_string(candidate.get("email"), "candidate.email")

    semantic_tags = payload["semantic_tags"]
    if not isinstance(semantic_tags, dict):
        raise ValueError("semantic_tags must be an object.")

    if not isinstance(payload["metadata"], dict):
        raise ValueError("metadata must be an object.")
    if not isinstance(payload["skills_raw"], dict):
        raise ValueError("skills_raw must be an object.")

    missing_semantic_keys = [k for k in REQUIRED_SEMANTIC_TAG_KEYS if k not in semantic_tags]
    if missing_semantic_keys:
        raise ValueError(
            "semantic_tags is missing required key(s): " + ", ".join(missing_semantic_keys)
        )

    for key in REQUIRED_SEMANTIC_TAG_KEYS:
        value = require_non_empty_string(semantic_tags.get(key), f"semantic_tags.{key}")
        if value != key:
            raise ValueError(f"semantic_tags.{key} must equal '{key}'.")

    document = payload["document"]
    if not isinstance(document, dict):
        raise ValueError("document must be an object.")

    document["professional_summary"] = require_list_of_strings(
        document.get("professional_summary"),
        "document.professional_summary",
        min_items=4,
        max_items=5,
    )

    role_requirements = document.get("role_requirements")
    if not isinstance(role_requirements, dict):
        raise ValueError("document.role_requirements must be an object.")
    role_requirements["heading"] = require_non_empty_string(
        role_requirements.get("heading"),
        "document.role_requirements.heading",
    )
    role_requirements["items"] = require_list_of_strings(
        role_requirements.get("items"),
        "document.role_requirements.items",
        min_items=4,
        max_items=6,
    )

    document["education_credentials"] = require_list_of_strings(
        document.get("education_credentials"),
        "document.education_credentials",
        min_items=2,
    )

    selected_roles = document.get("selected_key_roles")
    if not isinstance(selected_roles, list) or not selected_roles:
        raise ValueError("document.selected_key_roles must be a non-empty list.")
    if len(selected_roles) > 5:
        raise ValueError("document.selected_key_roles must contain at most 5 roles.")
    normalized_roles: list[dict] = []
    for idx, role in enumerate(selected_roles):
        if not isinstance(role, dict):
            raise ValueError(f"document.selected_key_roles[{idx}] must be an object.")
        heading = require_non_empty_string(role.get("heading"), f"document.selected_key_roles[{idx}].heading")
        date_range = normalize_month_year_range(
            role.get("date_range"),
            f"document.selected_key_roles[{idx}].date_range",
        )
        keywords = require_list_of_strings(
            role.get("keywords"),
            f"document.selected_key_roles[{idx}].keywords",
            min_items=1,
        )
        bullet_primary = require_list_of_strings(
            role.get("bullet_primary"),
            f"document.selected_key_roles[{idx}].bullet_primary",
            min_items=1,
        )
        bullet_secondary = require_list_of_strings(
            role.get("bullet_secondary", []),
            f"document.selected_key_roles[{idx}].bullet_secondary",
        )
        normalized_roles.append(
            {
                "heading": heading,
                "date_range": date_range,
                "app_store_url": normalize_optional_http_url(
                    role.get("app_store_url"),
                    f"document.selected_key_roles[{idx}].app_store_url",
                ),
                "keywords": keywords,
                "bullet_primary": bullet_primary,
                "bullet_secondary": bullet_secondary,
            }
        )
    document["selected_key_roles"] = normalized_roles

    earlier_career = document.get("earlier_career")
    if not isinstance(earlier_career, dict):
        raise ValueError("document.earlier_career must be an object.")
    earlier_career["intro"] = require_non_empty_string(
        earlier_career.get("intro"),
        "document.earlier_career.intro",
    )
    earlier_items = earlier_career.get("items")
    if not isinstance(earlier_items, list) or not earlier_items:
        raise ValueError("document.earlier_career.items must be a non-empty list.")
    normalized_earlier_items: list[dict] = []
    for idx, item in enumerate(earlier_items):
        if not isinstance(item, dict):
            raise ValueError(f"document.earlier_career.items[{idx}] must be an object.")
        role_title = require_non_empty_string(
            item.get("role_title"),
            f"document.earlier_career.items[{idx}].role_title",
        )
        company = require_non_empty_string(
            item.get("company"),
            f"document.earlier_career.items[{idx}].company",
        )
        technologies = require_list_of_strings(
            item.get("technologies"),
            f"document.earlier_career.items[{idx}].technologies",
            min_items=1,
        )
        date_range = normalize_month_year_range(
            item.get("date_range"),
            f"document.earlier_career.items[{idx}].date_range",
        )
        normalized_earlier_items.append(
            {
                "role_title": role_title,
                "company": company,
                "technologies": technologies,
                "date_range": date_range,
            }
        )
    earlier_career["items"] = normalized_earlier_items

    document["open_source_contributions"] = require_list_of_strings(
        document.get("open_source_contributions"),
        "document.open_source_contributions",
        min_items=3,
        max_items=5,
    )

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

    if "candidate_contact_lines" in document:
        document["candidate_contact_lines"] = require_list_of_strings(
            document.get("candidate_contact_lines"),
            "document.candidate_contact_lines",
        )

    return payload


def parse_and_validate_json_output(raw_text: str) -> dict:
    payload_text = extract_json_payload(raw_text)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model output JSON parsing failed: {exc}") from exc
    return validate_and_normalize_payload(payload)


def yaml_scalar(value) -> str:
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
    cleaned = text.strip()
    if cleaned.startswith("- ") or cleaned.startswith("* "):
        return cleaned[2:].strip()
    return cleaned


def render_tagged_markdown(payload: dict) -> str:
    candidate = payload["candidate"]
    document = payload["document"]

    frontmatter_keys = ["candidate", "metadata", "semantic_tags", "skills_raw"]
    frontmatter_lines = ["---"]
    for key in frontmatter_keys:
        value = payload[key]
        if isinstance(value, (dict, list)):
            frontmatter_lines.append(f"{key}:")
            frontmatter_lines.extend(render_yaml_block(value, 2))
        else:
            frontmatter_lines.append(f"{key}: {yaml_scalar(value)}")
    frontmatter_lines.append("---")

    lines: list[str] = [*frontmatter_lines, ""]
    lines.append(f"[candidate_name] {candidate['name']}")
    lines.append(f"[candidate_title] {candidate['title']}")

    phone = candidate.get("phone", "").strip()
    email = candidate.get("email", "").strip()
    if phone and email:
        lines.append(f"[candidate_contact] {phone} - [{email}](mailto:{email})")

    social_parts: list[str] = []
    if candidate.get("linkedin"):
        social_parts.append(f"[LinkedIn]({candidate['linkedin']})")
    if candidate.get("github"):
        social_parts.append(f"[GitHub]({candidate['github']})")
    if candidate.get("stackoverflow"):
        social_parts.append(f"[StackOverflow]({candidate['stackoverflow']})")
    if social_parts:
        lines.append("[candidate_contact] " + " | ".join(social_parts))

    for extra_contact_line in document.get("candidate_contact_lines", []):
        contact_line = require_non_empty_string(extra_contact_line, "document.candidate_contact_lines[]")
        lines.append(f"[candidate_contact] {contact_line}")

    lines.append("")
    lines.append("[section_heading] # Professional Summary")
    lines.append("")
    for item in document["professional_summary"]:
        lines.append(f"[summary_paragraph] {item}")

    lines.append("")
    lines.append(f"[role_requirements_heading] ### {document['role_requirements']['heading']}")
    for item in document["role_requirements"]["items"]:
        bullet = item if item.strip().startswith("-") else f"- {item}"
        lines.append(f"[role_requirements_item] {bullet}")

    lines.append("")
    lines.append("[section_heading] # Education, Certifications & Credentials")
    lines.append("")
    for item in document["education_credentials"]:
        lines.append(f"[education_item] * {clean_bullet_text(item)}")

    lines.append("")
    lines.append("[section_heading] # Selected Key Roles")
    lines.append("")
    for role in document["selected_key_roles"]:
        lines.append(f"[role_heading] ## {role['heading']}")
        role_dates = role["date_range"]
        app_store_url = role.get("app_store_url")
        if app_store_url:
            role_dates = f"{role_dates} ([AppStore]({app_store_url}))"
        lines.append(f"[date_range] **Dates:** {role_dates}")
        keywords_text = ", ".join(role["keywords"])
        lines.append(f"[keywords] **Keywords:** `[{keywords_text}]`")
        for item in role["bullet_primary"]:
            lines.append(f"[bullet_primary] * {clean_bullet_text(item)}")
        for item in role["bullet_secondary"]:
            lines.append(f"[bullet_secondary] * {clean_bullet_text(item)}")
        lines.append("")

    lines.append("[section_heading] # Earlier Career Highlights")
    lines.append("")
    lines.append(document["earlier_career"]["intro"])
    lines.append("")
    for item in document["earlier_career"]["items"]:
        tech_text = ", ".join(item["technologies"])
        lines.append(
            f"* **{item['role_title']}** | _{item['company']}_ ({tech_text}) - {item['date_range']}"
        )

    lines.append("")
    lines.append("[section_heading] # Open Source Contributions")
    lines.append("")
    for item in document["open_source_contributions"]:
        lines.append(f"[project_item] * {clean_bullet_text(item)}")

    lines.append("")
    lines.append("[section_heading] # Technical Skills and Expertise")
    lines.append("")
    for group in document["technical_skills"]:
        lines.append(f"**{group['group']}**")
        lines.append(f"- {', '.join(group['items'])}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


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
        "Prioritize speed and deterministic JSON structure over prose richness.\n"
        "Keep bullets concise and avoid unnecessary verbosity.\n"
        "Still obey the full JSON output contract exactly.\n"
    )
    return full_prompt + fast_instructions


def main() -> None:
    args = parse_args()

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

    if selected_provider == "gemini" and not shutil.which("gemini"):
        print(
            "Error: 'gemini' CLI tool not found. Install via: npm install -g @google/gemini-cli",
            file=sys.stderr,
        )
        sys.exit(1)

    if selected_provider == "huggingface":
        hf_token = (process_env.get("HF_API_TOKEN") or process_env.get("HUGGINGFACE_API_TOKEN") or "").strip()
        if not hf_token:
            print("Error: Missing HF_API_TOKEN for Hugging Face provider.", file=sys.stderr)
            sys.exit(1)

    if selected_provider == "openai":
        openai_token = (process_env.get("OPENAI_API_KEY") or process_env.get("OPENAI_TOKEN") or "").strip()
        if not openai_token:
            print("Error: Missing OPENAI_API_KEY for OpenAI provider.", file=sys.stderr)
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
        if selected_provider == "huggingface":
            completed = run_huggingface_attempt(
                model_name=model_name,
                prompt_text=full_prompt,
                env=process_env,
                timeout_seconds=HUGGINGFACE_TIMEOUT_SECONDS,
                heartbeat_seconds=GEMINI_HEARTBEAT_SECONDS,
                attempt_index=index,
                debug_log_dir=DEBUG_LOG_DIR,
                log_prefix="cv-attempt",
                emit_live_output=True,
            )
        elif selected_provider == "openai":
            completed = run_openai_attempt(
                model_name=model_name,
                prompt_text=full_prompt,
                env=process_env,
                timeout_seconds=OPENAI_TIMEOUT_SECONDS,
                heartbeat_seconds=GEMINI_HEARTBEAT_SECONDS,
                attempt_index=index,
                debug_log_dir=DEBUG_LOG_DIR,
                log_prefix="cv-attempt",
                emit_live_output=True,
            )
        elif selected_provider == "swiftlet":
            completed = run_swiftlet_attempt(
                model_name=model_name,
                prompt_text=full_prompt,
                env=process_env,
                timeout_seconds=SWIFTLET_TIMEOUT_SECONDS,
                heartbeat_seconds=GEMINI_HEARTBEAT_SECONDS,
                attempt_index=index,
                debug_log_dir=DEBUG_LOG_DIR,
                log_prefix="cv-attempt",
                emit_live_output=True,
            )
        elif selected_provider == "vscodebridge":
            completed = run_vscodebridge_attempt(
                model_name=model_name,
                prompt_text=full_prompt,
                env=process_env,
                timeout_seconds=VSCODE_BRIDGE_TIMEOUT_SECONDS,
                heartbeat_seconds=GEMINI_HEARTBEAT_SECONDS,
                attempt_index=index,
                debug_log_dir=DEBUG_LOG_DIR,
                log_prefix="cv-attempt",
                emit_live_output=True,
            )
        else:
            completed = run_gemini_attempt(
                model_name=model_name,
                prompt_text=full_prompt,
                env=process_env,
                timeout_seconds=GEMINI_TIMEOUT_SECONDS,
                heartbeat_seconds=GEMINI_HEARTBEAT_SECONDS,
                attempt_index=index,
                debug_log_dir=DEBUG_LOG_DIR,
                log_prefix="cv-attempt",
                emit_live_output=False,
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
            "inspect tailored.model-output.txt.",
            file=sys.stderr,
        )

    try:
        structured_payload = parse_and_validate_json_output(raw_model_output)
    except ValueError as exc:
        print(f"Generated output failed JSON contract validation: {exc}", file=sys.stderr)
        print(
            "Inspect tailored.model-output.txt and tailored.model.json for raw output details.",
            file=sys.stderr,
        )
        sys.exit(1)

    tailored_markdown = render_tagged_markdown(structured_payload)
    TAILORED_MD.write_text(tailored_markdown, encoding="utf-8")
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

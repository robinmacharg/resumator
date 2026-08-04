#!/usr/bin/env python3
"""
Architecture role:
- Layer: backend HTTP API and process orchestration entrypoint.
- Responsibility: serve static assets, expose JSON endpoints, validate request payloads,
    and coordinate CV/research subprocess lifecycle state.

Plain-language purpose:
- This module is the web server for the CV app. It is the bridge between frontend actions
    and backend file/process operations.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from provider_catalog import load_provider_catalog, provider_map

TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
LOG_DIR = OUTPUT_DIR / "gemini_debug_logs"
RESEARCH_COMPANY_FILE = INPUT_DIR / "research_company.txt"
RESEARCH_URLS_FILE = INPUT_DIR / "research_urls.txt"
RESEARCH_PROMPT_DEFAULT_FILE = INPUT_DIR / "research_prompt.default.md"
RESEARCH_OUTPUT_MD = OUTPUT_DIR / "research_output.md"
RESEARCH_OUTPUT_JSON = OUTPUT_DIR / "research_output.json"
RESEARCH_PROMPT_BUILT_FILE = OUTPUT_DIR / "research_prompt.built.txt"
RESEARCH_FORMATTED_MD = OUTPUT_DIR / "research_output.formatted.md"
RESEARCH_FORMATTED_PDF = OUTPUT_DIR / "research_output.formatted.pdf"

HOST = "127.0.0.1"
PORT = 8765
ENV_FILE_PATH = ROOT_DIR / ".env"
MODEL_CATALOG_PATH = ROOT_DIR / "model_providers.json"

EDITOR_FILES = {
    "cv": INPUT_DIR / "CV.md",
    "prompt": INPUT_DIR / "prompt.md",
    "research_prompt": INPUT_DIR / "research_prompt.md",
    "jobspec": INPUT_DIR / "jobspec.txt",
    "env": ROOT_DIR / ".env",
}

ALLOWED_OUTPUT_FILES = {
    "tailored_dev.pdf",
    "tailored_dev.docx",
    "tailored.md",
    "tailored.export.md",
    "tailored.docx.export.md",
    "research_output.formatted.md",
    "research_output.formatted.pdf",
}

RUN_LOCK = threading.Lock()
RUN_STATE_LOCK = threading.Lock()
LAST_RUN: dict[str, Any] = {}
CURRENT_RUN: dict[str, Any] = {}

RESEARCH_RUN_LOCK = threading.Lock()
RESEARCH_STATE_LOCK = threading.Lock()
LAST_RESEARCH_RUN: dict[str, Any] = {}
CURRENT_RESEARCH_RUN: dict[str, Any] = {}
RESEARCH_PROC_LOCK = threading.Lock()
CURRENT_RESEARCH_PROC: subprocess.Popen[str] | None = None


@dataclass(frozen=True)
class ResearchRunRequest:
    selected_provider: str
    selected_model: str
    company_name: str
    urls: list[str]
    dry_run: bool
    auto_format_pdf: bool


@dataclass(frozen=True)
class CvRunRequest:
    kind: str
    selected_provider: str
    selected_model: str


def schedule_process_restart() -> None:
    """Purpose: Execute schedule process restart for this module's workflow.
    
    Inputs:
    - None.
    
    Returns:
    - None. This function performs side effects only.
    """
    def _restart() -> None:
        # Small delay gives the HTTP response a chance to flush before process replacement.
        """Purpose: Execute restart for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        time.sleep(0.35)
        os.execv(sys.executable, [sys.executable, str(APP_DIR / "server.py")])

    threading.Thread(target=_restart, daemon=True).start()


def utc_now_iso() -> str:
    """Purpose: Execute utc now iso for this module's workflow.
    
    Inputs:
    - None.
    
    Returns:
    - `str` value representing the operation result.
    """
    return datetime.now(timezone.utc).isoformat()


def read_text(path: Path) -> str:
    """Purpose: Read text from file or runtime state.
    
    Inputs:
    - path: See type hints and call site for expected value.
    
    Returns:
    - `str` value representing the operation result.
    """
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """Purpose: Write text to the target location.
    
    Inputs:
    - path: See type hints and call site for expected value.
    - content: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def dedupe_keep_order(items: list[str]) -> list[str]:
    """Purpose: Execute dedupe keep order for this module's workflow.
    
    Inputs:
    - items: See type hints and call site for expected value.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def load_catalog() -> dict[str, Any]:
    """Purpose: Load catalog from configured source(s).
    
    Inputs:
    - None.
    
    Returns:
    - `dict[str, Any]` value representing the operation result.
    """
    return load_provider_catalog(MODEL_CATALOG_PATH)


def build_provider_options() -> list[dict[str, str]]:
    """Purpose: Build provider options from current inputs and state.
    
    Inputs:
    - None.
    
    Returns:
    - `list[dict[str, str]]` value representing the operation result.
    """
    catalog = load_catalog()
    return [
        {
            "value": item["id"],
            "label": item["label"],
            "enabled": bool(item.get("enabled", True)),
            "disabledReason": str(item.get("disabledReason") or ""),
        }
        for item in catalog.get("providers", [])
        if isinstance(item, dict) and item.get("id") and item.get("label")
    ]


def build_available_models(selected_provider: str) -> list[str]:
    """Purpose: Build available models from current inputs and state.
    
    Inputs:
    - selected_provider: See type hints and call site for expected value.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
    catalog = load_catalog()
    providers = provider_map(catalog)
    provider_entry = providers.get(selected_provider)
    if not provider_entry:
        provider_entry = providers.get(catalog.get("defaultProvider", ""))
    if not provider_entry:
        return []

    return dedupe_keep_order(
        [item for item in provider_entry.get("models", []) if isinstance(item, str)]
    )


def parse_selected_provider(payload: dict[str, Any]) -> str:
    """Purpose: Parse and validate selected provider for downstream use.
    
    Inputs:
    - payload: See type hints and call site for expected value.
    
    Returns:
    - `str` value representing the operation result.
    """
    catalog = load_catalog()
    providers = provider_map(catalog)
    all_provider_ids = [
        str(item.get("id") or "").strip()
        for item in catalog.get("providers", [])
        if isinstance(item, dict)
    ]
    enabled_provider_ids = [
        str(item.get("id") or "").strip()
        for item in catalog.get("providers", [])
        if isinstance(item, dict) and bool(item.get("enabled", True))
    ]
    default_provider = str(catalog.get("defaultProvider", "")).strip()
    if default_provider not in enabled_provider_ids:
        default_provider = enabled_provider_ids[0] if enabled_provider_ids else ""

    raw_provider = payload.get("selectedProvider", "")
    if raw_provider is None:
        return default_provider
    if not isinstance(raw_provider, str):
        raise ValueError("selectedProvider must be a string")

    selected_provider = raw_provider.strip() or default_provider
    if selected_provider not in providers or selected_provider not in all_provider_ids:
        raise ValueError("selectedProvider is not in available provider options")
    selected_entry = providers.get(selected_provider) or {}
    if not bool(selected_entry.get("enabled", True)):
        raise ValueError("selectedProvider is currently disabled")
    return selected_provider


def parse_selected_model(payload: dict[str, Any], selected_provider: str) -> str:
    """Purpose: Parse and validate selected model for downstream use.
    
    Inputs:
    - payload: See type hints and call site for expected value.
    - selected_provider: See type hints and call site for expected value.
    
    Returns:
    - `str` value representing the operation result.
    """
    raw_model = payload.get("selectedModel", "")
    if raw_model is None:
        return ""
    if not isinstance(raw_model, str):
        raise ValueError("selectedModel must be a string")

    selected_model = raw_model.strip()
    if not selected_model:
        return ""

    available = build_available_models(selected_provider)
    if selected_model not in available:
        raise ValueError("selectedModel is not in available model options")
    return selected_model


def parse_company_name(payload: dict[str, Any]) -> str:
    """Purpose: Parse and validate company name for downstream use.
    
    Inputs:
    - payload: See type hints and call site for expected value.
    
    Returns:
    - `str` value representing the operation result.
    """
    company_name = str(payload.get("companyName", "")).strip()
    if not company_name:
        raise ValueError("companyName is required")
    return company_name


def parse_url_list(payload: dict[str, Any]) -> list[str]:
    """Purpose: Parse and validate url list for downstream use.
    
    Inputs:
    - payload: See type hints and call site for expected value.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
    raw_urls = payload.get("urls", [])
    if not isinstance(raw_urls, list):
        raise ValueError("urls must be a list of strings")

    urls: list[str] = []
    for idx, item in enumerate(raw_urls):
        if not isinstance(item, str):
            raise ValueError(f"urls[{idx}] must be a string")
        cleaned = item.strip()
        if cleaned:
            urls.append(cleaned)
    return urls


def parse_auto_format_pdf(payload: dict[str, Any]) -> bool:
    """Purpose: Parse and validate auto format pdf for downstream use.
    
    Inputs:
    - payload: See type hints and call site for expected value.
    
    Returns:
    - `bool` value representing the operation result.
    """
    auto_format_pdf = payload.get("autoFormatPdf", True)
    if not isinstance(auto_format_pdf, bool):
        raise ValueError("autoFormatPdf must be a boolean")
    return auto_format_pdf


def parse_research_run_request(payload: dict[str, Any]) -> ResearchRunRequest:
    """Purpose: Parse and validate research run request for downstream use.
    
    Inputs:
    - payload: See type hints and call site for expected value.
    
    Returns:
    - `ResearchRunRequest` value representing the operation result.
    """
    selected_provider = parse_selected_provider(payload)
    selected_model = parse_selected_model(payload, selected_provider)
    company_name = parse_company_name(payload)
    urls = parse_url_list(payload)
    dry_run = bool(payload.get("dryRun", False))
    auto_format_pdf = parse_auto_format_pdf(payload)

    return ResearchRunRequest(
        selected_provider=selected_provider,
        selected_model=selected_model,
        company_name=company_name,
        urls=urls,
        dry_run=dry_run,
        auto_format_pdf=auto_format_pdf,
    )


def parse_cv_run_request(route: str, payload: dict[str, Any]) -> CvRunRequest:
    """Purpose: Parse and validate cv run request for downstream use.
    
    Inputs:
    - route: See type hints and call site for expected value.
    - payload: See type hints and call site for expected value.
    
    Returns:
    - `CvRunRequest` value representing the operation result.
    """
    kind = "full" if route.endswith("/full") else "format"
    selected_provider = parse_selected_provider(payload)
    selected_model = parse_selected_model(payload, selected_provider)
    model_override = selected_model if kind == "full" else ""
    return CvRunRequest(
        kind=kind,
        selected_provider=selected_provider,
        selected_model=model_override,
    )


def file_mtime(path: Path) -> float | None:
    """Purpose: Execute file mtime for this module's workflow.
    
    Inputs:
    - path: See type hints and call site for expected value.
    
    Returns:
    - `float | None` value representing the operation result.
    """
    if not path.exists():
        return None
    return path.stat().st_mtime


def build_state() -> dict[str, Any]:
    """Purpose: Build state from current inputs and state.
    
    Inputs:
    - None.
    
    Returns:
    - `dict[str, Any]` value representing the operation result.
    """
    files = {key: read_text(path) for key, path in EDITOR_FILES.items()}
    output_pdf = OUTPUT_DIR / "tailored_dev.pdf"
    output_docx = OUTPUT_DIR / "tailored_dev.docx"
    catalog = load_catalog()
    provider_options = build_provider_options()
    enabled_options = [item for item in provider_options if item.get("enabled", True)]
    default_provider = str(catalog.get("defaultProvider", "")).strip()
    if default_provider not in {item["value"] for item in enabled_options}:
        default_provider = enabled_options[0]["value"] if enabled_options else ""
    models_by_provider = {
        item["value"]: build_available_models(item["value"])
        for item in provider_options
    }
    return {
        "files": files,
        "providers": {
            "defaultProvider": default_provider,
            "options": provider_options,
        },
        "models": {
            "defaultOptionValue": "",
            "defaultOptionLabel": "Default order",
            "byProvider": models_by_provider,
        },
        "outputs": {
            "pdfExists": output_pdf.exists(),
            "docxExists": output_docx.exists(),
            "pdfMtime": file_mtime(output_pdf),
            "docxMtime": file_mtime(output_docx),
        },
        "lastRun": LAST_RUN,
    }


def read_research_urls(path: Path) -> list[str]:
    """Purpose: Read research urls from file or runtime state.
    
    Inputs:
    - path: See type hints and call site for expected value.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
    if not path.exists():
        return []

    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def build_research_state() -> dict[str, Any]:
    """Purpose: Build research state from current inputs and state.
    
    Inputs:
    - None.
    
    Returns:
    - `dict[str, Any]` value representing the operation result.
    """
    company_name = read_text(RESEARCH_COMPANY_FILE).strip()
    output_md_mtime = file_mtime(RESEARCH_OUTPUT_MD)
    output_json_mtime = file_mtime(RESEARCH_OUTPUT_JSON)
    built_prompt_mtime = file_mtime(RESEARCH_PROMPT_BUILT_FILE)
    formatted_md_mtime = file_mtime(RESEARCH_FORMATTED_MD)
    formatted_pdf_mtime = file_mtime(RESEARCH_FORMATTED_PDF)

    return {
        "companyName": company_name,
        "urls": read_research_urls(RESEARCH_URLS_FILE),
        "output": {
            "markdown": read_text(RESEARCH_OUTPUT_MD),
            "json": read_text(RESEARCH_OUTPUT_JSON),
            "markdownMtime": output_md_mtime,
            "jsonMtime": output_json_mtime,
            "builtPrompt": read_text(RESEARCH_PROMPT_BUILT_FILE),
            "builtPromptExists": RESEARCH_PROMPT_BUILT_FILE.exists(),
            "builtPromptMtime": built_prompt_mtime,
            "formattedMarkdownExists": RESEARCH_FORMATTED_MD.exists(),
            "formattedPdfExists": RESEARCH_FORMATTED_PDF.exists(),
            "formattedMarkdownMtime": formatted_md_mtime,
            "formattedPdfMtime": formatted_pdf_mtime,
        },
        "lastRun": LAST_RESEARCH_RUN,
    }


def collect_log_index(limit: int = 20) -> list[dict[str, Any]]:
    """Purpose: Execute collect log index for this module's workflow.
    
    Inputs:
    - limit: See type hints and call site for expected value.
    
    Returns:
    - `list[dict[str, Any]]` value representing the operation result.
    """
    if not LOG_DIR.exists():
        return []

    logs = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    indexed: list[dict[str, Any]] = []
    for path in logs[:limit]:
        stat = path.stat()
        indexed.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )
    return indexed


def read_log_file(name: str) -> str:
    """Purpose: Read log file from file or runtime state.
    
    Inputs:
    - name: See type hints and call site for expected value.
    
    Returns:
    - `str` value representing the operation result.
    """
    if "/" in name or "\\" in name:
        raise ValueError("Invalid log file name")

    path = LOG_DIR / name
    if not path.exists() or path.suffix != ".log":
        raise FileNotFoundError(name)

    return path.read_text(encoding="utf-8", errors="replace")


def make_command(kind: str, selected_provider: str = "", selected_model: str = "") -> list[str]:
    """Purpose: Execute make command for this module's workflow.
    
    Inputs:
    - kind: See type hints and call site for expected value.
    - selected_provider: See type hints and call site for expected value.
    - selected_model: See type hints and call site for expected value.
    
    Returns:
    - `list[str]` value representing the operation result.
    """
    if kind == "full":
        command = [sys.executable, str(ROOT_DIR / "generate_cv.py")]
        if selected_provider:
            command.extend(["--provider", selected_provider])
        if selected_model:
            command.extend(["--model", selected_model])
        return command
    elif kind == "format":
        return [
            sys.executable,
            str(ROOT_DIR / "cv_convert.py"),
            "output/tailored.md",
            "--pdf",
            "output/tailored_dev.pdf",
            "--docx",
            "output/tailored_dev.docx",
        ]

    raise ValueError(f"Unsupported run kind: {kind}")


def _run_output_mtimes() -> dict[str, float | None]:
    """Purpose: Run output mtimes and return its outcome.
    
    Inputs:
    - None.
    
    Returns:
    - `dict[str, float | None]` value representing the operation result.
    """
    return {
        "pdfMtime": file_mtime(OUTPUT_DIR / "tailored_dev.pdf"),
        "docxMtime": file_mtime(OUTPUT_DIR / "tailored_dev.docx"),
    }


def _build_run_state(
    *,
    kind: str,
    command: list[str],
    selected_provider: str,
    selected_model: str,
    exit_code: int | None,
    started_at: str,
    finished_at: str | None,
    elapsed_seconds: float,
    success: bool | None,
    running: bool,
    output: str,
    started_monotonic: float | None = None,
) -> dict[str, Any]:
    """Purpose: Build run state from current inputs and state.
    
    Inputs:
    - kind: See type hints and call site for expected value.
    - command: See type hints and call site for expected value.
    - selected_provider: See type hints and call site for expected value.
    - selected_model: See type hints and call site for expected value.
    - exit_code: See type hints and call site for expected value.
    - started_at: See type hints and call site for expected value.
    - finished_at: See type hints and call site for expected value.
    - elapsed_seconds: See type hints and call site for expected value.
    - success: See type hints and call site for expected value.
    - running: See type hints and call site for expected value.
    - output: See type hints and call site for expected value.
    - started_monotonic: See type hints and call site for expected value.
    
    Returns:
    - `dict[str, Any]` value representing the operation result.
    """
    run_state: dict[str, Any] = {
        "kind": kind,
        "command": command,
        "exitCode": exit_code,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "elapsedSeconds": elapsed_seconds,
        "success": success,
        "running": running,
        "output": output,
        "selectedProvider": selected_provider,
        "selectedModel": selected_model,
    }
    run_state.update(_run_output_mtimes())
    if started_monotonic is not None:
        run_state["_startedMonotonic"] = started_monotonic
    return run_state


def get_current_run_snapshot() -> dict[str, Any] | None:
    """Purpose: Return current run snapshot for callers.
    
    Inputs:
    - None.
    
    Returns:
    - `dict[str, Any] | None` value representing the operation result.
    """
    with RUN_STATE_LOCK:
        if not CURRENT_RUN:
            return None

        snapshot = {
            key: value
            for key, value in CURRENT_RUN.items()
            if not key.startswith("_")
        }

        started_monotonic = CURRENT_RUN.get("_startedMonotonic")
        if isinstance(started_monotonic, float) and snapshot.get("running"):
            snapshot["elapsedSeconds"] = round(time.monotonic() - started_monotonic, 2)

        return snapshot


def set_current_run(run_state: dict[str, Any]) -> None:
    """Purpose: Update current run with provided values.
    
    Inputs:
    - run_state: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    with RUN_STATE_LOCK:
        CURRENT_RUN.clear()
        CURRENT_RUN.update(run_state)


def append_current_run_output(chunk: str) -> None:
    """Purpose: Execute append current run output for this module's workflow.
    
    Inputs:
    - chunk: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    if not chunk:
        return

    with RUN_STATE_LOCK:
        if not CURRENT_RUN:
            return

        existing = CURRENT_RUN.get("output", "")
        CURRENT_RUN["output"] = existing + chunk


def finalize_current_run(return_code: int) -> dict[str, Any] | None:
    """Purpose: Execute finalize current run for this module's workflow.
    
    Inputs:
    - return_code: See type hints and call site for expected value.
    
    Returns:
    - `dict[str, Any] | None` value representing the operation result.
    """
    with RUN_STATE_LOCK:
        if not CURRENT_RUN:
            return None

        started_monotonic = CURRENT_RUN.get("_startedMonotonic")
        elapsed = round(time.monotonic() - started_monotonic, 2) if isinstance(started_monotonic, float) else 0.0

        CURRENT_RUN["running"] = False
        CURRENT_RUN["exitCode"] = return_code
        CURRENT_RUN["finishedAt"] = utc_now_iso()
        CURRENT_RUN["elapsedSeconds"] = elapsed
        CURRENT_RUN["success"] = return_code == 0
        CURRENT_RUN["pdfMtime"] = file_mtime(OUTPUT_DIR / "tailored_dev.pdf")
        CURRENT_RUN["docxMtime"] = file_mtime(OUTPUT_DIR / "tailored_dev.docx")

        snapshot = {
            key: value
            for key, value in CURRENT_RUN.items()
            if not key.startswith("_")
        }
        CURRENT_RUN.clear()

    LAST_RUN.clear()
    LAST_RUN.update(snapshot)
    return snapshot


def get_current_research_run_snapshot() -> dict[str, Any] | None:
    """Purpose: Return current research run snapshot for callers.
    
    Inputs:
    - None.
    
    Returns:
    - `dict[str, Any] | None` value representing the operation result.
    """
    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN:
            return None

        snapshot = {
            key: value
            for key, value in CURRENT_RESEARCH_RUN.items()
            if not key.startswith("_")
        }

        started_monotonic = CURRENT_RESEARCH_RUN.get("_startedMonotonic")
        if isinstance(started_monotonic, float) and snapshot.get("running"):
            snapshot["elapsedSeconds"] = round(time.monotonic() - started_monotonic, 2)

        return snapshot


def set_current_research_run(run_state: dict[str, Any]) -> None:
    """Purpose: Update current research run with provided values.
    
    Inputs:
    - run_state: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    with RESEARCH_STATE_LOCK:
        CURRENT_RESEARCH_RUN.clear()
        CURRENT_RESEARCH_RUN.update(run_state)


def set_current_research_proc(proc: subprocess.Popen[str] | None) -> None:
    """Purpose: Update current research proc with provided values.
    
    Inputs:
    - proc: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    with RESEARCH_PROC_LOCK:
        global CURRENT_RESEARCH_PROC
        CURRENT_RESEARCH_PROC = proc


def get_current_research_proc() -> subprocess.Popen[str] | None:
    """Purpose: Return current research proc for callers.
    
    Inputs:
    - None.
    
    Returns:
    - `subprocess.Popen[str] | None` value representing the operation result.
    """
    with RESEARCH_PROC_LOCK:
        return CURRENT_RESEARCH_PROC


def append_current_research_output(chunk: str) -> None:
    """Purpose: Execute append current research output for this module's workflow.
    
    Inputs:
    - chunk: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    if not chunk:
        return

    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN:
            return

        existing = CURRENT_RESEARCH_RUN.get("output", "")
        CURRENT_RESEARCH_RUN["output"] = existing + chunk


def update_current_research_run_fields(**fields: Any) -> None:
    """Purpose: Execute update current research run fields for this module's workflow.
    
    Inputs:
    - **fields: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN:
            return
        CURRENT_RESEARCH_RUN.update(fields)


def run_research_format_for_active_run_streaming() -> int:
    """Purpose: Run research format for active run streaming and return its outcome.
    
    Inputs:
    - None.
    
    Returns:
    - `int` value representing the operation result.
    """
    command = [
        sys.executable,
        str(ROOT_DIR / "research_format.py"),
    ]

    append_current_research_output("Auto-formatting research PDF...\n")
    append_current_research_output(
        f"Formatting command: {' '.join(command)}\n"
    )

    proc = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    stdout_thread = threading.Thread(target=stream_pipe_research, args=(proc.stdout,), daemon=True)
    stderr_thread = threading.Thread(
        target=stream_pipe_research,
        args=(proc.stderr, "[stderr] "),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    return_code = proc.wait()
    stdout_thread.join()
    stderr_thread.join()
    return return_code


def finalize_current_research_run(return_code: int) -> dict[str, Any] | None:
    """Purpose: Execute finalize current research run for this module's workflow.
    
    Inputs:
    - return_code: See type hints and call site for expected value.
    
    Returns:
    - `dict[str, Any] | None` value representing the operation result.
    """
    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN:
            return None

        started_monotonic = CURRENT_RESEARCH_RUN.get("_startedMonotonic")
        elapsed = round(time.monotonic() - started_monotonic, 2) if isinstance(started_monotonic, float) else 0.0

        CURRENT_RESEARCH_RUN["running"] = False
        CURRENT_RESEARCH_RUN["exitCode"] = return_code
        CURRENT_RESEARCH_RUN["finishedAt"] = utc_now_iso()
        CURRENT_RESEARCH_RUN["elapsedSeconds"] = elapsed
        CURRENT_RESEARCH_RUN["success"] = return_code == 0
        CURRENT_RESEARCH_RUN["stoppedByUser"] = bool(CURRENT_RESEARCH_RUN.get("stopRequested", False))
        CURRENT_RESEARCH_RUN["formattedPdfMtime"] = file_mtime(RESEARCH_FORMATTED_PDF)

        snapshot = {
            key: value
            for key, value in CURRENT_RESEARCH_RUN.items()
            if not key.startswith("_")
        }
        CURRENT_RESEARCH_RUN.clear()

    LAST_RESEARCH_RUN.clear()
    LAST_RESEARCH_RUN.update(snapshot)
    return snapshot


def _finalize_run_error_state(run_state: dict[str, Any]) -> None:
    """Purpose: Execute finalize run error state for this module's workflow.
    
    Inputs:
    - run_state: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    set_current_run(run_state)
    snapshot = get_current_run_snapshot()
    if snapshot is not None:
        LAST_RUN.clear()
        LAST_RUN.update(snapshot)
        with RUN_STATE_LOCK:
            CURRENT_RUN.clear()


def _finalize_research_run_error_state(run_state: dict[str, Any]) -> None:
    """Purpose: Execute finalize research run error state for this module's workflow.
    
    Inputs:
    - run_state: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    set_current_research_run(run_state)
    snapshot = get_current_research_run_snapshot()
    if snapshot is not None:
        LAST_RESEARCH_RUN.clear()
        LAST_RESEARCH_RUN.update(snapshot)
        with RESEARCH_STATE_LOCK:
            CURRENT_RESEARCH_RUN.clear()


def request_stop_research_run() -> bool:
    """Purpose: Execute request stop research run for this module's workflow.
    
    Inputs:
    - None.
    
    Returns:
    - `bool` value representing the operation result.
    """
    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN or not CURRENT_RESEARCH_RUN.get("running"):
            return False
        CURRENT_RESEARCH_RUN["stopRequested"] = True

    proc = get_current_research_proc()
    if proc is None:
        return False

    append_current_research_output("Stop requested by user. Terminating research process...\n")

    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            return False

    return True


def stream_pipe(pipe, prefix: str = "") -> None:
    """Purpose: Execute stream pipe for this module's workflow.
    
    Inputs:
    - pipe: See type hints and call site for expected value.
    - prefix: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    try:
        for line in iter(pipe.readline, ""):
            append_current_run_output(f"{prefix}{line}")
    finally:
        pipe.close()


def stream_pipe_research(pipe, prefix: str = "") -> None:
    """Purpose: Execute stream pipe research for this module's workflow.
    
    Inputs:
    - pipe: See type hints and call site for expected value.
    - prefix: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    try:
        for line in iter(pipe.readline, ""):
            append_current_research_output(f"{prefix}{line}")
    finally:
        pipe.close()


def run_subprocess_streaming(kind: str, selected_provider: str = "", selected_model: str = "") -> dict[str, Any]:
    """Purpose: Run subprocess streaming and return its outcome.
    
    Inputs:
    - kind: See type hints and call site for expected value.
    - selected_provider: See type hints and call site for expected value.
    - selected_model: See type hints and call site for expected value.
    
    Returns:
    - `dict[str, Any]` value representing the operation result.
    """
    command = make_command(kind, selected_provider=selected_provider, selected_model=selected_model)

    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    set_current_run(
        _build_run_state(
            kind=kind,
            command=command,
            selected_provider=selected_provider,
            selected_model=selected_model,
            exit_code=None,
            started_at=started_at,
            finished_at=None,
            elapsed_seconds=0.0,
            success=None,
            running=True,
            output="",
            started_monotonic=started_monotonic,
        )
    )

    proc = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    stdout_thread = threading.Thread(target=stream_pipe, args=(proc.stdout,), daemon=True)
    stderr_thread = threading.Thread(target=stream_pipe, args=(proc.stderr, "[stderr] "), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    return_code = proc.wait()
    stdout_thread.join()
    stderr_thread.join()

    run_result = finalize_current_run(return_code)
    if run_result is None:
        raise RuntimeError("Run completed but no run state was available.")

    return run_result


def run_subprocess_async(kind: str, selected_provider: str = "", selected_model: str = "") -> None:
    """Purpose: Run subprocess async and return its outcome.
    
    Inputs:
    - kind: See type hints and call site for expected value.
    - selected_provider: See type hints and call site for expected value.
    - selected_model: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    try:
        run_subprocess_streaming(kind, selected_provider=selected_provider, selected_model=selected_model)
    except Exception as exc:
        _finalize_run_error_state(
            _build_run_state(
                kind=kind,
                command=make_command(kind, selected_provider=selected_provider, selected_model=selected_model),
                selected_provider=selected_provider,
                selected_model=selected_model,
                exit_code=1,
                started_at=utc_now_iso(),
                finished_at=utc_now_iso(),
                elapsed_seconds=0.0,
                success=False,
                running=False,
                output=f"Wrapper failed to execute run: {exc}",
            )
        )
    finally:
        RUN_LOCK.release()


def run_research_subprocess_streaming(
    company_name: str,
    urls: list[str],
    dry_run: bool,
    auto_format_pdf: bool,
    selected_provider: str = "",
    selected_model: str = "",
) -> dict[str, Any]:
    """Purpose: Run research subprocess streaming and return its outcome.
    
    Inputs:
    - company_name: See type hints and call site for expected value.
    - urls: See type hints and call site for expected value.
    - dry_run: See type hints and call site for expected value.
    - auto_format_pdf: See type hints and call site for expected value.
    - selected_provider: See type hints and call site for expected value.
    - selected_model: See type hints and call site for expected value.
    
    Returns:
    - `dict[str, Any]` value representing the operation result.
    """
    command = [
        sys.executable,
        str(ROOT_DIR / "research_role.py"),
        "--company-name",
        company_name,
    ]
    if selected_model:
        command.extend(["--model", selected_model])
    if selected_provider:
        command.extend(["--provider", selected_provider])
    for url in urls:
        command.extend(["--url", url])
    if dry_run:
        command.append("--dry-run")

    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    set_current_research_run(
        {
            "kind": "research",
            "command": command,
            "companyName": company_name,
            "urls": urls,
            "dryRun": dry_run,
            "exitCode": None,
            "startedAt": started_at,
            "finishedAt": None,
            "elapsedSeconds": 0.0,
            "success": None,
            "running": True,
            "output": "",
            "autoFormatPdf": auto_format_pdf,
            "formatAttempted": False,
            "formatSuccess": None,
            "formatExitCode": None,
            "selectedProvider": selected_provider,
            "selectedModel": selected_model,
            "_startedMonotonic": started_monotonic,
        }
    )

    proc = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    set_current_research_proc(proc)

    stdout_thread = threading.Thread(target=stream_pipe_research, args=(proc.stdout,), daemon=True)
    stderr_thread = threading.Thread(target=stream_pipe_research, args=(proc.stderr, "[stderr] "), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    try:
        return_code = proc.wait()
        stdout_thread.join()
        stderr_thread.join()
    finally:
        set_current_research_proc(None)

    if return_code == 0 and not dry_run and auto_format_pdf:
        format_exit_code = run_research_format_for_active_run_streaming()
        format_success = format_exit_code == 0
        update_current_research_run_fields(
            formatAttempted=True,
            formatSuccess=format_success,
            formatExitCode=format_exit_code,
        )
        if format_success:
            append_current_research_output("Research PDF formatting complete.\n")
        else:
            append_current_research_output(
                "[stderr] Research succeeded, but PDF auto-format failed. "
                "Use Format Research PDF to retry.\n"
            )
    else:
        update_current_research_run_fields(
            formatAttempted=False,
            formatSuccess=None,
            formatExitCode=None,
        )

    run_result = finalize_current_research_run(return_code)
    if run_result is None:
        raise RuntimeError("Research run completed but no run state was available.")

    return run_result


def run_research_format_subprocess_streaming() -> dict[str, Any]:
    """Purpose: Run research format subprocess streaming and return its outcome.
    
    Inputs:
    - None.
    
    Returns:
    - `dict[str, Any]` value representing the operation result.
    """
    command = [
        sys.executable,
        str(ROOT_DIR / "research_format.py"),
    ]

    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    set_current_research_run(
        {
            "kind": "research_format",
            "command": command,
            "companyName": "",
            "urls": [],
            "dryRun": False,
            "exitCode": None,
            "startedAt": started_at,
            "finishedAt": None,
            "elapsedSeconds": 0.0,
            "success": None,
            "running": True,
            "output": "",
            "formattedPdfMtime": file_mtime(RESEARCH_FORMATTED_PDF),
            "_startedMonotonic": started_monotonic,
        }
    )

    proc = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    set_current_research_proc(proc)

    stdout_thread = threading.Thread(target=stream_pipe_research, args=(proc.stdout,), daemon=True)
    stderr_thread = threading.Thread(target=stream_pipe_research, args=(proc.stderr, "[stderr] "), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    try:
        return_code = proc.wait()
        stdout_thread.join()
        stderr_thread.join()
    finally:
        set_current_research_proc(None)

    run_result = finalize_current_research_run(return_code)
    if run_result is None:
        raise RuntimeError("Research format completed but no run state was available.")

    run_result["formattedPdfMtime"] = file_mtime(RESEARCH_FORMATTED_PDF)
    LAST_RESEARCH_RUN.clear()
    LAST_RESEARCH_RUN.update(run_result)
    return run_result


def run_research_subprocess_async(
    company_name: str,
    urls: list[str],
    dry_run: bool,
    auto_format_pdf: bool,
    selected_provider: str = "",
    selected_model: str = "",
) -> None:
    """Purpose: Run research subprocess async and return its outcome.
    
    Inputs:
    - company_name: See type hints and call site for expected value.
    - urls: See type hints and call site for expected value.
    - dry_run: See type hints and call site for expected value.
    - auto_format_pdf: See type hints and call site for expected value.
    - selected_provider: See type hints and call site for expected value.
    - selected_model: See type hints and call site for expected value.
    
    Returns:
    - None. This function performs side effects only.
    """
    try:
        run_research_subprocess_streaming(
            company_name=company_name,
            urls=urls,
            dry_run=dry_run,
            auto_format_pdf=auto_format_pdf,
            selected_provider=selected_provider,
            selected_model=selected_model,
        )
    except Exception as exc:
        _finalize_research_run_error_state(
            {
                "kind": "research",
                "command": [],
                "companyName": company_name,
                "urls": urls,
                "dryRun": dry_run,
                "autoFormatPdf": auto_format_pdf,
                "selectedProvider": selected_provider,
                "selectedModel": selected_model,
                "exitCode": 1,
                "startedAt": utc_now_iso(),
                "finishedAt": utc_now_iso(),
                "elapsedSeconds": 0.0,
                "success": False,
                "running": False,
                "output": f"Wrapper failed to execute research run: {exc}",
            }
        )
    finally:
        RESEARCH_RUN_LOCK.release()


def run_research_format_subprocess_async() -> None:
    """Purpose: Run research format subprocess async and return its outcome.
    
    Inputs:
    - None.
    
    Returns:
    - None. This function performs side effects only.
    """
    try:
        run_research_format_subprocess_streaming()
    except Exception as exc:
        _finalize_research_run_error_state(
            {
                "kind": "research_format",
                "command": [sys.executable, str(ROOT_DIR / "research_format.py")],
                "companyName": "",
                "urls": [],
                "dryRun": False,
                "exitCode": 1,
                "startedAt": utc_now_iso(),
                "finishedAt": utc_now_iso(),
                "elapsedSeconds": 0.0,
                "success": False,
                "running": False,
                "output": f"Wrapper failed to execute research format: {exc}",
                "formattedPdfMtime": file_mtime(RESEARCH_FORMATTED_PDF),
            }
        )
    finally:
        RESEARCH_RUN_LOCK.release()


class CVWebHandler(BaseHTTPRequestHandler):
    """HTTP request handler for static assets and CV/research JSON API routes."""

    server_version = "CVWebWrapper/1.0"

    def _json_response(self, payload: Any, status: int = 200) -> None:
        """Purpose: Execute json response for this module's workflow.
        
        Inputs:
        - payload: See type hints and call site for expected value.
        - status: See type hints and call site for expected value.
        
        Returns:
        - None. This function performs side effects only.
        """
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text_response(self, text: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
        """Purpose: Execute text response for this module's workflow.
        
        Inputs:
        - text: See type hints and call site for expected value.
        - status: See type hints and call site for expected value.
        - content_type: See type hints and call site for expected value.
        
        Returns:
        - None. This function performs side effects only.
        """
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path, content_type: str) -> None:
        """Purpose: Execute serve file for this module's workflow.
        
        Inputs:
        - path: See type hints and call site for expected value.
        - content_type: See type hints and call site for expected value.
        
        Returns:
        - None. This function performs side effects only.
        """
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if path.suffix == ".pdf":
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(data)

    def _parse_json_body(self) -> dict[str, Any]:
        """Purpose: Parse and validate json body for downstream use.
        
        Inputs:
        - None.
        
        Returns:
        - `dict[str, Any]` value representing the operation result.
        """
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON body")

    def _save_editor_payload(
        self,
        payload: dict[str, Any],
        *,
        allowed_keys: set[str] | None = None,
    ) -> None:
        """Purpose: Execute save editor payload for this module's workflow.
        
        Inputs:
        - payload: See type hints and call site for expected value.
        - allowed_keys: See type hints and call site for expected value.
        
        Returns:
        - None. This function performs side effects only.
        """
        files = payload.get("files", {})
        if not isinstance(files, dict):
            raise ValueError("'files' must be an object")

        for key, path in EDITOR_FILES.items():
            if allowed_keys is not None and key not in allowed_keys:
                continue
            if key in files:
                value = files[key]
                if not isinstance(value, str):
                    raise ValueError(f"File content for '{key}' must be a string")
                write_text(path, value)

    def _handle_save(self, payload: dict[str, Any]) -> None:
        """Purpose: Execute handle save for this module's workflow.
        
        Inputs:
        - payload: See type hints and call site for expected value.
        
        Returns:
        - None. This function performs side effects only.
        """
        try:
            self._save_editor_payload(payload)
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
            return
        self._json_response({"success": True, "savedAt": utc_now_iso(), "state": build_state()})

    def _handle_server_restart(self) -> None:
        """Purpose: Execute handle server restart for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        schedule_process_restart()
        self._json_response({"success": True, "restarting": True, "requestedAt": utc_now_iso()})

    def _handle_research_reset_prompt(self) -> None:
        """Purpose: Execute handle research reset prompt for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        if not RESEARCH_PROMPT_DEFAULT_FILE.exists():
            self._json_response(
                {"error": f"Default research prompt not found: {RESEARCH_PROMPT_DEFAULT_FILE.name}"},
                status=404,
            )
            return

        write_text(EDITOR_FILES["research_prompt"], read_text(RESEARCH_PROMPT_DEFAULT_FILE))
        self._json_response(
            {
                "success": True,
                "resetAt": utc_now_iso(),
                "state": build_research_state(),
            }
        )

    def _handle_research_run(self, payload: dict[str, Any]) -> None:
        """Purpose: Execute handle research run for this module's workflow.
        
        Inputs:
        - payload: See type hints and call site for expected value.
        
        Returns:
        - None. This function performs side effects only.
        """
        try:
            self._save_editor_payload(
                payload,
                allowed_keys={"cv", "prompt", "research_prompt", "jobspec"},
            )
            req = parse_research_run_request(payload)
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
            return

        prompt_text = read_text(EDITOR_FILES["research_prompt"]).strip()
        if not prompt_text and RESEARCH_PROMPT_DEFAULT_FILE.exists():
            default_prompt_text = read_text(RESEARCH_PROMPT_DEFAULT_FILE)
            if default_prompt_text.strip():
                write_text(EDITOR_FILES["research_prompt"], default_prompt_text)
                prompt_text = default_prompt_text.strip()

        if not prompt_text:
            self._json_response(
                {
                    "error": (
                        "Research prompt is empty. Reset prompt from default or save prompt content "
                        "before running research."
                    )
                },
                status=400,
            )
            return

        if not RESEARCH_RUN_LOCK.acquire(blocking=False):
            self._json_response({"error": "A research run is already in progress"}, status=409)
            return

        try:
            thread = threading.Thread(
                target=run_research_subprocess_async,
                args=(
                    req.company_name,
                    req.urls,
                    req.dry_run,
                    req.auto_format_pdf,
                    req.selected_provider,
                    req.selected_model,
                ),
                daemon=True,
            )
            thread.start()
        except Exception as exc:
            RESEARCH_RUN_LOCK.release()
            self._json_response({"error": f"Failed to start research run: {exc}"}, status=500)
            return

        self._json_response(
            {
                "success": True,
                "running": True,
                "run": get_current_research_run_snapshot(),
                "state": build_research_state(),
            }
        )

    def _handle_research_format(self) -> None:
        """Purpose: Execute handle research format for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        if not RESEARCH_RUN_LOCK.acquire(blocking=False):
            self._json_response({"error": "A research operation is already in progress"}, status=409)
            return

        try:
            thread = threading.Thread(target=run_research_format_subprocess_async, daemon=True)
            thread.start()
        except Exception as exc:
            RESEARCH_RUN_LOCK.release()
            self._json_response({"error": f"Failed to start research format: {exc}"}, status=500)
            return

        self._json_response(
            {
                "success": True,
                "running": True,
                "run": get_current_research_run_snapshot(),
                "state": build_research_state(),
            }
        )

    def _handle_research_stop(self) -> None:
        """Purpose: Execute handle research stop for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        snapshot = get_current_research_run_snapshot()
        if not snapshot or not snapshot.get("running"):
            self._json_response({"error": "No active research run to stop"}, status=409)
            return

        if not request_stop_research_run():
            self._json_response({"error": "Unable to stop active research run"}, status=500)
            return

        self._json_response(
            {
                "success": True,
                "stopping": True,
                "run": get_current_research_run_snapshot(),
            }
        )

    def _handle_cv_run(self, route: str, payload: dict[str, Any]) -> None:
        """Purpose: Execute handle cv run for this module's workflow.
        
        Inputs:
        - route: See type hints and call site for expected value.
        - payload: See type hints and call site for expected value.
        
        Returns:
        - None. This function performs side effects only.
        """
        try:
            self._save_editor_payload(
                payload,
                allowed_keys={"cv", "prompt", "research_prompt", "jobspec"},
            )
            req = parse_cv_run_request(route, payload)
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
            return

        if not RUN_LOCK.acquire(blocking=False):
            self._json_response({"error": "A run is already in progress"}, status=409)
            return

        try:
            thread = threading.Thread(
                target=run_subprocess_async,
                args=(req.kind, req.selected_provider, req.selected_model),
                daemon=True,
            )
            thread.start()
        except Exception as exc:
            RUN_LOCK.release()
            self._json_response({"error": f"Failed to start run: {exc}"}, status=500)
            return

        self._json_response(
            {
                "success": True,
                "running": True,
                "run": get_current_run_snapshot(),
                "state": build_state(),
            }
        )

    def _handle_static_get(self, route: str) -> bool:
        """Purpose: Execute handle static get for this module's workflow.
        
        Inputs:
        - route: See type hints and call site for expected value.
        
        Returns:
        - `bool` value representing the operation result.
        """
        if not route.startswith("/static/"):
            return False

        rel = route.removeprefix("/static/")
        if rel == "styles.css":
            self._serve_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return True
        if rel.startswith("styles/") and rel.endswith(".css"):
            css_path = STATIC_DIR / rel
            try:
                css_path.resolve().relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown static file")
                return True
            self._serve_file(css_path, "text/css; charset=utf-8")
            return True
        if rel.startswith("js/") and rel.endswith(".js"):
            js_path = STATIC_DIR / rel
            try:
                js_path.resolve().relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown static file")
                return True
            self._serve_file(js_path, "application/javascript; charset=utf-8")
            return True
        if rel == "app.js":
            self._serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return True

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown static file")
        return True

    def _handle_api_run_status_get(self) -> None:
        """Purpose: Execute handle api run status get for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        current = get_current_run_snapshot()
        run_payload = current if current is not None else (LAST_RUN if LAST_RUN else None)
        self._json_response(
            {
                "running": bool(current and current.get("running")),
                "run": run_payload,
            }
        )

    def _handle_api_research_status_get(self) -> None:
        """Purpose: Execute handle api research status get for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        current = get_current_research_run_snapshot()
        run_payload = current if current is not None else (LAST_RESEARCH_RUN if LAST_RESEARCH_RUN else None)
        self._json_response(
            {
                "running": bool(current and current.get("running")),
                "run": run_payload,
            }
        )

    def _handle_logs_content_get(self, parsed) -> None:
        """Purpose: Execute handle logs content get for this module's workflow.
        
        Inputs:
        - parsed: See type hints and call site for expected value.
        
        Returns:
        - None. This function performs side effects only.
        """
        query = parse_qs(parsed.query)
        name = (query.get("name") or [""])[0]
        if not name:
            self._json_response({"error": "Missing log file name"}, status=400)
            return
        try:
            content = read_log_file(name)
        except FileNotFoundError:
            self._json_response({"error": "Log file not found"}, status=404)
            return
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
            return
        self._json_response({"name": name, "content": content})

    def _handle_output_get(self, route: str) -> bool:
        """Purpose: Execute handle output get for this module's workflow.
        
        Inputs:
        - route: See type hints and call site for expected value.
        
        Returns:
        - `bool` value representing the operation result.
        """
        if not route.startswith("/output/"):
            return False

        name = route.removeprefix("/output/")
        if name not in ALLOWED_OUTPUT_FILES:
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown output file")
            return True
        output_path = OUTPUT_DIR / name
        content_type = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get(output_path.suffix, "text/plain; charset=utf-8")
        self._serve_file(output_path, content_type)
        return True

    def do_GET(self) -> None:
        """Purpose: Execute do GET for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        parsed = urlparse(self.path)
        route = parsed.path

        if route in {"/", "/index.html"}:
            self._serve_file(TEMPLATES_DIR / "index.html", "text/html; charset=utf-8")
            return

        if self._handle_static_get(route):
            return

        if route == "/api/state":
            self._json_response(build_state())
            return

        if route == "/api/run/status":
            self._handle_api_run_status_get()
            return

        if route == "/api/research/state":
            self._json_response(build_research_state())
            return

        if route == "/api/research/status":
            self._handle_api_research_status_get()
            return

        if route == "/api/logs":
            logs = collect_log_index()
            self._json_response({"logs": logs, "lastRun": LAST_RUN})
            return

        if route == "/api/logs/content":
            self._handle_logs_content_get(parsed)
            return

        if self._handle_output_get(route):
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown route")

    def do_POST(self) -> None:
        """Purpose: Execute do POST for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        parsed = urlparse(self.path)
        route = parsed.path

        try:
            payload = self._parse_json_body()
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
            return

        if route == "/api/save":
            self._handle_save(payload)
            return

        if route == "/api/server/restart":
            self._handle_server_restart()
            return

        if route == "/api/research/reset-prompt":
            self._handle_research_reset_prompt()
            return

        if route == "/api/research/run":
            self._handle_research_run(payload)
            return

        if route == "/api/research/format":
            self._handle_research_format()
            return

        if route == "/api/research/stop":
            self._handle_research_stop()
            return

        if route in {"/api/run/full", "/api/run/format"}:
            self._handle_cv_run(route, payload)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown route")


def run_server() -> None:
    """Purpose: Run server and return its outcome.
    
    Inputs:
    - None.
    
    Returns:
    - None. This function performs side effects only.
    """
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), CVWebHandler)
    print(f"CV wrapper running on http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()

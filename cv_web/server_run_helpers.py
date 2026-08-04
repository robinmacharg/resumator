"""
Architecture role:
- Layer: backend server composition helpers.
- Responsibility: construct command arrays and normalized run-state payloads for
  CV and research workflows.

Plain-language purpose:
- This module contains pure helper logic that used to live in `server.py` so the
  HTTP handler module can focus on request routing and orchestration.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
OUTPUT_DIR = ROOT_DIR / "output"
RESEARCH_FORMATTED_PDF = OUTPUT_DIR / "research_output.formatted.pdf"


def _file_mtime(path: Path) -> float | None:
    """Return file mtime when path exists, otherwise None."""
    if not path.exists():
        return None
    return path.stat().st_mtime


def make_command(kind: str, selected_provider: str = "", selected_model: str = "") -> list[str]:
    """Build command list for CV full/format runs.

    Raises:
    - ValueError when `kind` is unsupported.
    """
    if kind == "full":
        command = [sys.executable, str(ROOT_DIR / "generate_cv.py")]
        if selected_provider:
            command.extend(["--provider", selected_provider])
        if selected_model:
            command.extend(["--model", selected_model])
        return command
    if kind == "format":
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


def _build_research_command(
    company_name: str,
    urls: list[str],
    dry_run: bool,
    selected_provider: str = "",
    selected_model: str = "",
) -> list[str]:
    """Build command list for research-role runs."""
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
    return command


def _build_research_format_command() -> list[str]:
    """Build command list for research formatting runs."""
    return [
        sys.executable,
        str(ROOT_DIR / "research_format.py"),
    ]


def _run_output_mtimes() -> dict[str, float | None]:
    """Build output artifact mtime payload for CV run states."""
    return {
        "pdfMtime": _file_mtime(OUTPUT_DIR / "tailored_dev.pdf"),
        "docxMtime": _file_mtime(OUTPUT_DIR / "tailored_dev.docx"),
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
    """Build normalized CV run-state payload."""
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


def _build_research_run_state(
    *,
    command: list[str],
    company_name: str,
    urls: list[str],
    dry_run: bool,
    auto_format_pdf: bool,
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
    """Build normalized research run-state payload."""
    run_state: dict[str, Any] = {
        "kind": "research",
        "command": command,
        "companyName": company_name,
        "urls": urls,
        "dryRun": dry_run,
        "autoFormatPdf": auto_format_pdf,
        "exitCode": exit_code,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "elapsedSeconds": elapsed_seconds,
        "success": success,
        "running": running,
        "output": output,
        "formatAttempted": False,
        "formatSuccess": None,
        "formatExitCode": None,
        "selectedProvider": selected_provider,
        "selectedModel": selected_model,
    }
    if started_monotonic is not None:
        run_state["_startedMonotonic"] = started_monotonic
    return run_state


def _build_research_format_state(
    *,
    command: list[str],
    exit_code: int | None,
    started_at: str,
    finished_at: str | None,
    elapsed_seconds: float,
    success: bool | None,
    running: bool,
    output: str,
    started_monotonic: float | None = None,
) -> dict[str, Any]:
    """Build normalized research-format run-state payload."""
    run_state: dict[str, Any] = {
        "kind": "research_format",
        "command": command,
        "companyName": "",
        "urls": [],
        "dryRun": False,
        "exitCode": exit_code,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "elapsedSeconds": elapsed_seconds,
        "success": success,
        "running": running,
        "output": output,
        "formattedPdfMtime": _file_mtime(RESEARCH_FORMATTED_PDF),
    }
    if started_monotonic is not None:
        run_state["_startedMonotonic"] = started_monotonic
    return run_state

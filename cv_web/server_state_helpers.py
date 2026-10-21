"""State, file, and log helper functions for the CV web server.

Architecture role:
- Layer: backend state/view-model helpers.
- Responsibility: build API state payloads and provide shared file/log helpers
  without owning mutable runtime state directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    """Read UTF-8 text from a file, returning empty string when missing.

    Inputs:
    - path: File path to read.

    Returns:
    - File content as text, or empty string when the file does not exist.
    """
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """Write UTF-8 text to path, creating parent directories when needed.

    Inputs:
    - path: File path to write.
    - content: Text content to persist.

    Returns:
    - None. This function performs side effects only.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def file_mtime(path: Path) -> float | None:
    """Return file mtime when path exists, otherwise None.

    Inputs:
    - path: File path to inspect.

    Returns:
    - POSIX mtime as float, or None for missing paths.
    """
    if not path.exists():
        return None
    return path.stat().st_mtime


def read_research_urls(path: Path) -> list[str]:
    """Read URL list from file, skipping blank and commented lines.

    Inputs:
    - path: URL list file path.

    Returns:
    - Parsed URL strings preserving source order.
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


def build_state(deps: dict[str, Any]) -> dict[str, Any]:
    """Build frontend state payload for CV editor/workflow.

    Inputs:
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - JSON-serializable state object for /api/state.
    """
    files = {key: deps["read_text"](path) for key, path in deps["EDITOR_FILES"].items()}
    output_pdf = deps["OUTPUT_DIR"] / "tailored_dev.pdf"
    output_docx = deps["OUTPUT_DIR"] / "tailored_dev.docx"
    output_model = deps["OUTPUT_DIR"] / "tailored.model-output.txt"
    catalog = deps["load_catalog"]()
    provider_options = deps["build_provider_options"]()
    enabled_options = [item for item in provider_options if item.get("enabled", True)]
    default_provider = str(catalog.get("defaultProvider", "")).strip()
    if default_provider not in {item["value"] for item in enabled_options}:
        default_provider = enabled_options[0]["value"] if enabled_options else ""
    models_by_provider = {
        item["value"]: deps["build_available_models"](item["value"])
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
        "themes": deps["available_themes"](),
        "outputs": {
            "pdfExists": output_pdf.exists(),
            "docxExists": output_docx.exists(),
            "pdfMtime": deps["file_mtime"](output_pdf),
            "docxMtime": deps["file_mtime"](output_docx),
            "modelOutputMtime": deps["file_mtime"](output_model),
        },
        "lastRun": deps["LAST_RUN"],
    }


def build_research_state(deps: dict[str, Any]) -> dict[str, Any]:
    """Build frontend state payload for research workflow.

    Inputs:
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - JSON-serializable state object for research endpoints.
    """
    company_name = deps["read_text"](deps["RESEARCH_COMPANY_FILE"]).strip()
    output_md_mtime = deps["file_mtime"](deps["RESEARCH_OUTPUT_MD"])
    output_json_mtime = deps["file_mtime"](deps["RESEARCH_OUTPUT_JSON"])
    built_prompt_mtime = deps["file_mtime"](deps["RESEARCH_PROMPT_BUILT_FILE"])
    formatted_md_mtime = deps["file_mtime"](deps["RESEARCH_FORMATTED_MD"])
    formatted_pdf_mtime = deps["file_mtime"](deps["RESEARCH_FORMATTED_PDF"])

    return {
        "companyName": company_name,
        "urls": deps["read_research_urls"](deps["RESEARCH_URLS_FILE"]),
        "output": {
            "markdown": deps["read_text"](deps["RESEARCH_OUTPUT_MD"]),
            "json": deps["read_text"](deps["RESEARCH_OUTPUT_JSON"]),
            "markdownMtime": output_md_mtime,
            "jsonMtime": output_json_mtime,
            "builtPrompt": deps["read_text"](deps["RESEARCH_PROMPT_BUILT_FILE"]),
            "builtPromptExists": deps["RESEARCH_PROMPT_BUILT_FILE"].exists(),
            "builtPromptMtime": built_prompt_mtime,
            "formattedMarkdownExists": deps["RESEARCH_FORMATTED_MD"].exists(),
            "formattedPdfExists": deps["RESEARCH_FORMATTED_PDF"].exists(),
            "formattedMarkdownMtime": formatted_md_mtime,
            "formattedPdfMtime": formatted_pdf_mtime,
        },
        "lastRun": deps["LAST_RESEARCH_RUN"],
    }


def collect_log_index(deps: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    """Return metadata for newest debug log files.

    Inputs:
    - deps: Dependency map supplied by cv_web.server.
    - limit: Max number of logs to include.

    Returns:
    - Log metadata list sorted by newest first.
    """
    log_dir = deps["LOG_DIR"]
    if not log_dir.exists():
        return []

    logs = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
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


def read_log_file(name: str, deps: dict[str, Any]) -> str:
    """Read one debug log file after basic filename validation.

    Inputs:
    - name: Candidate log filename.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - Log content decoded as UTF-8 with replacement fallback.

    Raises:
    - ValueError: Invalid filename including path separators.
    - FileNotFoundError: Missing file or non-log extension.
    """
    if "/" in name or "\\" in name:
        raise ValueError("Invalid log file name")

    path = deps["LOG_DIR"] / name
    if not path.exists() or path.suffix != ".log":
        raise FileNotFoundError(name)

    return path.read_text(encoding="utf-8", errors="replace")

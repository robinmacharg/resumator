#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import sys
import threading
import time
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
LOG_DIR = ROOT_DIR / "gemini_debug_logs"
RESEARCH_COMPANY_FILE = ROOT_DIR / "research_company.txt"
RESEARCH_URLS_FILE = ROOT_DIR / "research_urls.txt"
RESEARCH_PROMPT_DEFAULT_FILE = ROOT_DIR / "research_prompt.default.md"
RESEARCH_OUTPUT_MD = ROOT_DIR / "research_output.md"
RESEARCH_OUTPUT_JSON = ROOT_DIR / "research_output.json"
RESEARCH_PROMPT_BUILT_FILE = ROOT_DIR / "research_prompt.built.txt"
RESEARCH_FORMATTED_MD = ROOT_DIR / "research_output.formatted.md"
RESEARCH_FORMATTED_PDF = ROOT_DIR / "research_output.formatted.pdf"

HOST = "127.0.0.1"
PORT = 8765
ENV_FILE_PATH = ROOT_DIR / ".env"
MODEL_CATALOG_PATH = ROOT_DIR / "model_providers.json"

EDITOR_FILES = {
    "cv": ROOT_DIR / "CV.md",
    "prompt": ROOT_DIR / "prompt.md",
    "research_prompt": ROOT_DIR / "research_prompt.md",
    "jobspec": ROOT_DIR / "jobspec.txt",
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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def parse_dotenv_file(path: Path) -> dict[str, str]:
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


def split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def load_catalog() -> dict[str, Any]:
    return load_provider_catalog(MODEL_CATALOG_PATH)


def build_provider_options() -> list[dict[str, str]]:
    catalog = load_catalog()
    return [
        {"value": item["id"], "label": item["label"]}
        for item in catalog.get("providers", [])
        if isinstance(item, dict) and item.get("id") and item.get("label")
    ]


def build_available_models(selected_provider: str) -> list[str]:
    catalog = load_catalog()
    providers = provider_map(catalog)
    provider_entry = providers.get(selected_provider)
    if not provider_entry:
        provider_entry = providers.get(catalog.get("defaultProvider", ""))
    if not provider_entry:
        return []

    env = parse_dotenv_file(ENV_FILE_PATH)
    provider_id = str(provider_entry.get("id", "")).strip()
    default_models = [item for item in provider_entry.get("models", []) if isinstance(item, str)]
    if provider_id == "gemini":
        env_models = [
            env.get("GEMINI_MODEL", "").strip(),
            *split_csv(env.get("GEMINI_MODEL_FALLBACKS", "")),
        ]
    elif provider_id == "huggingface":
        env_models = [
            env.get("HUGGINGFACE_MODEL", "").strip(),
            *split_csv(env.get("HUGGINGFACE_MODEL_FALLBACKS", "")),
        ]
    elif provider_id == "openai":
        env_models = [
            env.get("OPENAI_MODEL", "").strip(),
            *split_csv(env.get("OPENAI_MODEL_FALLBACKS", "")),
        ]
    elif provider_id == "swiftlet":
        env_models = [
            env.get("SWIFTLET_MODEL", "").strip(),
            *split_csv(env.get("SWIFTLET_MODEL_FALLBACKS", "")),
        ]
    else:
        env_models = []

    return dedupe_keep_order([*env_models, *default_models])


def parse_selected_provider(payload: dict[str, Any]) -> str:
    catalog = load_catalog()
    providers = provider_map(catalog)
    default_provider = str(catalog.get("defaultProvider", "gemini")).strip() or "gemini"

    raw_provider = payload.get("selectedProvider", "")
    if raw_provider is None:
        return default_provider
    if not isinstance(raw_provider, str):
        raise ValueError("selectedProvider must be a string")

    selected_provider = raw_provider.strip() or default_provider
    if selected_provider not in providers:
        raise ValueError("selectedProvider is not in available provider options")
    return selected_provider


def parse_selected_model(payload: dict[str, Any], selected_provider: str) -> str:
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


def file_mtime(path: Path) -> float | None:
    if not path.exists():
        return None
    return path.stat().st_mtime


def build_state() -> dict[str, Any]:
    files = {key: read_text(path) for key, path in EDITOR_FILES.items()}
    output_pdf = ROOT_DIR / "tailored_dev.pdf"
    output_docx = ROOT_DIR / "tailored_dev.docx"
    catalog = load_catalog()
    provider_options = build_provider_options()
    default_provider = str(catalog.get("defaultProvider", "gemini")).strip() or "gemini"
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
    if "/" in name or "\\" in name:
        raise ValueError("Invalid log file name")

    path = LOG_DIR / name
    if not path.exists() or path.suffix != ".log":
        raise FileNotFoundError(name)

    return path.read_text(encoding="utf-8", errors="replace")


def make_command(kind: str, selected_provider: str = "", selected_model: str = "") -> list[str]:
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
            "tailored.md",
            "--pdf",
            "tailored_dev.pdf",
            "--docx",
            "tailored_dev.docx",
        ]

    raise ValueError(f"Unsupported run kind: {kind}")


def get_current_run_snapshot() -> dict[str, Any] | None:
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
    with RUN_STATE_LOCK:
        CURRENT_RUN.clear()
        CURRENT_RUN.update(run_state)


def append_current_run_output(chunk: str) -> None:
    if not chunk:
        return

    with RUN_STATE_LOCK:
        if not CURRENT_RUN:
            return

        existing = CURRENT_RUN.get("output", "")
        CURRENT_RUN["output"] = existing + chunk


def finalize_current_run(return_code: int) -> dict[str, Any] | None:
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
        CURRENT_RUN["pdfMtime"] = file_mtime(ROOT_DIR / "tailored_dev.pdf")
        CURRENT_RUN["docxMtime"] = file_mtime(ROOT_DIR / "tailored_dev.docx")

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
    with RESEARCH_STATE_LOCK:
        CURRENT_RESEARCH_RUN.clear()
        CURRENT_RESEARCH_RUN.update(run_state)


def set_current_research_proc(proc: subprocess.Popen[str] | None) -> None:
    with RESEARCH_PROC_LOCK:
        global CURRENT_RESEARCH_PROC
        CURRENT_RESEARCH_PROC = proc


def get_current_research_proc() -> subprocess.Popen[str] | None:
    with RESEARCH_PROC_LOCK:
        return CURRENT_RESEARCH_PROC


def append_current_research_output(chunk: str) -> None:
    if not chunk:
        return

    with RESEARCH_STATE_LOCK:
        if not CURRENT_RESEARCH_RUN:
            return

        existing = CURRENT_RESEARCH_RUN.get("output", "")
        CURRENT_RESEARCH_RUN["output"] = existing + chunk


def finalize_current_research_run(return_code: int) -> dict[str, Any] | None:
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

        snapshot = {
            key: value
            for key, value in CURRENT_RESEARCH_RUN.items()
            if not key.startswith("_")
        }
        CURRENT_RESEARCH_RUN.clear()

    LAST_RESEARCH_RUN.clear()
    LAST_RESEARCH_RUN.update(snapshot)
    return snapshot


def request_stop_research_run() -> bool:
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
    try:
        for line in iter(pipe.readline, ""):
            append_current_run_output(f"{prefix}{line}")
    finally:
        pipe.close()


def stream_pipe_research(pipe, prefix: str = "") -> None:
    try:
        for line in iter(pipe.readline, ""):
            append_current_research_output(f"{prefix}{line}")
    finally:
        pipe.close()


def run_subprocess_streaming(kind: str, selected_provider: str = "", selected_model: str = "") -> dict[str, Any]:
    command = make_command(kind, selected_provider=selected_provider, selected_model=selected_model)

    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    set_current_run(
        {
            "kind": kind,
            "command": command,
            "exitCode": None,
            "startedAt": started_at,
            "finishedAt": None,
            "elapsedSeconds": 0.0,
            "success": None,
            "running": True,
            "output": "",
            "selectedProvider": selected_provider,
            "selectedModel": selected_model,
            "pdfMtime": file_mtime(ROOT_DIR / "tailored_dev.pdf"),
            "docxMtime": file_mtime(ROOT_DIR / "tailored_dev.docx"),
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
    try:
        run_subprocess_streaming(kind, selected_provider=selected_provider, selected_model=selected_model)
    except Exception as exc:
        set_current_run(
            {
                "kind": kind,
                "command": make_command(kind, selected_provider=selected_provider, selected_model=selected_model),
                "exitCode": 1,
                "startedAt": utc_now_iso(),
                "finishedAt": utc_now_iso(),
                "elapsedSeconds": 0.0,
                "success": False,
                "running": False,
                "output": f"Wrapper failed to execute run: {exc}",
                "selectedProvider": selected_provider,
                "selectedModel": selected_model,
                "pdfMtime": file_mtime(ROOT_DIR / "tailored_dev.pdf"),
                "docxMtime": file_mtime(ROOT_DIR / "tailored_dev.docx"),
            }
        )
        snapshot = get_current_run_snapshot()
        if snapshot is not None:
            LAST_RUN.clear()
            LAST_RUN.update(snapshot)
            with RUN_STATE_LOCK:
                CURRENT_RUN.clear()
    finally:
        RUN_LOCK.release()


def run_research_subprocess_streaming(
    company_name: str,
    urls: list[str],
    dry_run: bool,
    selected_provider: str = "",
    selected_model: str = "",
) -> dict[str, Any]:
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

    run_result = finalize_current_research_run(return_code)
    if run_result is None:
        raise RuntimeError("Research run completed but no run state was available.")

    return run_result


def run_research_format_subprocess_streaming() -> dict[str, Any]:
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
    selected_provider: str = "",
    selected_model: str = "",
) -> None:
    try:
        run_research_subprocess_streaming(
            company_name=company_name,
            urls=urls,
            dry_run=dry_run,
            selected_provider=selected_provider,
            selected_model=selected_model,
        )
    except Exception as exc:
        set_current_research_run(
            {
                "kind": "research",
                "command": [],
                "companyName": company_name,
                "urls": urls,
                "dryRun": dry_run,
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
        snapshot = get_current_research_run_snapshot()
        if snapshot is not None:
            LAST_RESEARCH_RUN.clear()
            LAST_RESEARCH_RUN.update(snapshot)
            with RESEARCH_STATE_LOCK:
                CURRENT_RESEARCH_RUN.clear()
    finally:
        RESEARCH_RUN_LOCK.release()


def run_research_format_subprocess_async() -> None:
    try:
        run_research_format_subprocess_streaming()
    except Exception as exc:
        set_current_research_run(
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
        snapshot = get_current_research_run_snapshot()
        if snapshot is not None:
            LAST_RESEARCH_RUN.clear()
            LAST_RESEARCH_RUN.update(snapshot)
            with RESEARCH_STATE_LOCK:
                CURRENT_RESEARCH_RUN.clear()
    finally:
        RESEARCH_RUN_LOCK.release()


class CVWebHandler(BaseHTTPRequestHandler):
    server_version = "CVWebWrapper/1.0"

    def _json_response(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text_response(self, text: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path, content_type: str) -> None:
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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

        if route in {"/", "/index.html"}:
            self._serve_file(TEMPLATES_DIR / "index.html", "text/html; charset=utf-8")
            return

        if route.startswith("/static/"):
            rel = route.removeprefix("/static/")
            if rel == "styles.css":
                self._serve_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
                return
            if rel == "app.js":
                self._serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown static file")
            return

        if route == "/api/state":
            self._json_response(build_state())
            return

        if route == "/api/run/status":
            current = get_current_run_snapshot()
            run_payload = current if current is not None else (LAST_RUN if LAST_RUN else None)
            self._json_response(
                {
                    "running": bool(current and current.get("running")),
                    "run": run_payload,
                }
            )
            return

        if route == "/api/research/state":
            self._json_response(build_research_state())
            return

        if route == "/api/research/status":
            current = get_current_research_run_snapshot()
            run_payload = current if current is not None else (LAST_RESEARCH_RUN if LAST_RESEARCH_RUN else None)
            self._json_response(
                {
                    "running": bool(current and current.get("running")),
                    "run": run_payload,
                }
            )
            return

        if route == "/api/logs":
            logs = collect_log_index()
            self._json_response({"logs": logs, "lastRun": LAST_RUN})
            return

        if route == "/api/logs/content":
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
            return

        if route.startswith("/output/"):
            name = route.removeprefix("/output/")
            if name not in ALLOWED_OUTPUT_FILES:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown output file")
                return
            output_path = ROOT_DIR / name
            content_type = {
                ".pdf": "application/pdf",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }.get(output_path.suffix, "text/plain; charset=utf-8")
            self._serve_file(output_path, content_type)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown route")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

        try:
            payload = self._parse_json_body()
        except ValueError as exc:
            self._json_response({"error": str(exc)}, status=400)
            return

        if route == "/api/save":
            try:
                self._save_editor_payload(payload)
            except ValueError as exc:
                self._json_response({"error": str(exc)}, status=400)
                return
            self._json_response({"success": True, "savedAt": utc_now_iso(), "state": build_state()})
            return

        if route == "/api/research/reset-prompt":
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
            return

        if route == "/api/research/run":
            try:
                self._save_editor_payload(
                    payload,
                    allowed_keys={"cv", "prompt", "research_prompt", "jobspec"},
                )
                selected_provider = parse_selected_provider(payload)
                selected_model = parse_selected_model(payload, selected_provider)
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

            company_name = str(payload.get("companyName", "")).strip()
            if not company_name:
                self._json_response({"error": "companyName is required"}, status=400)
                return

            raw_urls = payload.get("urls", [])
            if not isinstance(raw_urls, list):
                self._json_response({"error": "urls must be a list of strings"}, status=400)
                return

            urls: list[str] = []
            for idx, item in enumerate(raw_urls):
                if not isinstance(item, str):
                    self._json_response({"error": f"urls[{idx}] must be a string"}, status=400)
                    return
                cleaned = item.strip()
                if cleaned:
                    urls.append(cleaned)

            dry_run = bool(payload.get("dryRun", False))

            if not RESEARCH_RUN_LOCK.acquire(blocking=False):
                self._json_response({"error": "A research run is already in progress"}, status=409)
                return

            try:
                thread = threading.Thread(
                    target=run_research_subprocess_async,
                    args=(company_name, urls, dry_run, selected_provider, selected_model),
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
            return

        if route == "/api/research/format":
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
            return

        if route == "/api/research/stop":
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
            return

        if route in {"/api/run/full", "/api/run/format"}:
            try:
                self._save_editor_payload(
                    payload,
                    allowed_keys={"cv", "prompt", "research_prompt", "jobspec"},
                )
                selected_provider = parse_selected_provider(payload)
                selected_model = parse_selected_model(payload, selected_provider)
            except ValueError as exc:
                self._json_response({"error": str(exc)}, status=400)
                return

            kind = "full" if route.endswith("/full") else "format"
            if not RUN_LOCK.acquire(blocking=False):
                self._json_response({"error": "A run is already in progress"}, status=409)
                return

            try:
                model_override = selected_model if kind == "full" else ""
                thread = threading.Thread(
                    target=run_subprocess_async,
                    args=(kind, selected_provider, model_override),
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
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown route")


def run_server() -> None:
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

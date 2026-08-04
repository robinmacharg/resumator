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
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cv_web.server_run_helpers import (
    _build_research_command,
    _build_research_format_command,
    _build_research_format_state,
    _build_research_run_state,
    _build_run_state,
    make_command,
)
from cv_web.server_request_parsing import (
    CvRunRequest,
    build_available_models,
    build_provider_options,
    load_catalog,
    parse_auto_format_pdf,
    parse_company_name,
    parse_cv_run_request,
    parse_research_run_request,
    parse_url_list,
)
from cv_web import server_state_helpers as state_helpers
from cv_web import server_process_runners as process_runners
from cv_web.server_http_handlers import (
    dispatch_get,
    dispatch_post,
    handle_api_research_status_get,
    handle_api_run_status_get,
    handle_cv_run,
    handle_logs_content_get,
    handle_output_get,
    handle_research_format,
    handle_research_reset_prompt,
    handle_research_run,
    handle_research_stop,
    handle_save,
    handle_server_restart,
    handle_static_get,
)
from cv_web.server_runtime_state import (
    CURRENT_RESEARCH_RUN,
    CURRENT_RUN,
    LAST_RESEARCH_RUN,
    LAST_RUN,
    _finalize_research_run_error_state,
    _finalize_run_error_state,
    append_current_research_output,
    append_current_run_output,
    finalize_current_research_run,
    finalize_current_run,
    get_current_research_run_snapshot,
    get_current_run_snapshot,
    request_stop_research_run,
    set_current_research_proc,
    set_current_research_run,
    set_current_run,
    update_current_research_run_fields,
)

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

RESEARCH_RUN_LOCK = threading.Lock()


def schedule_process_restart() -> None:
    """Schedule in-process restart after current HTTP response flushes."""

    def _restart() -> None:
        time.sleep(0.35)
        os.execv(sys.executable, [sys.executable, str(APP_DIR / "server.py")])

    threading.Thread(target=_restart, daemon=True).start()


def utc_now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _state_helper_deps() -> dict[str, Any]:
    """Build dynamic dependency map for extracted state helper functions.

    The map is resolved at call time so tests patching symbols on this module
    still affect behavior.
    """
    return {
        "EDITOR_FILES": EDITOR_FILES,
        "LAST_RESEARCH_RUN": LAST_RESEARCH_RUN,
        "LAST_RUN": LAST_RUN,
        "LOG_DIR": LOG_DIR,
        "OUTPUT_DIR": OUTPUT_DIR,
        "RESEARCH_COMPANY_FILE": RESEARCH_COMPANY_FILE,
        "RESEARCH_FORMATTED_MD": RESEARCH_FORMATTED_MD,
        "RESEARCH_FORMATTED_PDF": RESEARCH_FORMATTED_PDF,
        "RESEARCH_OUTPUT_JSON": RESEARCH_OUTPUT_JSON,
        "RESEARCH_OUTPUT_MD": RESEARCH_OUTPUT_MD,
        "RESEARCH_PROMPT_BUILT_FILE": RESEARCH_PROMPT_BUILT_FILE,
        "RESEARCH_URLS_FILE": RESEARCH_URLS_FILE,
        "build_available_models": build_available_models,
        "build_provider_options": build_provider_options,
        "file_mtime": file_mtime,
        "load_catalog": load_catalog,
        "read_research_urls": read_research_urls,
        "read_text": read_text,
    }


def read_text(path: Path) -> str:
    """Read UTF-8 text from file, returning empty string when missing."""
    return state_helpers.read_text(path)


def write_text(path: Path, content: str) -> None:
    """Write UTF-8 text to path, creating parent directories as needed."""
    state_helpers.write_text(path, content)


def file_mtime(path: Path) -> float | None:
    """Return file mtime when path exists, otherwise None."""
    return state_helpers.file_mtime(path)


def build_state() -> dict[str, Any]:
    """Build current frontend state payload for CV editor/workflow."""
    return state_helpers.build_state(_state_helper_deps())


def read_research_urls(path: Path) -> list[str]:
    """Read URL list from file, skipping blank and commented lines."""
    return state_helpers.read_research_urls(path)


def build_research_state() -> dict[str, Any]:
    """Build current frontend state payload for research workflow."""
    return state_helpers.build_research_state(_state_helper_deps())


def collect_log_index(limit: int = 20) -> list[dict[str, Any]]:
    """Return metadata for newest debug log files."""
    return state_helpers.collect_log_index(_state_helper_deps(), limit=limit)


def read_log_file(name: str) -> str:
    """Read one debug log file after basic filename validation."""
    return state_helpers.read_log_file(name, _state_helper_deps())


def _process_runner_deps() -> dict[str, Any]:
    """Build dynamic dependency map for extracted process runner functions.

    The map is resolved at call time so tests patching symbols on this module
    still affect runner behavior.
    """
    return {
        "ROOT_DIR": ROOT_DIR,
        "RESEARCH_FORMATTED_PDF": RESEARCH_FORMATTED_PDF,
        "RUN_LOCK": RUN_LOCK,
        "RESEARCH_RUN_LOCK": RESEARCH_RUN_LOCK,
        "LAST_RESEARCH_RUN": LAST_RESEARCH_RUN,
        "_build_research_command": _build_research_command,
        "_build_research_format_command": _build_research_format_command,
        "_build_research_format_state": _build_research_format_state,
        "_build_research_run_state": _build_research_run_state,
        "_build_run_state": _build_run_state,
        "_finalize_research_run_error_state": _finalize_research_run_error_state,
        "_finalize_run_error_state": _finalize_run_error_state,
        "append_current_research_output": append_current_research_output,
        "append_current_run_output": append_current_run_output,
        "file_mtime": file_mtime,
        "finalize_current_research_run": finalize_current_research_run,
        "finalize_current_run": finalize_current_run,
        "make_command": make_command,
        "run_research_format_for_active_run_streaming": run_research_format_for_active_run_streaming,
        "run_research_format_subprocess_streaming": run_research_format_subprocess_streaming,
        "run_research_subprocess_streaming": run_research_subprocess_streaming,
        "run_subprocess_streaming": run_subprocess_streaming,
        "set_current_research_proc": set_current_research_proc,
        "set_current_research_run": set_current_research_run,
        "set_current_run": set_current_run,
        "stream_pipe": stream_pipe,
        "stream_pipe_research": stream_pipe_research,
        "update_current_research_run_fields": update_current_research_run_fields,
        "utc_now_iso": utc_now_iso,
    }


def run_research_format_for_active_run_streaming() -> int:
    """Purpose: Run research format for active run streaming and return its outcome.
    
    Inputs:
    - None.
    
    Returns:
    - `int` value representing the operation result.
    """
    return process_runners.run_research_format_for_active_run_streaming(_process_runner_deps())


def stream_pipe(pipe, prefix: str = "") -> None:
    """Purpose: Execute stream pipe for this module's workflow.
    
    Inputs:
    - pipe: Readable subprocess stream (typically stdout or stderr) for a CV run.
    - prefix: Optional label prepended to each streamed line, such as "[stderr] ".
    
    Returns:
    - None. This function performs side effects only.
    """
    process_runners.stream_pipe(pipe, _process_runner_deps(), prefix=prefix)


def stream_pipe_research(pipe, prefix: str = "") -> None:
    """Purpose: Execute stream pipe research for this module's workflow.
    
    Inputs:
    - pipe: Readable subprocess stream (typically stdout or stderr) for a research run.
    - prefix: Optional label prepended to each streamed line, such as "[stderr] ".
    
    Returns:
    - None. This function performs side effects only.
    """
    process_runners.stream_pipe_research(pipe, _process_runner_deps(), prefix=prefix)


def run_subprocess_streaming(kind: str, selected_provider: str = "", selected_model: str = "") -> dict[str, Any]:
    """Purpose: Run subprocess streaming and return its outcome.
    
    Inputs:
    - kind: CV pipeline mode, expected to be "full" or "format".
    - selected_provider: Optional provider override; empty string keeps default ordering.
    - selected_model: Optional model override for the selected provider.
    
    Returns:
    - `dict[str, Any]` value representing the operation result.
    """
    return process_runners.run_subprocess_streaming(
        kind,
        selected_provider=selected_provider,
        selected_model=selected_model,
        deps=_process_runner_deps(),
    )


def run_subprocess_async(kind: str, selected_provider: str = "", selected_model: str = "") -> None:
    """Purpose: Run subprocess async and return its outcome.
    
    Inputs:
    - kind: CV pipeline mode, expected to be "full" or "format".
    - selected_provider: Optional provider override; empty string keeps default ordering.
    - selected_model: Optional model override for the selected provider.
    
    Returns:
    - None. This function performs side effects only.
    """
    process_runners.run_subprocess_async(
        kind,
        selected_provider=selected_provider,
        selected_model=selected_model,
        deps=_process_runner_deps(),
    )


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
    - company_name: Company identifier used to tailor the research prompt and outputs.
    - urls: Source URLs to include as research input context.
    - dry_run: When true, skips provider execution and runs in preview/simulation mode.
    - auto_format_pdf: When true, triggers PDF formatting after successful research generation.
    - selected_provider: Optional provider override; empty string keeps default ordering.
    - selected_model: Optional model override for the selected provider.
    
    Returns:
    - `dict[str, Any]` value representing the operation result.
    """
    return process_runners.run_research_subprocess_streaming(
        company_name=company_name,
        urls=urls,
        dry_run=dry_run,
        auto_format_pdf=auto_format_pdf,
        selected_provider=selected_provider,
        selected_model=selected_model,
        deps=_process_runner_deps(),
    )


def run_research_format_subprocess_streaming() -> dict[str, Any]:
    """Purpose: Run research format subprocess streaming and return its outcome.
    
    Inputs:
    - None.
    
    Returns:
    - `dict[str, Any]` value representing the operation result.
    """
    return process_runners.run_research_format_subprocess_streaming(_process_runner_deps())


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
    - company_name: Company identifier used to tailor the research prompt and outputs.
    - urls: Source URLs to include as research input context.
    - dry_run: When true, skips provider execution and runs in preview/simulation mode.
    - auto_format_pdf: When true, triggers PDF formatting after successful research generation.
    - selected_provider: Optional provider override; empty string keeps default ordering.
    - selected_model: Optional model override for the selected provider.
    
    Returns:
    - None. This function performs side effects only.
    """
    process_runners.run_research_subprocess_async(
        company_name=company_name,
        urls=urls,
        dry_run=dry_run,
        auto_format_pdf=auto_format_pdf,
        selected_provider=selected_provider,
        selected_model=selected_model,
        deps=_process_runner_deps(),
    )


def run_research_format_subprocess_async() -> None:
    """Purpose: Run research format subprocess async and return its outcome.
    
    Inputs:
    - None.
    
    Returns:
    - None. This function performs side effects only.
    """
    process_runners.run_research_format_subprocess_async(_process_runner_deps())


def _http_handler_deps() -> dict[str, Any]:
    """Build dynamic dependency map for extracted HTTP handler functions.

    The map is resolved at call time so tests patching symbols on this module
    still affect handler behavior.
    """
    return {
        "ALLOWED_OUTPUT_FILES": ALLOWED_OUTPUT_FILES,
        "EDITOR_FILES": EDITOR_FILES,
        "LAST_RESEARCH_RUN": LAST_RESEARCH_RUN,
        "LAST_RUN": LAST_RUN,
        "OUTPUT_DIR": OUTPUT_DIR,
        "RESEARCH_PROMPT_DEFAULT_FILE": RESEARCH_PROMPT_DEFAULT_FILE,
        "RESEARCH_RUN_LOCK": RESEARCH_RUN_LOCK,
        "RUN_LOCK": RUN_LOCK,
        "STATIC_DIR": STATIC_DIR,
        "TEMPLATES_DIR": TEMPLATES_DIR,
        "build_research_state": build_research_state,
        "build_state": build_state,
        "collect_log_index": collect_log_index,
        "get_current_research_run_snapshot": get_current_research_run_snapshot,
        "get_current_run_snapshot": get_current_run_snapshot,
        "parse_cv_run_request": parse_cv_run_request,
        "parse_research_run_request": parse_research_run_request,
        "read_log_file": read_log_file,
        "read_text": read_text,
        "request_stop_research_run": request_stop_research_run,
        "run_research_format_subprocess_async": run_research_format_subprocess_async,
        "run_research_subprocess_async": run_research_subprocess_async,
        "run_subprocess_async": run_subprocess_async,
        "schedule_process_restart": schedule_process_restart,
        "utc_now_iso": utc_now_iso,
        "write_text": write_text,
    }


class CVWebHandler(BaseHTTPRequestHandler):
    """HTTP request handler for static assets and CV/research JSON API routes."""

    server_version = "CVWebWrapper/1.0"

    def _json_response(self, payload: Any, status: int = 200) -> None:
        """Purpose: Execute json response for this module's workflow.
        
        Inputs:
        - payload: JSON-serializable response object to send to the client.
        - status: HTTP status code for the response (default 200).
        
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
        - text: Raw text body to write to the HTTP response.
        - status: HTTP status code for the response (default 200).
        - content_type: MIME content type header value for the text response.
        
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
        - path: Absolute file path to serve.
        - content_type: MIME content type header value for the served file.
        
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
        - payload: Request body expected to include a `files` mapping of editor keys to text.
        - allowed_keys: Optional subset of editor keys permitted for this save operation.
        
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
        - payload: Parsed request body containing editor file content updates.
        
        Returns:
        - None. This function performs side effects only.
        """
        handle_save(self, payload, _http_handler_deps())

    def _handle_server_restart(self) -> None:
        """Purpose: Execute handle server restart for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        handle_server_restart(self, _http_handler_deps())

    def _handle_research_reset_prompt(self) -> None:
        """Purpose: Execute handle research reset prompt for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        handle_research_reset_prompt(self, _http_handler_deps())

    def _handle_research_run(self, payload: dict[str, Any]) -> None:
        """Purpose: Execute handle research run for this module's workflow.
        
        Inputs:
        - payload: Parsed request body containing research settings and editable file content.
        
        Returns:
        - None. This function performs side effects only.
        """
        handle_research_run(self, payload, _http_handler_deps())

    def _handle_research_format(self) -> None:
        """Purpose: Execute handle research format for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        handle_research_format(self, _http_handler_deps())

    def _handle_research_stop(self) -> None:
        """Purpose: Execute handle research stop for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        handle_research_stop(self, _http_handler_deps())

    def _handle_cv_run(self, route: str, payload: dict[str, Any]) -> None:
        """Purpose: Execute handle cv run for this module's workflow.
        
        Inputs:
        - route: Request path identifying run kind, such as `/api/run/full` or `/api/run/format`.
        - payload: Parsed request body containing run settings and editable file content.
        
        Returns:
        - None. This function performs side effects only.
        """
        handle_cv_run(self, route, payload, _http_handler_deps())

    def _handle_static_get(self, route: str) -> bool:
        """Purpose: Execute handle static get for this module's workflow.
        
        Inputs:
        - route: Parsed request path used to resolve static asset file routing.
        
        Returns:
        - `bool` value representing the operation result.
        """
        return handle_static_get(self, route, _http_handler_deps())

    def _handle_api_run_status_get(self) -> None:
        """Purpose: Execute handle api run status get for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        handle_api_run_status_get(self, _http_handler_deps())

    def _handle_api_research_status_get(self) -> None:
        """Purpose: Execute handle api research status get for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        handle_api_research_status_get(self, _http_handler_deps())

    def _handle_logs_content_get(self, parsed) -> None:
        """Purpose: Execute handle logs content get for this module's workflow.
        
        Inputs:
        - parsed: Parsed URL object containing query parameters for log lookup.
        
        Returns:
        - None. This function performs side effects only.
        """
        handle_logs_content_get(self, parsed, _http_handler_deps())

    def _handle_output_get(self, route: str) -> bool:
        """Purpose: Execute handle output get for this module's workflow.
        
        Inputs:
        - route: Parsed request path used to resolve output artifact file routing.
        
        Returns:
        - `bool` value representing the operation result.
        """
        return handle_output_get(self, route, _http_handler_deps())

    def do_GET(self) -> None:
        """Purpose: Execute do GET for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        dispatch_get(self, self.path, _http_handler_deps())

    def do_POST(self) -> None:
        """Purpose: Execute do POST for this module's workflow.
        
        Inputs:
        - None.
        
        Returns:
        - None. This function performs side effects only.
        """
        dispatch_post(self, self.path, _http_handler_deps())


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

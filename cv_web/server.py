#!/usr/bin/env python3
import json
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
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
LOG_DIR = ROOT_DIR / "gemini_debug_logs"

HOST = "127.0.0.1"
PORT = 8765

EDITOR_FILES = {
    "cv": ROOT_DIR / "CV.md",
    "prompt": ROOT_DIR / "prompt.md",
    "jobspec": ROOT_DIR / "jobspec.txt",
}

ALLOWED_OUTPUT_FILES = {
    "tailored_dev.pdf",
    "tailored_dev.docx",
    "tailored.md",
    "tailored.export.md",
    "tailored.docx.export.md",
}

RUN_LOCK = threading.Lock()
LAST_RUN: dict[str, Any] = {}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def file_mtime(path: Path) -> float | None:
    if not path.exists():
        return None
    return path.stat().st_mtime


def build_state() -> dict[str, Any]:
    files = {key: read_text(path) for key, path in EDITOR_FILES.items()}
    output_pdf = ROOT_DIR / "tailored_dev.pdf"
    output_docx = ROOT_DIR / "tailored_dev.docx"
    return {
        "files": files,
        "outputs": {
            "pdfExists": output_pdf.exists(),
            "docxExists": output_docx.exists(),
            "pdfMtime": file_mtime(output_pdf),
            "docxMtime": file_mtime(output_docx),
        },
        "lastRun": LAST_RUN,
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


def run_subprocess(kind: str) -> dict[str, Any]:
    if kind == "full":
        command = [sys.executable, str(ROOT_DIR / "generate_cv.py")]
    elif kind == "format":
        command = [
            sys.executable,
            str(ROOT_DIR / "cv_convert.py"),
            "tailored.md",
            "--pdf",
            "tailored_dev.pdf",
            "--docx",
            "tailored_dev.docx",
        ]
    else:
        raise ValueError(f"Unsupported run kind: {kind}")

    started_at = utc_now_iso()
    start_time = time.time()

    proc = subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
    )

    elapsed = round(time.time() - start_time, 2)
    output = "\n".join(part for part in [proc.stdout, proc.stderr] if part).strip()
    run_result = {
        "kind": kind,
        "command": command,
        "exitCode": proc.returncode,
        "startedAt": started_at,
        "finishedAt": utc_now_iso(),
        "elapsedSeconds": elapsed,
        "success": proc.returncode == 0,
        "output": output,
        "pdfMtime": file_mtime(ROOT_DIR / "tailored_dev.pdf"),
        "docxMtime": file_mtime(ROOT_DIR / "tailored_dev.docx"),
    }
    LAST_RUN.clear()
    LAST_RUN.update(run_result)
    return run_result


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

    def _save_editor_payload(self, payload: dict[str, Any]) -> None:
        files = payload.get("files", {})
        if not isinstance(files, dict):
            raise ValueError("'files' must be an object")

        for key, path in EDITOR_FILES.items():
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

        if route in {"/api/run/full", "/api/run/format"}:
            try:
                self._save_editor_payload(payload)
            except ValueError as exc:
                self._json_response({"error": str(exc)}, status=400)
                return

            kind = "full" if route.endswith("/full") else "format"
            if not RUN_LOCK.acquire(blocking=False):
                self._json_response({"error": "A run is already in progress"}, status=409)
                return

            try:
                result = run_subprocess(kind)
            finally:
                RUN_LOCK.release()

            self._json_response({"success": result["success"], "run": result, "state": build_state()})
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

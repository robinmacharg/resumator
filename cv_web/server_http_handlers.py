"""HTTP route/action handlers extracted from the main CV web server module.

Architecture role:
- Layer: backend HTTP action routing helpers.
- Responsibility: keep request-action logic modular while preserving behavior
  expected by CVWebHandler methods in cv_web.server.
"""

from __future__ import annotations

import threading
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse

from cv_web import server_roles


def handle_save(handler, payload: dict[str, Any], deps: dict[str, Any]) -> None:
    """Handle save payload requests and publish updated UI state.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - payload: Parsed JSON request body.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    try:
        handler._save_editor_payload(payload)
    except ValueError as exc:
        handler._json_response({"error": str(exc)}, status=400)
        return
    handler._json_response(
        {
            "success": True,
            "savedAt": deps["utc_now_iso"](),
            "state": deps["build_state"](),
        }
    )


def handle_server_restart(handler, deps: dict[str, Any]) -> None:
    """Handle server restart requests.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    deps["schedule_process_restart"]()
    handler._json_response(
        {
            "success": True,
            "restarting": True,
            "requestedAt": deps["utc_now_iso"](),
        }
    )


def handle_research_reset_prompt(handler, deps: dict[str, Any]) -> None:
    """Reset the research prompt to default prompt content.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    default_file = deps["RESEARCH_PROMPT_DEFAULT_FILE"]
    if not default_file.exists():
        handler._json_response(
            {"error": f"Default research prompt not found: {default_file.name}"},
            status=404,
        )
        return

    deps["write_text"](
        deps["EDITOR_FILES"]["research_prompt"],
        deps["read_text"](default_file),
    )
    handler._json_response(
        {
            "success": True,
            "resetAt": deps["utc_now_iso"](),
            "state": deps["build_research_state"](),
        }
    )


def handle_research_run(handler, payload: dict[str, Any], deps: dict[str, Any]) -> None:
    """Start asynchronous research generation request.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - payload: Parsed JSON request body.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    try:
        handler._save_editor_payload(
            payload,
            allowed_keys={"cv", "prompt", "research_prompt", "jobspec"},
        )
        req = deps["parse_research_run_request"](payload)
    except ValueError as exc:
        handler._json_response({"error": str(exc)}, status=400)
        return

    prompt_text = deps["read_text"](deps["EDITOR_FILES"]["research_prompt"]).strip()
    default_file = deps["RESEARCH_PROMPT_DEFAULT_FILE"]
    if not prompt_text and default_file.exists():
        default_prompt_text = deps["read_text"](default_file)
        if default_prompt_text.strip():
            deps["write_text"](deps["EDITOR_FILES"]["research_prompt"], default_prompt_text)
            prompt_text = default_prompt_text.strip()

    if not prompt_text:
        handler._json_response(
            {
                "error": (
                    "Research prompt is empty. Reset prompt from default or save prompt content "
                    "before running research."
                )
            },
            status=400,
        )
        return

    run_lock = deps["RESEARCH_RUN_LOCK"]
    if not run_lock.acquire(blocking=False):
        handler._json_response({"error": "A research run is already in progress"}, status=409)
        return

    try:
        thread = threading.Thread(
            target=deps["run_research_subprocess_async"],
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
        run_lock.release()
        handler._json_response({"error": f"Failed to start research run: {exc}"}, status=500)
        return

    handler._json_response(
        {
            "success": True,
            "running": True,
            "run": deps["get_current_research_run_snapshot"](),
            "state": deps["build_research_state"](),
        }
    )


def handle_research_format(handler, deps: dict[str, Any]) -> None:
    """Start asynchronous research formatting request.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    run_lock = deps["RESEARCH_RUN_LOCK"]
    if not run_lock.acquire(blocking=False):
        handler._json_response({"error": "A research operation is already in progress"}, status=409)
        return

    try:
        thread = threading.Thread(target=deps["run_research_format_subprocess_async"], daemon=True)
        thread.start()
    except Exception as exc:
        run_lock.release()
        handler._json_response({"error": f"Failed to start research format: {exc}"}, status=500)
        return

    handler._json_response(
        {
            "success": True,
            "running": True,
            "run": deps["get_current_research_run_snapshot"](),
            "state": deps["build_research_state"](),
        }
    )


def handle_research_stop(handler, deps: dict[str, Any]) -> None:
    """Request cancellation for currently-running research.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    snapshot = deps["get_current_research_run_snapshot"]()
    if not snapshot or not snapshot.get("running"):
        handler._json_response({"error": "No active research run to stop"}, status=409)
        return

    if not deps["request_stop_research_run"]():
        handler._json_response({"error": "Unable to stop active research run"}, status=500)
        return

    handler._json_response(
        {
            "success": True,
            "stopping": True,
            "run": deps["get_current_research_run_snapshot"](),
        }
    )


def handle_cv_run(handler, route: str, payload: dict[str, Any], deps: dict[str, Any]) -> None:
    """Start asynchronous CV generation/formatting request.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - route: Request route used to infer full vs format mode.
    - payload: Parsed JSON request body.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    try:
        handler._save_editor_payload(
            payload,
            allowed_keys={"cv", "prompt", "research_prompt", "jobspec"},
        )
        req = deps["parse_cv_run_request"](route, payload)
    except ValueError as exc:
        handler._json_response({"error": str(exc)}, status=400)
        return

    run_lock = deps["RUN_LOCK"]
    if not run_lock.acquire(blocking=False):
        handler._json_response({"error": "A run is already in progress"}, status=409)
        return

    try:
        steering_file = deps["prepare_steering_file"](req.steering) if req.kind == "full" else None
        thread = threading.Thread(
            target=deps["run_subprocess_async"],
            args=(req.kind, req.selected_provider, req.selected_model, req.theme, steering_file),
            daemon=True,
        )
        thread.start()
    except Exception as exc:
        run_lock.release()
        handler._json_response({"error": f"Failed to start run: {exc}"}, status=500)
        return

    handler._json_response(
        {
            "success": True,
            "running": True,
            "run": deps["get_current_run_snapshot"](),
            "state": deps["build_state"](),
        }
    )


def handle_static_get(handler, route: str, deps: dict[str, Any]) -> bool:
    """Serve static assets when the route targets /static resources.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - route: Parsed URL path.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - True when route is handled (including 404), otherwise False.
    """
    if not route.startswith("/static/"):
        return False

    static_dir = deps["STATIC_DIR"]
    rel = route.removeprefix("/static/")
    if rel == "styles.css":
        handler._serve_file(static_dir / "styles.css", "text/css; charset=utf-8")
        return True
    if rel.startswith("styles/") and rel.endswith(".css"):
        css_path = static_dir / rel
        try:
            css_path.resolve().relative_to(static_dir.resolve())
        except ValueError:
            handler.send_error(HTTPStatus.NOT_FOUND, "Unknown static file")
            return True
        handler._serve_file(css_path, "text/css; charset=utf-8")
        return True
    if rel.startswith("js/") and rel.endswith(".js"):
        js_path = static_dir / rel
        try:
            js_path.resolve().relative_to(static_dir.resolve())
        except ValueError:
            handler.send_error(HTTPStatus.NOT_FOUND, "Unknown static file")
            return True
        handler._serve_file(js_path, "application/javascript; charset=utf-8")
        return True
    if rel == "app.js":
        handler._serve_file(static_dir / "app.js", "application/javascript; charset=utf-8")
        return True

    handler.send_error(HTTPStatus.NOT_FOUND, "Unknown static file")
    return True


def handle_api_run_status_get(handler, deps: dict[str, Any]) -> None:
    """Return status payload for active/completed CV run.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    current = deps["get_current_run_snapshot"]()
    last_run = deps["LAST_RUN"]
    run_payload = current if current is not None else (last_run if last_run else None)
    handler._json_response(
        {
            "running": bool(current and current.get("running")),
            "run": run_payload,
        }
    )


def handle_api_research_status_get(handler, deps: dict[str, Any]) -> None:
    """Return status payload for active/completed research run.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    current = deps["get_current_research_run_snapshot"]()
    last_run = deps["LAST_RESEARCH_RUN"]
    run_payload = current if current is not None else (last_run if last_run else None)
    handler._json_response(
        {
            "running": bool(current and current.get("running")),
            "run": run_payload,
        }
    )


def handle_logs_content_get(handler, parsed: Any, deps: dict[str, Any]) -> None:
    """Return log file content for a validated log filename.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - parsed: Parsed URL object containing query string.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    query = parse_qs(parsed.query)
    name = (query.get("name") or [""])[0]
    if not name:
        handler._json_response({"error": "Missing log file name"}, status=400)
        return
    try:
        content = deps["read_log_file"](name)
    except FileNotFoundError:
        handler._json_response({"error": "Log file not found"}, status=404)
        return
    except ValueError as exc:
        handler._json_response({"error": str(exc)}, status=400)
        return
    handler._json_response({"name": name, "content": content})


def handle_output_get(handler, route: str, deps: dict[str, Any]) -> bool:
    """Serve approved output artifacts when requested via /output.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - route: Parsed URL path.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - True when route is handled (including 404), otherwise False.
    """
    if not route.startswith("/output/"):
        return False

    name = route.removeprefix("/output/")
    if name not in deps["ALLOWED_OUTPUT_FILES"]:
        handler.send_error(HTTPStatus.NOT_FOUND, "Unknown output file")
        return True
    output_path = deps["OUTPUT_DIR"] / name
    content_type = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(output_path.suffix, "text/plain; charset=utf-8")
    handler._serve_file(output_path, content_type)
    return True


def dispatch_get(handler, request_path: str, deps: dict[str, Any]) -> None:
    """Route and handle incoming GET requests.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - request_path: Raw request path from BaseHTTPRequestHandler.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    parsed = urlparse(request_path)
    route = parsed.path

    if route in {"/", "/index.html"}:
        handler._serve_file(deps["TEMPLATES_DIR"] / "index.html", "text/html; charset=utf-8")
        return

    if handle_static_get(handler, route, deps):
        return

    if route == "/api/state":
        handler._json_response(deps["build_state"]())
        return

    if route == "/api/run/status":
        handle_api_run_status_get(handler, deps)
        return

    if route == "/api/research/state":
        handler._json_response(deps["build_research_state"]())
        return

    if route == "/api/research/status":
        handle_api_research_status_get(handler, deps)
        return

    if route == "/api/logs":
        logs = deps["collect_log_index"]()
        handler._json_response({"logs": logs, "lastRun": deps["LAST_RUN"]})
        return

    if route == "/api/logs/content":
        handle_logs_content_get(handler, parsed, deps)
        return

    if handle_output_get(handler, route, deps):
        return

    if server_roles.dispatch(handler, "GET", parsed, None, deps):
        return

    handler.send_error(HTTPStatus.NOT_FOUND, "Unknown route")


def dispatch_post(handler, request_path: str, deps: dict[str, Any]) -> None:
    """Route and handle incoming POST requests.

    Inputs:
    - handler: Request handler instance providing response helpers.
    - request_path: Raw request path from BaseHTTPRequestHandler.
    - deps: Dependency map supplied by cv_web.server.

    Returns:
    - None. This function performs side effects only.
    """
    parsed = urlparse(request_path)
    route = parsed.path

    try:
        payload = handler._parse_json_body()
    except ValueError as exc:
        handler._json_response({"error": str(exc)}, status=400)
        return

    if route == "/api/save":
        handle_save(handler, payload, deps)
        return

    if route == "/api/server/restart":
        handle_server_restart(handler, deps)
        return

    if route == "/api/research/reset-prompt":
        handle_research_reset_prompt(handler, deps)
        return

    if route == "/api/research/run":
        handle_research_run(handler, payload, deps)
        return

    if route == "/api/research/format":
        handle_research_format(handler, deps)
        return

    if route == "/api/research/stop":
        handle_research_stop(handler, deps)
        return

    if route in {"/api/run/full", "/api/run/format"}:
        handle_cv_run(handler, route, payload, deps)
        return

    if server_roles.dispatch(handler, "POST", parsed, payload, deps):
        return

    handler.send_error(HTTPStatus.NOT_FOUND, "Unknown route")


def dispatch_put(handler, request_path: str, deps: dict[str, Any]) -> None:
    """Route and handle incoming PUT requests (only the settings save uses PUT)."""
    parsed = urlparse(request_path)
    try:
        payload = handler._parse_json_body()
    except ValueError as exc:
        handler._json_response({"error": str(exc)}, status=400)
        return
    if server_roles.dispatch(handler, "PUT", parsed, payload, deps):
        return
    handler.send_error(HTTPStatus.NOT_FOUND, "Unknown route")

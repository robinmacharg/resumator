"""Role API for the multi-role workspace: roles, role and master CVs, runs, and run PDFs/DOCX (multi-role step 8).

Architecture role:
- Layer: backend HTTP handlers over `cv_web/store.py` and `cv_web/role_runner.py`.
- Responsibility: the `/api/roles…` and `/api/master/cv` routes, including promote and pull (`…/merge`, step 10,
  over `cv_web/role_merge.py`), CV version history and restore, and importing `input/CV.md` (step 11). `server_http_handlers.dispatch_get/post` hand
  every request to `dispatch` first; it returns False for routes it doesn't own.

Design notes (docs/plans/multi-role-design.md R6, R16, R21):
- One DB connection per request (`store.connect`), and one per background run thread. JSON keys are camelCase.
- Role runs share the CV and research run locks and live run state with the file-based runs, so
  `/api/run/status` and `/api/research/status` show their progress (with `roleId`, and `runId` once saved).
- PDFs and DOCX are rendered from the run's raw output on demand, never stored (R6). `RENDER_CACHE` keeps them in
  memory by (run, theme, format); a finished run warms it with its own PDF (R16).
- Archiving is `status = closed` through the update route (R21).
"""

from __future__ import annotations

import base64
import re
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import closing
from datetime import date
from typing import Any
from urllib.parse import parse_qs

from cv_convert import available_themes, render_cv
from cv_web import role_merge, role_runner, store
from cv_web import server_runtime_state as runtime
from cv_web.server_request_parsing import parse_selected_model, parse_selected_provider, parse_url_list
from cv_web.server_run_helpers import _build_research_run_state, _build_run_state

DB_PATH = store.DB_PATH
IMPORT_PATH = role_merge.IMPORT_PATH

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Request keys (camelCase) → role columns.
_ROLE_INPUT_FIELDS = {
    "name": "name",
    "slug": "slug",
    "company": "company",
    "status": "status",
    "jobspec": "jobspec",
    "steeringText": "steering_text",
    "steeringEnabled": "steering_enabled",
    "theme": "theme",
}


class ApiError(Exception):
    """A request the role API refuses; becomes `{error}` with the status."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Render cache (R16)
# ---------------------------------------------------------------------------


class RenderCache:
    """Rendered run documents in memory, keyed by (run id, theme, format), least recently used dropped first."""

    def __init__(self, limit: int = 32) -> None:
        self.limit = limit
        self._items: OrderedDict[tuple[int, str, str], bytes] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[int, str, str]) -> bytes | None:
        with self._lock:
            data = self._items.get(key)
            if data is not None:
                self._items.move_to_end(key)
            return data

    def put(self, key: tuple[int, str, str], data: bytes) -> None:
        with self._lock:
            self._items[key] = data
            self._items.move_to_end(key)
            while len(self._items) > self.limit:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


RENDER_CACHE = RenderCache()


def cache_key(run_id: int, theme: str, output_format: str) -> tuple[int, str, str]:
    """DOCX ignores the theme, so all its themes share one entry."""
    return run_id, theme if output_format == "pdf" else "", output_format


def run_markdown(conn: sqlite3.Connection, run: dict[str, Any]) -> str:
    """Tagged markdown for a CV run: its raw output validated as on the run's day, with its CV's directives."""
    import cv_source
    import generate_cv

    if not run.get("success") or not run.get("raw_output"):
        raise ApiError(f"CV run {run['id']} has no output to render", 409)
    cv = store.get_cv_version(conn, run["cv_version_id"])
    directives = cv_source.parse_cv_source(cv["content"])["directives"] if cv else {}
    run_day = date.fromisoformat(run["started_at"][:10])
    try:
        payload = generate_cv.parse_and_validate_json_output(
            run["raw_output"], role_cutoff=generate_cv.selected_roles_cutoff(run_day)
        )
    except ValueError as exc:
        raise ApiError(f"CV run {run['id']} output doesn't validate: {exc}", 409) from exc
    return generate_cv.render_tagged_markdown(payload, directives=directives)


def render_run(conn: sqlite3.Connection, run: dict[str, Any], theme: str, output_format: str) -> bytes:
    """A run's PDF or DOCX for a theme ("" = default), from the cache or rendered now."""
    key = cache_key(run["id"], theme, output_format)
    data = RENDER_CACHE.get(key)
    if data is None:
        data = render_cv(run_markdown(conn, run), output_format, key[1] or None)
        if data is None:
            raise ApiError(f"Rendering CV run {run['id']} as {output_format} failed (see the server log)", 500)
        RENDER_CACHE.put(key, data)
    return data


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def camel(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Store row → camelCase keys for the frontend."""
    if row is None:
        return None
    return {re.sub(r"_([a-z])", lambda m: m.group(1).upper(), key): value for key, value in row.items()}


def connect() -> sqlite3.Connection:
    return store.connect(DB_PATH)


def _require_role(conn: sqlite3.Connection, role_id: int) -> dict[str, Any]:
    role = store.get_role(conn, role_id)
    if role is None:
        raise ApiError(f"No role {role_id}", 404)
    return role


def _require_run(conn: sqlite3.Connection, role_id: int, kind: str, run_id: int) -> dict[str, Any]:
    run = store.get_cv_run(conn, run_id) if kind == "cv" else store.get_research_run(conn, run_id)
    if run is None or run["role_id"] != role_id:
        raise ApiError(f"No {kind} run {run_id} for role {role_id}", 404)
    return run


def _check_theme(theme: Any) -> str:
    """'' (default) or a theme in themes/."""
    if theme is None or theme == "":
        return ""
    if not isinstance(theme, str) or theme not in available_themes():
        raise ApiError(f"Unknown theme: {theme!r}")
    return theme


def parse_role_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Role fields from a create/update body (camelCase), checked and mapped to store columns."""
    unknown = set(payload) - set(_ROLE_INPUT_FIELDS)
    if unknown:
        raise ApiError(f"Unknown role field(s): {', '.join(sorted(unknown))}")
    fields: dict[str, Any] = {}
    for key, column in _ROLE_INPUT_FIELDS.items():
        if key not in payload:
            continue
        value = payload[key]
        if key == "steeringEnabled":
            if not isinstance(value, bool):
                raise ApiError("steeringEnabled must be a boolean")
        elif key == "theme":
            value = _check_theme(value) or None
        elif not isinstance(value, str):
            raise ApiError(f"{key} must be a string")
        fields[column] = value
    return fields


def _optional_text(payload: dict[str, Any], key: str) -> str | None:
    """None when absent or null (use the role's value); otherwise the string."""
    value = payload.get(key)
    if value is not None and not isinstance(value, str):
        raise ApiError(f"{key} must be a string")
    return value


def _cv_payload(conn: sqlite3.Connection, role_id: int | None) -> dict[str, Any]:
    return {
        "cv": camel(store.current_cv_version(conn, role_id)),
        "versions": [camel(row) for row in store.list_cv_versions(conn, role_id)],
    }


def _require_version(conn: sqlite3.Connection, role_id: int | None, version_id: int) -> dict[str, Any]:
    version = store.get_cv_version(conn, version_id)
    if version is None or version["role_id"] != role_id:
        owner = "the master" if role_id is None else f"role {role_id}"
        raise ApiError(f"No CV version {version_id} for {owner}", 404)
    return version


def _restore_cv(conn: sqlite3.Connection, role_id: int | None, version_id: int) -> dict[str, Any]:
    """Restore an old version as a new `edit` version (R8: history is append-only)."""
    version = _require_version(conn, role_id, version_id)
    return _save_cv(conn, role_id, {"content": version["content"], "note": f"Restored version {version_id}"})


def _save_cv(conn: sqlite3.Connection, role_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
    """Save a CV as a new `edit` version, unless the content is unchanged."""
    content = payload.get("content")
    if not isinstance(content, str):
        raise ApiError("content must be a string")
    note = _optional_text(payload, "note")
    current = store.current_cv_version(conn, role_id)
    if current is not None and current["content"] == content:
        return {"success": True, "unchanged": True, **_cv_payload(conn, role_id)}
    if role_id is not None and current is None:
        raise ApiError("This role has no CV to edit (seed it from the master first)", 409)
    store.add_cv_version(conn, content, source="edit", role_id=role_id, note=note)
    return {"success": True, "unchanged": False, **_cv_payload(conn, role_id)}


# ---------------------------------------------------------------------------
# Role runs in the background
# ---------------------------------------------------------------------------


def run_cv_in_background(role_id: int, options: dict[str, Any], run_lock: threading.Lock) -> None:
    """Thread body for a role CV run: live state in CURRENT_RUN, the saved run in LAST_RUN, cache warmed."""
    started_monotonic = time.monotonic()
    state = _build_run_state(
        kind="role-cv", command=["generate_cv.py", "--io", "json"],
        selected_provider=options["provider"], selected_model=options["model"], exit_code=None,
        started_at=store.now_iso(), finished_at=None, elapsed_seconds=0.0, success=None, running=True, output="",
        started_monotonic=started_monotonic,
    )
    runtime.set_current_run({**state, "roleId": role_id})
    saved: dict[str, Any] = {}
    try:
        with closing(connect()) as conn:
            outcome = role_runner.run_cv(conn, role_id, on_log=runtime.append_current_run_output, **options)
            saved = {"runId": outcome.run_id, "error": outcome.error}
            if outcome.pdf_base64:
                run = store.get_cv_run(conn, outcome.run_id)
                RENDER_CACHE.put(cache_key(outcome.run_id, run["theme"] or "", "pdf"),
                                 base64.b64decode(outcome.pdf_base64))
            code = 0 if outcome.success else 1
    except Exception as exc:  # noqa: BLE001 - the run state must always finish
        runtime.append_current_run_output(f"[runner] error: {exc}\n")
        saved = {"error": str(exc)}
        code = 1
    try:
        runtime.finalize_current_run(code)
        runtime.LAST_RUN.update(saved)
    finally:
        run_lock.release()  # after finalizing, so the next run's state can't be cleared by this one


def run_research_in_background(role_id: int, options: dict[str, Any], run_lock: threading.Lock) -> None:
    """Thread body for a role research run, with the same live state as file-based research (stop works)."""
    started_monotonic = time.monotonic()
    state = _build_research_run_state(
        command=["research_role.py", "--io", "json"], company_name=options["company"] or "",
        urls=options["urls"], dry_run=options["dry_run"], auto_format_pdf=False,
        selected_provider=options["provider"], selected_model=options["model"], exit_code=None,
        started_at=store.now_iso(), finished_at=None, elapsed_seconds=0.0, success=None, running=True, output="",
        started_monotonic=started_monotonic,
    )
    runtime.set_current_research_run({**state, "roleId": role_id})
    saved: dict[str, Any] = {}
    try:
        with closing(connect()) as conn:
            outcome = role_runner.run_research(
                conn, role_id, on_log=runtime.append_current_research_output,
                on_start=runtime.set_current_research_proc, **options,
            )
            saved = {"runId": outcome.run_id, "error": outcome.error}
            code = 0 if outcome.success else 1
    except Exception as exc:  # noqa: BLE001 - the run state must always finish
        runtime.append_current_research_output(f"[runner] error: {exc}\n")
        saved = {"error": str(exc)}
        code = 1
    try:
        runtime.set_current_research_proc(None)
        runtime.finalize_current_research_run(code)
        runtime.LAST_RESEARCH_RUN.update(saved)
    finally:
        run_lock.release()


def _start_run(conn: sqlite3.Connection, role_id: int, kind: str, payload: dict[str, Any],
               deps: dict[str, Any]) -> dict[str, Any]:
    """Check the request (so refusals come back now, not in the log), then start the run thread."""
    try:
        provider = parse_selected_provider(payload)
        model = parse_selected_model(payload, provider)
        if kind == "cv":
            options: dict[str, Any] = {
                "provider": provider, "model": model, "theme": payload.get("theme"),
                "steering": _optional_text(payload, "steering"),
            }
            if options["theme"] is not None:
                options["theme"] = _check_theme(options["theme"])
            role_runner.build_cv_request(conn, role_id, **options)
        else:
            options = {
                "provider": provider, "model": model, "company": _optional_text(payload, "company"),
                "urls": parse_url_list(payload), "dry_run": bool(payload.get("dryRun", False)),
            }
            role_runner.build_research_request(conn, role_id, **options)
    except (ValueError, role_runner.RunnerError) as exc:
        raise ApiError(str(exc)) from exc

    run_lock = deps["RUN_LOCK"] if kind == "cv" else deps["RESEARCH_RUN_LOCK"]
    if not run_lock.acquire(blocking=False):
        raise ApiError("A run is already in progress" if kind == "cv" else "A research run is already in progress",
                       409)
    target = run_cv_in_background if kind == "cv" else run_research_in_background
    try:
        threading.Thread(target=target, args=(role_id, options, run_lock), daemon=True).start()
    except Exception as exc:
        run_lock.release()
        raise ApiError(f"Failed to start run: {exc}", 500) from exc
    snapshot = runtime.get_current_run_snapshot() if kind == "cv" else runtime.get_current_research_run_snapshot()
    return {"success": True, "running": True, "run": snapshot}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

_ROLE = r"/api/roles/(?P<role>\d+)"
_GET_ROUTES = [
    (re.compile(r"/api/roles"), "list_roles"),
    (re.compile(_ROLE), "get_role"),
    (re.compile(_ROLE + r"/cv"), "get_role_cv"),
    (re.compile(_ROLE + r"/cv/versions/(?P<version>\d+)"), "get_role_cv_version"),
    (re.compile(_ROLE + r"/merge"), "get_merge"),
    (re.compile(_ROLE + r"/runs"), "list_runs"),
    (re.compile(_ROLE + r"/runs/(?P<kind>cv|research)/(?P<run>\d+)"), "get_run"),
    (re.compile(_ROLE + r"/runs/cv/(?P<run>\d+)/cv\.(?P<format>pdf|docx)"), "get_run_document"),
    (re.compile(r"/api/master/cv"), "get_master_cv"),
    (re.compile(r"/api/master/cv/versions/(?P<version>\d+)"), "get_master_cv_version"),
    (re.compile(r"/api/master/import"), "get_import"),
]
_POST_ROUTES = [
    (re.compile(r"/api/roles"), "create_role"),
    (re.compile(_ROLE), "update_role"),
    (re.compile(_ROLE + r"/delete"), "delete_role"),
    (re.compile(_ROLE + r"/cv"), "save_role_cv"),
    (re.compile(_ROLE + r"/cv/versions/(?P<version>\d+)/restore"), "restore_role_cv"),
    (re.compile(_ROLE + r"/merge"), "save_merge"),
    (re.compile(_ROLE + r"/runs/(?P<kind>cv|research)"), "start_run"),
    (re.compile(_ROLE + r"/runs/(?P<kind>cv|research)/(?P<run>\d+)/current"), "select_run"),
    (re.compile(r"/api/master/cv"), "save_master_cv"),
    (re.compile(r"/api/master/cv/versions/(?P<version>\d+)/restore"), "restore_master_cv"),
    (re.compile(r"/api/master/import"), "save_import"),
]


def _match(routes: list, route: str) -> tuple[str, dict[str, str]] | None:
    for pattern, name in routes:
        found = pattern.fullmatch(route)
        if found:
            return name, found.groupdict()
    return None


def dispatch(handler, method: str, parsed: Any, payload: dict[str, Any] | None, deps: dict[str, Any]) -> bool:
    """Handle a role API request. Returns False when the route isn't one of ours."""
    matched = _match(_GET_ROUTES if method == "GET" else _POST_ROUTES, parsed.path)
    if matched is None:
        return False
    name, params = matched
    query = {key: values[0] for key, values in parse_qs(parsed.query, keep_blank_values=True).items()}
    try:
        with closing(connect()) as conn:
            role_id = int(params["role"]) if "role" in params else None
            role = _require_role(conn, role_id) if role_id is not None else None
            response = _HANDLERS[name](conn, role, params, query, payload or {}, deps)
    except ApiError as exc:
        handler._json_response({"error": str(exc)}, status=exc.status)
        return True
    except role_merge.MergeError as exc:
        handler._json_response({"error": str(exc)}, status=exc.status)
        return True
    except store.StoreError as exc:
        handler._json_response({"error": str(exc)}, status=400)
        return True
    if isinstance(response, tuple):
        data, content_type, filename = response
        handler._bytes_response(data, content_type, filename=filename)
    else:
        handler._json_response(response)
    return True


def _list_roles(conn, role, params, query, payload, deps):
    status = query.get("status") or None
    return {"roles": [camel(row) for row in store.list_roles(conn, status=status)]}


def _get_role(conn, role, params, query, payload, deps):
    return {"role": camel(role)}


def _create_role(conn, role, params, query, payload, deps):
    fields = parse_role_fields(payload)
    name = fields.pop("name", "")
    if store.current_cv_version(conn, None) is None:
        raise ApiError("There is no master CV to seed the role from", 409)
    with store.transaction(conn):
        role_id = store.create_role(conn, name, **fields)
        store.seed_role_cv(conn, role_id)
    return {"success": True, "role": camel(store.get_role(conn, role_id))}


def _update_role(conn, role, params, query, payload, deps):
    fields = parse_role_fields(payload)
    if not fields:
        raise ApiError("Nothing to update")
    return {"success": True, "role": camel(store.update_role(conn, role["id"], **fields))}


def _delete_role(conn, role, params, query, payload, deps):
    active = runtime.get_current_run_snapshot() or {}
    active_research = runtime.get_current_research_run_snapshot() or {}
    if role["id"] in (active.get("roleId"), active_research.get("roleId")):
        raise ApiError("This role has a run in progress", 409)
    store.delete_role(conn, role["id"])
    return {"success": True, "deleted": role["id"]}


def _get_role_cv(conn, role, params, query, payload, deps):
    return _cv_payload(conn, role["id"])


def _save_role_cv(conn, role, params, query, payload, deps):
    return _save_cv(conn, role["id"], payload)


def _get_master_cv(conn, role, params, query, payload, deps):
    return _cv_payload(conn, None)


def _save_master_cv(conn, role, params, query, payload, deps):
    return _save_cv(conn, None, payload)


def _get_cv_version(conn, role, params, query, payload, deps):
    return {"version": camel(_require_version(conn, role and role["id"], int(params["version"])))}


def _restore_cv_handler(conn, role, params, query, payload, deps):
    return _restore_cv(conn, role and role["id"], int(params["version"]))


def _version_id(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ApiError(f"{key} must be the version id from the merge view")
    return value


def _get_import(conn, role, params, query, payload, deps):
    return role_merge.import_view(conn, IMPORT_PATH)


def _save_import(conn, role, params, query, payload, deps):
    source_hash = payload.get("sourceHash")
    if not isinstance(source_hash, str):
        raise ApiError("sourceHash must be the file hash from the merge view")
    accept, resolutions = role_merge.parse_decisions(payload.get("accept", []), payload.get("resolutions", []))
    result = role_merge.apply_import(
        conn, target_id=_version_id(payload, "targetId"), source_hash=source_hash, accept=accept,
        resolutions=resolutions, note=_optional_text(payload, "note"), path=IMPORT_PATH,
    )
    return {"success": True, **result, "masterCv": _cv_payload(conn, None)}


def _get_merge(conn, role, params, query, payload, deps):
    return role_merge.view(conn, role["id"], query.get("direction", ""))


def _save_merge(conn, role, params, query, payload, deps):
    direction = payload.get("direction", "")
    target_id, source_id = _version_id(payload, "targetId"), _version_id(payload, "sourceId")
    accept, resolutions = role_merge.parse_decisions(payload.get("accept", []), payload.get("resolutions", []))
    result = role_merge.apply(
        conn, role["id"], direction, target_id=target_id, source_id=source_id, accept=accept,
        resolutions=resolutions, note=_optional_text(payload, "note"),
    )
    return {"success": True, **result, "roleCv": _cv_payload(conn, role["id"]), "masterCv": _cv_payload(conn, None)}


def _list_runs(conn, role, params, query, payload, deps):
    return {
        "cvRuns": [camel(row) for row in store.list_cv_runs(conn, role["id"])],
        "researchRuns": [camel(row) for row in store.list_research_runs(conn, role["id"])],
    }


def _get_run(conn, role, params, query, payload, deps):
    return {"run": camel(_require_run(conn, role["id"], params["kind"], int(params["run"])))}


def _select_run(conn, role, params, query, payload, deps):
    run = _require_run(conn, role["id"], params["kind"], int(params["run"]))
    if params["kind"] == "cv":
        store.set_current_cv_run(conn, run["id"])
    else:
        store.set_current_research_run(conn, run["id"])
    return {"success": True, **_list_runs(conn, role, params, query, payload, deps)}


def _start_run_handler(conn, role, params, query, payload, deps):
    return _start_run(conn, role["id"], params["kind"], payload, deps)


def _get_run_document(conn, role, params, query, payload, deps):
    run = _require_run(conn, role["id"], "cv", int(params["run"]))
    output_format = params["format"]
    theme = _check_theme(query["theme"]) if "theme" in query else (run["theme"] or "")
    data = render_run(conn, run, theme, output_format)
    return data, CONTENT_TYPES[output_format], f"{role['slug']}-run{run['id']}.{output_format}"


_HANDLERS = {
    "list_roles": _list_roles,
    "get_role": _get_role,
    "create_role": _create_role,
    "update_role": _update_role,
    "delete_role": _delete_role,
    "get_role_cv": _get_role_cv,
    "save_role_cv": _save_role_cv,
    "get_master_cv": _get_master_cv,
    "save_master_cv": _save_master_cv,
    "get_role_cv_version": _get_cv_version,
    "get_master_cv_version": _get_cv_version,
    "restore_role_cv": _restore_cv_handler,
    "restore_master_cv": _restore_cv_handler,
    "get_import": _get_import,
    "save_import": _save_import,
    "get_merge": _get_merge,
    "save_merge": _save_merge,
    "list_runs": _list_runs,
    "get_run": _get_run,
    "select_run": _select_run,
    "start_run": _start_run_handler,
    "get_run_document": _get_run_document,
}

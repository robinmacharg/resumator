"""Role runs: build a request from the store, run a pipeline script over pipes, and save the run (multi-role R14).

Architecture role:
- Layer: orchestration between `cv_web/store.py` and the `--io json` scripts (`generate_cv.py`, `research_role.py`).
- Responsibility: the one place that turns a role into a run. The server (step 8) and the role CLI (step 13) both
  call `run_cv` / `run_research`; the scripts never see the DB.

Design notes (docs/plans/multi-role-design.md, "Run I/O"):
- The request goes in on stdin, stderr lines are streamed to `on_log` as they arrive and saved as the run's `log`,
  and stdout is read whole as the one JSON result.
- The prompt text actually sent is saved in `prompt_version` and linked by hash (R15).
- `cv_run` has no error column, so a run's error is appended to its `log`. Failed runs are kept and never current.
- `pdf_base64` is never stored (R6); it's handed back to the caller to warm the PDF cache (R16).
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

from cv_web import store

ROOT_DIR = Path(__file__).resolve().parent.parent
CV_SCRIPT = ROOT_DIR / "generate_cv.py"
RESEARCH_SCRIPT = ROOT_DIR / "research_role.py"
CV_PROMPT_FILE = ROOT_DIR / "input" / "prompt.md"
RESEARCH_PROMPT_FILE = ROOT_DIR / "input" / "research_prompt.md"

LogCallback = Callable[[str], None]
StartCallback = Callable[[subprocess.Popen], None]


class RunnerError(ValueError):
    """The role can't be run as asked (no CV, no company, empty prompt). Nothing is saved."""


@dataclass
class RunOutcome:
    """What a role run produced. `run_id` is the saved cv_run/research_run row."""

    run_id: int
    success: bool
    error: str | None
    log: str
    result: dict[str, Any] = field(default_factory=dict)
    pdf_base64: str | None = None


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


def read_prompt(path: Path) -> str:
    """Prompt template text, stripped as the scripts strip it, so the saved hash matches what was sent."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RunnerError(f"{path} is empty")
    return text


def _role_and_cv(conn: sqlite3.Connection, role_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    role = store.get_role(conn, role_id)
    if role is None:
        raise RunnerError(f"No role {role_id}")
    cv = store.current_cv_version(conn, role_id)
    if cv is None:
        raise RunnerError(f"Role {role['name']!r} has no CV yet (seed it from the master)")
    return role, cv


def build_cv_request(
    conn: sqlite3.Connection,
    role_id: int,
    *,
    provider: str = "",
    model: str = "",
    theme: str | None = None,
    steering: str | None = None,
    prompt: str | None = None,
) -> tuple[dict[str, Any], int]:
    """The `generate_cv --io json` request for a role, and the CV version id it uses.

    - theme: None uses the role's theme ("" is the default theme).
    - steering: None uses the role's steering when it's enabled; "" sends none.
    - prompt: None reads `input/prompt.md`.
    """
    role, cv = _role_and_cv(conn, role_id)
    if steering is None:
        steering = role["steering_text"] if role["steering_enabled"] else ""
    request = {
        "cv": cv["content"],
        "jobspec": role["jobspec"],
        "steering": steering.strip(),
        "prompt": (prompt if prompt is not None else read_prompt(CV_PROMPT_FILE)).strip(),
        "theme": (role["theme"] or "") if theme is None else theme,
        "provider": provider,
        "model": model,
    }
    return request, cv["id"]


def build_research_request(
    conn: sqlite3.Connection,
    role_id: int,
    *,
    company: str | None = None,
    urls: Iterable[str] = (),
    provider: str = "",
    model: str = "",
    dry_run: bool = False,
    prompt: str | None = None,
) -> dict[str, Any]:
    """The `research_role --io json` request for a role. company: None uses the role's company.
    prompt: None reads `input/research_prompt.md`."""
    role, cv = _role_and_cv(conn, role_id)
    company = (role["company"] if company is None else company).strip()
    if not company:
        raise RunnerError(f"Role {role['name']!r} has no company to research")
    return {
        "cv": cv["content"],
        "jobspec": role["jobspec"],
        "prompt": (prompt if prompt is not None else read_prompt(RESEARCH_PROMPT_FILE)).strip(),
        "company": company,
        "urls": list(dict.fromkeys(url.strip() for url in urls if url.strip())),
        "provider": provider,
        "model": model,
        "dry_run": bool(dry_run),
    }


# ---------------------------------------------------------------------------
# Running a script
# ---------------------------------------------------------------------------


def run_script(
    script: Path,
    request: dict[str, Any],
    *,
    on_log: LogCallback | None = None,
    on_start: StartCallback | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], str]:
    """Run `script --io json` from the repo root with the request on stdin.

    Returns (exit code, result, log). Each stderr line goes to on_log as it arrives; on_start gets the process
    (for cancelling). A missing or unreadable result becomes `{success: False, error: …}`.
    """
    proc = subprocess.Popen(
        [sys.executable, str(script), "--io", "json"],
        cwd=ROOT_DIR,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
        env=env,
    )
    if on_start is not None:
        on_start(proc)
    log_lines: list[str] = []
    stdout_parts: list[str] = []

    def read_stderr() -> None:
        for line in iter(proc.stderr.readline, ""):
            log_lines.append(line)
            if on_log is not None:
                on_log(line)

    readers = [
        threading.Thread(target=read_stderr, daemon=True),
        threading.Thread(target=lambda: stdout_parts.append(proc.stdout.read()), daemon=True),
    ]
    for reader in readers:
        reader.start()
    try:
        proc.stdin.write(json.dumps(request, ensure_ascii=False))
        proc.stdin.close()
    except BrokenPipeError:
        pass  # the script exited early; its result (or lack of one) says why
    code = proc.wait()
    for reader in readers:
        reader.join()
    proc.stdout.close()
    proc.stderr.close()
    return code, _parse_result("".join(stdout_parts), code), "".join(log_lines)


def _parse_result(stdout: str, code: int) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if lines:
        try:
            result = json.loads(lines[-1])
        except json.JSONDecodeError:
            result = None
        if isinstance(result, dict):
            return result
    return {"success": False, "error": f"the script gave no JSON result (exit code {code})"}


def _final_log(log: str, error: str | None) -> str:
    if not error:
        return log
    separator = "" if not log or log.endswith("\n") else "\n"
    return f"{log}{separator}[runner] error: {error}\n"


# ---------------------------------------------------------------------------
# Role runs
# ---------------------------------------------------------------------------


def run_cv(
    conn: sqlite3.Connection,
    role_id: int,
    *,
    provider: str = "",
    model: str = "",
    theme: str | None = None,
    steering: str | None = None,
    prompt: str | None = None,
    make_current: bool = True,
    on_log: LogCallback | None = None,
    on_start: StartCallback | None = None,
    env: dict[str, str] | None = None,
) -> RunOutcome:
    """Generate a CV for a role and save the `cv_run` row. Options as in build_cv_request; a successful run
    becomes current unless make_current is False."""
    request, cv_version_id = build_cv_request(
        conn, role_id, provider=provider, model=model, theme=theme, steering=steering, prompt=prompt
    )
    prompt_hash = store.save_prompt(conn, "cv", request["prompt"])
    started_at = store.now_iso()
    _, result, log = run_script(CV_SCRIPT, request, on_log=on_log, on_start=on_start, env=env)
    success = bool(result.get("success"))
    error = result.get("error")
    # S5 step 15 adds token usage here: result["usage"] → a usage_json column.
    run_id = store.add_cv_run(
        conn,
        role_id,
        cv_version_id,
        success=success,
        make_current=make_current,
        prompt_hash=prompt_hash,
        provider=result.get("provider") or provider or None,
        model=result.get("model") or model or None,
        theme=request["theme"] or None,
        steering_text=request["steering"] or None,
        raw_output=result.get("raw_output"),
        model_json=result.get("model_json"),
        warnings_json=result.get("warnings"),
        page_count=result.get("page_count"),
        log=_final_log(log, error),
        started_at=started_at,
        finished_at=store.now_iso(),
    )
    return RunOutcome(run_id, success, error, log, result, result.get("pdf_base64"))


def run_markdown(conn: sqlite3.Connection, run: dict[str, Any]) -> str:
    """Tagged markdown for a CV run: its raw output validated as on the run's day, with its CV's directives.
    Used to render a run's PDF/DOCX on demand (R6) by the server and the role CLI."""
    import cv_source
    import generate_cv

    if not run.get("success") or not run.get("raw_output"):
        raise RunnerError(f"CV run {run['id']} has no output to render")
    cv = store.get_cv_version(conn, run["cv_version_id"])
    directives = cv_source.parse_cv_source(cv["content"])["directives"] if cv else {}
    run_day = date.fromisoformat(run["started_at"][:10])
    try:
        payload = generate_cv.parse_and_validate_json_output(
            run["raw_output"], role_cutoff=generate_cv.selected_roles_cutoff(run_day)
        )
    except ValueError as exc:
        raise RunnerError(f"CV run {run['id']} output doesn't validate: {exc}") from exc
    return generate_cv.render_tagged_markdown(payload, directives=directives)


def run_research(
    conn: sqlite3.Connection,
    role_id: int,
    *,
    company: str | None = None,
    urls: Iterable[str] = (),
    provider: str = "",
    model: str = "",
    dry_run: bool = False,
    prompt: str | None = None,
    make_current: bool = True,
    on_log: LogCallback | None = None,
    on_start: StartCallback | None = None,
    env: dict[str, str] | None = None,
) -> RunOutcome:
    """Research a role's company and save the `research_run` row. Options as in build_research_request."""
    request = build_research_request(
        conn, role_id, company=company, urls=urls, provider=provider, model=model, dry_run=dry_run, prompt=prompt
    )
    prompt_hash = store.save_prompt(conn, "research", request["prompt"])
    started_at = store.now_iso()
    _, result, log = run_script(RESEARCH_SCRIPT, request, on_log=on_log, on_start=on_start, env=env)
    success = bool(result.get("success"))
    error = result.get("error")
    run_id = store.add_research_run(
        conn,
        role_id,
        success=success,
        make_current=make_current,
        prompt_hash=prompt_hash,
        provider=result.get("provider") or provider or None,
        model=result.get("model") or model or None,
        company=request["company"],
        urls_json=request["urls"],
        dry_run=request["dry_run"],
        output_json=result.get("output_json"),
        output_md=result.get("output_md"),
        log=_final_log(log, error),
        started_at=started_at,
        finished_at=store.now_iso(),
    )
    return RunOutcome(run_id, success, error, log, result)

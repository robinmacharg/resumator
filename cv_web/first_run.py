"""First run for a new install: example data or a blank master CV (multi-role step 12, design R3).

Architecture role:
- Layer: backend data setup over `cv_web/store.py`, used by the `/api/setup` routes in `server_roles.py`.
- Responsibility: say whether the first-run choice is still due, and carry it out once.

Design notes (docs/plans/multi-role-design.md "First-run behaviour"):
- The choice is due while the DB has no master CV, no roles and no `first_run_done` setting. An install migrated
  with `migrate_single_role` already has a master, so it never sees the choice.
- **Example:** a fictional master CV, a role with a short job spec (its CV seeded from the master) and a canned,
  successful CV run, so the run picker and preview work without a model call. Files in `examples/`.
- **Blank:** a master CV template full of TODOs (`examples/blank-cv.md`) and no roles.
- Both master versions use source `example` (shipped content), with a note saying which.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from cv_web import store

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
SETTING_KEY = "first_run_done"
CHOICES = ("example", "blank")

EXAMPLE_ROLE = {"name": "Lead iOS Engineer", "company": "Northwind Health"}


class FirstRunError(Exception):
    """A setup request that's refused; `status` is the HTTP status the API returns."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def status(conn: sqlite3.Connection) -> dict[str, Any]:
    """`{needed, done, hasMaster, roleCount}`: needed = the first-run choice is still due."""
    done = store.get_setting(conn, SETTING_KEY)
    has_master = store.current_cv_version(conn, None) is not None
    role_count = len(store.list_roles(conn))
    return {
        "needed": done is None and not has_master and role_count == 0,
        "done": done,
        "hasMaster": has_master,
        "roleCount": role_count,
    }


def set_up(conn: sqlite3.Connection, choice: str, examples_dir: Path = EXAMPLES_DIR) -> dict[str, Any]:
    """Carry out the first-run choice and record it. Returns `{choice, masterVersionId, roleId, runId}`
    (role and run are None for blank). 409 when the choice was already made or the DB has data."""
    if choice not in CHOICES:
        raise FirstRunError(f"choice must be one of {', '.join(CHOICES)}")
    files = _read_examples(examples_dir, choice)
    with store.transaction(conn):
        if not status(conn)["needed"]:
            raise FirstRunError("First-run setup is already done", 409)
        if choice == "blank":
            master_id = store.add_cv_version(conn, files["blank"], source="example", note="Blank master CV template")
            role_id = run_id = None
        else:
            master_id = store.add_cv_version(conn, files["cv"], source="example", note="Example master CV")
            role_id = store.create_role(conn, EXAMPLE_ROLE["name"], company=EXAMPLE_ROLE["company"],
                                        jobspec=files["jobspec"])
            version_id = store.seed_role_cv(conn, role_id, note="Example role CV")
            run_id = store.add_cv_run(conn, role_id, version_id, success=True, **_example_run(files["run"]))
        store.set_setting(conn, SETTING_KEY, choice)
    return {"choice": choice, "masterVersionId": master_id, "roleId": role_id, "runId": run_id}


def _read_examples(examples_dir: Path, choice: str) -> dict[str, str]:
    names = {"blank": "blank-cv.md"} if choice == "blank" else {
        "cv": "master-cv.md", "jobspec": "jobspec.txt", "run": "run.json",
    }
    files = {}
    for key, name in names.items():
        path = examples_dir / name
        try:
            files[key] = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FirstRunError(f"Can't read {path}: {exc}", 500) from exc
    return files


def _example_run(text: str) -> dict[str, Any]:
    """The `add_cv_run` fields for the canned run: its output validated as on its own (fixed) run day."""
    import generate_cv

    spec = json.loads(text)
    raw_output = json.dumps(spec["output"], indent=2)
    warnings: list[str] = []
    run_day = date.fromisoformat(spec["startedAt"][:10])
    model_json = generate_cv.parse_and_validate_json_output(
        raw_output, role_cutoff=generate_cv.selected_roles_cutoff(run_day), warnings=warnings
    )
    return {
        "provider": spec.get("provider"),
        "model": spec.get("model"),
        "raw_output": raw_output,
        "model_json": model_json,
        "warnings_json": warnings,
        "log": "[first run] canned example run from examples/run.json; no model was called",
        "started_at": spec["startedAt"],
        "finished_at": spec.get("finishedAt"),
    }

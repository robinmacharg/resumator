"""Promote and pull between a role's CV and the master CV (multi-role step 10, R7, R11), and importing
`input/CV.md` into the master through the same merge view (step 11, R12).

Architecture role:
- Layer: workflow over `cv_web/store.py` and `cv_merge.py` (no HTTP; the role API and a future CLI call it).
- Responsibility: build the merge view for a direction, and save the merged CV as a new version.

Design notes (docs/plans/multi-role-design.md R7, R11):
- Both directions are three-way merges against the role CV's `base_master_id` version. Promote: ours = master,
  theirs = role, result = a new master version (`promote`). Pull: ours = role, theirs = master, result = a new role
  version (`pull`) whose base is the current master.
- Removals and conflicts start unticked (`cv_merge.default_accept`); every conflict needs a resolution to save.
- A promote moves the role's base to the new master only when the role already has every master change since its
  base (nothing left to pull). Moving it otherwise would make those master changes look like role reverts on the
  next promote. The move is a role version with unchanged content and source `promote`.
- The view carries the version ids it was built from; saving refuses (stale) if either CV changed since.
- Import: base = the file text as last imported (setting `master_import_text`; before the first import through
  the UI, the newest master `import` version, else empty), ours = master, theirs = the file. Saved as an `import`
  master version, and the file text becomes the next base even when nothing was accepted, so declined file changes
  don't come back. The base can't be the saved master version: it holds master edits the file lacks, which would
  then look like file reverts. The file has no version id, so its SHA-256 marks a stale view.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

import cv_merge
from cv_web import store

PROMOTE = "promote"
PULL = "pull"
DIRECTIONS = (PROMOTE, PULL)
IMPORT = "import"

IMPORT_BASE_SETTING = "master_import_text"  # file text at the last import (R12 merge base)
IMPORT_PATH = Path(__file__).resolve().parent.parent / "input" / "CV.md"

# Conflict choices from the client: keep the target's text, take the source's, or edited text.
CHOICES = ("current", "incoming", "edit")


class MergeError(ValueError):
    """A merge the caller can't do now. `status` is the HTTP status the role API should use."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _sides(conn: sqlite3.Connection, role_id: int, direction: str) -> dict[str, dict[str, Any]]:
    """Base, target (ours) and source (theirs) version rows, plus the role and master CVs."""
    if direction not in DIRECTIONS:
        raise MergeError(f"direction must be one of {', '.join(DIRECTIONS)}")
    role_cv = store.current_cv_version(conn, role_id)
    if role_cv is None:
        raise MergeError("This role has no CV (seed it from the master first)", 409)
    master = store.current_cv_version(conn, None)
    if master is None:
        raise MergeError("There is no master CV", 409)
    base = store.get_cv_version(conn, role_cv["base_master_id"])
    if direction == PROMOTE:
        target, source = master, role_cv
    else:
        target, source = role_cv, master
    return {"base": base, "target": target, "source": source, "role": role_cv, "master": master}


def _key(change: cv_merge.Change) -> list[str]:
    return list(change.key)


def _changes_payload(changes: list[cv_merge.Change]) -> list[dict[str, Any]]:
    defaults = cv_merge.default_accept(changes)
    return [
        {
            "key": _key(change),
            "kind": change.kind,
            "heading": change.heading,
            "status": change.status,
            "base": change.base,
            "current": change.ours,
            "incoming": change.theirs,
            "diff": change.diff,
            "accept": change.key in defaults,
        }
        for change in changes
    ]


def view(conn: sqlite3.Connection, role_id: int, direction: str) -> dict[str, Any]:
    """The merge view: every unit needing a decision, with default ticks and an inline diff (camelCase keys)."""
    sides = _sides(conn, role_id, direction)
    base, target, source = sides["base"], sides["target"], sides["source"]
    changes = cv_merge.compare(base["content"], target["content"], source["content"])
    return {
        "direction": direction,
        "baseId": base["id"],
        "targetId": target["id"],
        "sourceId": source["id"],
        "changes": _changes_payload(changes),
        # Pull with nothing to merge still moves the base when the master has moved on.
        "baseBehind": base["id"] != sides["master"]["id"],
    }


def _parse_key(value: Any) -> tuple[str, str]:
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(part, str) for part in value)):
        raise MergeError("Each key must be a [section, entry] pair of strings")
    return value[0], value[1]


def parse_decisions(
    accept: Any, resolutions: Any
) -> tuple[set[tuple[str, str]], dict[tuple[str, str], str | None]]:
    """Client decisions → `cv_merge.merge` arguments.

    - `accept`: list of keys to take from the source.
    - `resolutions`: list of `{key, choice: current|incoming|edit, text}`; blank edited text drops the unit.
    """
    if not isinstance(accept, list):
        raise MergeError("accept must be a list of keys")
    if not isinstance(resolutions, list):
        raise MergeError("resolutions must be a list")
    keys = {_parse_key(item) for item in accept}
    resolved: dict[tuple[str, str], str | None] = {}
    for item in resolutions:
        if not isinstance(item, dict):
            raise MergeError("Each resolution must be an object")
        key = _parse_key(item.get("key"))
        choice = item.get("choice")
        if choice not in CHOICES:
            raise MergeError(f"Resolution choice must be one of {', '.join(CHOICES)}")
        if choice == "current":
            resolved[key] = cv_merge.KEEP_OURS
        elif choice == "incoming":
            resolved[key] = cv_merge.TAKE_THEIRS
        else:
            text = item.get("text")
            if not isinstance(text, str):
                raise MergeError("An edited resolution needs text")
            resolved[key] = text if text.strip() else None
    return keys, resolved


def _check_decisions(
    changes: list[cv_merge.Change], accept: set[tuple[str, str]], resolutions: dict[tuple[str, str], str | None]
) -> None:
    """Ticks must name non-conflict changes, resolutions conflicts, and every conflict needs one."""
    conflicts = {change.key for change in changes if change.status == cv_merge.CONFLICT}
    others = {change.key for change in changes} - conflicts
    if accept - others:
        raise MergeError("accept names entries that aren't changes in this merge")
    if set(resolutions) - conflicts:
        raise MergeError("resolutions name entries that aren't conflicts in this merge")
    if conflicts - set(resolutions):
        raise MergeError(f"Resolve every conflict first ({len(conflicts - set(resolutions))} left)")


def apply(
    conn: sqlite3.Connection,
    role_id: int,
    direction: str,
    *,
    target_id: int,
    source_id: int,
    accept: set[tuple[str, str]],
    resolutions: dict[tuple[str, str], str | None],
    note: str | None = None,
) -> dict[str, Any]:
    """Save the merge as a new version. Returns `{unchanged, versionId, baseMoved}`."""
    with store.transaction(conn):
        sides = _sides(conn, role_id, direction)
        base, target, source = sides["base"], sides["target"], sides["source"]
        if (target["id"], source["id"]) != (target_id, source_id):
            raise MergeError("The role or master CV changed since the merge view opened; open it again", 409)
        changes = cv_merge.compare(base["content"], target["content"], source["content"])
        _check_decisions(changes, accept, resolutions)
        merged = cv_merge.merge(base["content"], target["content"], source["content"], accept, resolutions).text

        if direction == PULL:
            master_id = sides["master"]["id"]
            if merged == target["content"] and base["id"] == master_id:
                return {"unchanged": True, "versionId": None, "baseMoved": False}
            version_id = store.add_cv_version(
                conn, merged, source="pull", role_id=role_id, base_master_id=master_id, note=note
            )
            return {"unchanged": False, "versionId": version_id, "baseMoved": base["id"] != master_id}

        if merged == target["content"]:
            return {"unchanged": True, "versionId": None, "baseMoved": False}
        version_id = store.add_cv_version(conn, merged, source="promote", note=note)
        role_cv = sides["role"]
        base_moved = not cv_merge.compare(base["content"], role_cv["content"], merged)
        if base_moved:
            store.add_cv_version(
                conn, role_cv["content"], source="promote", role_id=role_id, base_master_id=version_id,
                note=f"Synced with master version {version_id} after promote",
            )
        return {"unchanged": False, "versionId": version_id, "baseMoved": base_moved}


# ---------------------------------------------------------------------------
# Import input/CV.md as master (R12)
# ---------------------------------------------------------------------------


def file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _import_sides(conn: sqlite3.Connection, path: Path) -> tuple[str, str, dict[str, Any], str]:
    """Base text and where it came from (`lastImport`, `importVersion` or `none`), current master, file text."""
    master = store.current_cv_version(conn, None)
    if master is None:
        raise MergeError("There is no master CV", 409)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MergeError(f"Can't read {path.name}: {exc.strerror or exc}", 409) from exc
    base_text = store.get_setting(conn, IMPORT_BASE_SETTING)
    if base_text is not None:
        return base_text, "lastImport", master, text
    version = next(
        (row for row in store.list_cv_versions(conn, None, include_content=True) if row["source"] == IMPORT), None
    )
    if version is not None:
        return version["content"], "importVersion", master, text
    return "", "none", master, text


def import_view(conn: sqlite3.Connection, path: Path = IMPORT_PATH) -> dict[str, Any]:
    """Merge view for importing the file into the master (same change shape as `view`)."""
    base_text, base_from, master, text = _import_sides(conn, path)
    return {
        "direction": IMPORT,
        "baseFrom": base_from,
        "targetId": master["id"],
        "sourceHash": file_hash(text),
        "changes": _changes_payload(cv_merge.compare(base_text, master["content"], text)),
    }


def apply_import(
    conn: sqlite3.Connection,
    *,
    target_id: int,
    source_hash: str,
    accept: set[tuple[str, str]],
    resolutions: dict[tuple[str, str], str | None],
    note: str | None = None,
    path: Path = IMPORT_PATH,
) -> dict[str, Any]:
    """Save the import as a new `import` master version and record the file as the next base.

    Returns `{unchanged, versionId}`; `unchanged` means the master didn't change (the base may still move).
    """
    with store.transaction(conn):
        base_text, _, master, text = _import_sides(conn, path)
        if (master["id"], file_hash(text)) != (target_id, source_hash):
            raise MergeError(f"The master CV or {path.name} changed since the merge view opened; open it again", 409)
        _check_decisions(cv_merge.compare(base_text, master["content"], text), accept, resolutions)
        merged = cv_merge.merge(base_text, master["content"], text, accept, resolutions).text
        store.set_setting(conn, IMPORT_BASE_SETTING, text)
        if merged == master["content"]:
            return {"unchanged": True, "versionId": None}
        version_id = store.add_cv_version(conn, merged, source=IMPORT, note=note or f"Imported {path.name}")
        return {"unchanged": False, "versionId": version_id}

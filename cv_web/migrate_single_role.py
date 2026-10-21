"""One-time migration of a single-role install into the multi-role store (docs/plans/multi-role.md R4).

Architecture role:
- Layer: CLI over `cv_web/store.py` (run once, from the repo root: `python3 -m cv_web.migrate_single_role`).
- Responsibility: turn today's `input/` and `output/` files into the master CV and a first role with its runs.

Design notes:
- Writes through `store` directly, not `role_runner`: nothing is generated.
- Master: `input/CV.md` as a master `import` version (skipped when it equals the current master).
- Role: `--name`, the company from `--company` or the current run's `metadata.company`, the job spec from
  `input/jobspec.txt`, and its CV seeded from the master (R1).
- CV runs: `output/tailored.model-output.txt` + `tailored.model.json` as the current run, and each `--archive` folder
  (same two files) as an older one. Steering, warnings and page count come from `metadata`. Provider, model, theme
  and prompt aren't recorded in those files, so they stay NULL. Every run points at the seeded CV version (the CV
  text the archived runs saw isn't kept). File modification times stand in for run times.
- Research: `output/research_output.json` (the envelope) + `.md`, with `input/research_company.txt` and
  `research_urls.txt` as fallbacks for the company and URLs. `--no-research` skips it.
- Idempotent: if the role already exists, nothing is written. Everything else happens in one transaction.
- Steering and theme live in browser localStorage; the UI copies them into the role later (step 9).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cv_web import store

CV_RAW_FILE = "tailored.model-output.txt"
CV_JSON_FILE = "tailored.model.json"
RESEARCH_JSON_FILE = "research_output.json"
RESEARCH_MD_FILE = "research_output.md"


class MigrationError(ValueError):
    """The files needed for the migration are missing or unreadable. Nothing is written."""


@dataclass
class MigrationReport:
    """What the migration did. `skipped` means the role already existed and nothing was written."""

    role_id: int
    skipped: bool = False
    master_version_id: int | None = None
    master_imported: bool = False
    cv_version_id: int | None = None
    cv_run_ids: list[int] = field(default_factory=list)
    current_cv_run_id: int | None = None
    research_run_id: int | None = None


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MigrationError(f"Can't read {path}: {exc}") from exc


def _read_json(path: Path) -> Any:
    try:
        return json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise MigrationError(f"{path} isn't valid JSON: {exc}") from exc


def read_cv_run(run_dir: Path) -> dict[str, Any]:
    """The `add_cv_run` fields for the run saved in run_dir (raw output + model JSON with run metadata)."""
    raw_path, json_path = run_dir / CV_RAW_FILE, run_dir / CV_JSON_FILE
    for path in (raw_path, json_path):
        if not path.is_file():
            raise MigrationError(f"No CV run in {run_dir}: {path.name} is missing")
    model_json = _read_json(json_path)
    metadata = model_json.get("metadata") if isinstance(model_json, dict) else None
    metadata = metadata if isinstance(metadata, dict) else {}
    stamp = _mtime_iso(json_path)
    return {
        "raw_output": _read_text(raw_path),
        "model_json": model_json,
        "steering_text": (metadata.get("steering") or "").strip() or None,
        "warnings_json": metadata.get("warnings") if isinstance(metadata.get("warnings"), list) else None,
        "page_count": metadata.get("page_count") if isinstance(metadata.get("page_count"), int) else None,
        "log": f"[migrate] imported from {run_dir / CV_RAW_FILE} and {CV_JSON_FILE}",
        "started_at": stamp,
        "finished_at": stamp,
    }


def read_research_run(input_dir: Path, output_dir: Path) -> dict[str, Any] | None:
    """The `add_research_run` fields for output/research_output.json + .md, or None when there's no research."""
    json_path, md_path = output_dir / RESEARCH_JSON_FILE, output_dir / RESEARCH_MD_FILE
    if not json_path.is_file():
        return None
    envelope = _read_json(json_path)
    if not isinstance(envelope, dict):
        raise MigrationError(f"{json_path} isn't a research result object")
    company = str(envelope.get("companyName") or "").strip()
    if not company and (input_dir / "research_company.txt").is_file():
        company = _read_text(input_dir / "research_company.txt").strip()
    urls = envelope.get("urls")
    if not isinstance(urls, list) and (input_dir / "research_urls.txt").is_file():
        urls = [line.strip() for line in _read_text(input_dir / "research_urls.txt").splitlines() if line.strip()]
    stamp = _mtime_iso(json_path)
    return {
        "provider": envelope.get("provider") or None,
        "model": envelope.get("model") or None,
        "company": company,
        "urls_json": urls if isinstance(urls, list) else [],
        "dry_run": bool(envelope.get("dryRun")),
        "output_json": envelope,
        "output_md": _read_text(md_path) if md_path.is_file() else "",
        "log": f"[migrate] imported from {json_path}",
        "started_at": stamp,
        "finished_at": stamp,
    }


def migrate_single_role(
    conn: sqlite3.Connection,
    name: str,
    *,
    company: str | None = None,
    input_dir: Path = Path("input"),
    output_dir: Path = Path("output"),
    archive_dirs: tuple[Path, ...] = (),
    research: bool = True,
) -> MigrationReport:
    """Import today's single-role files as the master CV and one role with its runs (R4).

    - All files are read before anything is written, so a missing file leaves the DB untouched.
    - Archived runs are saved oldest first (by file time), then the current run, which becomes current.
    - Returns a report; `skipped` is True when a role with this name already exists.
    """
    existing = store.find_role(conn, name)
    if existing is not None:
        return MigrationReport(role_id=existing["id"], skipped=True)

    cv_path = input_dir / "CV.md"
    if not cv_path.is_file():
        raise MigrationError(f"No master CV at {cv_path}")
    cv_text = _read_text(cv_path)
    jobspec_path = input_dir / "jobspec.txt"
    jobspec = _read_text(jobspec_path) if jobspec_path.is_file() else ""

    current_run = read_cv_run(output_dir) if (output_dir / CV_JSON_FILE).is_file() else None
    archived_runs = sorted((read_cv_run(path) for path in archive_dirs), key=lambda run: run["started_at"])
    research_run = read_research_run(input_dir, output_dir) if research else None

    if company is None:
        metadata = (current_run or {}).get("model_json", {}).get("metadata") or {}
        company = str(metadata.get("company") or "").strip()

    report = MigrationReport(role_id=0)
    with store.transaction(conn):
        master = store.current_cv_version(conn, None)
        if master is not None and master["content"] == cv_text:
            report.master_version_id = master["id"]
        else:
            report.master_version_id = store.add_cv_version(
                conn, cv_text, source="import", note=f"Imported from {cv_path}"
            )
            report.master_imported = True
        report.role_id = store.create_role(conn, name, company=company, jobspec=jobspec)
        report.cv_version_id = store.seed_role_cv(conn, report.role_id, note="Seeded by the single-role migration")
        for run in archived_runs:
            report.cv_run_ids.append(
                store.add_cv_run(conn, report.role_id, report.cv_version_id, success=True, make_current=False, **run)
            )
        if current_run is not None:
            report.current_cv_run_id = store.add_cv_run(
                conn, report.role_id, report.cv_version_id, success=True, **current_run
            )
            report.cv_run_ids.append(report.current_cv_run_id)
        if research_run is not None:
            report.research_run_id = store.add_research_run(conn, report.role_id, success=True, **research_run)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-time import of this install's input/ and output/ files as the first role (run from the "
        "repo root)."
    )
    parser.add_argument("--name", required=True, help="Role name, e.g. \"Quantum Base\"")
    parser.add_argument("--company", help="Company (default: the current CV run's metadata.company)")
    parser.add_argument("--archive", action="append", default=[], metavar="DIR",
                        help="Folder holding an older CV run (tailored.model-output.txt + .model.json); repeatable")
    parser.add_argument("--no-research", action="store_true", help="Don't import output/research_output.json")
    parser.add_argument("--db", default=str(store.DB_PATH), help="Database file (default: cv_web/resumator.db)")
    args = parser.parse_args(argv)

    conn = store.connect(args.db)
    try:
        report = migrate_single_role(
            conn, args.name, company=args.company, archive_dirs=tuple(Path(p) for p in args.archive),
            research=not args.no_research,
        )
    except (MigrationError, store.StoreError) as exc:
        print(f"Migration failed, nothing written: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    if report.skipped:
        print(f"Role {args.name!r} already exists (id {report.role_id}); nothing written.")
        return 0
    master = "imported" if report.master_imported else "unchanged (same as input/CV.md)"
    print(f"Master CV version {report.master_version_id}: {master}")
    print(f"Role {args.name!r}: id {report.role_id}, CV version {report.cv_version_id}")
    print(f"CV runs: {report.cv_run_ids or 'none found'} (current: {report.current_cv_run_id})")
    print(f"Research run: {report.research_run_id}" if report.research_run_id else "Research run: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())

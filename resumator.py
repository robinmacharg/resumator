"""Role-mode CLI for the multi-role workspace (multi-role step 13, design R5).

Run from the repo root: `python3 -m resumator --action list` (or `python3 resumator.py …`).

| Action | Does |
|---|---|
| `list` | Roles: id, slug, name, company, status, last updated and last run (🧭 = current CV run was steered) |
| `create` | New role (`--role NAME`), its CV seeded from the master (R1) |
| `cv` | Generate a CV for a role through `role_runner` (R14) and save the run; `--out` also writes its PDF |
| `research` | Research the role's company and save the run |
| `render` | PDF or DOCX of a role's current (or `--run`) CV run, rendered on demand (R6) |
| `backup` | Timestamped copy of the DB (R18) |
| `setup` | First-run choice on an empty DB: `--choice example` or `blank` (R3) |
| `settings-import` | Import `--env-file F` (or `--from-environment`) into the settings DB: merge, `--replace`, `--dry-run`, `--delete-after` (D7, D11) |
| `settings-export` | Print the stored settings as commented `.env` text; secrets masked unless `--reveal` |
| `settings-set` | Set `--key K`; the value comes from `getpass` for secrets (D9), else stdin |
| `settings-test` | One real model call against `--provider P` with the stored settings (D3) |
| `migrate-single-role` | One-time import of `input/`/`output/` files as a role (R4, `cv_web.migrate_single_role`) |

The one-shot, file-based scripts (`generate_cv.py`, `research_role.py`) are unchanged; this CLI never reads or
writes `input/` data files (the prompt templates excepted, as in the UI).
"""

from __future__ import annotations

import argparse
import base64
import getpass
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from cv_convert import available_themes, render_cv
import backend_registry
import settings_catalog
import settings_env
import settings_io
import startup_audit
from env_utils import parse_dotenv_text
from cv_web import first_run, migrate_single_role, role_runner, store

OUTPUT_DIR = Path("output")
ACTIONS = ("list", "create", "cv", "research", "render", "backup", "setup",
           "settings-import", "settings-export", "settings-set", "settings-test", "migrate-single-role")
NEEDS_ROLE = ("create", "cv", "research", "render", "migrate-single-role")


class CliError(Exception):
    """A request this CLI refuses; printed as `error: …` with exit code 1."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m resumator",
        description="Role-mode CLI: work with the roles in the Resumator DB (run from the repo root).",
    )
    parser.add_argument("--action", required=True, choices=ACTIONS)
    parser.add_argument("--role", help="Role name or slug (create and migrate-single-role: the new role's name)")
    parser.add_argument("--db", default=str(store.DB_PATH), help="Database file (default: cv_web/resumator.db)")

    runs = parser.add_argument_group("cv and research")
    runs.add_argument("--provider", default="", help="Provider id (default: the backend default)")
    runs.add_argument("--model", default="", help="Model (default: the provider's order)")
    runs.add_argument("--no-current", action="store_true", help="Keep the role's current run as it is")

    cv = parser.add_argument_group("cv and render")
    cv.add_argument("--theme", help="PDF theme for this run or render (default: the role's / the run's)")
    steering = cv.add_mutually_exclusive_group()
    steering.add_argument("--no-steering", action="store_true", help="cv: send no steering this run")
    steering.add_argument("--steering-file", type=Path, help="cv: steering text for this run instead of the role's")
    cv.add_argument("--out", type=Path, help="cv: also write the run's PDF here; render: output path "
                    "(default: output/<slug>-run<id>.<format>)")
    cv.add_argument("--run", type=int, help="render: run id (default: the role's current CV run)")
    cv.add_argument("--format", choices=("pdf", "docx"), default="pdf", help="render: output format")

    research = parser.add_argument_group("research")
    research.add_argument("--company", help="Company (create: the role's; research: override the role's)")
    research.add_argument("--url", action="append", default=[], help="research: source URL; repeatable")
    research.add_argument("--dry-run", action="store_true", help="research: build the prompt only")

    other = parser.add_argument_group("create, list, backup, setup, migrate-single-role")
    other.add_argument("--jobspec-file", type=Path, help="create: job spec text file")
    other.add_argument("--status", choices=store.ROLE_STATUSES, help="create: initial status; list: filter")
    other.add_argument("--dest", type=Path, default=store.BACKUP_DIR, help="backup: folder (default: cv_web/backups)")
    other.add_argument("--choice", choices=first_run.CHOICES, help="setup: example data or a blank master CV")
    other.add_argument("--archive", action="append", default=[], metavar="DIR",
                       help="migrate-single-role: folder with an older CV run; repeatable")
    other.add_argument("--no-research", action="store_true", help="migrate-single-role: skip research output")

    settings = parser.add_argument_group("settings-import, settings-export, settings-set, settings-test")
    settings.add_argument("--env-file", type=Path, help="settings-import: .env-style file to import")
    settings.add_argument("--from-environment", action="store_true",
                          help="settings-import: import the catalogued keys set in the current shell")
    settings.add_argument("--replace", action="store_true",
                          help="settings-import: make the stored settings exactly the imported ones")
    settings.add_argument("--delete-after", action="store_true",
                          help="settings-import: delete --env-file once imported")
    settings.add_argument("--reveal", action="store_true", help="settings-export: show secrets in plain text")
    settings.add_argument("--key", help="settings-set: the setting name, e.g. OPENAI_API_KEY")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.action in NEEDS_ROLE and not (args.role or "").strip():
        parser.error(f"--action {args.action} needs --role")
    if args.action == "setup" and not args.choice:
        parser.error("--action setup needs --choice example or blank")
    if args.action == "settings-import" and bool(args.env_file) == args.from_environment:
        parser.error("--action settings-import needs exactly one of --env-file or --from-environment")
    if args.action == "settings-set" and not (args.key or "").strip():
        parser.error("--action settings-set needs --key")
    if args.action == "settings-test" and not args.provider:
        parser.error("--action settings-test needs --provider")
    startup_audit.audit_or_exit(allow={"dotenv"} if args.action == "settings-import" else ())
    if args.action == "migrate-single-role":
        return _migrate(args)
    try:
        conn = store.connect(args.db)
    except sqlite3.Error as exc:
        print(f"error: can't open {args.db}: {exc}", file=sys.stderr)
        return 1
    try:
        return ACTION_HANDLERS[args.action](conn, args)
    except (CliError, role_runner.RunnerError, store.StoreError, first_run.FirstRunError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def _list(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    roles = store.list_roles(conn, status=args.status)
    if not roles:
        print("No roles." + ("" if store.current_cv_version(conn, None) else
                             " The DB has no master CV yet: try --action setup --choice example|blank."))
        return 0
    rows = [("ID", "SLUG", "NAME", "COMPANY", "STATUS", "UPDATED", "LAST RUN")]
    for role in roles:
        rows.append((
            str(role["id"]), role["slug"], ("🧭 " if role["current_steered"] else "") + role["name"],
            role["company"], role["status"], role["updated_at"][:10], (role["last_run_at"] or "")[:10] or "-",
        ))
    widths = [max(len(row[col]) for row in rows) for col in range(len(rows[0]))]
    for row in rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())
    return 0


def _create(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    if store.current_cv_version(conn, None) is None:
        raise CliError("there is no master CV to seed the role from (try --action setup or migrate-single-role)")
    jobspec = _read_text(args.jobspec_file) if args.jobspec_file else ""
    with store.transaction(conn):
        role_id = store.create_role(conn, args.role, company=args.company or "", jobspec=jobspec,
                                    status=args.status or "draft")
        store.seed_role_cv(conn, role_id)
    role = store.get_role(conn, role_id)
    print(f"Created role {role['name']!r} (id {role_id}, slug {role['slug']}) with a copy of the master CV.")
    return 0


def _cv(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    role = _require_role(conn, args.role)
    steering = None
    if args.no_steering:
        steering = ""
    elif args.steering_file:
        steering = _read_text(args.steering_file)
    print(f"Generating a CV for {role['name']!r}…", file=sys.stderr)
    outcome = _interruptible(lambda on_start: role_runner.run_cv(
        conn, role["id"], provider=args.provider, model=args.model, theme=_theme(args.theme), steering=steering,
        make_current=not args.no_current, on_log=_echo, on_start=on_start,
    ))
    if not outcome.success:
        print(f"error: CV run {outcome.run_id} failed: {outcome.error or 'see its log'}", file=sys.stderr)
        return 1
    for warning in outcome.result.get("warnings") or []:
        print(f"warning: {warning}", file=sys.stderr)
    pages = outcome.result.get("page_count")
    print(f"CV run {outcome.run_id} saved" + (f" ({pages} page(s))" if pages else "") +
          ("" if args.no_current else ", now current") + ".")
    if args.out:
        if not outcome.pdf_base64:
            raise CliError("the run returned no PDF to write (try --action render)")
        _write(args.out, base64.b64decode(outcome.pdf_base64))
    return 0


def _research(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    role = _require_role(conn, args.role)
    print(f"Researching for {role['name']!r}…", file=sys.stderr)
    outcome = _interruptible(lambda on_start: role_runner.run_research(
        conn, role["id"], company=args.company, urls=args.url, provider=args.provider, model=args.model,
        dry_run=args.dry_run, make_current=not args.no_current, on_log=_echo, on_start=on_start,
    ))
    if not outcome.success:
        print(f"error: research run {outcome.run_id} failed: {outcome.error or 'see its log'}", file=sys.stderr)
        return 1
    print(f"Research run {outcome.run_id} saved" + ("" if args.no_current else ", now current") + ".")
    return 0


def _render(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    role = _require_role(conn, args.role)
    theme = _theme(args.theme)
    if args.run is None:
        run = store.current_cv_run(conn, role["id"])
        if run is None:
            raise CliError(f"role {role['name']!r} has no current CV run")
    else:
        run = store.get_cv_run(conn, args.run)
        if run is None or run["role_id"] != role["id"]:
            raise CliError(f"role {role['name']!r} has no CV run {args.run}")
    theme = (run["theme"] or "") if theme is None else theme
    data = render_cv(role_runner.run_markdown(conn, run), args.format, theme or None)
    if data is None:
        raise CliError(f"rendering CV run {run['id']} as {args.format} failed (see the messages above)")
    suffix = f"-{theme}" if theme and args.format == "pdf" else ""
    _write(args.out or OUTPUT_DIR / f"{role['slug']}-run{run['id']}{suffix}.{args.format}", data)
    return 0


def _backup(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    print(f"Backup written: {store.backup(conn, args.dest)}")
    return 0


def _setup(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    result = first_run.set_up(conn, args.choice)
    if result["roleId"] is None:
        print(f"Blank master CV created (version {result['masterVersionId']}). Fill in its TODOs in the UI, "
              "then create a role.")
    else:
        role = store.get_role(conn, result["roleId"])
        print(f"Example data loaded: master CV, role {role['name']!r} (slug {role['slug']}) and CV run "
              f"{result['runId']}.")
    return 0


def _settings_import(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    if args.from_environment:
        values = settings_io.env_from_environment()
        source = "the current environment"
    else:
        values = parse_dotenv_text(_read_text(args.env_file))
        source = str(args.env_file)
    try:
        diff = settings_io.env_import_values(conn, values, "replace" if args.replace else "merge", args.dry_run)
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    print(("Dry run, nothing written. " if args.dry_run else "") + f"From {source}:")
    for label in ("added", "changed", "unchanged", "removed"):
        keys = diff[label]
        print(f"  {label}: {len(keys)}" + (f" ({', '.join(keys)})" if keys else ""))
    if args.delete_after and not args.dry_run and args.env_file:
        try:
            args.env_file.unlink()
        except OSError as exc:
            raise CliError(f"imported, but couldn't delete {args.env_file}: {exc}") from exc
        print(f"Deleted {args.env_file}.")
    return 0


def _settings_export(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    text = settings_io.env_export(conn, reveal=args.reveal)
    print(text if text else "# No settings stored.", end="" if text else "\n")
    return 0


def _settings_set(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    key = args.key.strip()
    if not settings_io.KEY_RE.match(key):
        raise CliError(f"invalid setting name {key!r}")
    if settings_io.is_secret(key):
        value = getpass.getpass(f"Value for {key} (hidden): ")
    else:
        value = sys.stdin.read()
    value = value.strip()
    if not value:
        raise CliError(f"no value given for {key}")
    store.set_env_setting(conn, key, value)
    print(f"Saved {key}.")
    return 0


def _settings_test(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    backend = next((b for b in backend_registry.load_backend_objects() if b.id == args.provider), None)
    if backend is None:
        ids = ", ".join(b.id for b in backend_registry.load_backend_objects())
        raise CliError(f"unknown provider {args.provider!r}; choose from {ids}")
    print(f"Testing {backend.label} (one real model call)…", file=sys.stderr)
    result = settings_catalog.test_connection(backend, settings_env.effective_env(conn))
    detail = f" ({result.model}, {result.elapsed_seconds:.1f}s)" if result.model else ""
    if result.ok:
        print(f"OK{detail}")
        return 0
    print(f"error: test failed{detail}: {result.message}", file=sys.stderr)
    return 1


def _migrate(args: argparse.Namespace) -> int:
    argv = ["--name", args.role, "--db", args.db]
    if args.company:
        argv += ["--company", args.company]
    for folder in args.archive:
        argv += ["--archive", folder]
    if args.no_research:
        argv.append("--no-research")
    return migrate_single_role.main(argv)


ACTION_HANDLERS = {
    "list": _list,
    "create": _create,
    "cv": _cv,
    "research": _research,
    "render": _render,
    "backup": _backup,
    "setup": _setup,
    "settings-import": _settings_import,
    "settings-export": _settings_export,
    "settings-set": _settings_set,
    "settings-test": _settings_test,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_role(conn: sqlite3.Connection, name_or_slug: str) -> dict[str, Any]:
    role = store.find_role(conn, name_or_slug.strip())
    if role is None:
        raise CliError(f"no role {name_or_slug!r} (see --action list)")
    return role


def _theme(theme: str | None) -> str | None:
    """None = not given; "default" = the default theme ("")."""
    if theme is None:
        return None
    if theme not in available_themes():
        raise CliError(f"unknown theme {theme!r}; choose from {', '.join(available_themes())}")
    return "" if theme == "default" else theme


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"can't read {path}: {exc}") from exc


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"Wrote {path}")


def _echo(line: str) -> None:
    sys.stderr.write(line)
    sys.stderr.flush()


def _interruptible(start_run):
    """Run a role run; on Ctrl-C stop the script (the terminal also sends SIGINT to it and its provider child,
    which share our process group) and exit 130. An interrupted run isn't saved."""
    procs: list[subprocess.Popen] = []
    try:
        return start_run(procs.append)
    except KeyboardInterrupt:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        print("\nInterrupted; the run wasn't saved.", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    sys.exit(main())

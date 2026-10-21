"""SQLite data layer for the multi-role workspace.

Architecture role:
- Layer: persistence (stdlib `sqlite3`, JSON in TEXT columns).
- Responsibility: open the DB, apply ordered schema migrations, and provide CRUD for roles, CV versions (master
  and role), prompt versions, CV runs, research runs and settings, plus an online `backup`.

Design notes (docs/plans/multi-role-design.md R8, R9, R13, R15, R18):
- One append-only `cv_version` table holds master (`role_id IS NULL`) and role CVs. A CV's current text is its
  newest row; `base_master_id` on role rows is the master version last synced with (the merge ancestor).
- Every `*_json` column has a `json_valid` CHECK. Writers take Python values and encode them; readers decode them.
- At most one current run per role and run kind (partial unique index); failed runs are never current.
- Connections run in autocommit mode; multi-statement writes use `transaction()`.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent / "resumator.db"
BACKUP_DIR = Path(__file__).resolve().parent / "backups"

ROLE_STATUSES = ("draft", "applied", "closed")
CV_SOURCES = ("seed", "edit", "promote", "pull", "import", "example")
PROMPT_KINDS = ("cv", "research")

# Ordered migrations: index + 1 is the schema version each one produces. Append only; never edit a shipped one.
MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE role (
        id INTEGER PRIMARY KEY,
        slug TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        company TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'applied', 'closed')),
        jobspec TEXT NOT NULL DEFAULT '',
        steering_text TEXT NOT NULL DEFAULT '',
        steering_enabled INTEGER NOT NULL DEFAULT 1 CHECK (steering_enabled IN (0, 1)),
        theme TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE cv_version (
        id INTEGER PRIMARY KEY,
        role_id INTEGER REFERENCES role(id) ON DELETE CASCADE,
        parent_id INTEGER REFERENCES cv_version(id),
        base_master_id INTEGER REFERENCES cv_version(id),
        source TEXT NOT NULL
            CHECK (source IN ('seed', 'edit', 'promote', 'pull', 'import', 'example')),
        note TEXT,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK (role_id IS NOT NULL OR base_master_id IS NULL)
    );
    CREATE INDEX cv_version_role ON cv_version(role_id, id);

    CREATE TABLE prompt_version (
        hash TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('cv', 'research')),
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE cv_run (
        id INTEGER PRIMARY KEY,
        role_id INTEGER NOT NULL REFERENCES role(id) ON DELETE CASCADE,
        cv_version_id INTEGER NOT NULL REFERENCES cv_version(id),
        prompt_hash TEXT REFERENCES prompt_version(hash),
        provider TEXT,
        model TEXT,
        theme TEXT,
        steering_text TEXT,
        raw_output TEXT,
        model_json TEXT CHECK (model_json IS NULL OR json_valid(model_json)),
        warnings_json TEXT CHECK (warnings_json IS NULL OR json_valid(warnings_json)),
        page_count INTEGER,
        log TEXT,
        success INTEGER NOT NULL CHECK (success IN (0, 1)),
        is_current INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0, 1)),
        started_at TEXT NOT NULL,
        finished_at TEXT,
        CHECK (is_current = 0 OR success = 1)
    );
    CREATE INDEX cv_run_role ON cv_run(role_id, id);
    CREATE UNIQUE INDEX cv_run_one_current ON cv_run(role_id) WHERE is_current = 1;

    CREATE TABLE research_run (
        id INTEGER PRIMARY KEY,
        role_id INTEGER NOT NULL REFERENCES role(id) ON DELETE CASCADE,
        prompt_hash TEXT REFERENCES prompt_version(hash),
        provider TEXT,
        model TEXT,
        company TEXT,
        urls_json TEXT CHECK (urls_json IS NULL OR json_valid(urls_json)),
        dry_run INTEGER NOT NULL DEFAULT 0 CHECK (dry_run IN (0, 1)),
        output_json TEXT CHECK (output_json IS NULL OR json_valid(output_json)),
        output_md TEXT,
        log TEXT,
        success INTEGER NOT NULL CHECK (success IN (0, 1)),
        is_current INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0, 1)),
        started_at TEXT NOT NULL,
        finished_at TEXT,
        CHECK (is_current = 0 OR success = 1)
    );
    CREATE INDEX research_run_role ON research_run(role_id, id);
    CREATE UNIQUE INDEX research_run_one_current ON research_run(role_id) WHERE is_current = 1;

    CREATE TABLE setting (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """,
)

_ROLE_FIELDS = ("slug", "name", "company", "status", "jobspec", "steering_text", "steering_enabled", "theme")
_RUN_TABLES = ("cv_run", "research_run")
_CV_RUN_FIELDS = (
    "cv_version_id", "prompt_hash", "provider", "model", "theme", "steering_text", "raw_output", "model_json",
    "warnings_json", "page_count", "log", "started_at", "finished_at",
)
_RESEARCH_RUN_FIELDS = (
    "prompt_hash", "provider", "model", "company", "urls_json", "dry_run", "output_json", "output_md", "log",
    "started_at", "finished_at",
)


class StoreError(ValueError):
    """Raised for requests the store refuses (unknown ids, cross-role references, invalid values)."""


def now_iso() -> str:
    """UTC timestamp as ISO 8601 with a `Z` suffix, to the second."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Connection, transactions, migrations
# ---------------------------------------------------------------------------


def connect(path: Path | str = DB_PATH, *, migrate_schema: bool = True) -> sqlite3.Connection:
    """Open the DB (creating it if needed) with foreign keys on, WAL journal and Row access.

    Inputs:
    - path: DB file, or ":memory:".
    - migrate_schema: apply pending migrations before returning.

    Returns:
    - An autocommit connection. One per thread: don't share it across server threads.
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    if migrate_schema:
        migrate(conn)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block in one write transaction; commit on success, roll back on error. Nested use joins the outer one."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def schema_version(conn: sqlite3.Connection) -> int:
    """Highest applied migration, or 0 for a new DB."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if not exists:
        return 0
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0] or 0)


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending MIGRATIONS in order, each in its own transaction. Returns the resulting schema version."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    current = schema_version(conn)
    if current > len(MIGRATIONS):
        raise StoreError(f"DB schema version {current} is newer than this code ({len(MIGRATIONS)})")
    for version in range(current + 1, len(MIGRATIONS) + 1):
        with transaction(conn):
            for statement in _split_sql(MIGRATIONS[version - 1]):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)", (version, now_iso())
            )
    return len(MIGRATIONS)


def _split_sql(script: str) -> list[str]:
    """Split a migration into complete statements (executescript would commit mid-transaction)."""
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise StoreError(f"Incomplete SQL statement in migration: {buffer.strip()[:60]}")
    return statements


def backup(conn: sqlite3.Connection, dest_dir: Path | str = BACKUP_DIR) -> Path:
    """Write a timestamped copy of the DB with SQLite's online backup API (R18). Returns the backup path."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"resumator-{stamp}.db"
    suffix = 2
    while dest.exists():
        dest = dest_dir / f"resumator-{stamp}-{suffix}.db"
        suffix += 1
    target = sqlite3.connect(str(dest))
    try:
        conn.backup(target)
    finally:
        target.close()
    return dest


# ---------------------------------------------------------------------------
# Row decoding
# ---------------------------------------------------------------------------


def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Row → dict, with `*_json` columns parsed."""
    if row is None:
        return None
    data = dict(row)
    for key, value in data.items():
        if key.endswith("_json") and value is not None:
            data[key] = json.loads(value)
    return data


def _encode_json(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    """Lowercase ASCII slug: runs of anything but letters and digits become one hyphen."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "role"


def _unique_slug(conn: sqlite3.Connection, base: str, exclude_id: int | None = None) -> str:
    slug, suffix = base, 2
    while True:
        row = conn.execute("SELECT id FROM role WHERE slug = ?", (slug,)).fetchone()
        if row is None or row["id"] == exclude_id:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


def create_role(
    conn: sqlite3.Connection,
    name: str,
    *,
    company: str = "",
    jobspec: str = "",
    status: str = "draft",
    steering_text: str = "",
    steering_enabled: bool = True,
    theme: str | None = None,
    slug: str | None = None,
) -> int:
    """Insert a role and return its id. The slug comes from the name, made unique with `-2`, `-3`… The role's CV
    is not created here: call `seed_role_cv` (R1)."""
    if not name.strip():
        raise StoreError("Role name is required")
    _check_status(status)
    stamp = now_iso()
    with transaction(conn):
        final_slug = _unique_slug(conn, slugify(slug or name))
        cursor = conn.execute(
            """INSERT INTO role (slug, name, company, status, jobspec, steering_text, steering_enabled, theme,
                                 created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (final_slug, name.strip(), company, status, jobspec, steering_text, int(steering_enabled), theme,
             stamp, stamp),
        )
    return int(cursor.lastrowid)


def get_role(conn: sqlite3.Connection, role_id: int) -> dict[str, Any] | None:
    return _decode(conn.execute("SELECT * FROM role WHERE id = ?", (role_id,)).fetchone())


def get_role_by_slug(conn: sqlite3.Connection, slug: str) -> dict[str, Any] | None:
    return _decode(conn.execute("SELECT * FROM role WHERE slug = ?", (slug,)).fetchone())


def find_role(conn: sqlite3.Connection, name_or_slug: str) -> dict[str, Any] | None:
    """Look a role up by slug, then by exact name (case-insensitive). For the role CLI's `--role "Name"`."""
    role = get_role_by_slug(conn, name_or_slug) or get_role_by_slug(conn, slugify(name_or_slug))
    if role:
        return role
    return _decode(
        conn.execute("SELECT * FROM role WHERE name = ? COLLATE NOCASE ORDER BY id LIMIT 1", (name_or_slug,))
        .fetchone()
    )


def list_roles(conn: sqlite3.Connection, *, status: str | None = None) -> list[dict[str, Any]]:
    """Roles for the sidebar (R20), most recently updated first, each with `last_run_at` (latest CV or research
    run start) and `current_steered` (the current CV run had steering)."""
    sql = """
        SELECT r.*,
               (SELECT MAX(started_at) FROM (
                    SELECT started_at FROM cv_run WHERE role_id = r.id
                    UNION ALL SELECT started_at FROM research_run WHERE role_id = r.id)) AS last_run_at,
               (SELECT COALESCE(steering_text, '') != '' FROM cv_run
                 WHERE role_id = r.id AND is_current = 1) AS current_steered
        FROM role r
    """
    params: tuple[Any, ...] = ()
    if status is not None:
        _check_status(status)
        sql += " WHERE r.status = ?"
        params = (status,)
    sql += " ORDER BY r.updated_at DESC, r.id DESC"
    return [_decode(row) for row in conn.execute(sql, params)]


def update_role(conn: sqlite3.Connection, role_id: int, **fields: Any) -> dict[str, Any]:
    """Update whitelisted role fields and bump `updated_at`. A new slug is made unique. Returns the updated role."""
    unknown = set(fields) - set(_ROLE_FIELDS)
    if unknown:
        raise StoreError(f"Unknown role field(s): {', '.join(sorted(unknown))}")
    if "status" in fields:
        _check_status(fields["status"])
    if "name" in fields and not str(fields["name"]).strip():
        raise StoreError("Role name is required")
    if "steering_enabled" in fields:
        fields["steering_enabled"] = int(bool(fields["steering_enabled"]))
    with transaction(conn):
        _require_role(conn, role_id)
        if "slug" in fields:
            fields["slug"] = _unique_slug(conn, slugify(fields["slug"]), exclude_id=role_id)
        fields["updated_at"] = now_iso()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(f"UPDATE role SET {assignments} WHERE id = ?", (*fields.values(), role_id))
    return get_role(conn, role_id)  # type: ignore[return-value]


def delete_role(conn: sqlite3.Connection, role_id: int) -> bool:
    """Delete a role with its CV versions and runs. Master versions are untouched. Returns False if absent."""
    with transaction(conn):
        cursor = conn.execute("DELETE FROM role WHERE id = ?", (role_id,))
    return cursor.rowcount > 0


def _touch_role(conn: sqlite3.Connection, role_id: int) -> None:
    conn.execute("UPDATE role SET updated_at = ? WHERE id = ?", (now_iso(), role_id))


def _require_role(conn: sqlite3.Connection, role_id: int) -> None:
    if conn.execute("SELECT 1 FROM role WHERE id = ?", (role_id,)).fetchone() is None:
        raise StoreError(f"No role {role_id}")


def _check_status(status: str) -> None:
    if status not in ROLE_STATUSES:
        raise StoreError(f"Role status must be one of {', '.join(ROLE_STATUSES)}")


# ---------------------------------------------------------------------------
# CV versions (master: role_id None)
# ---------------------------------------------------------------------------


def add_cv_version(
    conn: sqlite3.Connection,
    content: str,
    *,
    source: str,
    role_id: int | None = None,
    base_master_id: int | None = None,
    note: str | None = None,
) -> int:
    """Append a CV version for a role (or the master when role_id is None) and return its id.

    - `parent_id` is the CV's current newest version.
    - Role versions: `base_master_id` defaults to the parent's base; it must point at a master version, and a role's
      first version must have one (it's the merge ancestor, R7).
    - Master versions can't have a base.
    """
    if source not in CV_SOURCES:
        raise StoreError(f"CV source must be one of {', '.join(CV_SOURCES)}")
    with transaction(conn):
        if role_id is not None:
            _require_role(conn, role_id)
        parent = current_cv_version(conn, role_id)
        if role_id is None:
            if base_master_id is not None:
                raise StoreError("Master CV versions have no base_master_id")
        else:
            if base_master_id is None and parent is not None:
                base_master_id = parent["base_master_id"]
            if base_master_id is None:
                raise StoreError("A role's first CV version needs a base_master_id (seed it from the master)")
            base = get_cv_version(conn, base_master_id)
            if base is None or base["role_id"] is not None:
                raise StoreError(f"base_master_id {base_master_id} is not a master CV version")
        cursor = conn.execute(
            """INSERT INTO cv_version (role_id, parent_id, base_master_id, source, note, content, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (role_id, parent["id"] if parent else None, base_master_id, source, note, content, now_iso()),
        )
        if role_id is not None:
            _touch_role(conn, role_id)
    return int(cursor.lastrowid)


def seed_role_cv(conn: sqlite3.Connection, role_id: int, *, note: str | None = None) -> int:
    """Copy the current master CV into the role as a `seed` version (R1). Returns the new version id."""
    with transaction(conn):
        master = current_cv_version(conn, None)
        if master is None:
            raise StoreError("There is no master CV to seed from")
        return add_cv_version(
            conn, master["content"], source="seed", role_id=role_id, base_master_id=master["id"], note=note
        )


def get_cv_version(conn: sqlite3.Connection, version_id: int) -> dict[str, Any] | None:
    return _decode(conn.execute("SELECT * FROM cv_version WHERE id = ?", (version_id,)).fetchone())


def current_cv_version(conn: sqlite3.Connection, role_id: int | None = None) -> dict[str, Any] | None:
    """Newest version of a role's CV, or of the master when role_id is None."""
    return _decode(
        conn.execute(
            "SELECT * FROM cv_version WHERE role_id IS ? ORDER BY id DESC LIMIT 1", (role_id,)
        ).fetchone()
    )


def list_cv_versions(
    conn: sqlite3.Connection, role_id: int | None = None, *, include_content: bool = False
) -> list[dict[str, Any]]:
    """Version history of a role's CV (or the master), newest first. Content is omitted unless asked for."""
    columns = "*" if include_content else "id, role_id, parent_id, base_master_id, source, note, created_at"
    rows = conn.execute(
        f"SELECT {columns} FROM cv_version WHERE role_id IS ? ORDER BY id DESC", (role_id,)
    )
    return [_decode(row) for row in rows]


# ---------------------------------------------------------------------------
# Prompt versions (R15)
# ---------------------------------------------------------------------------


def prompt_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def save_prompt(conn: sqlite3.Connection, kind: str, content: str) -> str:
    """Store prompt text once per distinct content and return its sha256 hash."""
    if kind not in PROMPT_KINDS:
        raise StoreError(f"Prompt kind must be one of {', '.join(PROMPT_KINDS)}")
    digest = prompt_hash(content)
    conn.execute(
        "INSERT OR IGNORE INTO prompt_version (hash, kind, content, created_at) VALUES (?, ?, ?, ?)",
        (digest, kind, content, now_iso()),
    )
    return digest


def get_prompt(conn: sqlite3.Connection, digest: str) -> dict[str, Any] | None:
    return _decode(conn.execute("SELECT * FROM prompt_version WHERE hash = ?", (digest,)).fetchone())


# ---------------------------------------------------------------------------
# Runs (cv_run, research_run)
# ---------------------------------------------------------------------------


def add_cv_run(
    conn: sqlite3.Connection,
    role_id: int,
    cv_version_id: int,
    *,
    success: bool,
    make_current: bool = True,
    **fields: Any,
) -> int:
    """Record a CV run and return its id. `model_json` and `warnings_json` take Python values. The CV version
    must belong to the role. A successful run becomes current unless make_current is False."""
    with transaction(conn):
        version = get_cv_version(conn, cv_version_id)
        if version is None or version["role_id"] != role_id:
            raise StoreError(f"CV version {cv_version_id} doesn't belong to role {role_id}")
        return _add_run(conn, "cv_run", _CV_RUN_FIELDS, role_id, success, make_current,
                        {"cv_version_id": cv_version_id, **fields})


def add_research_run(
    conn: sqlite3.Connection, role_id: int, *, success: bool, make_current: bool = True, **fields: Any
) -> int:
    """Record a research run and return its id. `urls_json` and `output_json` take Python values."""
    if "dry_run" in fields:
        fields["dry_run"] = int(bool(fields["dry_run"]))
    with transaction(conn):
        return _add_run(conn, "research_run", _RESEARCH_RUN_FIELDS, role_id, success, make_current, fields)


def _add_run(
    conn: sqlite3.Connection,
    table: str,
    allowed: tuple[str, ...],
    role_id: int,
    success: bool,
    make_current: bool,
    fields: dict[str, Any],
) -> int:
    unknown = set(fields) - set(allowed)
    if unknown:
        raise StoreError(f"Unknown {table} field(s): {', '.join(sorted(unknown))}")
    _require_role(conn, role_id)
    values = {key: _encode_json(value) if key.endswith("_json") else value for key, value in fields.items()}
    values.setdefault("started_at", now_iso())
    values.update(role_id=role_id, success=int(bool(success)), is_current=0)
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    cursor = conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))
    run_id = int(cursor.lastrowid)
    if success and make_current:
        _set_current(conn, table, run_id)
    _touch_role(conn, role_id)
    return run_id


def set_current_cv_run(conn: sqlite3.Connection, run_id: int) -> None:
    with transaction(conn):
        _set_current(conn, "cv_run", run_id)


def set_current_research_run(conn: sqlite3.Connection, run_id: int) -> None:
    with transaction(conn):
        _set_current(conn, "research_run", run_id)


def _set_current(conn: sqlite3.Connection, table: str, run_id: int) -> None:
    row = conn.execute(f"SELECT role_id, success FROM {table} WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise StoreError(f"No {table} {run_id}")
    if not row["success"]:
        raise StoreError(f"{table} {run_id} failed, so it can't be current")
    conn.execute(f"UPDATE {table} SET is_current = 0 WHERE role_id = ? AND is_current = 1", (row["role_id"],))
    conn.execute(f"UPDATE {table} SET is_current = 1 WHERE id = ?", (run_id,))


def get_cv_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    return _get_run(conn, "cv_run", run_id)


def get_research_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    return _get_run(conn, "research_run", run_id)


def current_cv_run(conn: sqlite3.Connection, role_id: int) -> dict[str, Any] | None:
    return _current_run(conn, "cv_run", role_id)


def current_research_run(conn: sqlite3.Connection, role_id: int) -> dict[str, Any] | None:
    return _current_run(conn, "research_run", role_id)


def list_cv_runs(conn: sqlite3.Connection, role_id: int) -> list[dict[str, Any]]:
    """CV run history for the picker, newest first, without the large text columns."""
    return _list_runs(
        conn, "cv_run", role_id,
        "id, role_id, cv_version_id, prompt_hash, provider, model, theme, steering_text, page_count, "
        "warnings_json, success, is_current, started_at, finished_at",
    )


def list_research_runs(conn: sqlite3.Connection, role_id: int) -> list[dict[str, Any]]:
    """Research run history, newest first, without the large text columns."""
    return _list_runs(
        conn, "research_run", role_id,
        "id, role_id, prompt_hash, provider, model, company, urls_json, dry_run, success, is_current, "
        "started_at, finished_at",
    )


def _get_run(conn: sqlite3.Connection, table: str, run_id: int) -> dict[str, Any] | None:
    assert table in _RUN_TABLES
    return _decode(conn.execute(f"SELECT * FROM {table} WHERE id = ?", (run_id,)).fetchone())


def _current_run(conn: sqlite3.Connection, table: str, role_id: int) -> dict[str, Any] | None:
    assert table in _RUN_TABLES
    return _decode(
        conn.execute(f"SELECT * FROM {table} WHERE role_id = ? AND is_current = 1", (role_id,)).fetchone()
    )


def _list_runs(conn: sqlite3.Connection, table: str, role_id: int, columns: str) -> list[dict[str, Any]]:
    assert table in _RUN_TABLES
    rows = conn.execute(f"SELECT {columns} FROM {table} WHERE role_id = ? ORDER BY id DESC", (role_id,))
    return [_decode(row) for row in rows]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM setting WHERE key = ?", (key,)).fetchone()
    return default if row is None else row["value"]


def set_setting(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    conn.execute(
        "INSERT INTO setting (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def delete_setting(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM setting WHERE key = ?", (key,))

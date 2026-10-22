"""
Architecture role:
- Layer: configuration import/export.
- Responsibility: move settings between `.env`-style text (or the shell environment) and the DB's
  `env_setting` table, and render the stored settings back as commented `.env` text.

Plain-language purpose:
- The cold-start path: paste or load a `.env`, preview the diff, apply it. Export shows exactly what the
  DB holds, with secrets masked unless asked for.
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Mapping

import settings_catalog
from cv_web import store
from env_utils import parse_dotenv_text

MODES = ("merge", "replace")
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def is_secret(key: str, specs: Mapping[str, object] | None = None) -> bool:
    """Catalogued secrets, plus unknown keys whose name looks like one (for example `GEMINI_API_KEY`)."""
    specs = specs if specs is not None else _spec_map()
    spec = specs.get(key)
    if spec is not None:
        return bool(getattr(spec, "secret", False))
    return any(hint in key.upper() for hint in SECRET_HINTS)


def mask_secret(value: str) -> str:
    """`sk-…abcd`: a short prefix and the last four characters; short values are fully hidden."""
    if len(value) <= 8:
        return "…" if value else ""
    return f"{value[:3]}…{value[-4:]}"


def declared_specs(groups: list[settings_catalog.SettingGroup]) -> dict[str, object]:
    """Specs the catalog really declares; the synthesized "Other" entries are left out so `is_secret` falls back
    to the name heuristic for them."""
    return {
        spec.key: spec for group in groups if group.id != settings_catalog.OTHER_ID for spec in group.specs
    }


def _spec_map() -> dict[str, object]:
    return declared_specs(settings_catalog.catalog())


def env_from_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Catalogued keys with a value in the shell (`os.environ` by default): the "current environment" source (D11)."""
    keys = settings_catalog.catalog_keys()
    return {key: value for key, value in (os.environ if base is None else base).items() if key in keys and value}


def env_import(conn: sqlite3.Connection, text: str, mode: str = "merge", dry_run: bool = False) -> dict[str, list[str]]:
    """Import `.env` text. See `env_import_values`."""
    return env_import_values(conn, parse_dotenv_text(text), mode, dry_run)


def env_import_values(
    conn: sqlite3.Connection, values: Mapping[str, str], mode: str = "merge", dry_run: bool = False
) -> dict[str, list[str]]:
    """Apply `values` to the stored settings and report the diff as sorted key lists (never values).

    Inputs:
    - mode: "merge" adds and updates; "replace" also removes stored keys that `values` lacks.
    - dry_run: report the diff without writing.

    Returns `{added, changed, unchanged, removed}`. Raises ValueError for an unknown mode or invalid key.
    """
    if mode not in MODES:
        raise ValueError(f"unknown import mode {mode!r}; choose merge or replace")
    bad = sorted(key for key in values if not KEY_RE.match(key))
    if bad:
        raise ValueError(f"invalid setting name(s): {', '.join(bad)}")
    stored = store.env_settings(conn)
    # A masked export pasted back in must not overwrite the real secret with its placeholder.
    values = {
        key: stored[key] if key in stored and value == mask_secret(stored[key]) and is_secret(key) else value
        for key, value in values.items()
    }
    diff = {
        "added": sorted(key for key in values if key not in stored),
        "changed": sorted(key for key in values if key in stored and stored[key] != values[key]),
        "unchanged": sorted(key for key in values if key in stored and stored[key] == values[key]),
        "removed": sorted(set(stored) - set(values)) if mode == "replace" else [],
    }
    if not dry_run:
        if mode == "replace":
            store.replace_env_settings(conn, dict(values))
        else:
            with store.transaction(conn):
                for key, value in values.items():
                    store.set_env_setting(conn, key, value)
    return diff


def _quote(value: str) -> str:
    """Quote only when the parser would otherwise mangle the value (it strips matching quotes, no escapes)."""
    plain = value == value.strip() and not any(c in value for c in " \t#\"'") and value
    if plain or not value:
        return value
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    return value


def env_export(conn: sqlite3.Connection, reveal: bool = False) -> str:
    """Stored settings as `.env` text, grouped and commented by catalog section; secrets masked unless `reveal`."""
    stored = store.env_settings(conn)
    groups = settings_catalog.catalog(stored)
    specs = declared_specs(groups)
    lines: list[str] = []
    for group in groups:
        rows = [spec for spec in group.specs if spec.key in stored]
        if not rows:
            continue
        if lines:
            lines.append("")
        lines.append(f"# {group.label}")
        for spec in rows:
            value = stored[spec.key]
            if is_secret(spec.key, specs) and not reveal:
                value = mask_secret(value)
            if spec.label and spec.label != spec.key:
                lines.append(f"# {spec.label}")
            lines.append(f"{spec.key}={_quote(value)}")
    return "\n".join(lines) + ("\n" if lines else "")

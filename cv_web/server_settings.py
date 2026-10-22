"""Settings API: the `/api/settings…` routes over the `env_setting` table (settings-in-db task 6).

Architecture role:
- Layer: backend HTTP handlers over `cv_web/store.py`, `settings_catalog.py` and `settings_io.py`.
- Responsibility: list the catalog with stored values, save changes, reveal one secret, render the settings as
  `.env` text, import `.env` text with a diff, and test a provider. `server_roles.dispatch` routes here (same
  connection-per-request handling and `{error}` responses).

Design notes (docs/plans/settings-in-db/design.md "API", D2, D3):
- Secrets come back masked with `isSet`; only `POST /api/settings/reveal` returns one in plain text. A masked
  placeholder sent back unchanged (on save or as a test override) is ignored.
- Bad requests raise `store.StoreError` (400).
"""

from __future__ import annotations

import sqlite3
from typing import Any

import backend_registry
import settings_catalog
import settings_io
from cv_web import store
from settings_env import resolve_env


def _spec_json(spec, stored: dict[str, str], specs: dict[str, Any]) -> dict[str, Any]:
    secret = settings_io.is_secret(spec.key, specs)
    value = stored.get(spec.key, "")
    return {
        "key": spec.key,
        "label": spec.label,
        "secret": secret,
        "default": spec.default,
        "kind": spec.kind,
        "choices": list(spec.choices) if spec.choices else None,
        "help": spec.help,
        "advanced": spec.advanced,
        "isSet": spec.key in stored,
        "value": settings_io.mask_secret(value) if secret else value,
    }


def settings_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    stored = store.env_settings(conn)
    groups = settings_catalog.catalog(stored)
    specs = settings_io.declared_specs(groups)
    return {
        "groups": [
            {"id": group.id, "label": group.label, "settings": [_spec_json(s, stored, specs) for s in group.specs]}
            for group in groups
        ]
    }


def _string_map(value: Any, name: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise store.StoreError(f"'{name}' must be an object of strings")
    return value


def _real_changes(values: dict[str, str], stored: dict[str, str]) -> dict[str, str]:
    """Drop entries that echo a secret's masked placeholder back."""
    return {
        key: value for key, value in values.items()
        if not (key in stored and settings_io.is_secret(key) and value == settings_io.mask_secret(stored[key]))
    }


def get_settings(conn, role, params, query, payload, deps):
    return settings_payload(conn)


def put_settings(conn, role, params, query, payload, deps):
    to_set = _string_map(payload.get("set", {}), "set")
    to_delete = payload.get("delete", [])
    if not isinstance(to_delete, list) or not all(isinstance(k, str) for k in to_delete):
        raise store.StoreError("'delete' must be a list of names")
    to_set = _real_changes(to_set, store.env_settings(conn))
    bad = sorted(key for key in [*to_set, *to_delete] if not settings_io.KEY_RE.match(key))
    if bad:
        raise store.StoreError(f"invalid setting name(s): {', '.join(bad)}")
    with store.transaction(conn):
        for key in to_delete:
            store.delete_env_setting(conn, key)
        for key, value in to_set.items():
            store.set_env_setting(conn, key, value)
    return {"success": True, **settings_payload(conn)}


def reveal_setting(conn, role, params, query, payload, deps):
    key = payload.get("key")
    value = store.get_env_setting(conn, key) if isinstance(key, str) else None
    if value is None:
        raise store.StoreError(f"{key!r} is not set")
    return {"key": key, "value": value}


def get_env_text(conn, role, params, query, payload, deps):
    return {"text": settings_io.env_export(conn, reveal=query.get("reveal") == "1")}


def import_settings(conn, role, params, query, payload, deps):
    text = payload.get("text")
    if not isinstance(text, str):
        raise store.StoreError("'text' must be a string")
    dry_run = bool(payload.get("dry_run", payload.get("dryRun", False)))
    try:
        diff = settings_io.env_import(conn, text, payload.get("mode", "merge"), dry_run)
    except ValueError as exc:
        raise store.StoreError(str(exc)) from exc
    return {"success": True, "dryRun": dry_run, "diff": diff}


def test_provider(conn, role, params, query, payload, deps):
    provider = payload.get("provider")
    backend = next((b for b in backend_registry.load_backend_objects() if b.id == provider), None)
    if backend is None:
        raise store.StoreError(f"unknown provider {provider!r}")
    stored = store.env_settings(conn)
    overrides = _real_changes(_string_map(payload.get("overrides", {}), "overrides"), stored)
    merged = {**stored, **overrides}
    merged = {key: value for key, value in merged.items() if value != "" or key not in overrides}
    result = settings_catalog.test_connection(backend, resolve_env(merged))
    return {
        "ok": result.ok,
        "message": result.message,
        "elapsedSeconds": result.elapsed_seconds,
        "model": result.model,
    }

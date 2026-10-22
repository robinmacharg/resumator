"""
Architecture role:
- Layer: configuration resolution.
- Responsibility: build the environment a run sees: the process environment, minus every key the settings
  catalog declares, plus the settings stored in the DB. `.env` files are never read.

Plain-language purpose:
- One rule for every catalogued key: the DB wins and the shell can't override it (D8), so what the Settings page
  shows is what ran. Variables the catalog doesn't know (`PATH`, `HOME`, ...) pass through.
"""

from __future__ import annotations

import getpass
import os
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Mapping

import backend_registry
import settings_catalog
from cv_web import store


class SettingsError(RuntimeError):
    """The environment can't be resolved for a run; the message tells the user what to do."""


def effective_env(conn: sqlite3.Connection, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """`base` (default `os.environ`) without catalogued keys, plus the DB's env settings."""
    return resolve_env(store.env_settings(conn), base)


def resolve_env(stored: Mapping[str, str], base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The same rule for settings already read from the DB (or merged with unsaved form values)."""
    strip = settings_catalog.catalog_keys()
    merged = {key: value for key, value in (os.environ if base is None else base).items() if key not in strip}
    merged.update(stored)
    return merged


def shadowed_keys(base: Mapping[str, str] | None = None) -> list[str]:
    """Catalogued keys set in the shell, which are ignored (the startup audit warns about these)."""
    strip = settings_catalog.catalog_keys()
    return sorted(key for key, value in (os.environ if base is None else base).items() if key in strip and value)


def one_shot_env(
    db_path: Path | str | None = None,
    provider: str = "",
    overrides: Mapping[str, str] | None = None,
    *,
    interactive: bool | None = None,
    ask_secret: Callable[[str], str] = getpass.getpass,
    ask_save: Callable[[str], str] = input,
) -> dict[str, str]:
    """The environment for a one-shot script run: effective env from the DB, CLI-flag overrides on top, and a
    missing provider secret prompted for (D9).

    Inputs:
    - db_path: settings DB (default `cv_web/resumator.db`).
    - provider: the provider the run will use; "" means `MODEL_PROVIDER`, else the default (no prompt).
    - overrides: one-off non-secret values from CLI flags (`--fast`, `--font-priority`).
    - interactive: whether a person can answer prompts (default: stdin is a terminal).

    Raises:
    - SettingsError when the chosen provider lacks a secret and it can't be prompted for or is left blank.
    """
    conn = store.connect(db_path if db_path is not None else store.DB_PATH)
    try:
        env = effective_env(conn)
        env.update(overrides or {})
        ensure_provider_secret(
            conn, env, provider, interactive=interactive, ask_secret=ask_secret, ask_save=ask_save
        )
    finally:
        conn.close()
    return env


def ensure_provider_secret(
    conn: sqlite3.Connection,
    env: dict[str, str],
    provider: str,
    *,
    interactive: bool | None = None,
    ask_secret: Callable[[str], str] = getpass.getpass,
    ask_save: Callable[[str], str] = input,
) -> None:
    """If `provider` is disabled and declares a secret, prompt for it (never accepted as an argument, D9), put it
    in `env`, and offer to save it. Without a terminal, fail with how to set it."""
    provider = (provider or env.get("MODEL_PROVIDER") or "").strip().lower()
    backend = next((b for b in backend_registry.load_backend_objects() if b.id == provider), None)
    if backend is None:
        return
    secrets = [spec for spec in settings_catalog.backend_specs(backend) if spec.secret]
    if not secrets:
        return
    status = backend_registry._safe_status(backend, env)
    if status.enabled:
        return
    key = secrets[0].key
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        raise SettingsError(
            f"Provider '{provider}' is disabled ({status.reason}). Set {key} in the settings DB: "
            "python3 -m resumator --action settings-set --key " + key
        )
    value = ask_secret(f"{backend.label} is disabled ({status.reason}). Enter {key} (hidden; blank to cancel): ").strip()
    if not value:
        raise SettingsError(f"No {key} given for provider '{provider}'.")
    env[key] = value
    if ask_save("Save it to the settings DB? [y/N] ").strip().lower() in {"y", "yes"}:
        store.set_env_setting(conn, key, value)

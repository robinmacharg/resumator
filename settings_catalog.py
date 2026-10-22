"""
Architecture role:
- Layer: configuration catalog.
- Responsibility: declare every env key the app reads (globals plus each backend's `settings()`),
  group them for the Settings UI, and run provider connection tests.

Plain-language purpose:
- The DB stores bare key/value rows; this module says what each key means, which are secret, and
  which belong to which provider. Keys the DB holds that nobody declares land in "Other".
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import backend_registry
from backends.base import Backend, SettingSpec, TestResult

TEST_PROMPT = "Reply with OK"
TEST_TIMEOUT_SECONDS = 60
TEST_HEARTBEAT_SECONDS = 15

GLOBAL_ID = "global"
OTHER_ID = "other"


@dataclass
class SettingGroup:
    """One block of the Settings page: Global, a backend, or Other."""

    id: str
    label: str
    specs: list[SettingSpec]


def global_specs() -> list[SettingSpec]:
    """Settings that belong to no single backend."""
    import cv_convert

    provider_ids = tuple(backend.id for backend in backend_registry.load_backend_objects())
    return [
        SettingSpec(
            "MODEL_PROVIDER",
            "Default provider",
            kind="choice",
            choices=provider_ids,
            help="Used when a run names no provider.",
        ),
        SettingSpec(
            "CV_FAST_MODE",
            "Fast mode",
            kind="bool",
            default="false",
            help="Truncates the CV and prefers faster models.",
        ),
        SettingSpec("CV_THEME", "Default theme", kind="choice", choices=tuple(cv_convert.available_themes())),
        SettingSpec(
            "CV_FONT_PRIORITY",
            "Font priority",
            kind="csv",
            default="Calibri,Arial,Helvetica",
            help="Comma-separated, first available font wins.",
        ),
        SettingSpec(
            "RESEARCH_GEMINI_HEARTBEAT_SECONDS",
            "Research heartbeat (s)",
            kind="int",
            default="15",
            advanced=True,
            help="Progress check interval during research, for every provider.",
        ),
    ]


def backend_specs(backend: Backend) -> list[SettingSpec]:
    """A backend's declared settings; empty when it declares none or `settings()` fails."""
    declare = getattr(backend, "settings", None)
    if not callable(declare):
        return []
    try:
        return list(declare())
    except Exception:
        return []


def catalog_keys() -> set[str]:
    """Every key the catalog declares (globals and all backends). Shell values for these are ignored."""
    keys = {spec.key for spec in global_specs()}
    for backend in backend_registry.load_backend_objects():
        keys.update(spec.key for spec in backend_specs(backend))
    return keys


def catalog(env: dict[str, str] | None = None) -> list[SettingGroup]:
    """Group the declared settings: Global, one group per backend, then Other.

    Inputs:
    - env: Stored settings; keys not declared anywhere become the "Other" group (omitted when none).
    """
    groups = [SettingGroup(GLOBAL_ID, "Global", global_specs())]
    for backend in backend_registry.load_backend_objects():
        groups.append(SettingGroup(backend.id, backend.label, backend_specs(backend)))
    declared = {spec.key for group in groups for spec in group.specs}
    other = [SettingSpec(key, key) for key in sorted(env or {}) if key not in declared]
    if other:
        groups.append(SettingGroup(OTHER_ID, "Other", other))
    return groups


def default_test_connection(backend: Backend, env: dict[str, str]) -> TestResult:
    """Prove a provider works: interrogate, then one tiny real call on its first model, no fallback."""
    try:
        status = backend.interrogate(env)
    except Exception as exc:
        return TestResult(False, f"interrogate failed: {exc}")
    if not status.enabled:
        return TestResult(False, status.reason or "provider is disabled")
    models = backend.model_sequence(env, "")
    if not models:
        return TestResult(False, "no model configured")
    model = models[0]
    try:
        with tempfile.TemporaryDirectory(prefix="resumator-test-") as log_dir:
            attempt = backend.run_attempt(
                model_name=model,
                prompt_text=TEST_PROMPT,
                env=env,
                timeout_seconds=min(backend.timeout_seconds, TEST_TIMEOUT_SECONDS),
                heartbeat_seconds=TEST_HEARTBEAT_SECONDS,
                attempt_index=1,
                debug_log_dir=Path(log_dir),
                log_prefix="settings-test",
                emit_live_output=False,
            )
    except Exception as exc:
        return TestResult(False, f"{type(exc).__name__}: {exc}", model=model)
    if attempt.timed_out:
        return TestResult(False, "timed out", attempt.elapsed_seconds, model)
    if attempt.returncode != 0 or not attempt.stdout.strip():
        detail = (attempt.stderr or attempt.stdout).strip().splitlines()
        message = detail[-1][:300] if detail else f"exit code {attempt.returncode}"
        return TestResult(False, message, attempt.elapsed_seconds, model)
    return TestResult(True, "OK", attempt.elapsed_seconds, model)


def test_connection(backend: Backend, env: dict[str, str]) -> TestResult:
    """Run the backend's own `test_connection(env)` when it has one, else the default test."""
    custom = getattr(backend, "test_connection", None)
    if not callable(custom):
        return default_test_connection(backend, env)
    try:
        return custom(env)
    except Exception as exc:
        return TestResult(False, f"{type(exc).__name__}: {exc}")

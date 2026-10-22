"""
Architecture role:
- Layer: configuration safety.
- Responsibility: check the install for leftover file-based config before an entry point starts. Errors refuse
  to run; warnings are printed and the run goes on.

Plain-language purpose:
- Config lives in the DB only (D4). A stray `.env` would be ignored by us but still picked up by the `gemini` CLI
  (D7), so it blocks startup until it's imported. Settings import is the one action allowed to run past it.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

ROOT_DIR = Path(__file__).resolve().parent
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__"}
SKIP_PATHS = {("VSCodeExtension", "runtime")}
IMPORT_COMMAND = "python3 -m resumator --action settings-import --env-file {path} --delete-after"


@dataclass(frozen=True)
class Finding:
    level: str  # "error" refuses to run; "warn" is only printed
    code: str
    message: str


def _is_env_file(name: str) -> bool:
    return name == ".env" or name.startswith(".env.")


def _skipped(root: Path, directory: Path) -> bool:
    parts = directory.relative_to(root).parts
    return any(parts[: len(skip)] == skip for skip in SKIP_PATHS)


def check_dotenv(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for current, dirs, files in os.walk(root):
        here = Path(current)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not _skipped(root, here / d))
        for name in sorted(files):
            if _is_env_file(name):
                path = here / name
                findings.append(Finding(
                    "error",
                    "dotenv",
                    f"{path} found: config now lives in the settings DB and .env files are not read. Import it, "
                    f"then it is removed: {IMPORT_COMMAND.format(path=path)}",
                ))
    return findings


def check_model_providers(root: Path) -> list[Finding]:
    path = root / "model_providers.json"
    if not path.exists():
        return []
    return [Finding("warn", "model-providers", f"{path} is no longer used (the backend modules are the catalog); delete it.")]


def check_gemini_home_env(root: Path) -> list[Finding]:
    path = Path.home() / ".gemini" / ".env"
    if not path.exists():
        return []
    return [Finding("warn", "gemini-home-env", f"{path} exists. The gemini CLI reads it; Resumator does not.")]


def check_shadowed_env(root: Path) -> list[Finding]:
    import settings_env  # lazy: settings_catalog imports cv_convert, which imports this module

    keys = settings_env.shadowed_keys()
    if not keys:
        return []
    return [Finding(
        "warn",
        "shell-shadow",
        "Set in the shell and ignored (the settings DB wins): " + ", ".join(keys),
    )]


CHECKS: list[Callable[[Path], list[Finding]]] = [
    check_dotenv,
    check_model_providers,
    check_gemini_home_env,
    check_shadowed_env,
]


def run_audit(root: Path | str | None = None, *, allow: Iterable[str] = ()) -> list[Finding]:
    """All findings for the install at `root` (default: the repo), minus checks whose code is in `allow`."""
    root = Path(root) if root is not None else ROOT_DIR
    allowed = set(allow)
    return [f for check in CHECKS for f in check(root) if f.code not in allowed]


def audit_or_exit(root: Path | str | None = None, *, allow: Iterable[str] = ()) -> None:
    """Print warnings and errors to stderr; exit 1 if there are errors."""
    findings = run_audit(root, allow=allow)
    for finding in findings:
        print(f"{finding.level}: {finding.message}", file=sys.stderr)
    if any(f.level == "error" for f in findings):
        sys.exit(1)

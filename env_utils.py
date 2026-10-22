"""
Architecture role:
- Layer: shared backend utility.
- Responsibility: parse dotenv-style files into key/value mappings for runtime configuration.

Plain-language purpose:
- This module is the common .env parser used by backend modules to avoid duplicated
    environment parsing logic.
"""

from __future__ import annotations

from pathlib import Path


def parse_dotenv_text(text: str) -> dict[str, str]:
    """Parse dotenv-style key/value pairs from text.

    Boundaries:
    - Ignores blank/comment lines, optional `export` prefix, malformed rows,
      and strips matching quote wrappers around values. Later duplicates win.
    """
    env_vars: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        env_vars[key] = value

    return env_vars


def parse_dotenv_file(path: Path) -> dict[str, str]:
    """Parse a dotenv-style file; a missing file gives an empty mapping."""
    if not path.exists():
        return {}
    return parse_dotenv_text(path.read_text(encoding="utf-8"))

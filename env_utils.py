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


def parse_dotenv_file(path: Path) -> dict[str, str]:
    env_vars: dict[str, str] = {}
    if not path.exists():
        return env_vars

    for raw_line in path.read_text(encoding="utf-8").splitlines():
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

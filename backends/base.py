from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from provider_clients import AttemptResult


@dataclass
class BackendStatus:
    enabled: bool
    reason: str = ""
    models: list[str] | None = None
    default_model: str = ""


class Backend(Protocol):
    id: str
    label: str
    timeout_seconds: int

    def interrogate(self, env: dict[str, str]) -> BackendStatus:
        ...

    def model_sequence(self, env: dict[str, str], explicit_model: str = "") -> list[str]:
        ...

    def run_attempt(
        self,
        *,
        model_name: str,
        prompt_text: str,
        env: dict[str, str],
        timeout_seconds: int,
        heartbeat_seconds: int,
        attempt_index: int,
        debug_log_dir: Path,
        log_prefix: str,
        emit_live_output: bool,
        **extra_options: object,
    ) -> AttemptResult:
        ...

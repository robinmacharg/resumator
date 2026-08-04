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
        """Report backend readiness and available models for current environment.

        Inputs:
        - env: Runtime environment values.

        Returns:
        - Backend status with enabled flag, reason, and model metadata.
        """
        ...

    def model_sequence(self, env: dict[str, str], explicit_model: str = "") -> list[str]:
        """Return ordered model candidates for attempts.

        Inputs:
        - env: Runtime environment values.
        - explicit_model: Optional forced model id.

        Returns:
        - Ordered list of model ids to try.
        """
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
        """Execute one provider attempt for the supplied prompt payload.

        Inputs:
        - model_name: Selected model id for this attempt.
        - prompt_text: Prompt body sent to provider.
        - env: Runtime environment values.
        - timeout_seconds: Per-attempt timeout limit.
        - heartbeat_seconds: Output heartbeat interval for hanging detection.
        - attempt_index: 1-based attempt index.
        - debug_log_dir: Destination directory for per-attempt logs.
        - log_prefix: Prefix for emitted log file names.
        - emit_live_output: Whether to stream subprocess/provider output.

        Returns:
        - Normalized attempt result payload.
        """
        ...

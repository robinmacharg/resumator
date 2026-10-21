from __future__ import annotations

import shutil
from pathlib import Path

from backends.base import Backend, BackendStatus
from provider_clients import AttemptResult, run_claudecode_attempt

DEFAULT_MODEL = "opus"
# CLI aliases resolve to the latest model of each family, so this list doesn't go stale.
KNOWN_MODELS = ["opus", "sonnet", "fable", "haiku"]


def _split_csv(raw: str) -> list[str]:
    """Split comma-separated config value into trimmed tokens."""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _dedupe(items: list[str]) -> list[str]:
    """Return ordered unique non-empty strings."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


class ClaudeCodeBackend(Backend):
    id = "claudecode"
    label = "Claude Code"
    timeout_seconds = 600

    def model_sequence(self, env: dict[str, str], explicit_model: str = "") -> list[str]:
        """Build ordered Claude model candidates: explicit model only, else primary then env fallbacks."""
        explicit = explicit_model.strip()
        if explicit:
            return [explicit]
        primary = (env.get("CLAUDECODE_MODEL") or DEFAULT_MODEL).strip()
        return _dedupe([primary, *_split_csv(env.get("CLAUDECODE_MODEL_FALLBACKS", ""))])

    def interrogate(self, env: dict[str, str]) -> BackendStatus:
        """Report availability: enabled when the `claude` CLI is on PATH (login is checked at run time)."""
        if (env.get("BACKEND_CLAUDECODE_ENABLED") or "").strip().lower() in {"0", "false", "no", "off"}:
            return BackendStatus(enabled=False, reason="Disabled by BACKEND_CLAUDECODE_ENABLED.")
        if not shutil.which("claude"):
            return BackendStatus(enabled=False, reason="'claude' CLI not found on PATH (install Claude Code).")
        sequence = self.model_sequence(env, "")
        return BackendStatus(enabled=True, models=_dedupe([*sequence, *KNOWN_MODELS]), default_model=sequence[0])

    def run_attempt(
        self,
        *,
        model_name: str,
        prompt_text: str,
        env: dict[str, str],
        timeout_seconds: int,
        heartbeat_seconds: int,
        attempt_index: int,
        debug_log_dir: Path | None,
        log_prefix: str,
        emit_live_output: bool,
        **extra_options: object,
    ) -> AttemptResult:
        """Execute one Claude Code attempt through the shared client adapter."""
        return run_claudecode_attempt(
            model_name=model_name,
            prompt_text=prompt_text,
            env=env,
            timeout_seconds=timeout_seconds,
            heartbeat_seconds=heartbeat_seconds,
            attempt_index=attempt_index,
            debug_log_dir=debug_log_dir,
            log_prefix=log_prefix,
            emit_live_output=emit_live_output,
        )


def get_backend() -> Backend:
    """Construct backend instance for dynamic backend discovery."""
    return ClaudeCodeBackend()

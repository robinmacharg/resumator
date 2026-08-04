from __future__ import annotations

from pathlib import Path

from backends.base import Backend, BackendStatus
from provider_clients import AttemptResult, run_swiftlet_attempt

DEFAULT_MODEL = "qwen3_5_moe_text"
DEFAULT_FALLBACK_MODELS: list[str] = []


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


class SwiftletBackend(Backend):
    id = "swiftlet"
    label = "Swiftlet"
    timeout_seconds = 240

    def model_sequence(self, env: dict[str, str], explicit_model: str = "") -> list[str]:
        """Build ordered Swiftlet model candidates from config and defaults."""
        explicit = explicit_model.strip()
        if explicit:
            return [explicit]
        primary = (env.get("SWIFTLET_MODEL") or DEFAULT_MODEL).strip()
        fallback_env = _split_csv(env.get("SWIFTLET_MODEL_FALLBACKS", ""))
        return _dedupe([primary, *fallback_env, *DEFAULT_FALLBACK_MODELS])

    def interrogate(self, env: dict[str, str]) -> BackendStatus:
        """Report Swiftlet backend availability and model defaults."""
        models = self.model_sequence(env, "")
        return BackendStatus(enabled=True, models=models, default_model=models[0] if models else "")

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
        """Execute one Swiftlet provider attempt via shared request runner."""
        return run_swiftlet_attempt(
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
    return SwiftletBackend()

from __future__ import annotations

from pathlib import Path

from backends.base import Backend, BackendStatus
from provider_clients import AttemptResult, run_gemini_attempt

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_FAST_MODEL = "gemini-2.5-flash-lite"
DEFAULT_FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite-001",
    "gemini-2.0-flash-001",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]


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


class GeminiBackend(Backend):
    id = "gemini"
    label = "Gemini"
    timeout_seconds = 300

    def model_sequence(self, env: dict[str, str], explicit_model: str = "") -> list[str]:
        """Build ordered Gemini model candidates from explicit/env/default values."""
        explicit = explicit_model.strip()
        if explicit:
            return [explicit]

        fast_mode = (env.get("CV_FAST_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}
        default_primary = DEFAULT_FAST_MODEL if fast_mode else DEFAULT_MODEL
        primary = (env.get("GEMINI_MODEL") or default_primary).strip()
        fallback_env = _split_csv(env.get("GEMINI_MODEL_FALLBACKS", ""))

        return _dedupe([primary, *fallback_env, *DEFAULT_FALLBACK_MODELS])

    def interrogate(self, env: dict[str, str]) -> BackendStatus:
        """Report Gemini backend availability and model defaults."""
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
        """Execute one Gemini provider attempt through shared client adapter."""
        return run_gemini_attempt(
            model_name=model_name,
            prompt_text=prompt_text,
            env=env,
            timeout_seconds=timeout_seconds,
            heartbeat_seconds=heartbeat_seconds,
            attempt_index=attempt_index,
            debug_log_dir=debug_log_dir,
            log_prefix=log_prefix,
            emit_live_output=emit_live_output,
            max_429_lines_before_fallback=int(extra_options.get("max_429_lines_before_fallback", 0) or 0),
            rate_limit_grace_seconds=int(extra_options.get("rate_limit_grace_seconds", 0) or 0),
            max_retry_after_seconds_before_fallback=int(
                extra_options.get("max_retry_after_seconds_before_fallback", 0) or 0
            ),
        )


def get_backend() -> Backend:
    """Construct backend instance for dynamic backend discovery."""
    return GeminiBackend()

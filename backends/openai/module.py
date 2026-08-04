from __future__ import annotations

from pathlib import Path

from backends.base import Backend, BackendStatus
from provider_clients import AttemptResult, run_openai_attempt

DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_FALLBACK_MODELS = [
    "gpt-5.6-terra",
    "gpt-5.6-sol",
    "gpt-5.5",
    "gpt-4.1-mini",
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


class OpenAIBackend(Backend):
    id = "openai"
    label = "OpenAI"
    timeout_seconds = 180

    def model_sequence(self, env: dict[str, str], explicit_model: str = "") -> list[str]:
        """Build ordered OpenAI model candidates from config and defaults."""
        explicit = explicit_model.strip()
        if explicit:
            return [explicit]
        primary = (env.get("OPENAI_MODEL") or DEFAULT_MODEL).strip()
        fallback_env = _split_csv(env.get("OPENAI_MODEL_FALLBACKS", ""))
        return _dedupe([primary, *fallback_env, *DEFAULT_FALLBACK_MODELS])

    def interrogate(self, env: dict[str, str]) -> BackendStatus:
        """Report backend status, disabling when OpenAI credentials are missing."""
        token = (env.get("OPENAI_API_KEY") or env.get("OPENAI_TOKEN") or "").strip()
        models = self.model_sequence(env, "")
        if not token:
            return BackendStatus(
                enabled=False,
                reason="OPENAI_API_KEY missing in .env",
                models=models,
                default_model=models[0] if models else "",
            )
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
        """Execute one OpenAI provider attempt via shared request runner."""
        return run_openai_attempt(
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
    return OpenAIBackend()

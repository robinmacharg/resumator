from __future__ import annotations

from pathlib import Path

from backends.base import Backend, BackendStatus, SettingSpec
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

    def settings(self) -> list[SettingSpec]:
        """Declare every env key this backend reads, for the Settings catalog."""
        return [
            SettingSpec("OPENAI_API_KEY", "OpenAI API key", secret=True),
            SettingSpec("OPENAI_TOKEN", "OpenAI token (alias)", secret=True, help="Used when OPENAI_API_KEY is empty.", advanced=True),
            SettingSpec("OPENAI_API_URL", "OpenAI API URL", default="https://api.openai.com/v1/chat/completions"),
            SettingSpec("OPENAI_MODEL", "OpenAI model", default="gpt-5.6-luna"),
            SettingSpec("OPENAI_MODEL_FALLBACKS", "OpenAI fallback models", kind="csv", help="Comma-separated, tried in order after the primary model."),
            SettingSpec("OPENAI_MAX_RETRIES", "OpenAI max retries", kind="int", default="2", advanced=True),
            SettingSpec("OPENAI_INITIAL_BACKOFF_SECONDS", "OpenAI initial backoff (s)", kind="int", default="2", advanced=True),
        ]

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
                reason="OPENAI_API_KEY is not set (add it in Settings)",
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
        debug_log_dir: Path | None,
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

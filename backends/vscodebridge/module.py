from __future__ import annotations

from pathlib import Path

from backends.base import Backend, BackendStatus
from provider_clients import AttemptResult, run_vscodebridge_attempt

DEFAULT_MODEL = "copilot-vscode"
DEFAULT_FALLBACK_MODELS: list[str] = []


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


class VSCodeBridgeBackend(Backend):
    id = "vscodebridge"
    label = "VS Code Bridge"
    timeout_seconds = 240

    def model_sequence(self, env: dict[str, str], explicit_model: str = "") -> list[str]:
        explicit = explicit_model.strip()
        if explicit:
            return [explicit]
        primary = (env.get("VSCODE_BRIDGE_MODEL") or DEFAULT_MODEL).strip()
        fallback_env = _split_csv(env.get("VSCODE_BRIDGE_MODEL_FALLBACKS", ""))
        return _dedupe([primary, *fallback_env, *DEFAULT_FALLBACK_MODELS])

    def interrogate(self, env: dict[str, str]) -> BackendStatus:
        api_url = (env.get("VSCODE_BRIDGE_API_URL") or "http://127.0.0.1:8766/generate").strip()
        models = self.model_sequence(env, "")
        if not api_url:
            return BackendStatus(
                enabled=False,
                reason="VSCODE_BRIDGE_API_URL is empty",
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
        return run_vscodebridge_attempt(
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
    return VSCodeBridgeBackend()

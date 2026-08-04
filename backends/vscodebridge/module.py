from __future__ import annotations

import os
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

from backends.base import Backend, BackendStatus
from provider_clients import AttemptResult, run_vscodebridge_attempt

DEFAULT_MODEL = "copilot-vscode"
DEFAULT_FALLBACK_MODELS: list[str] = []
DEFAULT_API_URL = "http://127.0.0.1:8766/generate"
DEFAULT_STARTUP_TIMEOUT_SECONDS = 45
ROOT_DIR = Path(__file__).resolve().parents[2]
BRIDGE_DIR = ROOT_DIR / "VSCodeExtension"
BRIDGE_LAUNCHER = BRIDGE_DIR / "start_isolated_bridge.sh"


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


class VSCodeBridgeBackend(Backend):
    id = "vscodebridge"
    label = "VS Code Bridge"
    timeout_seconds = 240

    def model_sequence(self, env: dict[str, str], explicit_model: str = "") -> list[str]:
        """Build ordered bridge model candidates from explicit/config/default values."""
        explicit = explicit_model.strip()
        if explicit:
            return [explicit]
        primary = (env.get("VSCODE_BRIDGE_MODEL") or DEFAULT_MODEL).strip()
        fallback_env = _split_csv(env.get("VSCODE_BRIDGE_MODEL_FALLBACKS", ""))
        return _dedupe([primary, *fallback_env, *DEFAULT_FALLBACK_MODELS])

    @staticmethod
    def _api_url(env: dict[str, str]) -> str:
        """Resolve bridge API base URL from runtime config."""
        return (env.get("VSCODE_BRIDGE_API_URL") or DEFAULT_API_URL).strip()

    @staticmethod
    def _bridge_health_url(api_url: str) -> str:
        """Derive `/health` endpoint URL from configured API URL."""
        parsed = urlparse(api_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}/health"
        return ""

    @staticmethod
    def _bridge_api_key(env: dict[str, str]) -> str:
        """Resolve optional bridge API key from runtime config."""
        return (env.get("VSCODE_BRIDGE_API_KEY") or "").strip()

    @staticmethod
    def _health_check(api_url: str, api_key: str, timeout_seconds: float = 1.5) -> tuple[bool, str]:
        """Check bridge health endpoint and normalize readiness/error details.

        Returns:
        - Tuple `(is_ready, reason)` where `reason` is non-empty on failure.
        """
        health_url = VSCodeBridgeBackend._bridge_health_url(api_url)
        if not health_url:
            return False, "Unable to derive /health URL from VSCODE_BRIDGE_API_URL"

        headers = {}
        if api_key:
            headers["x-api-key"] = api_key

        req = request.Request(health_url, headers=headers, method="GET")
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                status = int(getattr(response, "status", 0) or 0)
                body = response.read().decode("utf-8", errors="replace").strip()
                if status != 200:
                    return False, f"Health check returned status {status}"

                try:
                    payload = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    return False, "Health check response was not valid JSON"

                if isinstance(payload, dict):
                    model_ready = payload.get("modelReady")
                    if model_ready is True:
                        return True, ""
                    reason = str(payload.get("reason") or "Copilot model is not ready").strip()
                    return False, reason

                return False, "Health check payload was not an object"
        except error.HTTPError as exc:
            details = ""
            try:
                details = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                details = ""
            return False, f"HTTP {int(exc.code or 0)} during health check{': ' + details if details else ''}"
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _autostart_enabled(env: dict[str, str]) -> bool:
        """Return whether bridge auto-start behavior is enabled."""
        return (env.get("VSCODE_BRIDGE_AUTOSTART") or "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _backend_enabled(env: dict[str, str]) -> bool:
        """Return whether the bridge backend is enabled by config flag."""
        return (env.get("BACKEND_VSCODEBRIDGE_ENABLED") or "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _startup_timeout_seconds(env: dict[str, str]) -> int:
        """Parse startup timeout setting with defensive fallback defaults."""
        raw = (env.get("VSCODE_BRIDGE_STARTUP_TIMEOUT_SECONDS") or "").strip()
        if not raw:
            return DEFAULT_STARTUP_TIMEOUT_SECONDS
        try:
            value = int(raw)
        except ValueError:
            return DEFAULT_STARTUP_TIMEOUT_SECONDS
        return value if value > 0 else DEFAULT_STARTUP_TIMEOUT_SECONDS

    @staticmethod
    def _launch_bridge(env: dict[str, str]) -> tuple[bool, str]:
        """Start bridge process using configured startup command or launcher script.

        Returns:
        - Tuple `(launched, reason)` where reason describes launch failure when false.
        """
        startup_cmd = (env.get("VSCODE_BRIDGE_STARTUP_CMD") or "").strip()
        launch_env = os.environ.copy()
        launch_env.update(env)

        api_url = VSCodeBridgeBackend._api_url(env)
        parsed = urlparse(api_url)
        if parsed.port:
            launch_env["CV_BRIDGE_PORT"] = str(parsed.port)
        api_key = VSCodeBridgeBackend._bridge_api_key(env)
        if api_key:
            launch_env["CV_BRIDGE_API_KEY"] = api_key

        try:
            if startup_cmd:
                subprocess.Popen(
                    startup_cmd,
                    shell=True,
                    cwd=str(ROOT_DIR),
                    env=launch_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True, ""

            if not BRIDGE_LAUNCHER.exists():
                return False, f"Bridge launcher not found at {BRIDGE_LAUNCHER}"

            subprocess.Popen(
                [str(BRIDGE_LAUNCHER)],
                cwd=str(BRIDGE_DIR),
                env=launch_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, ""
        except Exception as exc:
            return False, f"Bridge launch failed: {exc}"

    @staticmethod
    def _ensure_bridge_ready(env: dict[str, str]) -> tuple[bool, str]:
        """Ensure bridge is running/healthy, auto-starting when configured.

        Returns:
        - Tuple `(ready, reason)` where `reason` explains readiness failure.
        """
        api_url = VSCodeBridgeBackend._api_url(env)
        api_key = VSCodeBridgeBackend._bridge_api_key(env)

        is_up, reason = VSCodeBridgeBackend._health_check(api_url, api_key)
        if is_up:
            return True, ""

        if not VSCodeBridgeBackend._autostart_enabled(env):
            return False, f"Bridge is not running ({reason}) and VSCODE_BRIDGE_AUTOSTART is disabled"

        launched, launch_reason = VSCodeBridgeBackend._launch_bridge(env)
        if not launched:
            return False, f"{launch_reason} (last health reason: {reason})"

        deadline = time.monotonic() + VSCodeBridgeBackend._startup_timeout_seconds(env)
        last_reason = reason
        while time.monotonic() < deadline:
            is_up, last_reason = VSCodeBridgeBackend._health_check(api_url, api_key)
            if is_up:
                return True, ""
            time.sleep(0.6)

        return False, f"Bridge did not become ready in time ({last_reason})"

    def interrogate(self, env: dict[str, str]) -> BackendStatus:
        """Report bridge backend status for catalog display and routing decisions."""
        if not self._backend_enabled(env):
            return BackendStatus(
                enabled=False,
                reason="BACKEND_VSCODEBRIDGE_ENABLED=false",
                models=self.model_sequence(env, ""),
                default_model=self.model_sequence(env, "")[0],
            )

        api_url = self._api_url(env)
        models = self.model_sequence(env, "")
        if not api_url:
            return BackendStatus(
                enabled=False,
                reason="VSCODE_BRIDGE_API_URL is empty",
                models=models,
                default_model=models[0] if models else "",
            )

        is_up, reason = self._health_check(api_url, self._bridge_api_key(env))
        if is_up:
            return BackendStatus(enabled=True, models=models, default_model=models[0] if models else "")

        if self._autostart_enabled(env):
            return BackendStatus(
                enabled=True,
                reason="Bridge not running; will auto-start on first request",
                models=models,
                default_model=models[0] if models else "",
            )

        return BackendStatus(
            enabled=False,
            reason=f"Bridge unavailable: {reason}",
            models=models,
            default_model=models[0] if models else "",
        )

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
        """Execute one bridge-backed request attempt, creating failure log when unavailable."""
        ready, reason = self._ensure_bridge_ready(env)
        if not ready:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            safe_model = model_name.replace("/", "_")
            log_path = debug_log_dir / f"{log_prefix}-{attempt_index:02d}-{safe_model}-{timestamp}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "\n".join(
                    [
                        "provider=vscodebridge",
                        f"model={model_name}",
                        f"attempt={attempt_index}",
                        "return_code=503",
                        "elapsed_seconds=0.00",
                        "timed_out=False",
                        "--- STDOUT ---",
                        "",
                        "--- STDERR ---",
                        reason,
                    ]
                ),
                encoding="utf-8",
            )
            return AttemptResult(
                provider="vscodebridge",
                model=model_name,
                returncode=503,
                stdout="",
                stderr=reason,
                elapsed_seconds=0.0,
                log_path=log_path,
                timed_out=False,
            )

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
    """Construct backend instance for dynamic backend discovery."""
    return VSCodeBridgeBackend()

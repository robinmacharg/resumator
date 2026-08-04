from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from backends.base import Backend, BackendStatus

ROOT_DIR = Path(__file__).resolve().parent
BACKENDS_DIR = ROOT_DIR / "backends"
ENV_FILE_PATH = ROOT_DIR / ".env"


@dataclass
class RegisteredBackend:
    backend: Backend
    status: BackendStatus
    module_path: Path


@dataclass
class BackendCatalog:
    default_provider: str
    providers: list[dict[str, Any]]


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


def runtime_env() -> dict[str, str]:
    merged = os.environ.copy()
    merged.update(parse_dotenv_file(ENV_FILE_PATH))
    return merged


def _iter_backend_module_paths(backends_dir: Path = BACKENDS_DIR) -> list[Path]:
    if not backends_dir.exists():
        return []
    return sorted(backends_dir.glob("*/module.py"), key=lambda p: p.parent.name)


def _import_backend_module(module_path: Path) -> ModuleType:
    module_name = f"cvgen_backend_{module_path.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _safe_status(backend: Backend, env: dict[str, str]) -> BackendStatus:
    try:
        status = backend.interrogate(env)
    except Exception as exc:
        return BackendStatus(enabled=False, reason=f"interrogate failed: {exc}", models=[], default_model="")

    models = status.models if isinstance(status.models, list) else []
    cleaned_models = [m.strip() for m in models if isinstance(m, str) and m.strip()]
    default_model = (status.default_model or "").strip()
    if not default_model and cleaned_models:
        default_model = cleaned_models[0]
    if default_model and default_model not in cleaned_models:
        cleaned_models = [default_model, *cleaned_models]

    return BackendStatus(
        enabled=bool(status.enabled),
        reason=(status.reason or "").strip(),
        models=cleaned_models,
        default_model=default_model,
    )


def discover_backends(env: dict[str, str] | None = None) -> list[RegisteredBackend]:
    process_env = env or runtime_env()
    registered: list[RegisteredBackend] = []
    seen_ids: set[str] = set()

    for module_path in _iter_backend_module_paths():
        try:
            module = _import_backend_module(module_path)
            get_backend = getattr(module, "get_backend", None)
            if not callable(get_backend):
                continue

            backend_obj = get_backend()
            backend_id = str(getattr(backend_obj, "id", "")).strip()
            if not backend_id or backend_id in seen_ids:
                continue
            seen_ids.add(backend_id)

            status = _safe_status(backend_obj, process_env)
            registered.append(RegisteredBackend(backend=backend_obj, status=status, module_path=module_path))
        except Exception as exc:
            fallback_id = module_path.parent.name.strip() or module_path.parent.as_posix()
            if fallback_id in seen_ids:
                continue
            seen_ids.add(fallback_id)
            registered.append(
                RegisteredBackend(
                    backend=_FailedBackend(fallback_id),
                    status=BackendStatus(enabled=False, reason=f"module load failed: {exc}", models=[], default_model=""),
                    module_path=module_path,
                )
            )

    return registered


class _FailedBackend:
    def __init__(self, backend_id: str) -> None:
        self.id = backend_id
        self.label = backend_id
        self.timeout_seconds = 60

    def interrogate(self, _env: dict[str, str]) -> BackendStatus:
        return BackendStatus(enabled=False, reason="module load failed", models=[], default_model="")

    def model_sequence(self, _env: dict[str, str], explicit_model: str = "") -> list[str]:
        return [explicit_model] if explicit_model else []

    def run_attempt(self, **_kwargs: Any):
        raise RuntimeError("Backend is disabled due to module load failure")


def build_backend_catalog(env: dict[str, str] | None = None) -> BackendCatalog:
    discovered = discover_backends(env)
    providers: list[dict[str, Any]] = []

    for item in discovered:
        providers.append(
            {
                "id": item.backend.id,
                "label": item.backend.label,
                "enabled": bool(item.status.enabled),
                "disabledReason": item.status.reason or "",
                "defaultModel": item.status.default_model,
                "models": item.status.models or [],
            }
        )

    enabled = [p for p in providers if p.get("enabled")]
    if enabled:
        default_provider = str(enabled[0].get("id") or "")
    elif providers:
        default_provider = str(providers[0].get("id") or "")
    else:
        default_provider = ""

    return BackendCatalog(default_provider=default_provider, providers=providers)


def backend_map(env: dict[str, str] | None = None) -> dict[str, RegisteredBackend]:
    return {item.backend.id: item for item in discover_backends(env)}


def get_backend_or_raise(backend_id: str, env: dict[str, str] | None = None) -> RegisteredBackend:
    backend_id_clean = (backend_id or "").strip()
    found = backend_map(env).get(backend_id_clean)
    if not found:
        raise ValueError(f"Unsupported provider '{backend_id_clean}'.")
    return found

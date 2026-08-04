"""
Architecture role:
- Layer: backend provider discovery and capability catalog service.
- Responsibility: load backend implementations, interrogate runtime availability,
  normalize model metadata, and expose a stable provider catalog/map.

Plain-language purpose:
- This module is the provider registry for AI backends. It decides what providers exist,
  whether they are enabled, and which models can be used.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from backends.base import Backend, BackendStatus
from env_utils import parse_dotenv_file

ROOT_DIR = Path(__file__).resolve().parent
BACKENDS_DIR = ROOT_DIR / "backends"
ENV_FILE_PATH = ROOT_DIR / ".env"


@dataclass
class RegisteredBackend:
    """Runtime backend entry paired with interrogation status and module location."""

    backend: Backend
    status: BackendStatus
    module_path: Path


@dataclass
class BackendCatalog:
    """Serializable catalog payload returned to higher-level catalog builders."""

    default_provider: str
    providers: list[dict[str, Any]]


def runtime_env() -> dict[str, str]:
    """Build process environment values used by backend discovery and calls.

    Inputs:
    - None.

    Returns:
    - A merged environment dictionary where `.env` values override OS values.
    """
    merged = os.environ.copy()
    merged.update(parse_dotenv_file(ENV_FILE_PATH))
    return merged


def _iter_backend_module_paths(backends_dir: Path = BACKENDS_DIR) -> list[Path]:
    """List backend module entry files in deterministic order.

    Inputs:
    - backends_dir: Directory containing backend folders with `module.py` files.

    Returns:
    - Sorted list of backend module paths.
    """
    if not backends_dir.exists():
        return []
    return sorted(backends_dir.glob("*/module.py"), key=lambda p: p.parent.name)


def _import_backend_module(module_path: Path) -> ModuleType:
    """Import a backend module from disk using an isolated dynamic module name.

    Inputs:
    - module_path: Path to a backend `module.py` file.

    Returns:
    - Imported Python module object.

    Raises:
    - RuntimeError when the module specification cannot be created.
    - Any import-time exception raised by module execution.
    """
    module_name = f"cvgen_backend_{module_path.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _safe_status(backend: Backend, env: dict[str, str]) -> BackendStatus:
    """Interrogate backend status and normalize/guard the result.

    Inputs:
    - backend: Backend implementation to interrogate.
    - env: Runtime environment values used by the backend.

    Returns:
    - Sanitized `BackendStatus` that is always safe to serialize.

    Boundaries:
    - Backend exceptions are converted to disabled status records.
    """
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
    """Discover and interrogate all backend modules in the backends directory.

    Inputs:
    - env: Optional precomputed environment mapping.

    Returns:
    - List of registered backend entries with status and source module path.

    Boundaries:
    - Duplicate backend ids are ignored after first occurrence.
    - Module load failures are represented as disabled fallback backends.
    """
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
        """Create a backend placeholder used when module import fails."""
        self.id = backend_id
        self.label = backend_id
        self.timeout_seconds = 60

    def interrogate(self, _env: dict[str, str]) -> BackendStatus:
        """Return permanently disabled status for failed backend placeholders."""
        return BackendStatus(enabled=False, reason="module load failed", models=[], default_model="")

    def model_sequence(self, _env: dict[str, str], explicit_model: str = "") -> list[str]:
        """Return only explicit model when provided; otherwise no candidates."""
        return [explicit_model] if explicit_model else []

    def run_attempt(self, **_kwargs: Any):
        """Reject execution for failed backend placeholders.

        Raises:
        - RuntimeError always, because the underlying backend could not be loaded.
        """
        raise RuntimeError("Backend is disabled due to module load failure")


def build_backend_catalog(env: dict[str, str] | None = None) -> BackendCatalog:
    """Build normalized provider catalog payload from discovered backends.

    Inputs:
    - env: Optional environment mapping for backend interrogation.

    Returns:
    - `BackendCatalog` containing default provider id and provider records.
    """
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
    """Create id-to-backend lookup map for all discovered providers."""
    return {item.backend.id: item for item in discover_backends(env)}


def get_backend_or_raise(backend_id: str, env: dict[str, str] | None = None) -> RegisteredBackend:
    """Resolve a backend by id or raise a user-facing validation error.

    Inputs:
    - backend_id: Requested provider id.
    - env: Optional environment mapping for discovery.

    Returns:
    - Matched registered backend entry.

    Raises:
    - ValueError when provider id is unknown.
    """
    backend_id_clean = (backend_id or "").strip()
    found = backend_map(env).get(backend_id_clean)
    if not found:
        raise ValueError(f"Unsupported provider '{backend_id_clean}'.")
    return found

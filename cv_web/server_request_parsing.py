"""
Architecture role:
- Layer: backend server request parsing and provider selection helpers.
- Responsibility: validate API payloads and normalize provider/model option data.

Plain-language purpose:
- This module centralizes request-shape validation and provider/model selection logic
  so the HTTP server can focus on routing and process orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cv_convert import available_themes
from provider_catalog import load_provider_catalog, provider_map

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
MODEL_CATALOG_PATH = ROOT_DIR / "model_providers.json"


@dataclass(frozen=True)
class ResearchRunRequest:
    """Normalized payload for research-run API requests."""

    selected_provider: str
    selected_model: str
    company_name: str
    urls: list[str]
    dry_run: bool
    auto_format_pdf: bool


@dataclass(frozen=True)
class CvRunRequest:
    """Normalized payload for CV run API requests."""

    kind: str
    selected_provider: str
    selected_model: str
    theme: str = ""
    steering: str | None = None


def dedupe_keep_order(items: list[str]) -> list[str]:
    """Return unique non-empty strings while preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def load_catalog() -> dict[str, Any]:
    """Load provider catalog from configured runtime catalog source."""
    return load_provider_catalog(MODEL_CATALOG_PATH)


def build_provider_options() -> list[dict[str, str]]:
    """Build normalized provider options for API state payloads."""
    catalog = load_catalog()
    return [
        {
            "value": item["id"],
            "label": item["label"],
            "enabled": bool(item.get("enabled", True)),
            "disabledReason": str(item.get("disabledReason") or ""),
        }
        for item in catalog.get("providers", [])
        if isinstance(item, dict) and item.get("id") and item.get("label")
    ]


def build_available_models(selected_provider: str) -> list[str]:
    """Build model options for a provider, falling back to default provider."""
    catalog = load_catalog()
    providers = provider_map(catalog)
    provider_entry = providers.get(selected_provider)
    if not provider_entry:
        provider_entry = providers.get(catalog.get("defaultProvider", ""))
    if not provider_entry:
        return []

    return dedupe_keep_order(
        [item for item in provider_entry.get("models", []) if isinstance(item, str)]
    )


def parse_selected_provider(payload: dict[str, Any]) -> str:
    """Validate and resolve selected provider from request payload."""
    catalog = load_catalog()
    providers = provider_map(catalog)
    all_provider_ids = [
        str(item.get("id") or "").strip()
        for item in catalog.get("providers", [])
        if isinstance(item, dict)
    ]
    enabled_provider_ids = [
        str(item.get("id") or "").strip()
        for item in catalog.get("providers", [])
        if isinstance(item, dict) and bool(item.get("enabled", True))
    ]
    default_provider = str(catalog.get("defaultProvider", "")).strip()
    if default_provider not in enabled_provider_ids:
        default_provider = enabled_provider_ids[0] if enabled_provider_ids else ""

    raw_provider = payload.get("selectedProvider", "")
    if raw_provider is None:
        return default_provider
    if not isinstance(raw_provider, str):
        raise ValueError("selectedProvider must be a string")

    selected_provider = raw_provider.strip() or default_provider
    if selected_provider not in providers or selected_provider not in all_provider_ids:
        raise ValueError("selectedProvider is not in available provider options")
    selected_entry = providers.get(selected_provider) or {}
    if not bool(selected_entry.get("enabled", True)):
        raise ValueError("selectedProvider is currently disabled")
    return selected_provider


def parse_selected_model(payload: dict[str, Any], selected_provider: str) -> str:
    """Validate selected model against provider-available model options."""
    raw_model = payload.get("selectedModel", "")
    if raw_model is None:
        return ""
    if not isinstance(raw_model, str):
        raise ValueError("selectedModel must be a string")

    selected_model = raw_model.strip()
    if not selected_model:
        return ""

    available = build_available_models(selected_provider)
    if selected_model not in available:
        raise ValueError("selectedModel is not in available model options")
    return selected_model


def parse_company_name(payload: dict[str, Any]) -> str:
    """Validate and normalize company-name field from request payload."""
    company_name = str(payload.get("companyName", "")).strip()
    if not company_name:
        raise ValueError("companyName is required")
    return company_name


def parse_url_list(payload: dict[str, Any]) -> list[str]:
    """Validate and normalize URL list field from request payload."""
    raw_urls = payload.get("urls", [])
    if not isinstance(raw_urls, list):
        raise ValueError("urls must be a list of strings")

    urls: list[str] = []
    for idx, item in enumerate(raw_urls):
        if not isinstance(item, str):
            raise ValueError(f"urls[{idx}] must be a string")
        cleaned = item.strip()
        if cleaned:
            urls.append(cleaned)
    return urls


def parse_auto_format_pdf(payload: dict[str, Any]) -> bool:
    """Validate auto-format flag from request payload."""
    auto_format_pdf = payload.get("autoFormatPdf", True)
    if not isinstance(auto_format_pdf, bool):
        raise ValueError("autoFormatPdf must be a boolean")
    return auto_format_pdf


def parse_research_run_request(payload: dict[str, Any]) -> ResearchRunRequest:
    """Parse and normalize full research run request payload."""
    selected_provider = parse_selected_provider(payload)
    selected_model = parse_selected_model(payload, selected_provider)
    company_name = parse_company_name(payload)
    urls = parse_url_list(payload)
    dry_run = bool(payload.get("dryRun", False))
    auto_format_pdf = parse_auto_format_pdf(payload)

    return ResearchRunRequest(
        selected_provider=selected_provider,
        selected_model=selected_model,
        company_name=company_name,
        urls=urls,
        dry_run=dry_run,
        auto_format_pdf=auto_format_pdf,
    )


def parse_selected_theme(payload: dict[str, Any]) -> str:
    """Return the requested theme name, or "" (default theme) when it is missing or unknown."""
    theme = str(payload.get("selectedTheme") or "").strip()
    return theme if theme in available_themes() else ""


def parse_steering(payload: dict[str, Any]) -> str | None:
    """Return the steering text to send with a full run.

    None when the request has no `steering` object (legacy clients: generate_cv's own default applies);
    "" when steering is disabled or empty; otherwise the trimmed text.
    """
    steering = payload.get("steering")
    if steering is None:
        return None
    if not isinstance(steering, dict):
        raise ValueError("steering must be an object")
    enabled = steering.get("enabled", True)
    text = steering.get("text", "")
    if not isinstance(enabled, bool):
        raise ValueError("steering.enabled must be a boolean")
    if not isinstance(text, str):
        raise ValueError("steering.text must be a string")
    return text.strip() if enabled else ""


def parse_cv_run_request(route: str, payload: dict[str, Any]) -> CvRunRequest:
    """Parse and normalize CV run request payload from route and JSON body."""
    kind = "full" if route.endswith("/full") else "format"
    selected_provider = parse_selected_provider(payload)
    selected_model = parse_selected_model(payload, selected_provider)
    model_override = selected_model if kind == "full" else ""
    return CvRunRequest(
        kind=kind,
        selected_provider=selected_provider,
        selected_model=model_override,
        theme=parse_selected_theme(payload),
        steering=parse_steering(payload),
    )

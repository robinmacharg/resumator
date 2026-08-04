#!/usr/bin/env python3
"""
Architecture role:
- Layer: backend catalog adapter between provider registry and API server consumers.
- Responsibility: normalize discovered providers into frontend-facing catalog shape,
    and provide static fallback catalog behavior when discovery is unavailable.

Plain-language purpose:
- This module builds the provider/model list used by the app and keeps that payload
    consistent regardless of whether data comes from dynamic backends or static JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend_registry import build_backend_catalog, runtime_env

CATALOG_PATH = Path("model_providers.json")


def _dedupe(items: list[str]) -> list[str]:
    """Return ordered unique non-empty strings.

    Inputs:
    - items: Candidate string values.

    Returns:
    - Deduplicated list preserving first-seen order.
    """
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def load_provider_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load provider catalog from runtime discovery with static JSON fallback.

    Inputs:
    - path: Optional path to a static provider catalog JSON file.

    Returns:
    - Normalized provider catalog object consumed by the web server.

    Raises:
    - ValueError when static JSON exists but has invalid shape/content.
    """
    # Primary source: interrogated backend modules.
    discovered = build_backend_catalog(runtime_env())
    if discovered.providers:
        return {
            "defaultProvider": discovered.default_provider,
            "providers": [
                {
                    "id": item["id"],
                    "label": item["label"],
                    "defaultModel": item.get("defaultModel") or "",
                    "models": _dedupe([m for m in item.get("models", []) if isinstance(m, str)]),
                    "enabled": bool(item.get("enabled", False)),
                    "disabledReason": str(item.get("disabledReason") or ""),
                }
                for item in discovered.providers
            ],
        }

    # Fallback source: static JSON catalog.
    catalog_path = path or CATALOG_PATH
    if not catalog_path.exists():
        return {
            "defaultProvider": "gemini",
            "providers": [
                {
                    "id": "gemini",
                    "label": "Gemini",
                    "defaultModel": "gemini-3.5-flash-lite",
                    "models": ["gemini-3.5-flash-lite"],
                }
            ],
        }

    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    providers = raw.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ValueError("model_providers.json must include a non-empty providers array")

    normalized_providers: list[dict[str, Any]] = []
    provider_ids: set[str] = set()
    for item in providers:
        if not isinstance(item, dict):
            continue
        provider_id = str(item.get("id", "")).strip()
        if not provider_id or provider_id in provider_ids:
            continue
        label = str(item.get("label") or provider_id).strip()
        models_raw = item.get("models")
        models: list[str] = []
        if isinstance(models_raw, list):
            for model in models_raw:
                if isinstance(model, str):
                    models.append(model)
        models = _dedupe(models)
        if not models:
            continue
        default_model = str(item.get("defaultModel") or models[0]).strip()
        if default_model not in models:
            default_model = models[0]

        normalized_providers.append(
            {
                "id": provider_id,
                "label": label,
                "defaultModel": default_model,
                "models": models,
                "enabled": True,
                "disabledReason": "",
            }
        )
        provider_ids.add(provider_id)

    if not normalized_providers:
        raise ValueError("model_providers.json has no valid providers")

    default_provider = str(raw.get("defaultProvider") or normalized_providers[0]["id"]).strip()
    if default_provider not in provider_ids:
        default_provider = normalized_providers[0]["id"]

    return {
        "defaultProvider": default_provider,
        "providers": normalized_providers,
    }


def provider_ids(catalog: dict[str, Any]) -> list[str]:
    """Extract provider ids from normalized catalog payload."""
    return [item["id"] for item in catalog.get("providers", []) if isinstance(item, dict) and "id" in item]


def provider_map(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build id-keyed map of provider records for fast lookup."""
    return {
        item["id"]: item
        for item in catalog.get("providers", [])
        if isinstance(item, dict) and "id" in item
    }

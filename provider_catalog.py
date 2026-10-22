#!/usr/bin/env python3
"""
Architecture role:
- Layer: backend catalog adapter between provider registry and API server consumers.
- Responsibility: normalize discovered providers into frontend-facing catalog shape.

Plain-language purpose:
- This module builds the provider/model list used by the app and keeps that payload
    consistent for every consumer.
"""

from __future__ import annotations

from typing import Any

from backend_registry import build_backend_catalog, runtime_env


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


def load_provider_catalog(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Build the provider catalog from the discovered backend modules.

    Inputs:
    - env: Environment the backends are interrogated with (default `runtime_env()`).

    Returns:
    - Normalized provider catalog object consumed by the web server.
    """
    discovered = build_backend_catalog(runtime_env() if env is None else env)
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

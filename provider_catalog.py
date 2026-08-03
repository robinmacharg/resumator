#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CATALOG_PATH = Path("model_providers.json")


def _dedupe(items: list[str]) -> list[str]:
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
    return [item["id"] for item in catalog.get("providers", []) if isinstance(item, dict) and "id" in item]


def provider_map(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for item in catalog.get("providers", [])
        if isinstance(item, dict) and "id" in item
    }

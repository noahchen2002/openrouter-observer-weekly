"""Load core provider whitelist from config/core_providers.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline import config

DEFAULT_CONFIG_PATH = config.PROJECT_ROOT / "config" / "core_providers.json"


def load_core_providers(config_path: Path | None = None) -> list[dict[str, str]]:
    path = config_path or DEFAULT_CONFIG_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    providers: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            slug = item.strip().lower()
            if slug:
                providers.append({"provider_slug": slug, "provider_name": ""})
        elif isinstance(item, dict):
            slug = str(item.get("provider_slug") or "").strip().lower()
            if slug:
                providers.append(
                    {
                        "provider_slug": slug,
                        "provider_name": str(item.get("provider_name") or "").strip(),
                    }
                )
    return providers

"""Read persisted settings and history without trusting their JSON shape."""

import json
from pathlib import Path


def load_settings(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            return loaded
    except (OSError, ValueError):
        pass
    return {"onboarding_complete": False}


def load_history(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, list):
            return [
                item
                for item in loaded
                if isinstance(item, dict)
                and isinstance(item.get("text"), str)
                and isinstance(item.get("timestamp"), str)
            ]
    except (OSError, ValueError):
        pass
    return []

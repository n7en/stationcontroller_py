from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def get_networks(config: dict[str, Any]) -> list[dict[str, Any]]:
    return config.get("networks", [])


def get_buses(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the list of bus definitions from the new 'buses:' schema."""
    return config.get("buses", [])

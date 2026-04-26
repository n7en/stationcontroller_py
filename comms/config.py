from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, "r") as fh:
        return yaml.safe_load(fh) or {}


def get_networks(config: dict[str, Any]) -> list[dict[str, Any]]:
    return config.get("networks", [])

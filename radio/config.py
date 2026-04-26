"""
Loader and validator for radio_config.yaml.
"""
from __future__ import annotations

import yaml


def load_radio_config(config_path: str) -> dict:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    if not isinstance(cfg, dict):
        raise ValueError(f"{config_path}: expected a YAML mapping at top level")

    radios = cfg.get("radios", [])
    if not isinstance(radios, list):
        raise ValueError(f"{config_path}: 'radios' must be a list")

    for i, entry in enumerate(radios):
        if not isinstance(entry, dict):
            raise ValueError(f"{config_path}: radio entry {i} must be a mapping")
        if "name" not in entry:
            raise ValueError(f"{config_path}: radio entry {i} missing required field 'name'")
        if "backend" not in entry:
            raise ValueError(
                f"{config_path}: radio '{entry.get('name', i)}' missing required field 'backend'"
            )

    return cfg

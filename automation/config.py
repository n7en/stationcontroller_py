"""
Load automations from a YAML config file.

YAML structure (Home Assistant style):

  bands:                      # optional — omit for built-in amateur registry
    - name: "40m"
      start_hz: 7000000
      end_hz: 7300000

  automations:
    - name: "protect_high_swr"
      tier: protection
      priority: 100
      description: "..."
      mode: single            # single | restart | queued | parallel
      trigger:                # list — any trigger fires the automation
        - type: sensor_above
          sensor: watt_meter_swr
          threshold: 3.0
      condition:              # list — ALL must pass (optional)
        - type: ptt_active
      action:
        type: log
        message: "High SWR detected"
        level: WARNING
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .bands import Band, BandRegistry
from .trigger import trigger_from_config
from .condition import condition_from_config, And
from .action import action_from_config
from .automation import Automation, AutomationMode, AutomationTier
from .engine import AutomationEngine


def load_band_registry(cfg: dict) -> BandRegistry:
    raw = cfg.get("bands")
    if not raw:
        return BandRegistry.amateur()
    return BandRegistry([
        Band(
            name=b["name"],
            start_hz=float(b["start_hz"]),
            end_hz=float(b["end_hz"]),
            modes=tuple(b.get("modes", [])),
        )
        for b in raw
    ])


def _parse_conditions(raw) -> list:
    """Accept a single condition dict or a list; return list of Condition objects."""
    if not raw:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    return [condition_from_config(c) for c in raw]


def _parse_triggers(raw) -> list:
    """Accept a single trigger dict or a list; return list of Trigger objects."""
    if not raw:
        raise ValueError("automation must have at least one trigger")
    if isinstance(raw, dict):
        raw = [raw]
    return [trigger_from_config(t) for t in raw]


def load_automations(cfg: dict) -> list[Automation]:
    automations: list[Automation] = []
    for raw in cfg.get("automations", []):
        tier_str = raw.get("tier", "advisory").lower()
        try:
            tier = AutomationTier(tier_str)
        except ValueError:
            raise ValueError(
                f"Unknown tier {tier_str!r} in automation {raw.get('name')!r}. "
                f"Expected: protection, configuration, advisory"
            )

        mode_str = raw.get("mode", "single").lower()
        try:
            mode = AutomationMode(mode_str)
        except ValueError:
            raise ValueError(
                f"Unknown mode {mode_str!r} in automation {raw.get('name')!r}. "
                f"Expected: single, restart, queued, parallel"
            )

        automation = Automation(
            name=raw["name"],
            tier=tier,
            triggers=_parse_triggers(raw.get("trigger")),
            conditions=_parse_conditions(raw.get("condition")),
            action=action_from_config(raw["action"]),
            description=raw.get("description", ""),
            enabled=raw.get("enabled", True),
            mode=mode,
            priority=int(raw.get("priority", 0)),
        )
        automations.append(automation)
    return automations


def load_engine(config_path: str | Path) -> tuple[AutomationEngine, BandRegistry]:
    """
    Load an AutomationEngine and BandRegistry from a YAML config file.
    Returns (engine, band_registry).
    """
    with open(config_path) as fh:
        cfg = yaml.safe_load(fh) or {}

    band_registry = load_band_registry(cfg)
    engine = AutomationEngine()
    for automation in load_automations(cfg):
        engine.add_automation(automation)

    return engine, band_registry

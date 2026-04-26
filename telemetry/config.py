"""
Load TelemetryStore, SensorRecorder, and optionally DCNMessageLogger from config.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from .store import TelemetryStore
from .recorder import SensorRecorder
from .dcn_logger import DCNMessageLogger


def _defaults() -> dict:
    return {
        "telemetry": {
            "enabled": True,
            "database": {"url": "sqlite+aiosqlite:///data/station.db"},
            "sensor_recording": {
                "min_interval_s": 1.0,
                "min_change_threshold": 0.0,
                "exclude": [],
            },
            "dcn_logging": {
                "enabled": False,
            },
            "retention": {
                "sensor_readings_days": 90,
                "device_events_days": 365,
                "automation_events_days": 365,
                "application_log_days": 30,
            },
        }
    }


def load_telemetry(
    config_path: Optional[str | Path] = None,
    cfg: Optional[dict] = None,
) -> tuple[TelemetryStore, SensorRecorder, Optional[DCNMessageLogger]]:
    """
    Build a TelemetryStore, SensorRecorder, and optional DCNMessageLogger from config.

    Pass either a path to a YAML file or a pre-loaded dict.
    Missing keys fall back to defaults.

    Returns (store, recorder, dcn_logger).  dcn_logger is None when
    dcn_logging.enabled is false — attach it to a DCNNetwork to activate:

        if dcn_logger:
            dcn_logger.attach(network)

    Neither store nor recorder is open yet; call ``await store.open()`` before use.
    """
    defaults = _defaults()["telemetry"]

    if config_path is not None:
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        section = raw.get("telemetry", {})
    elif cfg is not None:
        section = cfg.get("telemetry", cfg)
    else:
        section = {}

    db_url = (
        section.get("database", {}).get("url")
        or defaults["database"]["url"]
    )

    sr_cfg = section.get("sensor_recording", {})
    min_interval = float(sr_cfg.get("min_interval_s", defaults["sensor_recording"]["min_interval_s"]))
    min_change   = float(sr_cfg.get("min_change_threshold", defaults["sensor_recording"]["min_change_threshold"]))
    exclude      = set(sr_cfg.get("exclude", []))

    dcn_enabled = bool(section.get("dcn_logging", {}).get("enabled", defaults["dcn_logging"]["enabled"]))

    store      = TelemetryStore(url=db_url)
    recorder   = SensorRecorder(store, min_interval_s=min_interval, min_change=min_change, exclude=exclude)
    dcn_logger = DCNMessageLogger(store) if dcn_enabled else None

    return store, recorder, dcn_logger

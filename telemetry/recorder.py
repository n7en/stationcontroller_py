"""
SensorRecorder - bridges SensorRegistry.on_any() to TelemetryStore.

Throttles writes so rapid sensor bursts don't flood the database.
Per-sensor state tracks last write time and last written value so both
interval and change thresholds can be applied independently.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sensors.sensor_registry import Measurement

if TYPE_CHECKING:
    from sensors.sensor_registry import SensorRegistry
    from .store import TelemetryStore

log = logging.getLogger(__name__)


@dataclass
class _SensorState:
    last_written_ts: float = 0.0
    last_written_value: float = float("nan")


class SensorRecorder:
    """
    Attach to a SensorRegistry and write throttled readings to a TelemetryStore.

    min_interval_s  - minimum seconds between writes for the same sensor (default 1.0)
    min_change      - minimum absolute change in value before writing again (default 0.0,
                      meaning any change triggers a write once the interval has elapsed)
    exclude         - set of sensor names to never record
    """

    def __init__(
        self,
        store: "TelemetryStore",
        min_interval_s: float = 1.0,
        min_change: float = 0.0,
        exclude: set[str] | None = None,
    ) -> None:
        self._store = store
        self._min_interval = min_interval_s
        self._min_change = min_change
        self._exclude: set[str] = exclude or set()
        self._state: dict[str, _SensorState] = {}

    def attach(self, registry: "SensorRegistry") -> None:
        registry.on_any(self._on_measurement)

    def _on_measurement(self, m: Measurement) -> None:
        if m.name in self._exclude:
            return
        state = self._state.setdefault(m.name, _SensorState())
        now = time.time()

        elapsed = now - state.last_written_ts
        if elapsed < self._min_interval:
            return

        import math
        delta = abs(m.value - state.last_written_value)
        if not math.isnan(state.last_written_value) and delta < self._min_change:
            return

        state.last_written_ts = now
        state.last_written_value = m.value

        # Fire-and-forget into the running event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._store.record_sensor(
                    sensor_name=m.name,
                    value=m.value,
                    unit=m.unit,
                    source=m.source,
                    ts=m.timestamp,
                ),
                name=f"telemetry.sensor.{m.name}",
            )
        except RuntimeError:
            log.debug("SensorRecorder: no running event loop, skipping %s", m.name)

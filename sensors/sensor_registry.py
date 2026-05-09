"""
SensorRegistry - shared live-value bus for device measurements.

Any module (watt meter, GPIO, future devices) publishes named float values.
The automation engine and any other consumer reads by name or subscribes
to change notifications.

Thread-safe: publish() may be called from any thread or asyncio coroutine.
Callbacks are fired via asyncio.create_task() when a running event loop
exists; they are silently dropped if called from a non-asyncio context
(background threads that haven't yet bridged to the loop).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable, Optional, Union

if TYPE_CHECKING:
    from .label_registry import LabelRegistry

log = logging.getLogger(__name__)

Callback = Callable[["Measurement"], Union[None, Awaitable[None]]]


@dataclass
class Measurement:
    name: str
    value: float
    unit: str = ""
    source: str = ""
    timestamp: float = field(default_factory=time.time)

    def age_s(self) -> float:
        """Seconds since this measurement was recorded."""
        return time.time() - self.timestamp


class SensorRegistry:
    """
    Key-value store of the most recent measurement for each named sensor.

    Usage::

        registry = SensorRegistry()

        # publish (from any module)
        registry.publish("swr", 1.8, source="watt_meter")

        # read
        m = registry.get("swr")
        if m and not registry.is_stale("swr", max_age_s=5.0):
            print(m.value)

        # subscribe
        @registry.on_change("swr")
        async def swr_changed(measurement):
            print("SWR is now", measurement.value)
    """

    def __init__(self) -> None:
        self._store: dict[str, Measurement] = {}
        self._per_key: dict[str, list[Callback]] = {}
        self._wildcard: list[Callback] = []
        self._lock = threading.Lock()
        self._labels: Optional["LabelRegistry"] = None

    def attach_labels(self, labels: "LabelRegistry") -> None:
        """Attach a LabelRegistry so friendly names resolve in get()/value()/is_stale()."""
        self._labels = labels

    def _resolve(self, name: str) -> str:
        """Return the hardware key for *name*, resolving through labels if attached."""
        if self._labels is not None:
            return self._labels.resolve(name)
        return name

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(
        self,
        name: str,
        value: float,
        unit: str = "",
        source: str = "",
    ) -> None:
        """Record a new measurement and notify subscribers."""
        m = Measurement(name=name, value=value, unit=unit, source=source)
        with self._lock:
            is_new = name not in self._store
            self._store[name] = m
            callbacks = list(self._per_key.get(name, [])) + list(self._wildcard)

        if is_new:
            log.debug("New sensor: %s  source=%s  unit=%s", name, source or "(none)", unit or "(none)")

        self._fire_all(callbacks, m)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[Measurement]:
        """Return the most recent measurement, or None if never published.

        *name* may be a hardware key or a friendly label (if a LabelRegistry
        is attached via attach_labels()).
        """
        with self._lock:
            return self._store.get(self._resolve(name))

    def value(self, name: str, default: float = 0.0) -> float:
        """Return the current value or *default* if name is unknown.

        *name* may be a hardware key or a friendly label.
        """
        m = self.get(name)
        return m.value if m is not None else default

    def is_stale(self, name: str, max_age_s: float = 5.0) -> bool:
        """Return True if the measurement is older than *max_age_s* or absent.

        *name* may be a hardware key or a friendly label.
        """
        m = self.get(name)
        if m is None:
            return True
        return m.age_s() > max_age_s

    def snapshot(self) -> dict[str, Measurement]:
        """Return a shallow copy of the store keyed by hardware names."""
        with self._lock:
            return dict(self._store)

    def snapshot_labeled(self) -> dict[str, Measurement]:
        """Return a shallow copy of the store keyed by friendly labels where available.

        Sensors without a label keep their hardware key.  Requires a LabelRegistry
        to be attached; without one this is identical to snapshot().
        """
        with self._lock:
            raw = dict(self._store)
        if self._labels is None:
            return raw
        return {self._labels.label_for(k): v for k, v in raw.items()}

    def names(self) -> list[str]:
        """Return all currently known sensor hardware keys."""
        with self._lock:
            return list(self._store.keys())

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def on_change(
        self,
        name: str,
        callback: Optional[Callback] = None,
    ) -> Callable:
        """
        Register a callback for a specific sensor name.
        Works as a decorator or a direct call::

            registry.on_change("swr", my_handler)

            @registry.on_change("swr")
            async def handler(m): ...
        """
        if callback is not None:
            with self._lock:
                self._per_key.setdefault(name, []).append(callback)
            return callback

        def decorator(fn: Callback) -> Callback:
            with self._lock:
                self._per_key.setdefault(name, []).append(fn)
            return fn

        return decorator

    def on_any(self, callback: Optional[Callback] = None) -> Callable:
        """
        Register a callback fired for every published measurement.
        Works as a decorator or a direct call.
        """
        if callback is not None:
            with self._lock:
                self._wildcard.append(callback)
            return callback

        def decorator(fn: Callback) -> Callback:
            with self._lock:
                self._wildcard.append(fn)
            return fn

        return decorator

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _fire_all(callbacks: list[Callback], measurement: Measurement) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        for cb in callbacks:
            try:
                result = cb(measurement)
                if asyncio.iscoroutine(result):
                    if loop:
                        loop.create_task(result)
                    else:
                        result.close()
            except Exception:
                log.exception("Sensor callback raised for %s", measurement.name)

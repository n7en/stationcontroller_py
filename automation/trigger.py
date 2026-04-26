"""
Trigger hierarchy for the automation engine.

Each trigger watches for a specific *transition* event and fires once when
that transition occurs.  Triggers are stateful — they track previous values
so they can detect crossings.

Trigger.update() is called by the engine on every state change.  It returns
TriggerData when the trigger fires, None otherwise.  The first call
establishes a baseline and never fires, matching Home Assistant behaviour.

ManualTrigger never fires from update() — it exists solely so the engine's
trigger() method can force-fire an automation for testing.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from radio.radio_state import RadioState
from sensors.sensor_registry import SensorRegistry
from .bands import BandRegistry


_UNSET = object()   # sentinel for "no previous value"


@dataclass
class TriggerData:
    trigger_type: str
    automation_name: str = ""
    sensor_name: Optional[str] = None
    from_value: Optional[float] = None
    to_value: Optional[float] = None
    from_band: Optional[str] = None
    to_band: Optional[str] = None
    manual: bool = False
    timestamp: float = field(default_factory=time.time)


class Trigger(ABC):
    @abstractmethod
    def update(
        self,
        registry: SensorRegistry,
        radio_state: RadioState,
        band_registry: BandRegistry,
    ) -> Optional[TriggerData]:
        """
        Evaluate current state.  Returns TriggerData if this trigger fires,
        None otherwise.  The very first call sets baseline and never fires.
        """

    def reset(self) -> None:
        """Clear internal state so the next update re-establishes baseline."""


# ---------------------------------------------------------------------------
# Sensor triggers
# ---------------------------------------------------------------------------

class SensorAboveTrigger(Trigger):
    """
    Fires when sensor value rises above threshold (crosses from <= to >).

    Optional for_seconds — the sensor must stay continuously above threshold
    for this many seconds before the trigger fires.  Useful for ignoring
    brief spikes (e.g. SWR during auto-tuner cycles).  Default 0 fires
    immediately on crossing, matching the original behaviour.
    """

    def __init__(self, sensor_name: str, threshold: float, for_seconds: float = 0.0) -> None:
        self.sensor_name = sensor_name
        self.threshold = threshold
        self.for_seconds = for_seconds
        self._was_above: object = _UNSET
        self._above_since: Optional[float] = None
        self._fired_this_period: bool = False

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        m = registry.get(self.sensor_name)
        if m is None:
            if self._was_above is _UNSET:
                self._was_above = False
            elif self._was_above is True:
                self._was_above = False
                self._above_since = None
                self._fired_this_period = False
            return None

        is_above = m.value > self.threshold
        prev = self._was_above
        self._was_above = is_above

        if prev is _UNSET:
            return None  # baseline — never fire on first call

        if not is_above:
            self._above_since = None
            self._fired_this_period = False
            return None

        # Sensor is above threshold
        if prev is False:
            self._above_since = time.time()  # fresh crossing — start timer

        if self._above_since is None or self._fired_this_period:
            return None

        if self.for_seconds <= 0:
            if prev is False:
                self._fired_this_period = True
                return TriggerData(
                    trigger_type="sensor_above",
                    sensor_name=self.sensor_name,
                    to_value=m.value,
                )
        elif time.time() - self._above_since >= self.for_seconds:
            self._fired_this_period = True
            return TriggerData(
                trigger_type="sensor_above",
                sensor_name=self.sensor_name,
                to_value=m.value,
            )
        return None

    def reset(self) -> None:
        self._was_above = _UNSET
        self._above_since = None
        self._fired_this_period = False


class SensorBelowTrigger(Trigger):
    """
    Fires when sensor value falls below threshold (crosses from >= to <).

    Optional for_seconds — the sensor must stay continuously below threshold
    for this many seconds before the trigger fires.  Default 0 fires
    immediately on crossing.
    """

    def __init__(self, sensor_name: str, threshold: float, for_seconds: float = 0.0) -> None:
        self.sensor_name = sensor_name
        self.threshold = threshold
        self.for_seconds = for_seconds
        self._was_below: object = _UNSET
        self._below_since: Optional[float] = None
        self._fired_this_period: bool = False

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        m = registry.get(self.sensor_name)
        if m is None:
            if self._was_below is _UNSET:
                self._was_below = False
            elif self._was_below is True:
                self._was_below = False
                self._below_since = None
                self._fired_this_period = False
            return None

        is_below = m.value < self.threshold
        prev = self._was_below
        self._was_below = is_below

        if prev is _UNSET:
            return None  # baseline

        if not is_below:
            self._below_since = None
            self._fired_this_period = False
            return None

        if prev is False:
            self._below_since = time.time()

        if self._below_since is None or self._fired_this_period:
            return None

        if self.for_seconds <= 0:
            if prev is False:
                self._fired_this_period = True
                return TriggerData(
                    trigger_type="sensor_below",
                    sensor_name=self.sensor_name,
                    to_value=m.value,
                )
        elif time.time() - self._below_since >= self.for_seconds:
            self._fired_this_period = True
            return TriggerData(
                trigger_type="sensor_below",
                sensor_name=self.sensor_name,
                to_value=m.value,
            )
        return None

    def reset(self) -> None:
        self._was_below = _UNSET
        self._below_since = None
        self._fired_this_period = False


class SensorChangedTrigger(Trigger):
    """Fires when a sensor's value changes by at least min_delta."""

    def __init__(self, sensor_name: str, min_delta: float = 0.0) -> None:
        self.sensor_name = sensor_name
        self.min_delta = min_delta
        self._last_value: object = _UNSET

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        m = registry.get(self.sensor_name)
        if m is None:
            return None

        prev = self._last_value
        self._last_value = m.value

        if prev is _UNSET:
            return None

        if m.value != prev and abs(m.value - prev) >= self.min_delta:
            return TriggerData(
                trigger_type="sensor_changed",
                sensor_name=self.sensor_name,
                from_value=prev,
                to_value=m.value,
            )
        return None

    def reset(self) -> None:
        self._last_value = _UNSET


# ---------------------------------------------------------------------------
# Band triggers
# ---------------------------------------------------------------------------

class BandEnteredTrigger(Trigger):
    """Fires when the operating frequency moves into the specified band."""

    def __init__(self, band_name: str) -> None:
        self.band_name = band_name
        self._was_in_band: object = _UNSET

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        freq = radio_state.frequency_hz
        band = band_registry.band_for_freq(freq) if freq is not None else None
        in_band = band is not None and band.name == self.band_name

        prev = self._was_in_band
        self._was_in_band = in_band

        if prev is False and in_band:
            return TriggerData(trigger_type="band_entered", to_band=self.band_name)
        return None

    def reset(self) -> None:
        self._was_in_band = _UNSET


class BandExitedTrigger(Trigger):
    """Fires when the operating frequency moves out of the specified band."""

    def __init__(self, band_name: str) -> None:
        self.band_name = band_name
        self._was_in_band: object = _UNSET

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        freq = radio_state.frequency_hz
        band = band_registry.band_for_freq(freq) if freq is not None else None
        in_band = band is not None and band.name == self.band_name

        prev = self._was_in_band
        self._was_in_band = in_band

        if prev is True and not in_band:
            return TriggerData(trigger_type="band_exited", from_band=self.band_name)
        return None

    def reset(self) -> None:
        self._was_in_band = _UNSET


class BandChangedTrigger(Trigger):
    """Fires whenever the current band changes (including entering/leaving no-band)."""

    def __init__(self) -> None:
        self._last_band: object = _UNSET

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        freq = radio_state.frequency_hz
        band = band_registry.band_for_freq(freq) if freq is not None else None
        current = band.name if band else None

        prev = self._last_band
        self._last_band = current

        if prev is _UNSET:
            return None

        if current != prev:
            return TriggerData(
                trigger_type="band_changed",
                from_band=prev if isinstance(prev, str) else None,
                to_band=current,
            )
        return None

    def reset(self) -> None:
        self._last_band = _UNSET


# ---------------------------------------------------------------------------
# PTT / radio triggers
# ---------------------------------------------------------------------------

class PTTOnTrigger(Trigger):
    """Fires when PTT transitions from inactive to active."""

    def __init__(self) -> None:
        self._prev: object = _UNSET

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        active = radio_state.ptt
        prev = self._prev
        self._prev = active
        if prev is False and active:
            return TriggerData(trigger_type="ptt_on")
        return None

    def reset(self) -> None:
        self._prev = _UNSET


class PTTOffTrigger(Trigger):
    """Fires when PTT transitions from active to inactive."""

    def __init__(self) -> None:
        self._prev: object = _UNSET

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        active = radio_state.ptt
        prev = self._prev
        self._prev = active
        if prev is True and not active:
            return TriggerData(trigger_type="ptt_off")
        return None

    def reset(self) -> None:
        self._prev = _UNSET


class RadioConnectedTrigger(Trigger):
    """Fires when the radio transitions to connected."""

    def __init__(self) -> None:
        self._prev: object = _UNSET

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        connected = radio_state.connected
        prev = self._prev
        self._prev = connected
        if prev is False and connected:
            return TriggerData(trigger_type="radio_connected")
        return None

    def reset(self) -> None:
        self._prev = _UNSET


class RadioDisconnectedTrigger(Trigger):
    """Fires when the radio transitions to disconnected."""

    def __init__(self) -> None:
        self._prev: object = _UNSET

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        connected = radio_state.connected
        prev = self._prev
        self._prev = connected
        if prev is True and not connected:
            return TriggerData(trigger_type="radio_disconnected")
        return None

    def reset(self) -> None:
        self._prev = _UNSET


# ---------------------------------------------------------------------------
# Time trigger
# ---------------------------------------------------------------------------

class TimeTrigger(Trigger):
    """
    Fires once per day when the wall-clock time matches HH:MM.

    Optional days list restricts firing to specific days of the week
    (three-letter abbreviations: "mon", "tue", "wed", "thu", "fri", "sat", "sun").

    The engine must be called at least once per minute near the scheduled time
    for the trigger to fire reliably — use a periodic background task alongside
    normal event-driven calls.
    """

    def __init__(self, time_str: str, days: list[str] | None = None) -> None:
        h, m = time_str.split(":")
        self._hour = int(h)
        self._minute = int(m)
        self._days: set[str] | None = {d.lower()[:3] for d in days} if days else None
        self._last_fired_key: tuple | None = None  # (year, month, day)

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        now = datetime.now()
        if now.hour != self._hour or now.minute != self._minute:
            return None
        if self._days is not None and now.strftime("%a").lower() not in self._days:
            return None
        key = (now.year, now.month, now.day)
        if key == self._last_fired_key:
            return None
        self._last_fired_key = key
        return TriggerData(trigger_type="time")

    def reset(self) -> None:
        self._last_fired_key = None


# ---------------------------------------------------------------------------
# Manual trigger
# ---------------------------------------------------------------------------

class ManualTrigger(Trigger):
    """
    Never fires from update() — it only activates via engine.trigger().

    Including this in an automation's trigger list documents that the
    automation supports manual testing.  It has no effect on normal operation.
    """

    def update(self, registry, radio_state, band_registry) -> Optional[TriggerData]:
        return None


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------

def trigger_from_config(cfg: dict) -> Trigger:
    kind = cfg.get("type", "")
    if kind == "sensor_above":
        return SensorAboveTrigger(cfg["sensor"], float(cfg["threshold"]), float(cfg.get("for_seconds", 0.0)))
    if kind == "sensor_below":
        return SensorBelowTrigger(cfg["sensor"], float(cfg["threshold"]), float(cfg.get("for_seconds", 0.0)))
    if kind == "sensor_changed":
        return SensorChangedTrigger(cfg["sensor"], float(cfg.get("min_delta", 0.0)))
    if kind == "band_entered":
        return BandEnteredTrigger(cfg["band"])
    if kind == "band_exited":
        return BandExitedTrigger(cfg["band"])
    if kind == "band_changed":
        return BandChangedTrigger()
    if kind == "ptt_on":
        return PTTOnTrigger()
    if kind == "ptt_off":
        return PTTOffTrigger()
    if kind == "radio_connected":
        return RadioConnectedTrigger()
    if kind == "radio_disconnected":
        return RadioDisconnectedTrigger()
    if kind == "manual":
        return ManualTrigger()
    if kind == "time":
        return TimeTrigger(cfg["time"], cfg.get("days"))
    raise ValueError(f"Unknown trigger type: {kind!r}")

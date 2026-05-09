"""
Condition hierarchy for the automation engine.

All conditions implement evaluate(ctx) -> bool.
Logical combinators (And, Or, Not) can be composed freely, including via
the & | ~ operators on any Condition subclass.

Conditions are stateless - safe to evaluate from multiple contexts.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from .context import AutomationContext


class Condition(ABC):
    @abstractmethod
    def evaluate(self, ctx: AutomationContext) -> bool: ...

    def __and__(self, other: "Condition") -> "And":
        return And(self, other)

    def __or__(self, other: "Condition") -> "Or":
        return Or(self, other)

    def __invert__(self) -> "Not":
        return Not(self)

    def reset(self) -> None:
        """Reset internal state. Only relevant for stateful conditions."""


# ---------------------------------------------------------------------------
# Trivial conditions
# ---------------------------------------------------------------------------

class Always(Condition):
    def evaluate(self, ctx: AutomationContext) -> bool:
        return True


class Never(Condition):
    def evaluate(self, ctx: AutomationContext) -> bool:
        return False


# ---------------------------------------------------------------------------
# Frequency / band
# ---------------------------------------------------------------------------

class FrequencyInBand(Condition):
    def __init__(self, band_name: str) -> None:
        self.band_name = band_name

    def evaluate(self, ctx: AutomationContext) -> bool:
        band = ctx.current_band()
        return band is not None and band.name == self.band_name


class FrequencyInRange(Condition):
    def __init__(self, start_hz: float, end_hz: float) -> None:
        self.start_hz = start_hz
        self.end_hz = end_hz

    def evaluate(self, ctx: AutomationContext) -> bool:
        freq = ctx.radio_state.frequency_hz
        if freq is None:
            return False
        return self.start_hz <= freq <= self.end_hz


# ---------------------------------------------------------------------------
# Sensor value conditions
# ---------------------------------------------------------------------------

class SensorAbove(Condition):
    def __init__(self, sensor_name: str, threshold: float) -> None:
        self.sensor_name = sensor_name
        self.threshold = threshold

    def evaluate(self, ctx: AutomationContext) -> bool:
        return ctx.sensor(self.sensor_name) > self.threshold


class SensorBelow(Condition):
    def __init__(self, sensor_name: str, threshold: float) -> None:
        self.sensor_name = sensor_name
        self.threshold = threshold

    def evaluate(self, ctx: AutomationContext) -> bool:
        return ctx.sensor(self.sensor_name) < self.threshold


class SensorBetween(Condition):
    def __init__(self, sensor_name: str, low: float, high: float) -> None:
        self.sensor_name = sensor_name
        self.low = low
        self.high = high

    def evaluate(self, ctx: AutomationContext) -> bool:
        v = ctx.sensor(self.sensor_name)
        return self.low <= v <= self.high


class SensorPresent(Condition):
    """True when the sensor has a value in the registry (regardless of staleness)."""

    def __init__(self, sensor_name: str) -> None:
        self.sensor_name = sensor_name

    def evaluate(self, ctx: AutomationContext) -> bool:
        return ctx.registry.get(self.sensor_name) is not None


class SensorStale(Condition):
    """True when the sensor is absent or older than max_age_s."""

    def __init__(self, sensor_name: str, max_age_s: float = 5.0) -> None:
        self.sensor_name = sensor_name
        self.max_age_s = max_age_s

    def evaluate(self, ctx: AutomationContext) -> bool:
        return ctx.registry.is_stale(self.sensor_name, self.max_age_s)


# ---------------------------------------------------------------------------
# Relay conditions
# ---------------------------------------------------------------------------

class RelayOn(Condition):
    def __init__(self, relay_sensor_key: str) -> None:
        self.relay_sensor_key = relay_sensor_key

    def evaluate(self, ctx: AutomationContext) -> bool:
        state = ctx.relay_on(self.relay_sensor_key)
        return state is True


class RelayOff(Condition):
    def __init__(self, relay_sensor_key: str) -> None:
        self.relay_sensor_key = relay_sensor_key

    def evaluate(self, ctx: AutomationContext) -> bool:
        state = ctx.relay_on(self.relay_sensor_key)
        return state is False


# ---------------------------------------------------------------------------
# Radio state conditions
# ---------------------------------------------------------------------------

class RadioConnected(Condition):
    def evaluate(self, ctx: AutomationContext) -> bool:
        return ctx.radio_state.connected is True


class ModeIs(Condition):
    def __init__(self, mode: str) -> None:
        self.mode = mode.upper()

    def evaluate(self, ctx: AutomationContext) -> bool:
        m = ctx.radio_state.mode
        if m is None:
            return False
        val = m.value if hasattr(m, "value") else str(m)
        return val.upper() == self.mode


class PTTActive(Condition):
    def evaluate(self, ctx: AutomationContext) -> bool:
        return ctx.radio_state.ptt is True


class PTTDurationAbove(Condition):
    """
    True when PTT is active and has been continuously held for at least min_seconds.

    Stateful: tracks when PTT first became active.  The timer starts from the
    first evaluate() call where PTT is observed as active; it resets whenever
    PTT goes inactive.  Useful for qualifying that an SWR spike is from a real
    transmission rather than a brief auto-tuner keyup.
    """

    def __init__(self, min_seconds: float) -> None:
        self.min_seconds = min_seconds
        self._ptt_active_since: Optional[float] = None

    def evaluate(self, ctx: AutomationContext) -> bool:
        if not ctx.radio_state.ptt:
            self._ptt_active_since = None
            return False
        if self._ptt_active_since is None:
            self._ptt_active_since = time.time()
        return time.time() - self._ptt_active_since >= self.min_seconds

    def reset(self) -> None:
        self._ptt_active_since = None


class PTTDurationBelow(Condition):
    """
    True when PTT is active and has been held for less than max_seconds.

    Identifies short keyups (e.g. auto-tuner cycles under 60 s) vs longer
    real transmissions.  Returns False when PTT is not active.
    """

    def __init__(self, max_seconds: float) -> None:
        self.max_seconds = max_seconds
        self._ptt_active_since: Optional[float] = None

    def evaluate(self, ctx: AutomationContext) -> bool:
        if not ctx.radio_state.ptt:
            self._ptt_active_since = None
            return False
        if self._ptt_active_since is None:
            self._ptt_active_since = time.time()
        return time.time() - self._ptt_active_since < self.max_seconds

    def reset(self) -> None:
        self._ptt_active_since = None


# ---------------------------------------------------------------------------
# Logical combinators
# ---------------------------------------------------------------------------

class And(Condition):
    def __init__(self, *conditions: Condition) -> None:
        self.conditions = conditions

    def evaluate(self, ctx: AutomationContext) -> bool:
        return all(c.evaluate(ctx) for c in self.conditions)


class Or(Condition):
    def __init__(self, *conditions: Condition) -> None:
        self.conditions = conditions

    def evaluate(self, ctx: AutomationContext) -> bool:
        return any(c.evaluate(ctx) for c in self.conditions)


class Not(Condition):
    def __init__(self, condition: Condition) -> None:
        self.condition = condition

    def evaluate(self, ctx: AutomationContext) -> bool:
        return not self.condition.evaluate(ctx)


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------

def condition_from_config(cfg: dict) -> Condition:
    """
    Build a Condition from a config dict.

    The 'type' key selects the condition class; remaining keys are arguments.
    Compound conditions (and, or, not) recurse into their sub-conditions.
    """
    kind = cfg.get("type", "")
    if kind == "always":
        return Always()
    if kind == "never":
        return Never()
    if kind == "frequency_in_band":
        return FrequencyInBand(cfg["band"])
    if kind == "frequency_in_range":
        return FrequencyInRange(float(cfg["start_hz"]), float(cfg["end_hz"]))
    if kind == "sensor_above":
        return SensorAbove(cfg["sensor"], float(cfg["threshold"]))
    if kind == "sensor_below":
        return SensorBelow(cfg["sensor"], float(cfg["threshold"]))
    if kind == "sensor_between":
        return SensorBetween(cfg["sensor"], float(cfg["low"]), float(cfg["high"]))
    if kind == "sensor_present":
        return SensorPresent(cfg["sensor"])
    if kind == "sensor_stale":
        return SensorStale(cfg["sensor"], float(cfg.get("max_age_s", 5.0)))
    if kind == "relay_on":
        return RelayOn(cfg["relay"])
    if kind == "relay_off":
        return RelayOff(cfg["relay"])
    if kind == "radio_connected":
        return RadioConnected()
    if kind == "mode_is":
        return ModeIs(cfg["mode"])
    if kind == "ptt_active":
        return PTTActive()
    if kind == "ptt_duration_above":
        return PTTDurationAbove(float(cfg["min_seconds"]))
    if kind == "ptt_duration_below":
        return PTTDurationBelow(float(cfg["max_seconds"]))
    if kind == "and":
        return And(*(condition_from_config(c) for c in cfg["conditions"]))
    if kind == "or":
        return Or(*(condition_from_config(c) for c in cfg["conditions"]))
    if kind == "not":
        return Not(condition_from_config(cfg["condition"]))
    raise ValueError(f"Unknown condition type: {kind!r}")

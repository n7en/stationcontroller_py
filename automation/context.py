"""
AutomationContext - unified snapshot passed to every condition and action.

Bundles radio state, the live sensor registry, and the band registry so
conditions and actions have a single consistent view of the station.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from sensors.sensor_registry import Measurement, SensorRegistry
from radio.radio_state import RadioState
from .bands import Band, BandRegistry

if TYPE_CHECKING:
    pass


@dataclass
class AutomationContext:
    radio_state: RadioState
    registry: SensorRegistry
    band_registry: BandRegistry

    # Optional wiring for actions that control hardware.
    # Set these when constructing the context if the engine has hardware access.
    radio_interface: Optional[Any] = field(default=None, repr=False)
    control_network: Optional[Any] = field(default=None, repr=False)

    # Maximum radio output power in watts - used by SetRadioPower to convert
    # watts to the 0.0–1.0 normalized level the radio backend expects.
    radio_max_power_w: Optional[float] = None

    def sensor(self, name: str, default: float = 0.0) -> float:
        return self.registry.value(name, default)

    def sensor_measurement(self, name: str) -> Optional[Measurement]:
        return self.registry.get(name)

    def current_band(self) -> Optional[Band]:
        if self.radio_state.frequency_hz is None:
            return None
        return self.band_registry.band_for_freq(self.radio_state.frequency_hz)

    def current_band_name(self) -> Optional[str]:
        band = self.current_band()
        return band.name if band else None

    def relay_on(self, sensor_key: str) -> Optional[bool]:
        """
        Return True if the relay sensor reads 1.0, False if 0.0, None if absent.
        sensor_key is the SensorRegistry key, e.g. 'gpio_relay_3'.
        """
        m = self.registry.get(sensor_key)
        if m is None:
            return None
        return m.value == 1.0

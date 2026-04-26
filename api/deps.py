"""
Shared application state — injected into FastAPI routes via Depends().

AppState is populated once at startup (in app.py lifespan) and holds
references to every live singleton.  Routes receive it via get_state().
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from automation.engine import AutomationEngine
    from automation.bands import BandRegistry
    from comms.dcn_network import DCNNetwork
    from radio.radio_state import RadioState
    from sensors.sensor_registry import SensorRegistry
    from sensors.label_registry import LabelRegistry
    from telemetry.store import TelemetryStore
    from .ws_hub import WSHub


class AppState:
    def __init__(self) -> None:
        self.sensor_registry: Optional["SensorRegistry"] = None
        self.label_registry: Optional["LabelRegistry"] = None
        self.control_network: Optional["DCNNetwork"] = None
        self.radio_state: Optional["RadioState"] = None
        self.radio_interface: Optional[Any] = None
        self.engine: Optional["AutomationEngine"] = None
        self.band_registry: Optional["BandRegistry"] = None
        self.telemetry: Optional["TelemetryStore"] = None
        self.ws_hub: Optional["WSHub"] = None


# Module-level singleton — created once, mutated at startup
_state = AppState()


def get_state() -> AppState:
    return _state

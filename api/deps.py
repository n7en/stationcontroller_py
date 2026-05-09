"""
Shared application state - injected into FastAPI routes via Depends().

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
    from .log_buffer import LogBuffer
    from .ws_hub import WSHub


class AppState:
    def __init__(self) -> None:
        self.sensor_registry: Optional["SensorRegistry"] = None
        self.label_registry: Optional["LabelRegistry"] = None

        # Multi-bus DCN support.
        # networks    - all active buses keyed by bus name
        # devices     - all device instances keyed by device name
        # device_bus  - DCN address -> bus name mapping for outbound routing
        self.networks: dict[str, "DCNNetwork"] = {}
        self.devices: dict[str, Any] = {}
        self.device_bus: dict[str, str] = {}   # address -> bus name

        self.radio_state: Optional["RadioState"] = None
        self.radio_interface: Optional[Any] = None
        self.radio_manager: Optional[Any] = None   # holds all RadioInterface instances
        self.engine: Optional["AutomationEngine"] = None
        self.band_registry: Optional["BandRegistry"] = None
        self.telemetry:   Optional["TelemetryStore"] = None
        self.ws_hub:      Optional["WSHub"]          = None
        self.log_buffer:  Optional["LogBuffer"]      = None

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def control_network(self) -> Optional["DCNNetwork"]:
        """Return the 'control' bus, or the first available bus if absent."""
        networks = self.networks or {}
        return networks.get("control") or (
            next(iter(networks.values())) if networks else None
        )

    def network_for_addr(self, address: str) -> Optional["DCNNetwork"]:
        """Return the network responsible for *address*, with control-bus fallback."""
        networks   = self.networks   or {}
        device_bus = self.device_bus or {}
        bus = device_bus.get(address)
        if bus:
            net = networks.get(bus)
            if net is not None:
                return net
        return self.control_network


# Module-level singleton - created once, mutated at startup
_state = AppState()


def get_state() -> AppState:
    return _state

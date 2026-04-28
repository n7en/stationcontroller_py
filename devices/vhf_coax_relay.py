"""
DCN CX-2 Two Port VHF Coax Relay Module (#332).

Single-pole, double-throw (SPDT) RF relay switch.  The Common port connects
to either the Normally-Closed (NC) or Normally-Open (NO) antenna port
depending on relay state:

    Relay OFF (de-energized) → Common connects to NC port
    Relay ON  (energized)    → Common connects to NO port

Control commands (master → device):
    RY1,1   Energize relay    (Common → NO)
    RY1,0   De-energize relay (Common → NC)
    RY1,T   Toggle relay state

Status packet (device → master, UPDATE,CX2):
    args[0]  CX2     module type identifier
    args[1]  <state> relay state — "1" = energized, "0" = de-energized

Published sensor names (with name="vhf_coax"):
    vhf_coax_relay   1.0 = energized (Common→NO), 0.0 = de-energized (Common→NC)
    vhf_coax_nc      1.0 when NC port is active (relay OFF)
    vhf_coax_no      1.0 when NO port is active (relay ON)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from comms.dcn_network import DCNNetwork
from comms.dcn_packet import DCNPacket
from sensors.sensor_registry import SensorRegistry


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------

@dataclass
class VHFCoaxRelayState:
    name: str
    address: str

    relay_on: Optional[bool] = None  # True = energized (Common→NO), False = Common→NC

    updated_at: float = field(default_factory=time.time)

    @property
    def nc_active(self) -> Optional[bool]:
        """True when Common is connected to the NC port (relay de-energized)."""
        if self.relay_on is None:
            return None
        return not self.relay_on

    @property
    def no_active(self) -> Optional[bool]:
        """True when Common is connected to the NO port (relay energized)."""
        return self.relay_on


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class VHFCoaxRelay:
    """
    DCN CX-2 Two Port VHF Coax Relay Module (#332).

    Attaches to a DCNNetwork, listens for UPDATE,CX2 packets from the
    configured device address, and publishes relay state to a SensorRegistry.

    set_relay() and toggle() send control commands back to the device.

    Usage::

        registry = SensorRegistry()
        sw = VHFCoaxRelay(name="vhf_coax", address="05", registry=registry)
        sw.attach(network)

        await sw.set_relay(network, True)   # Common → NO
        await sw.set_relay(network, False)  # Common → NC
        await sw.toggle(network)            # flip current state

        print(sw.state.relay_on)                       # True/False/None
        print(registry.value("vhf_coax_relay"))        # 1.0 / 0.0
    """

    def __init__(
        self,
        name: str,
        address: str,
        registry: SensorRegistry,
    ) -> None:
        self.name = name
        self.address = address
        self._registry = registry
        self.state = VHFCoaxRelayState(name=name, address=address)
        src = f"vhf_coax_relay:{name}"
        registry.publish(f"{name}_relay", 0.0, "", src)
        registry.publish(f"{name}_nc",    1.0, "", src)
        registry.publish(f"{name}_no",    0.0, "", src)

    def attach(self, network: DCNNetwork) -> None:
        """Register the packet handler with a DCN network."""
        network.on_packet(self._handle_packet)

    async def set_relay(self, network: DCNNetwork, state: bool) -> None:
        """Energize (True) or de-energize (False) the relay."""
        await network.send(self.address, f"RY1,{1 if state else 0}")

    async def toggle(self, network: DCNNetwork) -> None:
        """Toggle the relay to the opposite state."""
        await network.send(self.address, "RY1,T")

    async def _handle_packet(self, packet: DCNPacket, transport_name: str) -> None:
        if packet.from_addr != self.address:
            return
        if packet.command != "UPDATE":
            return
        args = packet.args
        if not args or args[0] != "CX2":
            return
        self._parse_and_publish(args)

    def _parse_and_publish(self, args: list[str]) -> None:
        if len(args) < 2:
            return
        try:
            state_int = int(args[1])
        except ValueError:
            return
        if state_int not in (0, 1):
            return

        relay_on = bool(state_int)
        self.state.relay_on = relay_on
        self.state.updated_at = time.time()

        src = f"vhf_coax_relay:{self.name}"
        pfx = self.name
        self._registry.publish(f"{pfx}_relay", float(relay_on),     "", src)
        self._registry.publish(f"{pfx}_nc",    float(not relay_on), "", src)
        self._registry.publish(f"{pfx}_no",    float(relay_on),     "", src)


# ---------------------------------------------------------------------------
# Standalone packet parser
# ---------------------------------------------------------------------------

def parse_cx2_update(packet: DCNPacket) -> dict:
    """
    Parse an UPDATE,CX2 DCNPacket into a structured dict.

    Returned keys: module_type, relay_on (bool or None)
    """
    args = packet.args
    result: dict = {
        "module_type": args[0] if args else None,
        "relay_on": None,
    }
    if len(args) >= 2:
        try:
            v = int(args[1])
            result["relay_on"] = bool(v) if v in (0, 1) else None
        except ValueError:
            pass
    return result

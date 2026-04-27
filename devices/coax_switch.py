"""
DCN #331 CX-1 4 Port HF Coax Relay Module.

Switches a common RF port to one of four antenna ports using latching relays.
The currently selected port is retained even when power is removed.

DCN status packet (device → master, UPDATE,CX1):
    args[0]  CX1           module type identifier
    args[1]  <active_port> currently selected port, 1-indexed (0 = none selected)

Control command (master → device):
    CX,<port>              select port 1–4; port 0 = disconnect all

Published sensor names (with name="coax"):
    coax_active_port       — selected port as float (0.0 = none)
    coax_port_1 … port_4   — 1.0 if active, 0.0 otherwise
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from comms.dcn_network import DCNNetwork
from comms.dcn_packet import DCNPacket
from sensors.sensor_registry import SensorRegistry

N_PORTS = 4  # CX-1 is always a 4-port device


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------

@dataclass
class CoaxSwitchState:
    name: str
    address: str

    n_ports: int = N_PORTS              # fixed hardware — always 4
    active_port: Optional[int] = None   # 1-indexed; 0 = none selected

    updated_at: float = field(default_factory=time.time)

    def is_port_active(self, port: int) -> Optional[bool]:
        """True if *port* is the currently selected port, False otherwise, None if unknown."""
        if self.active_port is None:
            return None
        return self.active_port == port


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class CoaxSwitch:
    """
    DCN #331 CX-1 4 Port HF Coax Relay Module.

    Attaches to a DCNNetwork, listens for UPDATE,CX1 packets from the
    configured device address, and publishes port state to a SensorRegistry.

    Published sensor names (with name="coax"):
        coax_active_port       — selected port as float (0.0 = none)
        coax_port_1 … port_4   — 1.0 if active, 0.0 otherwise

    Usage::

        registry = SensorRegistry()
        switch = CoaxSwitch(name="coax", address="02", registry=registry)
        switch.attach(network)

        # Later:
        print(switch.state.active_port)               # 2
        print(registry.value("coax_active_port"))     # 2.0

        # Command the switch to select port 3:
        await switch.select_port(network, 3)
        # Or disconnect all:
        await switch.select_port(network, 0)
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
        self.state = CoaxSwitchState(name=name, address=address)

    def attach(self, network: DCNNetwork) -> None:
        """Register the packet handler with a DCN network."""
        network.on_packet(self._handle_packet)

    async def select_port(self, network: DCNNetwork, port: int) -> None:
        """Command the switch to select *port* (1–4, 0 = disconnect all)."""
        await network.send(self.address, f"CX,{port}")

    def optimistic_select(self, port: int) -> None:
        """Immediately publish *port* as active without waiting for hardware confirmation."""
        self._parse_and_publish(["CX1", str(port)])

    async def _handle_packet(self, packet: DCNPacket, transport_name: str) -> None:  # pyright: ignore[reportUnusedParameter]
        if packet.from_addr != self.address:
            return
        if packet.command != "UPDATE":
            return
        args = packet.args
        if not args or args[0] != "CX1":
            return
        self._parse_and_publish(args)

    def _parse_and_publish(self, args: list[str]) -> None:
        if len(args) < 2:
            return
        try:
            active_port = int(args[1])
        except ValueError:
            return

        self.state.active_port = active_port
        self.state.updated_at = time.time()

        src = f"coax_switch:{self.name}"
        pfx = self.name

        self._registry.publish(f"{pfx}_active_port", float(active_port), "", src)

        for port in range(1, N_PORTS + 1):
            self._registry.publish(
                f"{pfx}_port_{port}",
                1.0 if active_port == port else 0.0,
                "",
                src,
            )


# ---------------------------------------------------------------------------
# Standalone packet parser
# ---------------------------------------------------------------------------

def parse_cx1_update(packet: DCNPacket) -> dict:
    """
    Parse an UPDATE,CX1 DCNPacket into a structured dict.

    Returned keys: module_type, active_port (int or None)
    """
    args = packet.args
    result: dict = {
        "module_type": args[0] if args else None,
        "active_port": None,
    }
    if len(args) >= 2:
        try:
            result["active_port"] = int(args[1])
        except ValueError:
            pass
    return result


"""
DCN #361 Antenna Relay Control Module.

8 dry-contact SPST relays controlled over DCN.  Supports individual relay
control, bulk mask control, one-hot position selection, toggle, and pulse.

Status packet (device → master, UPDATE,ARC1):
    args[0]  ARC1            module type identifier
    args[1]  <relay_states>  8-char string, one char per relay ("0"/"1")

Control commands (master → device):
    RYx,y           Set relay x (1-8) to state y (1=ON, 0=OFF)
    RY              Turn off all 8 relays
    RY,xxxxxxxx     Set relays by mask — "1" on, "0" off, any other char = no change
    RYx,T           Toggle relay x
    RYx,P           Pulse relay x on for 500 ms (default)
    RYx,P,y         Pulse relay x on for y seconds
    POS,x           One-hot position select — turns off all relays then turns on relay x

Published sensor names (with name="ant_relay"):
    ant_relay_relay_1 … relay_8   1.0 = ON, 0.0 = OFF
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
class AntennaRelayState:
    name: str
    address: str

    relay_states: Optional[str] = None  # e.g. "01000000", index 0 = relay 1

    updated_at: float = field(default_factory=time.time)

    def relay(self, relay_num: int) -> Optional[bool]:
        """Return True/False for relay *relay_num* (1-indexed), or None if unknown."""
        if self.relay_states is None:
            return None
        if not 1 <= relay_num <= len(self.relay_states):
            return None
        return self.relay_states[relay_num - 1] == "1"

    def active_position(self) -> Optional[int]:
        """
        Return the active one-hot position (1-8) when exactly one relay is ON,
        0 when all relays are OFF, None when state is unknown or multiple are ON.
        """
        if self.relay_states is None:
            return None
        on_positions = [i + 1 for i, c in enumerate(self.relay_states) if c == "1"]
        if len(on_positions) == 0:
            return 0
        if len(on_positions) == 1:
            return on_positions[0]
        return None  # multiple relays on — not a valid one-hot position


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class AntennaRelayModule:
    """
    DCN #361 Antenna Relay Control Module.

    Attaches to a DCNNetwork, listens for UPDATE,ARC1 packets from the
    configured device address, and publishes individual relay states to a
    SensorRegistry.

    Usage::

        registry = SensorRegistry()
        arm = AntennaRelayModule(name="ant_relay", address="06", registry=registry)
        arm.attach(network)

        # Set a single relay:
        await arm.set_relay(network, 3, True)

        # One-hot position select (all off, then relay 2 on):
        await arm.select_position(network, 2)

        # Turn everything off:
        await arm.all_off(network)

        # Pulse relay 5 on for 2 seconds:
        await arm.pulse_relay(network, 5, seconds=2)
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
        self.state = AntennaRelayState(name=name, address=address)

    def attach(self, network: DCNNetwork) -> None:
        """Register the packet handler with a DCN network."""
        network.on_packet(self._handle_packet)

    # ------------------------------------------------------------------
    # Control commands
    # ------------------------------------------------------------------

    async def set_relay(self, network: DCNNetwork, relay_num: int, state: bool) -> None:
        """Set relay *relay_num* (1-8) on or off."""
        await network.send(self.address, f"RY{relay_num},{1 if state else 0}")

    async def all_off(self, network: DCNNetwork) -> None:
        """Turn off all 8 relays."""
        await network.send(self.address, "RY")

    async def set_relay_mask(self, network: DCNNetwork, mask: str) -> None:
        """
        Set relays by 8-character mask string.

        Each position maps to relay 1-8: "1" turns on, "0" turns off,
        any other character (e.g. "X") leaves that relay unchanged.
        """
        await network.send(self.address, f"RY,{mask}")

    async def toggle_relay(self, network: DCNNetwork, relay_num: int) -> None:
        """Toggle relay *relay_num* (1-8) to its opposite state."""
        await network.send(self.address, f"RY{relay_num},T")

    async def pulse_relay(
        self,
        network: DCNNetwork,
        relay_num: int,
        seconds: Optional[float] = None,
    ) -> None:
        """
        Pulse relay *relay_num* on then off.

        *seconds* sets the pulse duration; omit for the firmware default (500 ms).
        The pulse is handled entirely by the device — this method returns
        immediately after sending the command.
        """
        if seconds is None:
            await network.send(self.address, f"RY{relay_num},P")
        else:
            await network.send(self.address, f"RY{relay_num},P,{seconds:g}")

    async def select_position(self, network: DCNNetwork, position: int) -> None:
        """
        One-hot position select.

        Turns off all 8 relays then turns on relay *position* (1-8).
        Position 0 is not a valid one-hot position for this command; use
        all_off() instead.
        """
        await network.send(self.address, f"POS,{position}")

    # ------------------------------------------------------------------
    # Packet handling
    # ------------------------------------------------------------------

    async def _handle_packet(self, packet: DCNPacket, transport_name: str) -> None:
        if packet.from_addr != self.address:
            return
        if packet.command != "UPDATE":
            return
        args = packet.args
        if not args or args[0] != "ARC1":
            return
        self._parse_and_publish(args)

    def _parse_and_publish(self, args: list[str]) -> None:
        relay_states = args[1] if len(args) > 1 else None
        if relay_states is None:
            return

        self.state.relay_states = relay_states
        self.state.updated_at = time.time()

        src = f"antenna_relay:{self.name}"
        pfx = self.name

        for i, ch in enumerate(relay_states, start=1):
            self._registry.publish(f"{pfx}_relay_{i}", float(ch == "1"), "", src)


# ---------------------------------------------------------------------------
# Standalone packet parser
# ---------------------------------------------------------------------------

def parse_arc1_update(packet: DCNPacket) -> dict:
    """
    Parse an UPDATE,ARC1 DCNPacket into a structured dict.

    Returned keys: module_type, relay_states
    """
    args = packet.args
    return {
        "module_type":  args[0] if args else None,
        "relay_states": args[1] if len(args) > 1 else None,
    }

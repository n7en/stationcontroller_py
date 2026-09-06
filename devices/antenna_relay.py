"""
DCN #361 Antenna Relay Control Module.

8 dry-contact SPST relays controlled over DCN.  Supports individual relay
control, bulk mask control, one-hot position selection, toggle, and pulse.

Status packet (device -> master, UPDATE,ARC1):
    args[0]  ARC1            module type identifier
    args[1]  <relay_states>  8-char string, one char per relay ("0"/"1")

Control commands (master -> device):
    RYx,y           Set relay x (0-7) to state y (1=ON, 0=OFF)
    RY              Turn off all 8 relays
    RY,xxxxxxxx     Set relays by mask -- "1" on, "0" off, any other char = no change
    RYx,T           Toggle relay x
    RYx,P           Pulse relay x on for 500 ms (default)
    RYx,P,y         Pulse relay x on for y seconds
    POS,x           One-hot position select -- turns off all relays then turns on relay x (0-7)

Published sensor names (with name="ant"):
    ant_relay_0 ... relay_{N-1}   1.0 = ON, 0.0 = OFF  (N determined by persona)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from comms.dcn_network import DCNNetwork
from comms.dcn_packet import DCNPacket
from sensors.sensor_registry import SensorRegistry

N_RELAYS = 8  # maximum physical relays on ARC1 hardware

# ---------------------------------------------------------------------------
# Persona definitions
# ---------------------------------------------------------------------------
# Each persona describes a common wiring/application for the #361 board.
# n_relays: how many of the 8 relays are used by this application.
# mode:     "individual" = each relay toggled independently
#           "one_hot"   = exactly one relay active at a time (POS command)
#           "bcd"       = 4 relays encode a binary position (0-15)

PERSONAS: dict[str, dict] = {
    "1_of_8":            {"n_relays": 8, "mode": "one_hot",    "label": "1-of-8 Array Switching (DXE-EC-8)"},
    "dual_vertical":     {"n_relays": 2, "mode": "individual", "label": "Dual Vertical Array Control"},
    "bcd":               {"n_relays": 4, "mode": "bcd",        "label": "BCD Control Console"},
    "three_ant_phasing": {"n_relays": 3, "mode": "individual", "label": "Pro-Stack 3-Ant Phasing"},
    "two_ant_phasing":   {"n_relays": 2, "mode": "individual", "label": "Pro-Stack 2-Ant Phasing"},
    "cc_8a":             {"n_relays": 8, "mode": "individual", "label": "CC-8A Control Console"},
    "hi_z_3el":          {"n_relays": 3, "mode": "individual", "label": "Hi-Z 3-Element Array"},
    "hi_z_4el":          {"n_relays": 4, "mode": "individual", "label": "Hi-Z 4-Element Array"},
    "hi_z_4_8_pro":      {"n_relays": 8, "mode": "individual", "label": "Hi-Z 4-8 Pro Array"},
    "hi_z_8el":          {"n_relays": 8, "mode": "individual", "label": "Hi-Z 8-Element Array"},
}
DEFAULT_PERSONA = "cc_8a"


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
        return None  # multiple relays on -- not a valid one-hot position


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class AntennaRelayModule:
    """
    DCN #361 Antenna Relay Control Module.

    Attaches to a DCNNetwork, listens for UPDATE,ARC1 packets from the
    configured device address, and publishes individual relay states to a
    SensorRegistry.

    The *persona* parameter selects a wiring/application preset that sets
    n_relays (how many of the 8 physical relays are used) and mode
    ("individual", "one_hot", or "bcd").  See PERSONAS for options.

    Usage::

        registry = SensorRegistry()
        arm = AntennaRelayModule(name="ant", address="06", registry=registry,
                                 persona="1_of_8")
        arm.attach(network)

        # Set a single relay:
        await arm.set_relay(network, 3, True)

        # One-hot position select (all off, then relay 2 on):
        await arm.select_position(network, 2)
    """

    def __init__(
        self,
        name: str,
        address: str,
        registry: SensorRegistry,
        persona: Optional[str] = None,
    ) -> None:
        self.name = name
        self.address = address
        self._registry = registry

        p = PERSONAS.get(persona or "") or PERSONAS[DEFAULT_PERSONA]
        self.persona     = persona or DEFAULT_PERSONA
        self.n_relays    = p["n_relays"]
        self.mode        = p["mode"]
        self.persona_label = p["label"]

        self.state = AntennaRelayState(name=name, address=address)

        src = f"antenna_relay:{name}"
        for _i in range(self.n_relays):
            registry.publish(f"{name}_relay_{_i}", 0.0, "", src)

    def attach(self, network: DCNNetwork) -> None:
        """Register the packet handler with a DCN network."""
        network.on_packet(self._handle_packet)

    # ------------------------------------------------------------------
    # Control commands
    # ------------------------------------------------------------------

    async def set_relay(self, network: DCNNetwork, relay_num: int, state: bool) -> None:
        """Set relay *relay_num* (0-7) on or off."""
        await network.send(self.address, f"RY{relay_num},{1 if state else 0}")

    async def all_off(self, network: DCNNetwork) -> None:
        """Turn off all 8 relays."""
        await network.send(self.address, "RY")

    async def set_relay_mask(self, network: DCNNetwork, mask: str) -> None:
        """
        Set relays by 8-character mask string.

        Character position i maps to relay i (0-7): "1" turns on, "0" turns off,
        any other character (e.g. "X") leaves that relay unchanged.
        """
        await network.send(self.address, f"RY,{mask}")

    async def toggle_relay(self, network: DCNNetwork, relay_num: int) -> None:
        """Toggle relay *relay_num* (0-7) to its opposite state."""
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
        The pulse is handled entirely by the device -- this method returns
        immediately after sending the command.
        """
        if seconds is None:
            await network.send(self.address, f"RY{relay_num},P")
        else:
            await network.send(self.address, f"RY{relay_num},P,{seconds:g}")

    async def select_position(self, network: DCNNetwork, position: int) -> None:
        """
        One-hot position select.

        Turns off all 8 relays then turns on relay *position* (0-7).
        Use all_off() to clear all relays.
        """
        await network.send(self.address, f"POS,{position}")

    def optimistic_select_position(self, position: int) -> None:
        """Immediately publish one-hot position (0-based) without waiting for hardware confirmation."""
        states = "".join("1" if i == position else "0" for i in range(N_RELAYS))
        self._parse_and_publish(["ARC1", states])

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

        for i, ch in enumerate(relay_states):
            if i < self.n_relays:
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

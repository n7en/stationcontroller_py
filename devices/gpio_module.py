"""
DCN GPIO Module (#321) device module.

Subscribes to UPDATE,GPIO1 packets from the DCN network, parses all
fields, and publishes them to a SensorRegistry.

DCN packet format (UPDATE,GPIO1):
    args[0]  GPIO1            module type identifier
    args[1]  <relay_states>   8-char string, one char per relay ('0'/'1')
    args[2]  <digital_inputs> 4-char string, one char per input  ('0'/'1')
    args[3]  <voltmeter_0>    voltmeter 0 reading (V, float)
    args[4]  <voltmeter_1>    voltmeter 1 reading (V, float)
    args[5]  <voltmeter_2>    voltmeter 2 reading (V, float)
    args[6]  <voltmeter_3>    voltmeter 3 reading (V, float)
    args[7]  <temp_0_f>       temperature probe 0 (°F, float)
    args[8]  <temp_1_f>       temperature probe 1 (°F, float)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from comms.dcn_network import DCNNetwork
from comms.dcn_packet import DCNPacket
from sensors.sensor_registry import SensorRegistry

if TYPE_CHECKING:
    from sensors.label_registry import LabelRegistry


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------

@dataclass
class GPIOState:
    name: str
    address: str

    relay_states: Optional[str] = None     # e.g. "01000000"
    digital_inputs: Optional[str] = None   # e.g. "0110"
    voltmeter_1: Optional[float] = None    # volts
    voltmeter_2: Optional[float] = None
    voltmeter_3: Optional[float] = None
    voltmeter_4: Optional[float] = None
    temp_1_f: Optional[float] = None       # Fahrenheit
    temp_2_f: Optional[float] = None

    updated_at: float = field(default_factory=time.time)

    def relay(self, relay_num: int) -> Optional[bool]:
        """
        Return True/False for relay *relay_num* (1-indexed), or None if unknown.
        """
        if self.relay_states is None:
            return None
        if not 1 <= relay_num <= len(self.relay_states):
            return None
        return self.relay_states[relay_num - 1] == "1"

    def digital_input(self, input_num: int) -> Optional[bool]:
        """Return True/False for digital input *input_num* (1-indexed)."""
        if self.digital_inputs is None:
            return None
        if not 1 <= input_num <= len(self.digital_inputs):
            return None
        return self.digital_inputs[input_num - 1] == "1"


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class GPIOModule:
    """
    DCN GPIO Module (#321) device module.

    Attaches to a DCNNetwork and listens for UPDATE,GPIO1 packets from the
    configured device address.  Publishes all field values to a SensorRegistry
    under keys prefixed with the instance name.

    Published sensor names (with name="gpio"):
        gpio_relay_0 ... _7    - individual relay states (0.0 or 1.0)
        gpio_input_0 ... _3    - individual digital inputs (0.0 or 1.0)
        gpio_voltmeter_0 ... _3 - voltmeter readings in volts
        gpio_temp_0_f, _1_f   - temperature in Fahrenheit

    Usage::

        registry = SensorRegistry()
        gpio = GPIOModule(name="gpio", address="01", registry=registry)
        gpio.attach(network)

        # Later:
        print(gpio.state.relay(1))              # True/False/None
        print(registry.value("gpio_voltmeter_1"))
    """

    def __init__(
        self,
        name: str,
        address: str,
        registry: SensorRegistry,
        label_registry: "Optional[LabelRegistry]" = None,
    ) -> None:
        self.name = name
        self.address = address
        self._registry = registry
        self.state = GPIOState(name=name, address=address)
        src = f"gpio_module:{name}"
        for _i in range(8):
            registry.publish(f"{name}_relay_{_i}", 0.0, "", src)
        for _i in range(4):
            registry.publish(f"{name}_input_{_i}", 0.0, "", src)
            registry.publish(f"{name}_voltmeter_{_i}", 0.0, "V", src)
        registry.publish(f"{name}_temp_0_f", 0.0, "°F", src)
        registry.publish(f"{name}_temp_1_f", 0.0, "°F", src)

        if label_registry is not None:
            for _i in range(8):
                label_registry.set_default(f"{name}_relay_{_i}", f"Relay {_i + 1}")
            for _i in range(4):
                label_registry.set_default(f"{name}_input_{_i}", f"Input {_i + 1}")
                label_registry.set_default(f"{name}_voltmeter_{_i}", f"Voltmeter {_i + 1}")
            label_registry.set_default(f"{name}_temp_0_f", "Temperature 1")
            label_registry.set_default(f"{name}_temp_1_f", "Temperature 2")

    def attach(self, network: DCNNetwork) -> None:
        """Register the packet handler with a DCN network."""
        network.on_packet(self._handle_packet)

    async def _handle_packet(self, packet: DCNPacket, transport_name: str) -> None:
        if packet.from_addr != self.address:
            return
        if packet.command != "UPDATE":
            return
        args = packet.args
        if not args or args[0] != "GPIO1":
            return
        self._parse_and_publish(args)

    def _parse_and_publish(self, args: list[str]) -> None:
        relay_states   = args[1] if len(args) > 1 else None
        digital_inputs = args[2] if len(args) > 2 else None

        def _float(idx: int) -> Optional[float]:
            try:
                return float(args[idx]) if len(args) > idx else None
            except ValueError:
                return None

        v1 = _float(3)
        v2 = _float(4)
        v3 = _float(5)
        v4 = _float(6)
        t1 = _float(7)
        t2 = _float(8)

        self.state.relay_states   = relay_states
        self.state.digital_inputs = digital_inputs
        self.state.voltmeter_1    = v1
        self.state.voltmeter_2    = v2
        self.state.voltmeter_3    = v3
        self.state.voltmeter_4    = v4
        self.state.temp_1_f       = t1
        self.state.temp_2_f       = t2
        self.state.updated_at     = time.time()

        src = f"gpio_module:{self.name}"
        pfx = self.name

        if relay_states is not None:
            for i, ch in enumerate(relay_states):
                self._registry.publish(f"{pfx}_relay_{i}", float(ch == "1"), "", src)

        if digital_inputs is not None:
            for i, ch in enumerate(digital_inputs):
                self._registry.publish(f"{pfx}_input_{i}", float(ch == "1"), "", src)

        for key, val, unit in [
            ("voltmeter_0", v1, "V"),
            ("voltmeter_1", v2, "V"),
            ("voltmeter_2", v3, "V"),
            ("voltmeter_3", v4, "V"),
            ("temp_0_f",    t1, "°F"),
            ("temp_1_f",    t2, "°F"),
        ]:
            if val is not None:
                self._registry.publish(f"{pfx}_{key}", val, unit, src)


# ---------------------------------------------------------------------------
# Standalone packet parser (for use in tests / hardware conftest)
# ---------------------------------------------------------------------------

def parse_gpio_update(packet: DCNPacket) -> dict:
    """
    Parse an UPDATE,GPIO1 DCNPacket into a structured dict.

    Returned keys:
        module_type, relay_states, digital_inputs,
        voltmeter_1..4, temp_1_f, temp_2_f
    """
    args = packet.args

    def _float(idx: int) -> Optional[float]:
        try:
            return float(args[idx]) if len(args) > idx else None
        except ValueError:
            return None

    return {
        "module_type":    args[0] if args else None,
        "relay_states":   args[1] if len(args) > 1 else None,
        "digital_inputs": args[2] if len(args) > 2 else None,
        "voltmeter_1":    _float(3),
        "voltmeter_2":    _float(4),
        "voltmeter_3":    _float(5),
        "voltmeter_4":    _float(6),
        "temp_1_f":       _float(7),
        "temp_2_f":       _float(8),
    }

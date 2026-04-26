"""
Tests for devices/gpio_module.py.

Covers GPIOModule packet handling, registry publishing, GPIOState helpers,
and the standalone parse_gpio_update() helper.
"""
import asyncio
import pytest

from comms.dcn_packet import build_packet, DCNPacket
from devices.gpio_module import GPIOModule, GPIOState, parse_gpio_update
from sensors.sensor_registry import SensorRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gpio_packet(
    address: str,
    relay_states: str = "00000000",
    digital_inputs: str = "0000",
    voltmeters: tuple = (12.0, 13.7, 13.85, 4.95),
    temps: tuple = (72.0, 74.0),
) -> DCNPacket:
    v = ",".join(f"{v:.3f}" for v in voltmeters)
    t = ",".join(f"{t:.2f}" for t in temps)
    payload = f"UPDATE,GPIO1,{relay_states},{digital_inputs},{v},{t}"
    return build_packet(address, payload, from_addr=address)


# ---------------------------------------------------------------------------
# GPIOState helpers
# ---------------------------------------------------------------------------

class TestGPIOState:

    def test_relay_returns_true_for_1(self):
        s = GPIOState(name="gpio", address="01", relay_states="01000000")
        assert s.relay(2) is True
        assert s.relay(1) is False

    def test_relay_returns_false_for_0(self):
        s = GPIOState(name="gpio", address="01", relay_states="00000000")
        assert s.relay(1) is False

    def test_relay_returns_none_when_unknown(self):
        s = GPIOState(name="gpio", address="01")
        assert s.relay(1) is None

    def test_relay_returns_none_for_out_of_range(self):
        s = GPIOState(name="gpio", address="01", relay_states="00000000")
        assert s.relay(0) is None
        assert s.relay(9) is None

    def test_digital_input_returns_correct_value(self):
        s = GPIOState(name="gpio", address="01", digital_inputs="0110")
        assert s.digital_input(1) is False
        assert s.digital_input(2) is True
        assert s.digital_input(3) is True
        assert s.digital_input(4) is False

    def test_digital_input_returns_none_when_unknown(self):
        s = GPIOState(name="gpio", address="01")
        assert s.digital_input(1) is None

    def test_digital_input_out_of_range(self):
        s = GPIOState(name="gpio", address="01", digital_inputs="0000")
        assert s.digital_input(0) is None
        assert s.digital_input(5) is None


# ---------------------------------------------------------------------------
# Packet handling
# ---------------------------------------------------------------------------

class TestGPIOPacketHandling:

    async def test_handle_packet_updates_relay_states(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = _gpio_packet("01", relay_states="01000000")
        await gpio._handle_packet(pkt, "control")
        assert gpio.state.relay_states == "01000000"

    async def test_handle_packet_updates_digital_inputs(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = _gpio_packet("01", digital_inputs="1010")
        await gpio._handle_packet(pkt, "control")
        assert gpio.state.digital_inputs == "1010"

    async def test_handle_packet_updates_voltmeters(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = _gpio_packet("01", voltmeters=(12.5, 13.2, 13.9, 5.0))
        await gpio._handle_packet(pkt, "control")
        assert gpio.state.voltmeter_1 == pytest.approx(12.5)
        assert gpio.state.voltmeter_2 == pytest.approx(13.2)
        assert gpio.state.voltmeter_3 == pytest.approx(13.9)
        assert gpio.state.voltmeter_4 == pytest.approx(5.0)

    async def test_handle_packet_updates_temperatures(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = _gpio_packet("01", temps=(72.0, 74.0))
        await gpio._handle_packet(pkt, "control")
        assert gpio.state.temp_1_f == pytest.approx(72.0)
        assert gpio.state.temp_2_f == pytest.approx(74.0)

    async def test_handle_packet_ignores_wrong_address(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = _gpio_packet("02", relay_states="11111111")
        await gpio._handle_packet(pkt, "control")
        assert gpio.state.relay_states is None

    async def test_handle_packet_ignores_non_update_command(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = build_packet("01", "PING", from_addr="01")
        await gpio._handle_packet(pkt, "control")
        assert gpio.state.relay_states is None

    async def test_handle_packet_ignores_non_gpio1_update(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = build_packet("01", "UPDATE,WM1,00,0.00,0.00", from_addr="01")
        await gpio._handle_packet(pkt, "control")
        assert gpio.state.relay_states is None

    async def test_relay_helper_correct_after_packet(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = _gpio_packet("01", relay_states="10100000")
        await gpio._handle_packet(pkt, "control")
        assert gpio.state.relay(1) is True
        assert gpio.state.relay(2) is False
        assert gpio.state.relay(3) is True


# ---------------------------------------------------------------------------
# Registry publishing
# ---------------------------------------------------------------------------

class TestGPIORegistryPublishing:

    async def test_publishes_individual_relays(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = _gpio_packet("01", relay_states="01000000")
        await gpio._handle_packet(pkt, "control")
        assert registry.value("gpio_relay_1") == 0.0
        assert registry.value("gpio_relay_2") == 1.0
        assert registry.value("gpio_relay_3") == 0.0

    async def test_publishes_individual_inputs(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = _gpio_packet("01", digital_inputs="1010")
        await gpio._handle_packet(pkt, "control")
        assert registry.value("gpio_input_1") == 1.0
        assert registry.value("gpio_input_2") == 0.0
        assert registry.value("gpio_input_3") == 1.0
        assert registry.value("gpio_input_4") == 0.0

    async def test_publishes_voltmeters(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = _gpio_packet("01", voltmeters=(13.8, 13.7, 13.6, 5.1))
        await gpio._handle_packet(pkt, "control")
        assert registry.value("gpio_voltmeter_1") == pytest.approx(13.8)
        assert registry.value("gpio_voltmeter_4") == pytest.approx(5.1)

    async def test_publishes_temperatures(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        pkt = _gpio_packet("01", temps=(68.0, 77.5))
        await gpio._handle_packet(pkt, "control")
        assert registry.value("gpio_temp_1_f") == pytest.approx(68.0)
        assert registry.value("gpio_temp_2_f") == pytest.approx(77.5)

    async def test_name_prefix_isolates_multiple_modules(self):
        registry = SensorRegistry()
        g1 = GPIOModule("shack", "01", registry)
        g2 = GPIOModule("tower", "02", registry)
        await g1._handle_packet(_gpio_packet("01", voltmeters=(13.8, 0, 0, 0)), "control")
        await g2._handle_packet(_gpio_packet("02", voltmeters=(12.5, 0, 0, 0)), "control")
        assert registry.value("shack_voltmeter_1") == pytest.approx(13.8)
        assert registry.value("tower_voltmeter_1") == pytest.approx(12.5)

    async def test_source_is_set_correctly(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        await gpio._handle_packet(_gpio_packet("01"), "control")
        m = registry.get("gpio_voltmeter_1")
        assert m.source == "gpio_module:gpio"

    async def test_voltmeter_unit_is_volts(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        await gpio._handle_packet(_gpio_packet("01"), "control")
        assert registry.get("gpio_voltmeter_1").unit == "V"

    async def test_temperature_unit_is_fahrenheit(self):
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        await gpio._handle_packet(_gpio_packet("01"), "control")
        assert registry.get("gpio_temp_1_f").unit == "°F"


# ---------------------------------------------------------------------------
# attach() integration
# ---------------------------------------------------------------------------

class TestGPIOAttach:

    async def test_attach_registers_handler(self):
        from unittest.mock import MagicMock
        registry = SensorRegistry()
        gpio = GPIOModule("gpio", "01", registry)
        net = MagicMock()
        gpio.attach(net)
        net.on_packet.assert_called_once_with(gpio._handle_packet)


# ---------------------------------------------------------------------------
# parse_gpio_update standalone helper
# ---------------------------------------------------------------------------

class TestParseGpioUpdate:

    def test_parses_all_fields(self):
        pkt = _gpio_packet(
            "01",
            relay_states="01000000",
            digital_inputs="0110",
            voltmeters=(12.0, 13.7, 13.85, 4.95),
            temps=(72.0, 74.0),
        )
        data = parse_gpio_update(pkt)
        assert data["module_type"] == "GPIO1"
        assert data["relay_states"] == "01000000"
        assert data["digital_inputs"] == "0110"
        assert data["voltmeter_1"] == pytest.approx(12.0)
        assert data["voltmeter_2"] == pytest.approx(13.7)
        assert data["voltmeter_3"] == pytest.approx(13.85)
        assert data["voltmeter_4"] == pytest.approx(4.95)
        assert data["temp_1_f"] == pytest.approx(72.0)
        assert data["temp_2_f"] == pytest.approx(74.0)

    def test_returns_none_for_missing_fields(self):
        pkt = build_packet("01", "UPDATE,GPIO1", from_addr="01")
        data = parse_gpio_update(pkt)
        assert data["relay_states"] is None
        assert data["voltmeter_1"] is None

    def test_handles_bad_float_gracefully(self):
        pkt = build_packet(
            "01", "UPDATE,GPIO1,00000000,0000,bad,13.7,13.8,5.0,72.0,74.0",
            from_addr="01"
        )
        data = parse_gpio_update(pkt)
        assert data["voltmeter_1"] is None
        assert data["voltmeter_2"] == pytest.approx(13.7)

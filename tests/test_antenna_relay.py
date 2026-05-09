"""Tests for devices/antenna_relay.py - #361 Antenna Relay Control Module."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from comms.dcn_packet import build_packet, DCNPacket
from devices.antenna_relay import AntennaRelayModule, AntennaRelayState, parse_arc1_update
from sensors.sensor_registry import SensorRegistry


def _arc1_packet(address: str, relay_states: str) -> DCNPacket:
    return build_packet(address, f"UPDATE,ARC1,{relay_states}", from_addr=address)


# ---------------------------------------------------------------------------
# AntennaRelayState helpers
# ---------------------------------------------------------------------------

class TestAntennaRelayState:

    def test_relay_true_for_1(self):
        s = AntennaRelayState(name="ant", address="06", relay_states="01000000")
        assert s.relay(2) is True
        assert s.relay(1) is False

    def test_relay_none_when_unknown(self):
        s = AntennaRelayState(name="ant", address="06")
        assert s.relay(1) is None

    def test_relay_none_out_of_range(self):
        s = AntennaRelayState(name="ant", address="06", relay_states="00000000")
        assert s.relay(0) is None
        assert s.relay(9) is None

    def test_active_position_single_relay_on(self):
        s = AntennaRelayState(name="ant", address="06", relay_states="00100000")
        assert s.active_position() == 3

    def test_active_position_all_off(self):
        s = AntennaRelayState(name="ant", address="06", relay_states="00000000")
        assert s.active_position() == 0

    def test_active_position_multiple_on_returns_none(self):
        s = AntennaRelayState(name="ant", address="06", relay_states="11000000")
        assert s.active_position() is None

    def test_active_position_unknown(self):
        s = AntennaRelayState(name="ant", address="06")
        assert s.active_position() is None


# ---------------------------------------------------------------------------
# Packet handling
# ---------------------------------------------------------------------------

class TestAntennaRelayPacketHandling:

    async def test_updates_relay_states(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        await arm._handle_packet(_arc1_packet("06", "01000000"), "control")
        assert arm.state.relay_states == "01000000"

    async def test_ignores_wrong_address(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        await arm._handle_packet(_arc1_packet("07", "11111111"), "control")
        assert arm.state.relay_states is None

    async def test_ignores_non_update_command(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        pkt = build_packet("06", "PING", from_addr="06")
        await arm._handle_packet(pkt, "control")
        assert arm.state.relay_states is None

    async def test_ignores_non_arc1_update(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        pkt = build_packet("06", "UPDATE,GPIO1,00000000,0000", from_addr="06")
        await arm._handle_packet(pkt, "control")
        assert arm.state.relay_states is None

    async def test_ignores_missing_relay_states(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        pkt = build_packet("06", "UPDATE,ARC1", from_addr="06")
        await arm._handle_packet(pkt, "control")
        assert arm.state.relay_states is None


# ---------------------------------------------------------------------------
# Registry publishing
# ---------------------------------------------------------------------------

class TestAntennaRelayRegistryPublishing:

    async def test_publishes_individual_relays(self):
        reg = SensorRegistry()
        arm = AntennaRelayModule("ant", "06", reg)
        await arm._handle_packet(_arc1_packet("06", "01000000"), "control")
        assert reg.value("ant_relay_0") == pytest.approx(0.0)
        assert reg.value("ant_relay_1") == pytest.approx(1.0)
        assert reg.value("ant_relay_2") == pytest.approx(0.0)

    async def test_updates_on_state_change(self):
        reg = SensorRegistry()
        arm = AntennaRelayModule("ant", "06", reg)
        await arm._handle_packet(_arc1_packet("06", "01000000"), "control")
        await arm._handle_packet(_arc1_packet("06", "00100000"), "control")
        assert reg.value("ant_relay_1") == pytest.approx(0.0)
        assert reg.value("ant_relay_2") == pytest.approx(1.0)

    async def test_all_relays_published(self):
        reg = SensorRegistry()
        arm = AntennaRelayModule("ant", "06", reg)
        await arm._handle_packet(_arc1_packet("06", "10101010"), "control")
        expected = [1, 0, 1, 0, 1, 0, 1, 0]
        for i, v in enumerate(expected, start=0):
            assert reg.value(f"ant_relay_{i}") == pytest.approx(float(v))

    async def test_name_prefix_isolates_modules(self):
        reg = SensorRegistry()
        arm1 = AntennaRelayModule("east", "06", reg)
        arm2 = AntennaRelayModule("west", "07", reg)
        await arm1._handle_packet(_arc1_packet("06", "10000000"), "control")
        await arm2._handle_packet(_arc1_packet("07", "00000001"), "control")
        assert reg.value("east_relay_0") == pytest.approx(1.0)
        assert reg.value("west_relay_7") == pytest.approx(1.0)
        assert reg.value("east_relay_7") == pytest.approx(0.0)

    async def test_source_tag(self):
        reg = SensorRegistry()
        arm = AntennaRelayModule("ant", "06", reg)
        await arm._handle_packet(_arc1_packet("06", "10000000"), "control")
        assert reg.get("ant_relay_0").source == "antenna_relay:ant"


# ---------------------------------------------------------------------------
# Control commands
# ---------------------------------------------------------------------------

class TestAntennaRelayCommands:

    async def test_set_relay_on(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await arm.set_relay(net, 3, True)
        net.send.assert_called_once_with("06", "RY3,1")

    async def test_set_relay_off(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await arm.set_relay(net, 5, False)
        net.send.assert_called_once_with("06", "RY5,0")

    async def test_all_off(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await arm.all_off(net)
        net.send.assert_called_once_with("06", "RY")

    async def test_set_relay_mask(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await arm.set_relay_mask(net, "111X00XX")
        net.send.assert_called_once_with("06", "RY,111X00XX")

    async def test_toggle_relay(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await arm.toggle_relay(net, 4)
        net.send.assert_called_once_with("06", "RY4,T")

    async def test_pulse_relay_default(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await arm.pulse_relay(net, 2)
        net.send.assert_called_once_with("06", "RY2,P")

    async def test_pulse_relay_with_duration(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await arm.pulse_relay(net, 2, seconds=3)
        net.send.assert_called_once_with("06", "RY2,P,3")

    async def test_pulse_relay_fractional_seconds(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await arm.pulse_relay(net, 1, seconds=0.5)
        net.send.assert_called_once_with("06", "RY1,P,0.5")

    async def test_select_position(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await arm.select_position(net, 3)
        net.send.assert_called_once_with("06", "POS,3")

    async def test_commands_use_correct_address(self):
        arm = AntennaRelayModule("ant", "09", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await arm.select_position(net, 1)
        net.send.assert_called_once_with("09", "POS,1")


# ---------------------------------------------------------------------------
# attach()
# ---------------------------------------------------------------------------

class TestAntennaRelayAttach:

    def test_attach_registers_handler(self):
        arm = AntennaRelayModule("ant", "06", SensorRegistry())
        net = MagicMock()
        arm.attach(net)
        net.on_packet.assert_called_once_with(arm._handle_packet)


# ---------------------------------------------------------------------------
# parse_arc1_update standalone helper
# ---------------------------------------------------------------------------

class TestParseArc1Update:

    def test_parses_relay_states(self):
        data = parse_arc1_update(_arc1_packet("06", "01010101"))
        assert data["module_type"] == "ARC1"
        assert data["relay_states"] == "01010101"

    def test_returns_none_for_missing_states(self):
        pkt = build_packet("06", "UPDATE,ARC1", from_addr="06")
        data = parse_arc1_update(pkt)
        assert data["module_type"] == "ARC1"
        assert data["relay_states"] is None

    def test_returns_none_module_type_on_empty(self):
        pkt = build_packet("06", "UPDATE", from_addr="06")
        data = parse_arc1_update(pkt)
        assert data["module_type"] is None

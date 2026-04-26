"""Tests for devices/vhf_coax_relay.py — CX-2 Two Port VHF Coax Relay Module (#332)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from comms.dcn_packet import build_packet, DCNPacket
from devices.vhf_coax_relay import VHFCoaxRelay, VHFCoaxRelayState, parse_cx2_update
from sensors.sensor_registry import SensorRegistry


def _cx2_packet(address: str, state: int) -> DCNPacket:
    return build_packet(address, f"UPDATE,CX2,{state}", from_addr=address)


class TestVHFCoaxRelayState:

    def test_nc_active_when_relay_off(self):
        s = VHFCoaxRelayState(name="vhf", address="05", relay_on=False)
        assert s.nc_active is True
        assert s.no_active is False

    def test_no_active_when_relay_on(self):
        s = VHFCoaxRelayState(name="vhf", address="05", relay_on=True)
        assert s.no_active is True
        assert s.nc_active is False

    def test_both_none_when_unknown(self):
        s = VHFCoaxRelayState(name="vhf", address="05")
        assert s.nc_active is None
        assert s.no_active is None


class TestVHFCoaxRelayPacketHandling:

    async def test_updates_state_relay_on(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        await sw._handle_packet(_cx2_packet("05", 1), "control")
        assert sw.state.relay_on is True

    async def test_updates_state_relay_off(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        await sw._handle_packet(_cx2_packet("05", 0), "control")
        assert sw.state.relay_on is False

    async def test_ignores_wrong_address(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        await sw._handle_packet(_cx2_packet("06", 1), "control")
        assert sw.state.relay_on is None

    async def test_ignores_non_update_command(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        pkt = build_packet("05", "PING", from_addr="05")
        await sw._handle_packet(pkt, "control")
        assert sw.state.relay_on is None

    async def test_ignores_non_cx2_update(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        pkt = build_packet("05", "UPDATE,CX1,4,2", from_addr="05")
        await sw._handle_packet(pkt, "control")
        assert sw.state.relay_on is None

    async def test_ignores_missing_state_arg(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        pkt = build_packet("05", "UPDATE,CX2", from_addr="05")
        await sw._handle_packet(pkt, "control")
        assert sw.state.relay_on is None

    async def test_ignores_malformed_state(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        pkt = build_packet("05", "UPDATE,CX2,bad", from_addr="05")
        await sw._handle_packet(pkt, "control")
        assert sw.state.relay_on is None

    async def test_ignores_out_of_range_state(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        pkt = build_packet("05", "UPDATE,CX2,2", from_addr="05")
        await sw._handle_packet(pkt, "control")
        assert sw.state.relay_on is None


class TestVHFCoaxRelayRegistryPublishing:

    async def test_publishes_all_three_sensors_on(self):
        reg = SensorRegistry()
        sw = VHFCoaxRelay("vhf", "05", reg)
        await sw._handle_packet(_cx2_packet("05", 1), "control")
        assert reg.value("vhf_relay") == pytest.approx(1.0)
        assert reg.value("vhf_no")    == pytest.approx(1.0)
        assert reg.value("vhf_nc")    == pytest.approx(0.0)

    async def test_publishes_all_three_sensors_off(self):
        reg = SensorRegistry()
        sw = VHFCoaxRelay("vhf", "05", reg)
        await sw._handle_packet(_cx2_packet("05", 0), "control")
        assert reg.value("vhf_relay") == pytest.approx(0.0)
        assert reg.value("vhf_nc")    == pytest.approx(1.0)
        assert reg.value("vhf_no")    == pytest.approx(0.0)

    async def test_name_prefix_isolates_multiple_relays(self):
        reg = SensorRegistry()
        sw1 = VHFCoaxRelay("hf_coax",  "02", reg)
        sw2 = VHFCoaxRelay("vhf_coax", "05", reg)
        await sw1._handle_packet(_cx2_packet("02", 0), "control")
        await sw2._handle_packet(_cx2_packet("05", 1), "control")
        assert reg.value("hf_coax_relay")  == pytest.approx(0.0)
        assert reg.value("vhf_coax_relay") == pytest.approx(1.0)

    async def test_source_tag(self):
        reg = SensorRegistry()
        sw = VHFCoaxRelay("vhf", "05", reg)
        await sw._handle_packet(_cx2_packet("05", 1), "control")
        assert reg.get("vhf_relay").source == "vhf_coax_relay:vhf"


class TestVHFCoaxRelayCommands:

    async def test_set_relay_on(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await sw.set_relay(net, True)
        net.send.assert_called_once_with("05", "RY1,1")

    async def test_set_relay_off(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await sw.set_relay(net, False)
        net.send.assert_called_once_with("05", "RY1,0")

    async def test_toggle(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await sw.toggle(net)
        net.send.assert_called_once_with("05", "RY1,T")

    async def test_commands_use_correct_address(self):
        sw = VHFCoaxRelay("hf_coax", "02", SensorRegistry())
        net = MagicMock(); net.send = AsyncMock()
        await sw.set_relay(net, True)
        net.send.assert_called_once_with("02", "RY1,1")


class TestVHFCoaxRelayAttach:

    def test_attach_registers_handler(self):
        sw = VHFCoaxRelay("vhf", "05", SensorRegistry())
        net = MagicMock()
        sw.attach(net)
        net.on_packet.assert_called_once_with(sw._handle_packet)


class TestParseCx2Update:

    def test_parses_relay_on(self):
        data = parse_cx2_update(_cx2_packet("05", 1))
        assert data["module_type"] == "CX2"
        assert data["relay_on"] is True

    def test_parses_relay_off(self):
        data = parse_cx2_update(_cx2_packet("05", 0))
        assert data["relay_on"] is False

    def test_returns_none_for_missing_state(self):
        pkt = build_packet("05", "UPDATE,CX2", from_addr="05")
        data = parse_cx2_update(pkt)
        assert data["relay_on"] is None

    def test_returns_none_for_bad_state(self):
        pkt = build_packet("05", "UPDATE,CX2,bad", from_addr="05")
        data = parse_cx2_update(pkt)
        assert data["relay_on"] is None

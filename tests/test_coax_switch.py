"""Tests for devices/coax_switch.py - #331 CX-1 4 Port HF Coax Relay Module."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from comms.dcn_packet import build_packet, DCNPacket
from devices.coax_switch import CoaxSwitch, CoaxSwitchState, parse_cx1_update
from sensors.sensor_registry import SensorRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cx1_packet(address: str, active_port: int) -> DCNPacket:
    return build_packet(address, f"UPDATE,CX1,{active_port}", from_addr=address)


# ---------------------------------------------------------------------------
# CoaxSwitchState helpers
# ---------------------------------------------------------------------------

class TestCoaxSwitchState:

    def test_n_ports_always_4(self):
        s = CoaxSwitchState(name="coax", address="02")
        assert s.n_ports == 4

    def test_is_port_active_true(self):
        s = CoaxSwitchState(name="coax", address="02", active_port=2)
        assert s.is_port_active(2) is True

    def test_is_port_active_false(self):
        s = CoaxSwitchState(name="coax", address="02", active_port=2)
        assert s.is_port_active(1) is False
        assert s.is_port_active(3) is False

    def test_is_port_active_none_when_unknown(self):
        s = CoaxSwitchState(name="coax", address="02")
        assert s.is_port_active(1) is None

    def test_active_port_zero_means_first_port_selected(self):
        s = CoaxSwitchState(name="coax", address="02", active_port=0)
        assert s.is_port_active(1) is False
        assert s.is_port_active(0) is True


# ---------------------------------------------------------------------------
# Packet handling
# ---------------------------------------------------------------------------

class TestCoaxSwitchPacketHandling:

    async def test_updates_state_on_valid_packet(self):
        sw = CoaxSwitch("coax", "02", SensorRegistry())
        await sw._handle_packet(_cx1_packet("02", 2), "control")
        assert sw.state.n_ports == 4
        assert sw.state.active_port == 2

    async def test_ignores_wrong_address(self):
        sw = CoaxSwitch("coax", "02", SensorRegistry())
        await sw._handle_packet(_cx1_packet("03", 3), "control")
        assert sw.state.active_port is None

    async def test_ignores_non_update_command(self):
        sw = CoaxSwitch("coax", "02", SensorRegistry())
        pkt = build_packet("02", "PING", from_addr="02")
        await sw._handle_packet(pkt, "control")
        assert sw.state.active_port is None

    async def test_ignores_non_cx1_update(self):
        sw = CoaxSwitch("coax", "02", SensorRegistry())
        pkt = build_packet("02", "UPDATE,GPIO1,00000000,0000", from_addr="02")
        await sw._handle_packet(pkt, "control")
        assert sw.state.active_port is None

    async def test_handles_malformed_args_gracefully(self):
        sw = CoaxSwitch("coax", "02", SensorRegistry())
        pkt = build_packet("02", "UPDATE,CX1,bad", from_addr="02")
        await sw._handle_packet(pkt, "control")
        assert sw.state.active_port is None

    async def test_handles_missing_args_gracefully(self):
        sw = CoaxSwitch("coax", "02", SensorRegistry())
        pkt = build_packet("02", "UPDATE,CX1", from_addr="02")
        await sw._handle_packet(pkt, "control")
        assert sw.state.active_port is None


# ---------------------------------------------------------------------------
# Registry publishing
# ---------------------------------------------------------------------------

class TestCoaxSwitchRegistryPublishing:

    async def test_publishes_active_port(self):
        reg = SensorRegistry()
        sw = CoaxSwitch("coax", "02", reg)
        await sw._handle_packet(_cx1_packet("02", 2), "control")
        assert reg.value("coax_active_port") == pytest.approx(2.0)

    async def test_publishes_individual_port_sensors(self):
        reg = SensorRegistry()
        sw = CoaxSwitch("coax", "02", reg)
        await sw._handle_packet(_cx1_packet("02", 2), "control")
        assert reg.value("coax_port_0") == pytest.approx(0.0)
        assert reg.value("coax_port_1") == pytest.approx(0.0)
        assert reg.value("coax_port_2") == pytest.approx(1.0)
        assert reg.value("coax_port_3") == pytest.approx(0.0)

    async def test_updates_port_sensors_when_port_changes(self):
        reg = SensorRegistry()
        sw = CoaxSwitch("coax", "02", reg)
        await sw._handle_packet(_cx1_packet("02", 2), "control")
        await sw._handle_packet(_cx1_packet("02", 3), "control")
        assert reg.value("coax_port_2") == pytest.approx(0.0)
        assert reg.value("coax_port_3") == pytest.approx(1.0)

    async def test_publishes_first_port_when_port_zero_selected(self):
        reg = SensorRegistry()
        sw = CoaxSwitch("coax", "02", reg)
        await sw._handle_packet(_cx1_packet("02", 0), "control")
        assert reg.value("coax_active_port") == pytest.approx(0.0)
        assert reg.value("coax_port_0") == pytest.approx(1.0)
        for p in range(1, 4):
            assert reg.value(f"coax_port_{p}") == pytest.approx(0.0)

    async def test_all_four_ports_published(self):
        reg = SensorRegistry()
        sw = CoaxSwitch("coax", "02", reg)
        await sw._handle_packet(_cx1_packet("02", 3), "control")
        assert reg.value("coax_port_0") == pytest.approx(0.0)
        assert reg.value("coax_port_1") == pytest.approx(0.0)
        assert reg.value("coax_port_2") == pytest.approx(0.0)
        assert reg.value("coax_port_3") == pytest.approx(1.0)

    async def test_name_prefix_isolates_multiple_switches(self):
        reg = SensorRegistry()
        sw1 = CoaxSwitch("hf_ant",  "02", reg)
        sw2 = CoaxSwitch("vhf_ant", "03", reg)
        await sw1._handle_packet(_cx1_packet("02", 1), "control")
        await sw2._handle_packet(_cx1_packet("03", 2), "control")
        assert reg.value("hf_ant_active_port")  == pytest.approx(1.0)
        assert reg.value("vhf_ant_active_port") == pytest.approx(2.0)

    async def test_source_is_set_correctly(self):
        reg = SensorRegistry()
        sw = CoaxSwitch("coax", "02", reg)
        await sw._handle_packet(_cx1_packet("02", 1), "control")
        assert reg.get("coax_active_port").source == "coax_switch:coax"


# ---------------------------------------------------------------------------
# select_port command
# ---------------------------------------------------------------------------

class TestCoaxSwitchSelectPort:

    async def test_select_port_sends_cx_command(self):
        sw = CoaxSwitch("coax", "02", SensorRegistry())
        net = MagicMock()
        net.send = AsyncMock()
        await sw.select_port(net, 3)
        net.send.assert_called_once_with("02", "CX,3")

    async def test_select_port_zero_selects_first_port(self):
        sw = CoaxSwitch("coax", "02", SensorRegistry())
        net = MagicMock()
        net.send = AsyncMock()
        await sw.select_port(net, 0)
        net.send.assert_called_once_with("02", "CX,0")

    async def test_select_port_uses_correct_address(self):
        sw = CoaxSwitch("vhf_ant", "07", SensorRegistry())
        net = MagicMock()
        net.send = AsyncMock()
        await sw.select_port(net, 2)
        net.send.assert_called_once_with("07", "CX,2")


# ---------------------------------------------------------------------------
# attach()
# ---------------------------------------------------------------------------

class TestCoaxSwitchAttach:

    def test_attach_registers_handler(self):
        sw = CoaxSwitch("coax", "02", SensorRegistry())
        net = MagicMock()
        sw.attach(net)
        net.on_packet.assert_called_once_with(sw._handle_packet)


# ---------------------------------------------------------------------------
# parse_cx1_update standalone helper
# ---------------------------------------------------------------------------

class TestParseCx1Update:

    def test_parses_all_fields(self):
        data = parse_cx1_update(_cx1_packet("02", 2))
        assert data["module_type"] == "CX1"
        assert data["active_port"] == 2

    def test_parses_disconnected_state(self):
        data = parse_cx1_update(_cx1_packet("02", 0))
        assert data["active_port"] == 0

    def test_returns_none_for_missing_args(self):
        pkt = build_packet("02", "UPDATE,CX1", from_addr="02")
        data = parse_cx1_update(pkt)
        assert data["module_type"] == "CX1"
        assert data["active_port"] is None

    def test_returns_none_for_bad_int(self):
        pkt = build_packet("02", "UPDATE,CX1,bad", from_addr="02")
        data = parse_cx1_update(pkt)
        assert data["active_port"] is None

"""
Tests for devices/watt_meter.py.

Covers compute_rf_metrics(), WattMeter packet handling, registry publishing,
and the standalone parse_wm1_update() helper.
"""
import math
import asyncio
import pytest

from comms.dcn_packet import build_packet, DCNPacket
from devices.watt_meter import WattMeter, WattMeterState, compute_rf_metrics, parse_wm1_update
from sensors.sensor_registry import SensorRegistry


# ---------------------------------------------------------------------------
# compute_rf_metrics - pure function tests
# ---------------------------------------------------------------------------

class TestComputeRfMetrics:

    def test_zero_forward_power_returns_all_none(self):
        m = compute_rf_metrics(0.0, 0.0)
        assert m["swr"] is None
        assert m["reflection_coefficient"] is None
        assert m["return_loss_db"] is None
        assert m["mismatch_loss_db"] is None

    def test_negative_forward_power_returns_all_none(self):
        m = compute_rf_metrics(-1.0, 0.0)
        assert m["swr"] is None

    def test_zero_reflected_perfect_match(self):
        m = compute_rf_metrics(100.0, 0.0)
        assert m["swr"] == pytest.approx(1.0, abs=0.01)
        assert m["reflection_coefficient"] == pytest.approx(0.0, abs=0.001)
        assert m["return_loss_db"] == float("inf")

    def test_known_swr_calculation(self):
        # Gamma = 0.5 -> SWR = (1+0.5)/(1-0.5) = 3.0
        # Gamma = sqrt(Pr/Pf) = 0.5 -> Pr/Pf = 0.25
        forward_w = 100.0
        reflected_w = 25.0
        m = compute_rf_metrics(forward_w, reflected_w)
        assert m["swr"] == pytest.approx(3.0, abs=0.01)
        assert m["reflection_coefficient"] == pytest.approx(0.5, abs=0.001)

    def test_swr_increases_with_reflected_power(self):
        m1 = compute_rf_metrics(100.0, 10.0)
        m2 = compute_rf_metrics(100.0, 50.0)
        assert m2["swr"] > m1["swr"]

    def test_return_loss_decreases_with_more_reflected(self):
        m1 = compute_rf_metrics(100.0, 1.0)    # low reflected -> high return loss
        m2 = compute_rf_metrics(100.0, 50.0)   # high reflected -> low return loss
        assert m2["return_loss_db"] < m1["return_loss_db"]

    def test_return_loss_is_positive(self):
        m = compute_rf_metrics(100.0, 10.0)
        assert m["return_loss_db"] > 0.0

    def test_mismatch_loss_non_negative(self):
        m = compute_rf_metrics(100.0, 25.0)
        assert m["mismatch_loss_db"] >= 0.0

    def test_reflected_exceeds_forward_clamped(self):
        # Physically impossible but must not crash or produce negative SWR
        m = compute_rf_metrics(10.0, 20.0)
        assert m["swr"] is not None
        assert m["swr"] >= 1.0

    def test_swr_1_for_tiny_reflected(self):
        m = compute_rf_metrics(1000.0, 0.001)
        assert m["swr"] == pytest.approx(1.0, abs=0.1)

    def test_reflection_coefficient_between_0_and_1(self):
        for reflected in [0, 1, 10, 25, 50, 75, 99]:
            m = compute_rf_metrics(100.0, float(reflected))
            assert 0.0 <= m["reflection_coefficient"] <= 1.0

    def test_return_loss_formula(self):
        # RL_dB = -10 * log10(Pr/Pf)
        forward_w = 100.0
        reflected_w = 10.0
        m = compute_rf_metrics(forward_w, reflected_w)
        expected_rl = -10.0 * math.log10(reflected_w / forward_w)
        assert m["return_loss_db"] == pytest.approx(expected_rl, abs=0.001)


# ---------------------------------------------------------------------------
# WattMeter packet handling
# ---------------------------------------------------------------------------

def _wm1_packet(address: str, forward: float, reflected: float, port: str = "00") -> DCNPacket:
    """Build a synthetic UPDATE,WM1 DCNPacket."""
    payload = f"UPDATE,WM1,{port},{forward:.2f},{reflected:.2f}"
    return build_packet(address, payload, from_addr=address)


class TestWattMeterPacketHandling:

    async def test_handle_packet_updates_state(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = _wm1_packet("03", forward=100.0, reflected=10.0)
        await meter._handle_packet(pkt, "control")
        assert meter.state.forward_power_w == pytest.approx(100.0)
        assert meter.state.reflected_power_w == pytest.approx(10.0)

    async def test_handle_packet_computes_swr(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = _wm1_packet("03", forward=100.0, reflected=25.0)
        await meter._handle_packet(pkt, "control")
        assert meter.state.swr == pytest.approx(3.0, abs=0.01)

    async def test_handle_packet_ignores_wrong_address(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = _wm1_packet("04", forward=100.0, reflected=0.0)
        await meter._handle_packet(pkt, "control")
        assert meter.state.forward_power_w is None

    async def test_handle_packet_ignores_non_update_command(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = build_packet("03", "PING", from_addr="03")
        await meter._handle_packet(pkt, "control")
        assert meter.state.forward_power_w is None

    async def test_handle_packet_ignores_non_wm1_update(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = build_packet("03", "UPDATE,GPIO1,00000000,0000", from_addr="03")
        await meter._handle_packet(pkt, "control")
        assert meter.state.forward_power_w is None

    async def test_handle_packet_stores_port(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = _wm1_packet("03", forward=50.0, reflected=5.0, port="02")
        await meter._handle_packet(pkt, "control")
        assert meter.state.port == "02"

    async def test_zero_forward_sets_none_metrics(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = _wm1_packet("03", forward=0.0, reflected=0.0)
        await meter._handle_packet(pkt, "control")
        assert meter.state.swr is None
        assert meter.state.return_loss_db is None


# ---------------------------------------------------------------------------
# Registry publishing
# ---------------------------------------------------------------------------

class TestWattMeterRegistryPublishing:

    async def test_publishes_forward_power(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = _wm1_packet("03", forward=143.5, reflected=3.0)
        await meter._handle_packet(pkt, "control")
        assert registry.value("main_port_0_forward_power_w") == pytest.approx(143.5)

    async def test_publishes_reflected_power(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = _wm1_packet("03", forward=100.0, reflected=8.0)
        await meter._handle_packet(pkt, "control")
        assert registry.value("main_port_0_reflected_power_w") == pytest.approx(8.0)

    async def test_publishes_swr(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = _wm1_packet("03", forward=100.0, reflected=25.0)
        await meter._handle_packet(pkt, "control")
        assert registry.value("main_port_0_swr") == pytest.approx(3.0, abs=0.01)

    async def test_publishes_all_rf_metrics(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = _wm1_packet("03", forward=100.0, reflected=10.0)
        await meter._handle_packet(pkt, "control")
        assert registry.get("main_port_0_swr") is not None
        assert registry.get("main_port_0_reflection_coefficient") is not None
        assert registry.get("main_port_0_return_loss_db") is not None
        assert registry.get("main_port_0_mismatch_loss_db") is not None

    async def test_name_prefix_isolates_multiple_meters(self):
        registry = SensorRegistry()
        m1 = WattMeter("hf", "03", registry)
        m2 = WattMeter("vhf", "04", registry)
        await m1._handle_packet(_wm1_packet("03", 100.0, 10.0), "power")
        await m2._handle_packet(_wm1_packet("04", 50.0, 2.0), "power")
        assert registry.value("hf_port_0_forward_power_w") == pytest.approx(100.0)
        assert registry.value("vhf_port_0_forward_power_w") == pytest.approx(50.0)

    async def test_zero_forward_does_not_update_swr(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        # Pre-registration seeds swr at 0.0; a zero-forward packet must not
        # overwrite it with a real SWR value (transmitter is off).
        pre_ts = registry.get("main_port_0_swr").timestamp
        pkt = _wm1_packet("03", forward=0.0, reflected=0.0)
        await meter._handle_packet(pkt, "control")
        assert registry.get("main_port_0_swr").value == pytest.approx(0.0)
        assert registry.get("main_port_0_swr").timestamp == pre_ts

    async def test_source_is_set_correctly(self):
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)
        pkt = _wm1_packet("03", forward=100.0, reflected=5.0)
        await meter._handle_packet(pkt, "control")
        m = registry.get("main_port_0_forward_power_w")
        assert m.source == "watt_meter:main"


# ---------------------------------------------------------------------------
# attach() integration with DCNNetwork mock
# ---------------------------------------------------------------------------

class TestWattMeterAttach:

    async def test_attach_registers_handler(self):
        from unittest.mock import MagicMock
        registry = SensorRegistry()
        meter = WattMeter("main", "03", registry)

        net = MagicMock()
        meter.attach(net)
        net.on_packet.assert_called_once_with(meter._handle_packet)


# ---------------------------------------------------------------------------
# parse_wm1_update standalone helper
# ---------------------------------------------------------------------------

class TestParseWm1Update:

    def test_parses_standard_packet(self):
        pkt = _wm1_packet("03", forward=150.0, reflected=6.0)
        data = parse_wm1_update(pkt)
        assert data["module_type"] == "WM1"
        assert data["forward_power_w"] == pytest.approx(150.0)
        assert data["reflected_power_w"] == pytest.approx(6.0)

    def test_includes_rf_metrics(self):
        pkt = _wm1_packet("03", forward=100.0, reflected=25.0)
        data = parse_wm1_update(pkt)
        assert data["swr"] == pytest.approx(3.0, abs=0.01)
        assert data["reflection_coefficient"] is not None
        assert data["return_loss_db"] is not None

    def test_zero_power_returns_none_metrics(self):
        pkt = _wm1_packet("03", forward=0.0, reflected=0.0)
        data = parse_wm1_update(pkt)
        assert data["swr"] is None

    def test_parses_port_field(self):
        pkt = _wm1_packet("03", forward=50.0, reflected=2.0, port="01")
        data = parse_wm1_update(pkt)
        assert data["port"] == "01"

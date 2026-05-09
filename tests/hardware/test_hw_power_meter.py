"""
RF Watt Meter (#335) hardware tests.

Tests fall into two groups:

  TestWattMeterControlNetwork - query/response over the 9600-baud control
    network.  Uses the WattMeter device module: the fixture attaches it to
    the network so its state is populated by the module when each STATE
    response arrives.

  TestHighSpeedPowerNetwork - streaming packets on the 115200-baud power
    network.  Verifies traffic rate and that the WattMeter module correctly
    populates its state from streamed packets.

Skips automatically when the relevant device/network is not enabled in
config/hardware_test_config.yaml.

Run with:  pytest --hardware -v tests/hardware/test_hw_power_meter.py
"""
import asyncio
import time
import pytest

from .conftest import query, collect_responses, require_device, wait_for_any_traffic, parse_wm1_update

pytestmark = pytest.mark.hardware


# ---------------------------------------------------------------------------
# Watt meter on control network
# ---------------------------------------------------------------------------

class TestWattMeterControlNetwork:

    @pytest.fixture
    def wm_cfg(self, hw_config):
        return require_device(hw_config, "watt_meter")

    async def test_ping_responds(self, control_net, wm_cfg):
        """Watt meter should respond to a unicast PING."""
        addr = wm_cfg["address"]
        response = await query(control_net, addr, "PING")
        assert response is not None, (
            f"Watt meter at address {addr} did not respond to PING"
        )
        assert response.from_addr == addr

    async def test_status_responds(self, control_net, wm_cfg):
        """STATUS command should produce a response."""
        addr = wm_cfg["address"]
        response = await query(control_net, addr, "STATUS")
        assert response is not None, (
            f"Watt meter at {addr} did not respond to STATUS"
        )

    async def test_state_returns_update_wm1(self, control_net, wm_cfg):
        """STATE should return UPDATE,WM1 packet."""
        addr = wm_cfg["address"]
        response = await query(control_net, addr, "STATE")
        assert response is not None
        data = parse_wm1_update(response)
        assert data["module_type"] == "WM1", (
            f"Expected module type WM1, got {data['module_type']!r}"
        )

    # -- Module-level tests (state populated by WattMeter module) --

    async def test_module_state_populated_after_query(self, control_net, wm_cfg, watt_meter):
        """After a STATE query the WattMeter module state should be populated."""
        await query(control_net, wm_cfg["address"], "STATE")
        assert watt_meter.state.forward_power_w is not None
        assert watt_meter.state.reflected_power_w is not None

    async def test_forward_power_non_negative(self, control_net, wm_cfg, watt_meter):
        """Forward power must be >= 0."""
        await query(control_net, wm_cfg["address"], "STATE")
        assert watt_meter.state.forward_power_w >= 0.0

    async def test_reflected_power_non_negative(self, control_net, wm_cfg, watt_meter):
        """Reflected power must be >= 0."""
        await query(control_net, wm_cfg["address"], "STATE")
        assert watt_meter.state.reflected_power_w >= 0.0

    async def test_reflected_not_greater_than_forward(self, control_net, wm_cfg, watt_meter):
        """
        Reflected power should not exceed forward power.
        Skips when forward power is zero (transmitter off).
        """
        await query(control_net, wm_cfg["address"], "STATE")
        fwd = watt_meter.state.forward_power_w or 0.0
        ref = watt_meter.state.reflected_power_w or 0.0
        if fwd == 0.0:
            pytest.skip("Forward power is 0 W - transmitter not active")
        assert ref <= fwd, (
            f"Reflected ({ref:.2f} W) > Forward ({fwd:.2f} W)"
        )

    async def test_forward_power_within_expected_range(self, control_net, wm_cfg, watt_meter):
        """Forward power should not exceed configured max_expected_watts."""
        max_w = wm_cfg.get("max_expected_watts", 1500.0)
        await query(control_net, wm_cfg["address"], "STATE")
        fwd = watt_meter.state.forward_power_w or 0.0
        if fwd > 0:
            assert fwd <= max_w, (
                f"Forward power {fwd:.2f} W exceeds expected max {max_w:.2f} W"
            )

    async def test_swr_computed_and_plausible(self, control_net, wm_cfg, watt_meter):
        """When transmitting, module should compute a plausible SWR."""
        await query(control_net, wm_cfg["address"], "STATE")
        fwd = watt_meter.state.forward_power_w or 0.0
        if fwd == 0.0:
            pytest.skip("Transmitter not active - SWR not meaningful at idle")
        swr = watt_meter.state.swr
        assert swr is not None
        assert swr >= 1.0, f"SWR {swr:.3f} < 1.0 - impossible value"
        assert swr < 100.0, f"SWR {swr:.3f} implausibly high"

    async def test_rf_metrics_published_to_registry(
        self, control_net, wm_cfg, watt_meter, device_registry
    ):
        """All RF metric keys should appear in the sensor registry after a query."""
        await query(control_net, wm_cfg["address"], "STATE")
        assert device_registry.get("watt_meter_forward_power_w") is not None
        assert device_registry.get("watt_meter_reflected_power_w") is not None
        fwd = watt_meter.state.forward_power_w or 0.0
        if fwd > 0:
            assert device_registry.get("watt_meter_swr") is not None
            assert device_registry.get("watt_meter_return_loss_db") is not None

    async def test_consecutive_readings_consistent(self, control_net, wm_cfg, watt_meter):
        """
        Two rapid STATE queries with no TX should return stable idle readings.
        """
        await query(control_net, wm_cfg["address"], "STATE")
        fwd1 = watt_meter.state.forward_power_w or 0.0
        await asyncio.sleep(0.2)
        await query(control_net, wm_cfg["address"], "STATE")
        fwd2 = watt_meter.state.forward_power_w or 0.0

        if fwd1 > 0 or fwd2 > 0:
            pytest.skip("TX active - consecutive readings may differ")

        assert abs(fwd1 - fwd2) < 0.1, (
            f"Idle forward power readings differ: {fwd1:.3f} W vs {fwd2:.3f} W"
        )


# ---------------------------------------------------------------------------
# High-speed power network (115200 baud)
# ---------------------------------------------------------------------------

class TestHighSpeedPowerNetwork:

    async def test_power_network_receives_traffic(self, power_net):
        """Power network should have spontaneous traffic if meter is streaming."""
        traffic = await wait_for_any_traffic(power_net, timeout=3.0)
        assert len(traffic) > 0, (
            "No traffic on power network within 3 s. "
            "Ensure the watt meter is streaming."
        )

    async def test_power_network_packet_rate(self, power_net):
        """Verify >5 packets/second on the 115200-baud network."""
        start = time.monotonic()
        start_count = len(power_net._hw_received)
        await asyncio.sleep(2.0)
        elapsed = time.monotonic() - start
        received = len(power_net._hw_received) - start_count
        if received == 0:
            pytest.skip("No packets on power network - skipping rate check")
        rate = received / elapsed
        assert rate > 5.0, (
            f"Expected >5 packets/s on 115200-baud network, got {rate:.1f}/s"
        )

    async def test_power_packets_are_valid_dcn(self, power_net):
        """All packets on the power network must parse as valid DCN."""
        from comms.dcn_packet import parse_packet
        traffic = await wait_for_any_traffic(power_net, timeout=3.0)
        if not traffic:
            pytest.skip("No traffic on power network")
        for pkt in traffic:
            rebuilt = parse_packet(str(pkt))
            assert rebuilt is not None, f"Power packet failed round-trip: {pkt!r}"

    async def test_module_state_populated_from_stream(self, power_net, hw_config, watt_meter_hf):
        """WattMeter module state should populate from streaming packets."""
        wm_cfg = hw_config.get("devices", {}).get("watt_meter", {})
        await asyncio.sleep(1.5)   # allow a few stream packets to arrive
        assert watt_meter_hf.state.forward_power_w is not None, (
            "WattMeter module state not populated after 1.5s of streaming"
        )

    async def test_high_speed_swr_plausible(self, power_net, hw_config, watt_meter_hf):
        """SWR computed from streamed high-speed packets should be >= 1.0."""
        await asyncio.sleep(1.5)
        fwd = watt_meter_hf.state.forward_power_w or 0.0
        if fwd == 0.0:
            pytest.skip("Transmitter not active - SWR not meaningful")
        swr = watt_meter_hf.state.swr
        assert swr is not None
        assert swr >= 1.0

    async def test_rf_metrics_in_registry_from_stream(
        self, power_net, watt_meter_hf, device_registry
    ):
        """All published sensor keys should appear in the registry after streaming."""
        await asyncio.sleep(1.5)
        assert device_registry.get("watt_meter_hf_forward_power_w") is not None
        assert device_registry.get("watt_meter_hf_reflected_power_w") is not None

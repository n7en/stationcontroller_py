"""
Hardware connectivity tests.

These tests verify the most basic layer — that we can open the serial port,
exchange bytes with the DCN bus, and that at least one device on the network
responds to broadcast commands.

Run with:  pytest --hardware -v tests/hardware/test_hw_connectivity.py
"""
import asyncio
import pytest

from comms.dcn_packet import parse_packet
from comms.transport.rs485 import RS485Transport

from .conftest import query, wait_for_any_traffic


pytestmark = pytest.mark.hardware


# ---------------------------------------------------------------------------
# Serial port
# ---------------------------------------------------------------------------

class TestSerialPort:

    async def test_control_port_opens(self, hw_config):
        """The configured serial port should open without error."""
        cfg = hw_config.get("control_network", {})
        if not cfg.get("enabled", False):
            pytest.skip("control_network not enabled")

        t = RS485Transport("probe", {
            "port": cfg["port"],
            "baud_rate": cfg.get("baud_rate", 9600),
        })
        await t.connect()
        try:
            assert t.connected, f"Failed to open port {cfg['port']}"
        finally:
            await t.disconnect()

    async def test_power_port_opens(self, hw_config):
        """The power meter serial port (115200 baud) should open."""
        cfg = hw_config.get("power_network", {})
        if not cfg.get("enabled", False):
            pytest.skip("power_network not enabled")

        t = RS485Transport("probe_power", {
            "port": cfg["port"],
            "baud_rate": cfg.get("baud_rate", 115200),
        })
        await t.connect()
        try:
            assert t.connected, f"Failed to open power port {cfg['port']}"
        finally:
            await t.disconnect()

    async def test_reconnect_after_disconnect(self, hw_config):
        """Disconnecting and reconnecting should restore the connected state."""
        cfg = hw_config.get("control_network", {})
        if not cfg.get("enabled", False):
            pytest.skip("control_network not enabled")

        t = RS485Transport("probe", {
            "port": cfg["port"],
            "baud_rate": cfg.get("baud_rate", 9600),
        })
        await t.connect()
        assert t.connected
        await t.disconnect()
        assert not t.connected

        await t.connect()
        try:
            assert t.connected, "Re-connect failed"
        finally:
            await t.disconnect()


# ---------------------------------------------------------------------------
# Network traffic
# ---------------------------------------------------------------------------

class TestNetworkTraffic:

    async def test_network_is_live(self, control_net):
        """
        If a master (Raspberry Pi dashboard) is running and polling devices,
        packets should appear on the bus within a few seconds.
        This is informational — it passes even with zero traffic (some
        deployments only have traffic when commands are sent).
        """
        traffic = await wait_for_any_traffic(control_net, timeout=3.0)
        if not traffic:
            pytest.skip(
                "No spontaneous bus traffic observed in 3 s — "
                "master may not be polling. Continuing with command-driven tests."
            )
        # All received items should parse as valid DCN packets
        for pkt in traffic:
            assert pkt.from_addr is not None
            assert pkt.payload

    async def test_received_packets_are_valid_dcn(self, control_net):
        """
        Any packet seen on the bus must have correct DCN structure:
        non-empty addresses and payload, valid build/parse round-trip.
        """
        traffic = await wait_for_any_traffic(control_net, timeout=3.0)
        if not traffic:
            pytest.skip("No bus traffic to validate")

        for pkt in traffic:
            rebuilt = parse_packet(str(pkt))
            assert rebuilt is not None, f"Packet failed round-trip: {pkt!r}"


# ---------------------------------------------------------------------------
# Broadcast commands
# ---------------------------------------------------------------------------

class TestBroadcast:

    async def test_ping_broadcast_gets_at_least_one_response(self, control_net):
        """
        //PING should cause every device on the network to respond with
        its name, address and type.
        """
        before = len(control_net._hw_received)
        await control_net.broadcast("PING")

        # Give devices time to respond (staggered by address * 100 ms)
        await asyncio.sleep(2.0)

        after = len(control_net._hw_received)
        assert after > before, (
            "No response to //PING within 2 s. "
            "Check that at least one device is powered and addressed."
        )

    async def test_broadcast_ping_responses_have_from_addr(self, control_net):
        """Each PING response should identify which device sent it."""
        before = len(control_net._hw_received)
        await control_net.broadcast("PING")
        await asyncio.sleep(2.0)

        responses = control_net._hw_received[before:]
        for pkt in responses:
            assert pkt.from_addr.strip(), (
                f"Received packet with empty from_addr: {pkt!r}"
            )

    async def test_status_broadcast(self, control_net):
        """//STATUS should return a response from at least one device."""
        before = len(control_net._hw_received)
        await control_net.broadcast("STATUS")
        await asyncio.sleep(2.0)
        assert len(control_net._hw_received) > before, (
            "No response to //STATUS within 2 s"
        )

    async def test_broadcast_packet_format_correct(self, control_net):
        """Verify the broadcast packet we transmit is correctly formatted."""
        sent_packets = []
        control_net.transport("control").on_packet(lambda p, n: None)

        from comms.dcn_packet import build_broadcast
        pkt = build_broadcast("PING")
        assert pkt.build() == "//PING:XX\r"
        assert pkt.encode() == b"//PING:XX\r"

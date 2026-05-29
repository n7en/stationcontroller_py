"""
Tests for comms/dcn_network.py - transport orchestration, routing, config loading.
Uses a MockTransport that records sent packets and can inject received ones.
"""
import asyncio
import pytest

from comms.dcn_network import DCNNetwork
from comms.transport.base import DCNTransport
from comms.dcn_packet import DCNPacket, build_packet, build_broadcast


# ---------------------------------------------------------------------------
# Test double
# ---------------------------------------------------------------------------

class MockTransport(DCNTransport):
    """Records sends; exposes inject() to simulate incoming packets."""

    def __init__(self, name: str, config: dict | None = None) -> None:
        super().__init__(name, config or {})
        self.sent: list[DCNPacket] = []
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.connect_raises: Exception | None = None

    async def connect(self) -> None:
        if self.connect_raises:
            raise self.connect_raises
        self._connected = True
        self.connect_calls += 1

    async def disconnect(self) -> None:
        self._connected = False
        self.disconnect_calls += 1

    async def send(self, packet: DCNPacket) -> None:
        self.sent.append(packet)

    async def inject(self, packet: DCNPacket) -> None:
        """Simulate a packet arriving on this transport."""
        await self._dispatch(packet)


# ---------------------------------------------------------------------------
# Transport registration
# ---------------------------------------------------------------------------

class TestTransportManagement:

    def test_add_transport(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)
        assert "ctrl" in net.transports

    def test_transport_getter_returns_instance(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)
        assert net.transport("ctrl") is t

    def test_transport_getter_returns_none_for_missing(self):
        net = DCNNetwork()
        assert net.transport("missing") is None

    def test_transports_property_returns_copy(self):
        net = DCNNetwork()
        net.add_transport(MockTransport("ctrl"))
        snapshot = net.transports
        net.add_transport(MockTransport("power"))
        assert "power" not in snapshot  # copy was not mutated

    def test_add_duplicate_name_raises(self):
        net = DCNNetwork()
        net.add_transport(MockTransport("ctrl"))
        with pytest.raises(ValueError, match="ctrl"):
            net.add_transport(MockTransport("ctrl"))


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:

    async def test_connect_all_calls_each_transport(self):
        net = DCNNetwork()
        t1, t2 = MockTransport("t1"), MockTransport("t2")
        net.add_transport(t1)
        net.add_transport(t2)
        await net.connect_all()
        assert t1.connect_calls == 1
        assert t2.connect_calls == 1

    async def test_disconnect_all_calls_each_transport(self):
        net = DCNNetwork()
        t1, t2 = MockTransport("t1"), MockTransport("t2")
        net.add_transport(t1)
        net.add_transport(t2)
        await net.connect_all()
        await net.disconnect_all()
        assert t1.disconnect_calls == 1
        assert t2.disconnect_calls == 1

    async def test_connect_all_continues_if_one_fails(self):
        net = DCNNetwork()
        t1 = MockTransport("t1")
        t1.connect_raises = OSError("port unavailable")
        t2 = MockTransport("t2")
        net.add_transport(t1)
        net.add_transport(t2)

        await net.connect_all()  # should not raise

        assert not t1.connected
        assert t2.connected

    async def test_async_context_manager(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)

        async with net:
            assert t.connected

        assert not t.connected


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

class TestSend:

    async def test_send_unicast_to_all_connected_transports(self):
        net = DCNNetwork()
        t1, t2 = MockTransport("t1"), MockTransport("t2")
        net.add_transport(t1)
        net.add_transport(t2)
        await net.connect_all()

        await net.send("01", "STATE")

        assert len(t1.sent) == 1
        assert len(t2.sent) == 1

    async def test_send_unicast_correct_addresses(self):
        net = DCNNetwork(master_addr="00")
        t = MockTransport("ctrl")
        net.add_transport(t)
        await t.connect()

        await net.send("01", "RY3,1")

        assert t.sent[0].from_addr == "00"
        assert t.sent[0].to_addr == "01"
        assert t.sent[0].payload == "RY3,1"

    async def test_send_custom_from_addr(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)
        await t.connect()

        await net.send("02", "STATE", from_addr="05")

        assert t.sent[0].from_addr == "05"

    async def test_send_to_specific_transport(self):
        net = DCNNetwork()
        t1, t2 = MockTransport("t1"), MockTransport("t2")
        net.add_transport(t1)
        net.add_transport(t2)
        await net.connect_all()

        await net.send("01", "STATE", transport_name="t1")

        assert len(t1.sent) == 1
        assert len(t2.sent) == 0

    async def test_send_skips_disconnected_transports(self):
        net = DCNNetwork()
        t1, t2 = MockTransport("t1"), MockTransport("t2")
        net.add_transport(t1)
        net.add_transport(t2)
        await t1.connect()  # only t1 connected

        await net.send("01", "STATE")

        assert len(t1.sent) == 1
        assert len(t2.sent) == 0

    async def test_send_no_connected_transports_does_not_raise(self):
        net = DCNNetwork()
        net.add_transport(MockTransport("ctrl"))
        await net.send("01", "STATE")  # disconnected - should warn and return

    async def test_broadcast_sends_broadcast_packet(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)
        await t.connect()

        await net.broadcast("PING")

        assert len(t.sent) == 1
        assert t.sent[0].broadcast
        assert t.sent[0].payload == "PING"

    async def test_send_packet_sends_prebuilt(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)
        await t.connect()

        pkt = build_packet("03", "STATE")
        await net.send_packet(pkt)

        assert t.sent[0] is pkt


# ---------------------------------------------------------------------------
# Receiving / handler routing
# ---------------------------------------------------------------------------

class TestReceive:

    async def test_on_packet_handler_called_with_packet_and_name(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)

        received = []

        @net.on_packet
        async def handler(p, n):
            received.append((p, n))

        pkt = build_packet("01", "STATE")
        await t.inject(pkt)

        assert len(received) == 1
        assert received[0][0] is pkt
        assert received[0][1] == "ctrl"

    async def test_on_packet_direct_call_registers_handler(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)

        received = []
        net.on_packet(lambda p, n: received.append(p))

        await t.inject(build_packet("01", "STATE"))

        assert len(received) == 1

    async def test_multiple_handlers_all_invoked(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)
        order = []

        net.on_packet(lambda p, n: order.append(1))
        net.on_packet(lambda p, n: order.append(2))
        net.on_packet(lambda p, n: order.append(3))

        await t.inject(build_packet("01", "STATE"))

        assert order == [1, 2, 3]

    async def test_handler_exception_does_not_stop_others(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)
        calls = []

        def bad_handler(p, n):
            raise ValueError("handler failure")

        net.on_packet(bad_handler)
        net.on_packet(lambda p, n: calls.append(1))

        await t.inject(build_packet("01", "STATE"))

        assert calls == [1]

    async def test_packets_from_multiple_transports_routed(self):
        net = DCNNetwork()
        t1 = MockTransport("t1")
        t2 = MockTransport("t2")
        net.add_transport(t1)
        net.add_transport(t2)

        origins = []
        net.on_packet(lambda p, n: origins.append(n))

        await t1.inject(build_packet("01", "STATE"))
        await t2.inject(build_packet("02", "STATE"))

        assert origins == ["t1", "t2"]

    async def test_async_handler_awaited(self):
        net = DCNNetwork()
        t = MockTransport("ctrl")
        net.add_transport(t)

        received = []

        async def async_handler(p, n):
            await asyncio.sleep(0)
            received.append(p)

        net.on_packet(async_handler)
        await t.inject(build_packet("01", "STATE"))

        assert len(received) == 1


# ---------------------------------------------------------------------------
# from_config factory
# ---------------------------------------------------------------------------

class TestFromConfig:

    def test_creates_rs485_transport(self, tmp_path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text(
            "networks:\n"
            "  - name: control\n"
            "    type: rs485\n"
            "    port: /dev/ttyUSB0\n"
            "    baud_rate: 9600\n"
        )
        net = DCNNetwork.from_config(str(cfg))
        from comms.transport.rs485 import RS485Transport
        assert isinstance(net.transport("control"), RS485Transport)

    def test_creates_nodered_mqtt_transport(self, tmp_path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text(
            "networks:\n"
            "  - name: nr\n"
            "    type: nodered_mqtt\n"
            "    broker: localhost\n"
            "    port: 1883\n"
        )
        net = DCNNetwork.from_config(str(cfg))
        from comms.transport.nodered_mqtt import NodeRedMQTTTransport
        assert isinstance(net.transport("nr"), NodeRedMQTTTransport)

    def test_creates_nodered_tcp_transport(self, tmp_path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text(
            "networks:\n"
            "  - name: tcp\n"
            "    type: nodered_tcp\n"
            "    host: 0.0.0.0\n"
            "    port: 4880\n"
        )
        net = DCNNetwork.from_config(str(cfg))
        from comms.transport.nodered_tcp import NodeRedTCPTransport
        assert isinstance(net.transport("tcp"), NodeRedTCPTransport)

    def test_multiple_networks_all_created(self, tmp_path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text(
            "networks:\n"
            "  - name: control\n"
            "    type: rs485\n"
            "    port: COM3\n"
            "    baud_rate: 9600\n"
            "  - name: power\n"
            "    type: rs485\n"
            "    port: COM4\n"
            "    baud_rate: 115200\n"
        )
        net = DCNNetwork.from_config(str(cfg))
        assert "control" in net.transports
        assert "power" in net.transports
        assert net.transport("power").baud_rate == 115200

    def test_unknown_transport_type_skipped(self, tmp_path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text(
            "networks:\n"
            "  - name: future\n"
            "    type: zigbee\n"
        )
        net = DCNNetwork.from_config(str(cfg))
        assert "future" not in net.transports
        assert len(net.transports) == 0

    def test_empty_networks_list(self, tmp_path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text("networks: []\n")
        net = DCNNetwork.from_config(str(cfg))
        assert len(net.transports) == 0

    def test_master_addr_passed_through(self, tmp_path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text("networks: []\n")
        net = DCNNetwork.from_config(str(cfg), master_addr="05")
        assert net.master_addr == "05"

    def test_mixed_valid_and_unknown_types(self, tmp_path):
        cfg = tmp_path / "c.yaml"
        cfg.write_text(
            "networks:\n"
            "  - name: good\n"
            "    type: rs485\n"
            "    port: COM1\n"
            "  - name: bad\n"
            "    type: unknown_type\n"
        )
        net = DCNNetwork.from_config(str(cfg))
        assert "good" in net.transports
        assert "bad" not in net.transports


# ---------------------------------------------------------------------------
# buses_from_config factory
# ---------------------------------------------------------------------------

class TestBusesFromConfig:

    def _yaml(self, text: str, tmp_path) -> str:
        p = tmp_path / "c.yaml"
        p.write_text(text)
        return str(p)

    def test_returns_dict_keyed_by_bus_name(self, tmp_path):
        path = self._yaml(
            "buses:\n"
            "  - name: control\n"
            "    transports:\n"
            "      - name: ctrl_serial\n"
            "        type: rs485\n"
            "        port: /dev/ttyUSB0\n"
            "  - name: power\n"
            "    transports:\n"
            "      - name: pwr_serial\n"
            "        type: rs485\n"
            "        port: /dev/ttyUSB1\n"
            "        baud_rate: 115200\n",
            tmp_path,
        )
        buses = DCNNetwork.buses_from_config(path)
        assert set(buses.keys()) == {"control", "power"}
        assert isinstance(buses["control"], DCNNetwork)
        assert isinstance(buses["power"], DCNNetwork)

    def test_each_bus_has_own_transports(self, tmp_path):
        path = self._yaml(
            "buses:\n"
            "  - name: control\n"
            "    transports:\n"
            "      - name: ctrl_serial\n"
            "        type: rs485\n"
            "        port: COM3\n"
            "  - name: power\n"
            "    transports:\n"
            "      - name: pwr_serial\n"
            "        type: rs485\n"
            "        port: COM4\n"
            "        baud_rate: 115200\n",
            tmp_path,
        )
        buses = DCNNetwork.buses_from_config(path)
        assert "ctrl_serial" in buses["control"].transports
        assert "pwr_serial" in buses["power"].transports
        assert "ctrl_serial" not in buses["power"].transports

    def test_baud_rate_preserved_per_bus(self, tmp_path):
        path = self._yaml(
            "buses:\n"
            "  - name: power\n"
            "    transports:\n"
            "      - name: pwr\n"
            "        type: rs485\n"
            "        port: COM4\n"
            "        baud_rate: 115200\n",
            tmp_path,
        )
        buses = DCNNetwork.buses_from_config(path)
        assert buses["power"].transport("pwr").baud_rate == 115200

    def test_multiple_transports_on_one_bus(self, tmp_path):
        path = self._yaml(
            "buses:\n"
            "  - name: control\n"
            "    transports:\n"
            "      - name: ctrl_serial\n"
            "        type: rs485\n"
            "        port: COM3\n"
            "      - name: ctrl_tcp\n"
            "        type: nodered_tcp\n"
            "        port: 4880\n",
            tmp_path,
        )
        buses = DCNNetwork.buses_from_config(path)
        assert len(buses) == 1
        assert "ctrl_serial" in buses["control"].transports
        assert "ctrl_tcp" in buses["control"].transports

    def test_unknown_transport_type_skipped(self, tmp_path):
        path = self._yaml(
            "buses:\n"
            "  - name: control\n"
            "    transports:\n"
            "      - name: good\n"
            "        type: rs485\n"
            "        port: COM3\n"
            "      - name: bad\n"
            "        type: zigbee\n",
            tmp_path,
        )
        buses = DCNNetwork.buses_from_config(path)
        assert "good" in buses["control"].transports
        assert "bad" not in buses["control"].transports

    def test_empty_buses_list(self, tmp_path):
        path = self._yaml("buses: []\n", tmp_path)
        buses = DCNNetwork.buses_from_config(path)
        assert buses == {}

    def test_no_buses_key_returns_empty(self, tmp_path):
        path = self._yaml("networks: []\n", tmp_path)
        buses = DCNNetwork.buses_from_config(path)
        assert buses == {}

    def test_master_addr_applied_to_all_buses(self, tmp_path):
        path = self._yaml(
            "buses:\n"
            "  - name: a\n"
            "    transports: []\n"
            "  - name: b\n"
            "    transports: []\n",
            tmp_path,
        )
        buses = DCNNetwork.buses_from_config(path, master_addr="07")
        assert buses["a"].master_addr == "07"
        assert buses["b"].master_addr == "07"

    def test_buses_are_independent_networks(self, tmp_path):
        path = self._yaml(
            "buses:\n"
            "  - name: a\n"
            "    transports: []\n"
            "  - name: b\n"
            "    transports: []\n",
            tmp_path,
        )
        buses = DCNNetwork.buses_from_config(path)
        assert buses["a"] is not buses["b"]

    def test_same_device_address_on_two_buses(self, tmp_path):
        """Two watt meters at address 03 on separate buses - valid config."""
        path = self._yaml(
            "buses:\n"
            "  - name: power1\n"
            "    transports:\n"
            "      - name: p1\n"
            "        type: rs485\n"
            "        port: COM4\n"
            "  - name: power2\n"
            "    transports:\n"
            "      - name: p2\n"
            "        type: rs485\n"
            "        port: COM5\n",
            tmp_path,
        )
        buses = DCNNetwork.buses_from_config(path)
        assert "power1" in buses
        assert "power2" in buses

"""
Tests for comms/transport/nodered_tcp.py.
Uses real asyncio TCP on 127.0.0.1 with OS-assigned ports (port=0).
No external processes or hardware required.
"""
import asyncio
import pytest

from comms.transport.nodered_tcp import NodeRedTCPTransport
from comms.dcn_packet import build_packet, parse_packet


def _make():
    # port=0 → OS picks a free port
    return NodeRedTCPTransport("test", {"host": "127.0.0.1", "port": 0})


def _port(transport: NodeRedTCPTransport) -> int:
    return transport._server.sockets[0].getsockname()[1]


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:

    async def test_connect_starts_server(self):
        t = _make()
        await t.connect()
        try:
            assert t.connected
            assert t._server is not None
            assert len(t._server.sockets) > 0
        finally:
            await t.disconnect()

    async def test_disconnect_stops_server(self):
        t = _make()
        await t.connect()
        await t.disconnect()
        assert not t.connected

    async def test_send_without_client_does_not_raise(self):
        t = _make()
        await t.connect()
        try:
            await t.send(build_packet("01", "STATE"))  # no client — should warn only
        finally:
            await t.disconnect()


# ---------------------------------------------------------------------------
# Receiving packets from a connected client
# ---------------------------------------------------------------------------

class TestReceive:

    async def test_single_packet_dispatched(self):
        t = _make()
        await t.connect()
        port = _port(t)
        received = []
        t.on_packet(lambda p, n: received.append(p))

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"/0001:STATE:XX\r")
            await writer.drain()
            await asyncio.sleep(0.1)

            assert len(received) == 1
            assert received[0].payload == "STATE"
            assert received[0].from_addr == "00"
            assert received[0].to_addr == "01"
        finally:
            writer.close()
            await writer.wait_closed()
            await t.disconnect()

    async def test_multiple_packets_in_one_write(self):
        t = _make()
        await t.connect()
        port = _port(t)
        received = []
        t.on_packet(lambda p, n: received.append(p))

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"/0001:RY1,1:XX\r/0001:RY2,0:XX\r")
            await writer.drain()
            await asyncio.sleep(0.1)

            assert len(received) == 2
            assert received[0].command == "RY1"
            assert received[1].command == "RY2"
        finally:
            writer.close()
            await writer.wait_closed()
            await t.disconnect()

    async def test_broadcast_packet_dispatched(self):
        t = _make()
        await t.connect()
        port = _port(t)
        received = []
        t.on_packet(lambda p, n: received.append(p))

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"//ROLLCALL:XX\r")
            await writer.drain()
            await asyncio.sleep(0.1)

            assert len(received) == 1
            assert received[0].broadcast
        finally:
            writer.close()
            await writer.wait_closed()
            await t.disconnect()

    async def test_non_dcn_data_ignored(self):
        t = _make()
        await t.connect()
        port = _port(t)
        received = []
        t.on_packet(lambda p, n: received.append(p))

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"random garbage line\r")
            await writer.drain()
            await asyncio.sleep(0.1)

            assert len(received) == 0
        finally:
            writer.close()
            await writer.wait_closed()
            await t.disconnect()

    async def test_mixed_garbage_and_valid_packet(self):
        t = _make()
        await t.connect()
        port = _port(t)
        received = []
        t.on_packet(lambda p, n: received.append(p))

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"noise\r/0001:STATE:XX\r")
            await writer.drain()
            await asyncio.sleep(0.1)

            assert len(received) == 1
            assert received[0].payload == "STATE"
        finally:
            writer.close()
            await writer.wait_closed()
            await t.disconnect()

    async def test_transport_name_passed_to_handler(self):
        t = NodeRedTCPTransport("myname", {"host": "127.0.0.1", "port": 0})
        await t.connect()
        port = _port(t)
        names = []
        t.on_packet(lambda p, n: names.append(n))

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"/0001:STATE:XX\r")
            await writer.drain()
            await asyncio.sleep(0.1)

            assert names == ["myname"]
        finally:
            writer.close()
            await writer.wait_closed()
            await t.disconnect()


# ---------------------------------------------------------------------------
# Sending packets to a connected client
# ---------------------------------------------------------------------------

class TestSend:

    async def test_python_sends_packet_received_by_client(self):
        t = _make()
        await t.connect()
        port = _port(t)

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await asyncio.sleep(0.05)  # let server register connection

            # Drain the initial CR ping sent on connect
            ping = await asyncio.wait_for(reader.read(1), timeout=1.0)
            assert ping == b"\r"

            pkt = build_packet("01", "RY1,1")
            await t.send(pkt)

            data = await asyncio.wait_for(reader.read(128), timeout=1.0)
            assert data == pkt.encode()
        finally:
            writer.close()
            await writer.wait_closed()
            await t.disconnect()

    async def test_send_broadcast_received_by_client(self):
        from comms.dcn_packet import build_broadcast
        t = _make()
        await t.connect()
        port = _port(t)

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await asyncio.sleep(0.05)

            # Drain the initial CR ping sent on connect
            ping = await asyncio.wait_for(reader.read(1), timeout=1.0)
            assert ping == b"\r"

            pkt = build_broadcast("PING")
            await t.send(pkt)

            data = await asyncio.wait_for(reader.read(128), timeout=1.0)
            assert data == pkt.encode()
        finally:
            writer.close()
            await writer.wait_closed()
            await t.disconnect()


# ---------------------------------------------------------------------------
# Client connection management
# ---------------------------------------------------------------------------

class TestClientManagement:

    async def test_writer_set_on_client_connect(self):
        t = _make()
        await t.connect()
        port = _port(t)

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await asyncio.sleep(0.05)
            assert t._writer is not None
        finally:
            writer.close()
            await writer.wait_closed()
            await t.disconnect()

    async def test_writer_cleared_on_client_disconnect(self):
        t = _make()
        await t.connect()
        port = _port(t)

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.sleep(0.05)
        assert t._writer is not None

        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.1)  # let handler detect EOF

        assert t._writer is None
        await t.disconnect()

    async def test_second_client_replaces_first(self):
        t = _make()
        await t.connect()
        port = _port(t)

        try:
            r1, w1 = await asyncio.open_connection("127.0.0.1", port)
            await asyncio.sleep(0.05)
            writer_1 = t._writer

            r2, w2 = await asyncio.open_connection("127.0.0.1", port)
            await asyncio.sleep(0.05)
            writer_2 = t._writer

            assert writer_2 is not writer_1
        finally:
            w1.close()
            w2.close()
            await t.disconnect()

"""Tests for telemetry/dcn_logger.py and DcnMessageLog in the store."""
import asyncio
import time
import pytest

from comms.dcn_network import DCNNetwork
from comms.dcn_packet import DCNPacket, build_packet, build_broadcast, parse_packet
from telemetry.store import TelemetryStore
from telemetry.dcn_logger import DCNMessageLogger
from telemetry.models import DcnMessageLog
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def store():
    async with TelemetryStore("sqlite+aiosqlite:///:memory:") as s:
        yield s


@pytest.fixture
def network():
    return DCNNetwork()


# ---------------------------------------------------------------------------
# TelemetryStore.record_dcn_message
# ---------------------------------------------------------------------------

class TestRecordDcnMessage:

    async def test_record_rx(self, store):
        await store.record_dcn_message(
            direction="rx",
            payload="STATUS,OK",
            from_addr="01",
            to_addr="00",
            transport="rs485_control",
            raw="/0100:STATUS,OK:XX",
        )
        async with store._session() as s:
            rows = list((await s.execute(select(DcnMessageLog))).scalars())
        assert len(rows) == 1
        assert rows[0].direction == "rx"
        assert rows[0].from_addr == "01"
        assert rows[0].payload == "STATUS,OK"
        assert rows[0].transport == "rs485_control"
        assert rows[0].broadcast is False

    async def test_record_tx(self, store):
        await store.record_dcn_message(
            direction="tx",
            payload="RY1,1",
            from_addr="00",
            to_addr="01",
            transport="rs485_control",
        )
        async with store._session() as s:
            rows = list((await s.execute(select(DcnMessageLog))).scalars())
        assert rows[0].direction == "tx"
        assert rows[0].to_addr == "01"

    async def test_record_broadcast(self, store):
        await store.record_dcn_message(
            direction="tx",
            payload="PING",
            broadcast=True,
            transport="rs485_control",
        )
        async with store._session() as s:
            rows = list((await s.execute(select(DcnMessageLog))).scalars())
        assert rows[0].broadcast is True
        assert rows[0].from_addr == ""
        assert rows[0].to_addr == ""


# ---------------------------------------------------------------------------
# TelemetryStore.prune — dcn_message_log
# ---------------------------------------------------------------------------

class TestPruneDcnMessageLog:

    async def test_prune_removes_old_messages(self, store):
        old_ts = time.time() - 25 * 3600   # 25 hours ago
        await store.record_dcn_message("rx", "STATUS,OK", ts=old_ts)
        await store.record_dcn_message("rx", "STATUS,OK")   # recent
        await store.prune(dcn_message_log_hours=24)
        async with store._session() as s:
            rows = list((await s.execute(select(DcnMessageLog))).scalars())
        assert len(rows) == 1

    async def test_prune_keeps_recent_messages(self, store):
        await store.record_dcn_message("rx", "STATUS,OK")
        await store.record_dcn_message("tx", "RY1,1")
        await store.prune(dcn_message_log_hours=24)
        async with store._session() as s:
            rows = list((await s.execute(select(DcnMessageLog))).scalars())
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# DCNMessageLogger — RX hook
# ---------------------------------------------------------------------------

class TestDCNMessageLoggerRx:

    async def test_logs_received_packet(self, store, network):
        logger = DCNMessageLogger(store)
        logger.attach(network)

        packet = parse_packet("/0100:STATUS,OK:XX")
        await network._route_packet(packet, "rs485_control")
        await asyncio.sleep(0)

        async with store._session() as s:
            rows = list((await s.execute(select(DcnMessageLog))).scalars())
        assert len(rows) == 1
        assert rows[0].direction == "rx"
        assert rows[0].from_addr == "01"
        assert rows[0].payload == "STATUS,OK"
        assert rows[0].transport == "rs485_control"

    async def test_logs_broadcast_received(self, store, network):
        logger = DCNMessageLogger(store)
        logger.attach(network)

        packet = parse_packet("//PING:XX")
        await network._route_packet(packet, "rs485_control")
        await asyncio.sleep(0)

        async with store._session() as s:
            rows = list((await s.execute(select(DcnMessageLog))).scalars())
        assert rows[0].broadcast is True
        assert rows[0].payload == "PING"


# ---------------------------------------------------------------------------
# DCNNetwork.on_transmit — hook fires on send
# ---------------------------------------------------------------------------

class TestOnTransmitHook:

    async def test_tx_handler_called_on_send(self, network):
        captured = []

        @network.on_transmit
        def handler(packet, transport_name):
            captured.append((packet, transport_name))

        # Simulate a connected transport
        from unittest.mock import AsyncMock, MagicMock
        t = MagicMock()
        t.name = "rs485_control"
        t.connected = True
        t.send = AsyncMock()
        network._transports["rs485_control"] = t

        await network.send("01", "RY1,1")
        assert len(captured) == 1
        assert captured[0][0].payload == "RY1,1"
        assert captured[0][1] == "rs485_control"

    async def test_tx_handler_called_on_broadcast(self, network):
        captured = []
        network.on_transmit(lambda pkt, tn: captured.append(pkt))

        from unittest.mock import AsyncMock, MagicMock
        t = MagicMock()
        t.name = "rs485_control"
        t.connected = True
        t.send = AsyncMock()
        network._transports["rs485_control"] = t

        await network.broadcast("PING")
        assert len(captured) == 1
        assert captured[0].broadcast is True

    async def test_tx_handler_exception_does_not_prevent_send(self, network):
        def bad_handler(pkt, tn):
            raise RuntimeError("boom")

        network.on_transmit(bad_handler)

        from unittest.mock import AsyncMock, MagicMock
        t = MagicMock()
        t.name = "rs485_control"
        t.connected = True
        t.send = AsyncMock()
        network._transports["rs485_control"] = t

        await network.send("01", "RY1,1")   # must not raise
        t.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# DCNMessageLogger — TX via full network path
# ---------------------------------------------------------------------------

class TestDCNMessageLoggerTx:

    async def test_logs_transmitted_packet(self, store, network):
        logger = DCNMessageLogger(store)
        logger.attach(network)

        from unittest.mock import AsyncMock, MagicMock
        t = MagicMock()
        t.name = "rs485_control"
        t.connected = True
        t.send = AsyncMock()
        network._transports["rs485_control"] = t

        await network.send("01", "RY1,1")
        await asyncio.sleep(0)

        async with store._session() as s:
            rows = list((await s.execute(select(DcnMessageLog))).scalars())
        assert len(rows) == 1
        assert rows[0].direction == "tx"
        assert rows[0].to_addr == "01"
        assert rows[0].payload == "RY1,1"
        assert rows[0].transport == "rs485_control"

    async def test_raw_field_populated_for_tx(self, store, network):
        logger = DCNMessageLogger(store)
        logger.attach(network)

        from unittest.mock import AsyncMock, MagicMock
        t = MagicMock()
        t.name = "rs485_control"
        t.connected = True
        t.send = AsyncMock()
        network._transports["rs485_control"] = t

        await network.send("01", "RY1,1")
        await asyncio.sleep(0)

        async with store._session() as s:
            rows = list((await s.execute(select(DcnMessageLog))).scalars())
        assert rows[0].raw == "/0001:RY1,1:XX"

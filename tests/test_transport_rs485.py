"""
Tests for comms/transport/rs485.py.
Serial port is mocked; threading is verified via asyncio event scheduling.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch, call

import serial

from comms.transport.rs485 import RS485Transport
from comms.dcn_packet import build_packet


def _make(port="COM1", baud=9600, **extra):
    cfg = {"port": port, "baud_rate": baud}
    cfg.update(extra)
    return RS485Transport("test", cfg)


def _mock_serial(is_open=True):
    """Return a patched serial.Serial and the mock instance."""
    patcher = patch("comms.transport.rs485.serial.Serial")
    mock_cls = patcher.start()
    mock_port = MagicMock()
    mock_port.is_open = is_open
    mock_port.in_waiting = 0
    mock_cls.return_value = mock_port
    return patcher, mock_cls, mock_port


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------

class TestConnectDisconnect:

    async def test_connect_opens_correct_port(self):
        patcher, mock_cls, mock_port = _mock_serial()
        try:
            t = _make(port="/dev/ttyUSB0", baud=9600)
            await t.connect()
            kw = mock_cls.call_args.kwargs
            assert kw["port"] == "/dev/ttyUSB0"
            assert kw["baudrate"] == 9600
            assert kw["bytesize"] == serial.EIGHTBITS
            assert kw["parity"] == serial.PARITY_NONE
            assert kw["stopbits"] == serial.STOPBITS_ONE
            assert t.connected
        finally:
            await t.disconnect()
            patcher.stop()

    async def test_connect_115200_baud(self):
        patcher, mock_cls, mock_port = _mock_serial()
        try:
            t = _make(port="/dev/ttyUSB1", baud=115200)
            await t.connect()
            assert mock_cls.call_args.kwargs["baudrate"] == 115200
        finally:
            await t.disconnect()
            patcher.stop()

    async def test_disconnect_closes_port(self):
        patcher, _, mock_port = _mock_serial()
        try:
            t = _make()
            await t.connect()
            await t.disconnect()
            mock_port.close.assert_called()
            assert not t.connected
        finally:
            patcher.stop()

    async def test_connect_failed_open_starts_thread_anyway(self):
        """If the port can't be opened, the reconnect thread should start."""
        patcher = patch("comms.transport.rs485.serial.Serial",
                        side_effect=serial.SerialException("not found"))
        patcher.start()
        try:
            t = _make()
            await t.connect()
            assert not t.connected
            assert t._read_thread is not None
            assert t._read_thread.is_alive()
        finally:
            await t.disconnect()
            patcher.stop()


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------

class TestSend:

    async def test_send_writes_encoded_packet(self):
        patcher, _, mock_port = _mock_serial()
        try:
            t = _make()
            await t.connect()
            pkt = build_packet("01", "STATE")
            await t.send(pkt)
            mock_port.write.assert_called_once_with(pkt.encode())
        finally:
            await t.disconnect()
            patcher.stop()

    async def test_send_not_connected_does_not_raise(self):
        t = _make()
        pkt = build_packet("01", "STATE")
        await t.send(pkt)  # not connected - should warn and return cleanly

    async def test_send_serial_exception_does_not_raise(self):
        patcher, _, mock_port = _mock_serial()
        mock_port.write.side_effect = serial.SerialException("write error")
        try:
            t = _make()
            await t.connect()
            await t.send(build_packet("01", "STATE"))  # should log, not raise
        finally:
            await t.disconnect()
            patcher.stop()


# ---------------------------------------------------------------------------
# _process_buffer - packet extraction and dispatch
# ---------------------------------------------------------------------------

class TestProcessBuffer:
    """
    Call _process_buffer() directly with a pre-loaded _buffer string.
    Set transport._loop to the running test loop so run_coroutine_threadsafe
    schedules on it; yield with sleep(0.05) to let coroutines execute.
    """

    async def test_single_packet_dispatched(self):
        t = _make()
        t._loop = asyncio.get_event_loop()
        received = []
        t.on_packet(lambda p, n: received.append(p))

        t._buffer = "/0001:STATE:XX\r"
        t._process_buffer()
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].payload == "STATE"

    async def test_multiple_packets_dispatched(self):
        t = _make()
        t._loop = asyncio.get_event_loop()
        received = []
        t.on_packet(lambda p, n: received.append(p))

        t._buffer = "/0001:RY1,1:XX\r/0001:RY2,0:XX\r"
        t._process_buffer()
        await asyncio.sleep(0.05)

        assert len(received) == 2
        assert received[0].command == "RY1"
        assert received[1].command == "RY2"

    async def test_partial_packet_stays_in_buffer(self):
        t = _make()
        t._loop = asyncio.get_event_loop()
        t.on_packet(lambda p, n: None)

        t._buffer = "/0001:STATE:XX\r/0001:PING"
        t._process_buffer()
        await asyncio.sleep(0.05)

        assert t._buffer == "/0001:PING"

    async def test_garbage_line_before_valid_packet(self):
        t = _make()
        t._loop = asyncio.get_event_loop()
        received = []
        t.on_packet(lambda p, n: received.append(p))

        t._buffer = "noise data\r/0001:STATE:XX\r"
        t._process_buffer()
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].payload == "STATE"

    async def test_empty_lines_skipped(self):
        t = _make()
        t._loop = asyncio.get_event_loop()
        received = []
        t.on_packet(lambda p, n: received.append(p))

        t._buffer = "\r\r/0001:STATE:XX\r"
        t._process_buffer()
        await asyncio.sleep(0.05)

        assert len(received) == 1

    async def test_broadcast_packet_dispatched(self):
        t = _make()
        t._loop = asyncio.get_event_loop()
        received = []
        t.on_packet(lambda p, n: received.append(p))

        t._buffer = "//ROLLCALL:XX\r"
        t._process_buffer()
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].broadcast

    async def test_transport_name_passed_to_handler(self):
        t = RS485Transport("power", {"port": "COM2", "baud_rate": 115200})
        t._loop = asyncio.get_event_loop()
        names = []
        t.on_packet(lambda p, n: names.append(n))

        t._buffer = "/0001:STATE:XX\r"
        t._process_buffer()
        await asyncio.sleep(0.05)

        assert names == ["power"]

    async def test_buffer_empty_after_full_packets_consumed(self):
        t = _make()
        t._loop = asyncio.get_event_loop()
        t.on_packet(lambda p, n: None)

        t._buffer = "/0001:STATE:XX\r/0001:PING:XX\r"
        t._process_buffer()
        await asyncio.sleep(0.05)

        assert t._buffer == ""

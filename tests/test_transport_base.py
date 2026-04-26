"""
Tests for comms/transport/base.py — dispatch mechanism and base properties.
Uses a minimal concrete subclass; no I/O.
"""
import pytest

from comms.transport.base import DCNTransport
from comms.dcn_packet import build_packet


class _ConcreteTransport(DCNTransport):
    """Minimal subclass used only in tests."""
    async def connect(self): self._connected = True
    async def disconnect(self): self._connected = False
    async def send(self, packet): pass


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class TestProperties:

    def test_not_connected_initially(self):
        t = _ConcreteTransport("t", {})
        assert not t.connected

    def test_default_baud_rate(self):
        t = _ConcreteTransport("t", {})
        assert t.baud_rate == 9600

    def test_custom_baud_rate(self):
        t = _ConcreteTransport("t", {"baud_rate": 115200})
        assert t.baud_rate == 115200

    def test_baud_rate_coerced_to_int(self):
        t = _ConcreteTransport("t", {"baud_rate": "115200"})
        assert t.baud_rate == 115200

    def test_description_empty_default(self):
        t = _ConcreteTransport("t", {})
        assert t.description == ""

    def test_description_from_config(self):
        t = _ConcreteTransport("t", {"description": "Main control"})
        assert t.description == "Main control"

    def test_name_stored(self):
        t = _ConcreteTransport("control", {})
        assert t.name == "control"


# ---------------------------------------------------------------------------
# Handler dispatch
# ---------------------------------------------------------------------------

class TestDispatch:

    async def test_sync_handler_receives_packet_and_name(self):
        t = _ConcreteTransport("ctrl", {})
        calls = []
        t.on_packet(lambda p, n: calls.append((p, n)))

        pkt = build_packet("01", "STATE")
        await t._dispatch(pkt)

        assert len(calls) == 1
        assert calls[0][0] is pkt
        assert calls[0][1] == "ctrl"

    async def test_async_handler_awaited(self):
        t = _ConcreteTransport("ctrl", {})
        calls = []

        async def handler(p, n):
            calls.append((p, n))

        t.on_packet(handler)
        await t._dispatch(build_packet("01", "STATE"))
        assert len(calls) == 1

    async def test_multiple_handlers_all_called(self):
        t = _ConcreteTransport("ctrl", {})
        order = []
        t.on_packet(lambda p, n: order.append(1))
        t.on_packet(lambda p, n: order.append(2))
        t.on_packet(lambda p, n: order.append(3))

        await t._dispatch(build_packet("01", "STATE"))
        assert order == [1, 2, 3]

    async def test_no_handlers_does_not_raise(self):
        t = _ConcreteTransport("ctrl", {})
        await t._dispatch(build_packet("01", "STATE"))  # should be silent

    async def test_handler_exception_does_not_propagate(self):
        t = _ConcreteTransport("ctrl", {})

        def bad(p, n):
            raise RuntimeError("handler boom")

        calls = []
        t.on_packet(bad)
        t.on_packet(lambda p, n: calls.append(1))

        # Bad handler raises but subsequent handler still runs
        await t._dispatch(build_packet("01", "STATE"))
        assert calls == [1]

    async def test_async_handler_exception_does_not_propagate(self):
        t = _ConcreteTransport("ctrl", {})

        async def bad(p, n):
            raise RuntimeError("async handler boom")

        calls = []
        t.on_packet(bad)
        t.on_packet(lambda p, n: calls.append(1))

        await t._dispatch(build_packet("01", "STATE"))
        assert calls == [1]

    async def test_connect_sets_connected(self):
        t = _ConcreteTransport("ctrl", {})
        await t.connect()
        assert t.connected

    async def test_disconnect_clears_connected(self):
        t = _ConcreteTransport("ctrl", {})
        await t.connect()
        await t.disconnect()
        assert not t.connected

"""
Tests for /api/comms/* endpoints (api/routers/comms.py).

Covers:
  GET  /api/comms/buses    — list live bus names
  POST /api/comms/discover — broadcast PING, collect UPDATE responses
"""
from __future__ import annotations

import asyncio
import pytest
from httpx import ASGITransport, AsyncClient

from api.app import create_app
from api.deps import AppState, _state
from comms.dcn_network import DCNNetwork
from comms.dcn_packet import DCNPacket, build_packet
from comms.transport.base import DCNTransport


# ---------------------------------------------------------------------------
# Test double — transport that responds to PING immediately
# ---------------------------------------------------------------------------

class RespondingTransport(DCNTransport):
    """
    A DCN transport stub that replies to any broadcast with configured
    UPDATE packets.  Used to simulate devices responding to a PING scan.
    """

    def __init__(self, name: str, responses: list[tuple[str, str]]) -> None:
        super().__init__(name, {})
        self._responses = responses   # [(from_addr, payload), ...]
        self._sent: list[DCNPacket] = []

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def send(self, packet: DCNPacket) -> None:
        self._sent.append(packet)
        if packet.broadcast:
            for addr, payload in self._responses:
                resp = build_packet(addr, payload, from_addr=addr)
                await self._dispatch(resp)


def _make_network(responses: list[tuple[str, str]], connected: bool = True) -> DCNNetwork:
    """Build a DCNNetwork with a RespondingTransport pre-connected."""
    net = DCNNetwork()
    t = RespondingTransport("control", responses)
    net.add_transport(t)
    if connected:
        t._connected = True
    return net


# ---------------------------------------------------------------------------
# App fixtures
# ---------------------------------------------------------------------------

def _app_with_networks(networks: dict) -> object:
    fresh = AppState()
    for attr in vars(fresh):
        setattr(_state, attr, getattr(fresh, attr))
    state = AppState()
    state.networks = networks
    return create_app(state)


@pytest.fixture
def empty_app():
    fresh = AppState()
    for attr in vars(fresh):
        setattr(_state, attr, getattr(fresh, attr))
    return create_app()


# ---------------------------------------------------------------------------
# GET /api/comms/buses
# ---------------------------------------------------------------------------

class TestListBuses:

    async def test_no_networks_returns_empty_list(self, empty_app):
        async with AsyncClient(
            transport=ASGITransport(app=empty_app), base_url="http://test"
        ) as c:
            r = await c.get("/api/comms/buses")
        assert r.status_code == 200
        assert r.json() == {"buses": []}

    async def test_returns_bus_names(self):
        net = _make_network([])
        app = _app_with_networks({"control": net, "power": DCNNetwork()})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.get("/api/comms/buses")
        assert r.status_code == 200
        buses = r.json()["buses"]
        assert "control" in buses
        assert "power" in buses

    async def test_buses_sorted_alphabetically(self):
        app = _app_with_networks({"zebra": DCNNetwork(), "alpha": DCNNetwork()})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.get("/api/comms/buses")
        assert r.json()["buses"] == ["alpha", "zebra"]


# ---------------------------------------------------------------------------
# POST /api/comms/discover
# ---------------------------------------------------------------------------

class TestDiscover:

    async def test_no_networks_returns_503(self, empty_app):
        async with AsyncClient(
            transport=ASGITransport(app=empty_app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        assert r.status_code == 503

    async def test_discovers_gpio_device(self):
        net = _make_network([
            ("01", "UPDATE,GPIO1,00000000,0000,0.0,20.0"),
        ])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?bus=control&timeout=0.5")
        assert r.status_code == 200
        data = r.json()
        assert data["bus"] == "control"
        devices = data["devices"]
        assert len(devices) == 1
        assert devices[0]["address"] == "01"
        assert devices[0]["device_type"] == "gpio"
        assert devices[0]["raw_type"] == "GPIO1"

    async def test_discovers_antenna_relay(self):
        net = _make_network([
            ("06", "UPDATE,ARC1,00000000"),
        ])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        devices = r.json()["devices"]
        assert devices[0]["device_type"] == "antenna_relay"
        assert devices[0]["raw_type"] == "ARC1"

    async def test_discovers_coax_switch(self):
        net = _make_network([("02", "UPDATE,CX1,1")])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        assert r.json()["devices"][0]["device_type"] == "coax_switch"

    async def test_discovers_vhf_relay(self):
        net = _make_network([("03", "UPDATE,CX2,0")])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        assert r.json()["devices"][0]["device_type"] == "vhf_coax_relay"

    async def test_discovers_watt_meter(self):
        net = _make_network([("04", "UPDATE,WM1,1,0.000,0.000")])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        assert r.json()["devices"][0]["device_type"] == "watt_meter"

    async def test_discovers_multiple_devices(self):
        net = _make_network([
            ("01", "UPDATE,GPIO1,00000000,0000,0.0,20.0"),
            ("06", "UPDATE,ARC1,00000000"),
            ("04", "UPDATE,WM1,1,0.000,0.000"),
        ])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        devices = r.json()["devices"]
        assert len(devices) == 3
        addresses = {d["address"] for d in devices}
        assert addresses == {"01", "06", "04"}

    async def test_devices_sorted_by_address(self):
        net = _make_network([
            ("06", "UPDATE,ARC1,00000000"),
            ("01", "UPDATE,GPIO1,00000000,0000,0.0,20.0"),
        ])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        devices = r.json()["devices"]
        assert devices[0]["address"] == "01"
        assert devices[1]["address"] == "06"

    async def test_unknown_device_type_has_null_device_type(self):
        net = _make_network([("05", "UPDATE,XYZ1,data")])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        d = r.json()["devices"][0]
        assert d["device_type"] is None
        assert d["raw_type"] == "XYZ1"

    async def test_non_update_packets_ignored(self):
        net = _make_network([
            ("01", "STATUS,OK"),           # not an UPDATE packet
            ("02", "UPDATE,GPIO1,00000000,0000,0.0,20.0"),
        ])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        devices = r.json()["devices"]
        # Only the GPIO device should be found
        assert len(devices) == 1
        assert devices[0]["address"] == "02"

    async def test_no_responding_devices_returns_empty_list(self):
        net = _make_network([])   # no responses
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        assert r.status_code == 200
        assert r.json()["devices"] == []

    async def test_named_bus_used_when_specified(self):
        net_control = _make_network([("01", "UPDATE,GPIO1,00000000,0000,0.0,20.0")])
        net_power   = _make_network([("09", "UPDATE,WM1,1,0.000,0.000")])
        app = _app_with_networks({"control": net_control, "power": net_power})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?bus=power&timeout=0.5")
        assert r.json()["bus"] == "power"
        devices = r.json()["devices"]
        assert len(devices) == 1
        assert devices[0]["address"] == "09"

    async def test_unknown_bus_falls_back_to_control(self):
        net = _make_network([("01", "UPDATE,GPIO1,00000000,0000,0.0,20.0")])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?bus=nonexistent&timeout=0.5")
        # Falls back to control network — still discovers the device
        assert r.status_code == 200
        assert len(r.json()["devices"]) == 1

    async def test_duplicate_address_only_reported_once(self):
        # Simulate a device that replies twice (shouldn't happen but be safe)
        net = _make_network([
            ("01", "UPDATE,GPIO1,00000000,0000,0.0,20.0"),
            ("01", "UPDATE,GPIO1,11111111,0000,0.0,20.0"),
        ])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.5")
        assert len(r.json()["devices"]) == 1

    async def test_timeout_below_minimum_returns_422(self):
        net = _make_network([])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=0.1")
        assert r.status_code == 422

    async def test_timeout_above_maximum_returns_422(self):
        net = _make_network([])
        app = _app_with_networks({"control": net})
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/api/comms/discover?timeout=99")
        assert r.status_code == 422

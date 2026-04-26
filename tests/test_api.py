"""Tests for the FastAPI backend."""
import json
import pytest
from httpx import ASGITransport, AsyncClient

from api.app import create_app
from api.deps import AppState, _state
from sensors.sensor_registry import SensorRegistry
from radio.radio_state import RadioState
from automation.bands import BandRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_state():
    reg = SensorRegistry()
    reg.publish("watt_meter_fwd_w", 125.3, unit="W", source="watt_meter")
    reg.publish("watt_meter_swr", 1.8, unit="ratio", source="watt_meter")
    reg.publish("gpio_01_relay_1", 0.0, unit="", source="gpio")

    rs = RadioState(name="test", frequency_hz=14_225_000, ptt=False, connected=True)

    s = AppState()
    s.sensor_registry = reg
    s.radio_state = rs
    s.band_registry = BandRegistry.amateur()
    return s


@pytest.fixture
def app(app_state):
    # Reset module-level state between tests
    fresh = AppState()
    for attr in vars(fresh):
        setattr(_state, attr, getattr(fresh, attr))
    return create_app(app_state)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------

class TestSensorsRouter:

    async def test_get_all_sensors(self, client):
        r = await client.get("/api/sensors")
        assert r.status_code == 200
        data = r.json()
        assert "watt_meter_fwd_w" in data
        assert data["watt_meter_fwd_w"]["value"] == pytest.approx(125.3)
        assert data["watt_meter_fwd_w"]["unit"] == "W"

    async def test_get_single_sensor(self, client):
        r = await client.get("/api/sensors/watt_meter_swr")
        assert r.status_code == 200
        assert r.json()["value"] == pytest.approx(1.8)

    async def test_missing_sensor_returns_404(self, client):
        r = await client.get("/api/sensors/nonexistent")
        assert r.status_code == 404

    async def test_no_registry_returns_empty(self):
        fresh = AppState()
        for attr in vars(fresh):
            setattr(_state, attr, getattr(fresh, attr))
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/sensors")
        assert r.status_code == 200
        assert r.json() == {}


# ---------------------------------------------------------------------------
# Radio
# ---------------------------------------------------------------------------

class TestRadioRouter:

    async def test_get_radio_state(self, client):
        r = await client.get("/api/radio")
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is True
        assert data["frequency_hz"] == pytest.approx(14_225_000)
        assert data["ptt"] is False

    async def test_no_radio_returns_disconnected(self):
        fresh = AppState()
        for attr in vars(fresh):
            setattr(_state, attr, getattr(fresh, attr))
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/radio")
        assert r.status_code == 200
        assert r.json()["connected"] is False

    async def test_tune_without_interface_returns_503(self, client):
        r = await client.post("/api/radio/tune", json={"frequency_hz": 7_100_000})
        assert r.status_code == 503


# ---------------------------------------------------------------------------
# Relays
# ---------------------------------------------------------------------------

class TestRelaysRouter:

    async def test_get_relays_filters_by_name(self, client):
        r = await client.get("/api/relays")
        assert r.status_code == 200
        data = r.json()
        assert "gpio_01_relay_1" in data

    async def test_set_relay_without_network_returns_503(self, client):
        r = await client.post("/api/relays/gpio_01_relay_1", json={
            "state": 1, "device_addr": "01", "relay_num": 1
        })
        assert r.status_code == 503

    async def test_set_relay_invalid_state(self, client):
        r = await client.post("/api/relays/gpio_01_relay_1", json={
            "state": 2, "device_addr": "01", "relay_num": 1
        })
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------

class TestDashboardsRouter:

    async def test_list_dashboards(self, client):
        r = await client.get("/api/dashboards")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_get_existing_dashboard(self, client):
        r = await client.get("/api/dashboards/main")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "main"
        assert "cards" in data

    async def test_get_missing_dashboard_returns_404(self, client):
        r = await client.get("/api/dashboards/nonexistent_xyz")
        assert r.status_code == 404

    async def test_save_and_retrieve_dashboard(self, client, tmp_path, monkeypatch):
        import api.routers.dashboards as db_mod
        monkeypatch.setattr(db_mod, "DASHBOARDS_DIR", tmp_path)
        yaml_text = "id: test\ntitle: Test\ncards: []\n"
        r = await client.put("/api/dashboards/test", json={"yaml": yaml_text})
        assert r.status_code == 200
        r2 = await client.get("/api/dashboards/test")
        assert r2.status_code == 200
        assert r2.json()["title"] == "Test"

    async def test_save_invalid_yaml_returns_422(self, client, tmp_path, monkeypatch):
        import api.routers.dashboards as db_mod
        monkeypatch.setattr(db_mod, "DASHBOARDS_DIR", tmp_path)
        r = await client.put("/api/dashboards/bad", json={"yaml": "key: [invalid"})
        assert r.status_code == 422

    async def test_invalid_dashboard_id_rejected(self, client):
        # ID with special chars — our regex rejects these with 422
        r = await client.get("/api/dashboards/bad%20id")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Automations
# ---------------------------------------------------------------------------

class TestAutomationsRouter:

    async def test_list_automations_no_engine(self, client):
        r = await client.get("/api/automations")
        assert r.status_code == 200
        assert r.json() == []

    async def test_get_config_missing(self, client, tmp_path, monkeypatch):
        import api.routers.automations as am
        monkeypatch.setattr(am, "AUTOMATION_CONFIG", tmp_path / "missing.yaml")
        r = await client.get("/api/automations/config")
        assert r.status_code == 200
        assert r.json()["yaml"] == ""

    async def test_trigger_no_engine_returns_503(self, client):
        r = await client.post("/api/automations/my_rule/trigger", json={})
        assert r.status_code == 503


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class TestNotificationsRouter:

    async def test_subscribe_and_list(self, client, tmp_path, monkeypatch):
        import api.routers.notifications as notif
        monkeypatch.setattr(notif, "SUBSCRIPTIONS_FILE", tmp_path / "subs.json")
        r = await client.post("/api/push/subscribe", json={
            "endpoint": "https://example.com/push/abc",
            "keys": {"p256dh": "key1", "auth": "auth1"},
            "label": "test browser",
        })
        assert r.status_code == 200
        assert r.json()["subscribed"] == 1

    async def test_unsubscribe(self, client, tmp_path, monkeypatch):
        import api.routers.notifications as notif
        monkeypatch.setattr(notif, "SUBSCRIPTIONS_FILE", tmp_path / "subs.json")
        sub = {"endpoint": "https://example.com/push/abc", "keys": {}, "label": ""}
        await client.post("/api/push/subscribe", json=sub)
        r = await client.post("/api/push/unsubscribe", json=sub)
        assert r.status_code == 200
        assert r.json()["removed"] == 1


# ---------------------------------------------------------------------------
# AppState.control_network / network_for_addr
# ---------------------------------------------------------------------------

class TestAppStateNetworking:

    def test_control_network_returns_named_control_bus(self):
        from comms.dcn_network import DCNNetwork
        s = AppState()
        ctrl = DCNNetwork()
        s.networks = {"control": ctrl}
        assert s.control_network is ctrl

    def test_control_network_falls_back_to_first_bus(self):
        from comms.dcn_network import DCNNetwork
        s = AppState()
        first = DCNNetwork()
        s.networks = {"power": first}
        assert s.control_network is first

    def test_control_network_returns_none_when_empty(self):
        s = AppState()
        s.networks = {}
        assert s.control_network is None

    def test_control_network_returns_none_with_default_state(self):
        s = AppState()
        assert s.control_network is None

    def test_network_for_addr_uses_device_bus_map(self):
        from comms.dcn_network import DCNNetwork
        s = AppState()
        ctrl = DCNNetwork()
        power = DCNNetwork()
        s.networks = {"control": ctrl, "power": power}
        s.device_bus = {"03": "power"}
        assert s.network_for_addr("03") is power

    def test_network_for_addr_falls_back_to_control_bus(self):
        from comms.dcn_network import DCNNetwork
        s = AppState()
        ctrl = DCNNetwork()
        s.networks = {"control": ctrl}
        s.device_bus = {}
        assert s.network_for_addr("01") is ctrl

    def test_network_for_addr_unknown_address_uses_control(self):
        from comms.dcn_network import DCNNetwork
        s = AppState()
        ctrl = DCNNetwork()
        s.networks = {"control": ctrl}
        s.device_bus = {"03": "power"}  # "power" bus not in networks
        assert s.network_for_addr("03") is ctrl

    def test_network_for_addr_no_networks_returns_none(self):
        s = AppState()
        assert s.network_for_addr("01") is None

"""Tests for GET /api/history/sensors/* and /api/history/devices."""
import time
import pytest
from httpx import ASGITransport, AsyncClient

from api.app         import create_app
from api.deps        import AppState, _state
from telemetry.store import TelemetryStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def store():
    async with TelemetryStore("sqlite+aiosqlite:///:memory:") as s:
        yield s


def _make_app(state: AppState) -> object:
    fresh = AppState()
    for attr in vars(fresh):
        setattr(_state, attr, getattr(fresh, attr))
    return create_app(state)


@pytest.fixture
async def client(store):
    state = AppState()
    state.telemetry = store
    app = _make_app(state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def client_no_telemetry():
    app = _make_app(AppState())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/history/sensors/names
# ---------------------------------------------------------------------------

class TestHistorySensorNames:

    async def test_returns_empty_when_no_data(self, client):
        r = await client.get("/api/history/sensors/names")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_recorded_sensor_names(self, client, store):
        await store.record_sensor("swr", 1.8)
        await store.record_sensor("voltage", 13.5)
        r = await client.get("/api/history/sensors/names")
        assert r.status_code == 200
        assert set(r.json()) == {"swr", "voltage"}

    async def test_names_are_deduplicated(self, client, store):
        await store.record_sensor("swr", 1.8)
        await store.record_sensor("swr", 2.0)
        r = await client.get("/api/history/sensors/names")
        assert r.json().count("swr") == 1

    async def test_names_are_sorted(self, client, store):
        for name in ["temp_f", "ant_relay_0", "swr"]:
            await store.record_sensor(name, 1.0)
        r = await client.get("/api/history/sensors/names")
        names = r.json()
        assert names == sorted(names)

    async def test_returns_empty_without_telemetry(self, client_no_telemetry):
        r = await client_no_telemetry.get("/api/history/sensors/names")
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# GET /api/history/sensors
# ---------------------------------------------------------------------------

class TestHistorySensors:

    async def test_returns_readings_for_sensor(self, client, store):
        now = time.time()
        await store.record_sensor("swr", 1.8, unit="ratio", ts=now - 5)
        await store.record_sensor("swr", 2.1, unit="ratio", ts=now - 2)
        r = await client.get(f"/api/history/sensors?name=swr&since={now - 10}")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert data[0]["value"] == pytest.approx(1.8)
        assert data[1]["value"] == pytest.approx(2.1)

    async def test_response_shape(self, client, store):
        now = time.time()
        await store.record_sensor("swr", 1.5, unit="ratio", ts=now - 1)
        r = await client.get(f"/api/history/sensors?name=swr&since={now - 5}")
        item = r.json()[0]
        assert set(item.keys()) >= {"ts", "value", "unit"}
        assert item["unit"] == "ratio"
        assert item["value"] == pytest.approx(1.5)

    async def test_filters_by_since(self, client, store):
        now = time.time()
        await store.record_sensor("temp", 70.0, ts=now - 100)  # old
        await store.record_sensor("temp", 72.0, ts=now - 5)    # recent
        r = await client.get(f"/api/history/sensors?name=temp&since={now - 10}")
        data = r.json()
        assert len(data) == 1
        assert data[0]["value"] == pytest.approx(72.0)

    async def test_filters_by_until(self, client, store):
        now = time.time()
        await store.record_sensor("temp", 70.0, ts=now - 20)
        await store.record_sensor("temp", 72.0, ts=now - 10)
        await store.record_sensor("temp", 74.0, ts=now - 2)
        r = await client.get(
            f"/api/history/sensors?name=temp&since={now - 25}&until={now - 8}"
        )
        data = r.json()
        assert len(data) == 2
        assert data[-1]["value"] == pytest.approx(72.0)

    async def test_limit_is_respected(self, client, store):
        now = time.time()
        for i in range(20):
            await store.record_sensor("swr", float(i), ts=now - 20 + i)
        r = await client.get(f"/api/history/sensors?name=swr&since={now - 25}&limit=5")
        assert r.status_code == 200
        assert len(r.json()) == 5

    async def test_returns_empty_for_unknown_sensor(self, client):
        r = await client.get(f"/api/history/sensors?name=nonexistent&since=0")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_only_requested_sensor(self, client, store):
        now = time.time()
        await store.record_sensor("swr", 1.8, ts=now - 5)
        await store.record_sensor("voltage", 13.5, ts=now - 5)
        r = await client.get(f"/api/history/sensors?name=swr&since={now - 10}")
        data = r.json()
        assert all(item["value"] == pytest.approx(1.8) for item in data)

    async def test_readings_ordered_by_timestamp(self, client, store):
        now = time.time()
        # Insert out of order
        await store.record_sensor("swr", 3.0, ts=now - 1)
        await store.record_sensor("swr", 1.5, ts=now - 10)
        await store.record_sensor("swr", 2.0, ts=now - 5)
        r = await client.get(f"/api/history/sensors?name=swr&since={now - 15}")
        values = [item["value"] for item in r.json()]
        assert values == sorted(values)

    async def test_returns_400_for_future_since(self, client):
        future = time.time() + 3600
        r = await client.get(f"/api/history/sensors?name=swr&since={future}")
        assert r.status_code == 400

    async def test_returns_empty_without_telemetry(self, client_no_telemetry):
        r = await client_no_telemetry.get(f"/api/history/sensors?name=swr&since=0")
        assert r.status_code == 200
        assert r.json() == []

    async def test_missing_name_param_returns_422(self, client):
        r = await client.get(f"/api/history/sensors?since=0")
        assert r.status_code == 422

    async def test_missing_since_param_returns_422(self, client):
        r = await client.get(f"/api/history/sensors?name=swr")
        assert r.status_code == 422

    async def test_limit_above_max_returns_422(self, client):
        r = await client.get(f"/api/history/sensors?name=swr&since=0&limit=99999")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/history/devices
# ---------------------------------------------------------------------------

class TestHistoryDevices:

    async def test_returns_device_events(self, client, store):
        await store.record_device_event(
            event_type="relay_toggle",
            device_key="ant_relay_0",
            device_name="Antenna Relay 0",
            old_value="0",
            new_value="1",
            source="automation",
        )
        r = await client.get(f"/api/history/devices?since=0")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["event_type"] == "relay_toggle"
        assert data[0]["new_value"] == "1"

    async def test_response_shape(self, client, store):
        await store.record_device_event("relay_toggle", "ant_relay_0",
                                        old_value="0", new_value="1")
        r = await client.get("/api/history/devices?since=0")
        item = r.json()[0]
        assert set(item.keys()) >= {"ts", "event_type", "device_key", "device_name",
                                    "old_value", "new_value"}

    async def test_filters_by_device_key(self, client, store):
        await store.record_device_event("relay_toggle", "ant_relay_0")
        await store.record_device_event("relay_toggle", "ant_relay_1")
        r = await client.get("/api/history/devices?device_key=ant_relay_0&since=0")
        data = r.json()
        assert len(data) == 1
        assert data[0]["device_key"] == "ant_relay_0"

    async def test_filters_by_since(self, client, store):
        now = time.time()
        await store.record_device_event("relay_toggle", "ant_relay_0", ts=now - 100)
        await store.record_device_event("relay_toggle", "ant_relay_0", ts=now - 2)
        r = await client.get(f"/api/history/devices?since={now - 5}")
        data = r.json()
        assert len(data) == 1

    async def test_limit_is_respected(self, client, store):
        now = time.time()
        for i in range(10):
            await store.record_device_event("relay_toggle", "ant_relay_0",
                                            ts=now - 10 + i)
        r = await client.get(f"/api/history/devices?since=0&limit=3")
        assert len(r.json()) == 3

    async def test_returns_empty_when_no_events(self, client):
        r = await client.get("/api/history/devices?since=0")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_empty_without_telemetry(self, client_no_telemetry):
        r = await client_no_telemetry.get("/api/history/devices?since=0")
        assert r.status_code == 200
        assert r.json() == []

    async def test_null_old_value_preserved(self, client, store):
        await store.record_device_event("online", "gpio", old_value=None, new_value="connected")
        r = await client.get("/api/history/devices?since=0")
        assert r.json()[0]["old_value"] is None

    async def test_multiple_event_types_all_returned(self, client, store):
        now = time.time()
        await store.record_device_event("online",        "gpio", ts=now - 10)
        await store.record_device_event("relay_toggle",  "gpio", ts=now - 5)
        await store.record_device_event("offline",       "gpio", ts=now - 1)
        r = await client.get(f"/api/history/devices?device_key=gpio&since=0")
        event_types = {e["event_type"] for e in r.json()}
        assert event_types == {"online", "relay_toggle", "offline"}

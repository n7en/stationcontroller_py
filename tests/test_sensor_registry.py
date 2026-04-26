"""Tests for sensors/sensor_registry.py."""
import asyncio
import time
import pytest

from sensors.sensor_registry import SensorRegistry, Measurement


# ---------------------------------------------------------------------------
# Measurement dataclass
# ---------------------------------------------------------------------------

class TestMeasurement:

    def test_age_increases_over_time(self):
        m = Measurement(name="x", value=1.0)
        time.sleep(0.01)
        assert m.age_s() > 0.0

    def test_fresh_measurement_is_not_old(self):
        m = Measurement(name="x", value=1.0)
        assert m.age_s() < 1.0

    def test_unit_and_source_default_empty(self):
        m = Measurement(name="x", value=42.0)
        assert m.unit == ""
        assert m.source == ""


# ---------------------------------------------------------------------------
# Basic publish / read
# ---------------------------------------------------------------------------

class TestPublishRead:

    def test_get_returns_none_before_publish(self):
        r = SensorRegistry()
        assert r.get("swr") is None

    def test_get_returns_measurement_after_publish(self):
        r = SensorRegistry()
        r.publish("swr", 1.8, unit="", source="watt_meter")
        m = r.get("swr")
        assert m is not None
        assert m.value == 1.8
        assert m.source == "watt_meter"

    def test_value_returns_latest(self):
        r = SensorRegistry()
        r.publish("forward_power_w", 100.0)
        r.publish("forward_power_w", 150.0)
        assert r.value("forward_power_w") == 150.0

    def test_value_returns_default_when_unknown(self):
        r = SensorRegistry()
        assert r.value("unknown", default=-1.0) == -1.0

    def test_value_default_is_zero(self):
        r = SensorRegistry()
        assert r.value("missing") == 0.0

    def test_publish_stores_unit(self):
        r = SensorRegistry()
        r.publish("voltage", 13.8, unit="V")
        assert r.get("voltage").unit == "V"

    def test_publish_stores_timestamp(self):
        before = time.time()
        r = SensorRegistry()
        r.publish("x", 1.0)
        after = time.time()
        ts = r.get("x").timestamp
        assert before <= ts <= after


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------

class TestStaleness:

    def test_fresh_value_is_not_stale(self):
        r = SensorRegistry()
        r.publish("x", 1.0)
        assert not r.is_stale("x", max_age_s=60.0)

    def test_absent_value_is_stale(self):
        r = SensorRegistry()
        assert r.is_stale("missing", max_age_s=1.0)

    def test_old_value_is_stale(self):
        r = SensorRegistry()
        m = Measurement(name="x", value=1.0, timestamp=time.time() - 10.0)
        with r._lock:
            r._store["x"] = m
        assert r.is_stale("x", max_age_s=5.0)

    def test_value_within_window_is_not_stale(self):
        r = SensorRegistry()
        m = Measurement(name="x", value=1.0, timestamp=time.time() - 3.0)
        with r._lock:
            r._store["x"] = m
        assert not r.is_stale("x", max_age_s=5.0)


# ---------------------------------------------------------------------------
# Snapshot and names
# ---------------------------------------------------------------------------

class TestSnapshot:

    def test_snapshot_empty_initially(self):
        r = SensorRegistry()
        assert r.snapshot() == {}

    def test_snapshot_contains_all_published(self):
        r = SensorRegistry()
        r.publish("a", 1.0)
        r.publish("b", 2.0)
        snap = r.snapshot()
        assert set(snap.keys()) == {"a", "b"}

    def test_snapshot_is_a_copy(self):
        r = SensorRegistry()
        r.publish("a", 1.0)
        snap = r.snapshot()
        snap["a"] = None  # mutate copy
        assert r.get("a") is not None

    def test_names_returns_all_keys(self):
        r = SensorRegistry()
        r.publish("x", 1.0)
        r.publish("y", 2.0)
        assert set(r.names()) == {"x", "y"}


# ---------------------------------------------------------------------------
# Subscriptions — sync callbacks
# ---------------------------------------------------------------------------

class TestSyncCallbacks:

    async def test_on_change_fires_on_publish(self):
        r = SensorRegistry()
        received = []
        r.on_change("swr", lambda m: received.append(m.value))
        r.publish("swr", 1.8)
        await asyncio.sleep(0)
        assert received == [1.8]

    async def test_on_change_only_fires_for_named_key(self):
        r = SensorRegistry()
        received = []
        r.on_change("swr", lambda m: received.append(m.value))
        r.publish("voltage", 13.8)
        r.publish("swr", 2.1)
        await asyncio.sleep(0)
        assert received == [2.1]

    async def test_on_any_fires_for_all_keys(self):
        r = SensorRegistry()
        names = []
        r.on_any(lambda m: names.append(m.name))
        r.publish("a", 1.0)
        r.publish("b", 2.0)
        await asyncio.sleep(0)
        assert "a" in names
        assert "b" in names

    async def test_multiple_callbacks_all_called(self):
        r = SensorRegistry()
        results = []
        r.on_change("x", lambda m: results.append("first"))
        r.on_change("x", lambda m: results.append("second"))
        r.publish("x", 1.0)
        await asyncio.sleep(0)
        assert results == ["first", "second"]

    def test_on_change_as_decorator(self):
        r = SensorRegistry()
        received = []

        @r.on_change("temp")
        def handler(m):
            received.append(m.value)

        r.publish("temp", 72.0)
        assert received == [72.0]

    def test_on_any_as_decorator(self):
        r = SensorRegistry()
        received = []

        @r.on_any
        def handler(m):
            received.append(m.name)

        r.publish("pressure", 1013.0)
        assert "pressure" in received


# ---------------------------------------------------------------------------
# Subscriptions — async callbacks
# ---------------------------------------------------------------------------

class TestAsyncCallbacks:

    async def test_async_callback_is_scheduled(self):
        r = SensorRegistry()
        results = []

        @r.on_change("swr")
        async def handler(m):
            results.append(m.value)

        r.publish("swr", 3.2)
        await asyncio.sleep(0.05)
        assert results == [3.2]

    async def test_async_on_any_callback(self):
        r = SensorRegistry()
        names = []

        @r.on_any
        async def handler(m):
            names.append(m.name)

        r.publish("a", 1.0)
        r.publish("b", 2.0)
        await asyncio.sleep(0.05)
        assert "a" in names and "b" in names

    async def test_callback_receives_correct_measurement(self):
        r = SensorRegistry()
        captured = []

        @r.on_change("rfpower")
        async def handler(m):
            captured.append(m)

        r.publish("rfpower", 0.75, unit="", source="radio")
        await asyncio.sleep(0.05)
        assert len(captured) == 1
        assert captured[0].value == 0.75
        assert captured[0].source == "radio"

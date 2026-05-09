"""Tests for telemetry/store.py and telemetry/recorder.py."""
import asyncio
import math
import time
import pytest

from sensors.sensor_registry import Measurement, SensorRegistry
from telemetry.store import TelemetryStore
from telemetry.recorder import SensorRecorder
from telemetry.config import load_telemetry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def store():
    async with TelemetryStore("sqlite+aiosqlite:///:memory:") as s:
        yield s


# ---------------------------------------------------------------------------
# TelemetryStore - sensor names
# ---------------------------------------------------------------------------

class TestSensorNames:

    async def test_returns_empty_when_no_readings(self, store):
        assert await store.get_sensor_names() == []

    async def test_returns_name_of_recorded_sensor(self, store):
        await store.record_sensor("swr", 1.8)
        assert await store.get_sensor_names() == ["swr"]

    async def test_deduplicates_multiple_readings_same_name(self, store):
        await store.record_sensor("swr", 1.8)
        await store.record_sensor("swr", 2.0)
        names = await store.get_sensor_names()
        assert names.count("swr") == 1

    async def test_returns_all_distinct_names(self, store):
        for name in ["voltage", "temp_f", "swr"]:
            await store.record_sensor(name, 1.0)
        assert set(await store.get_sensor_names()) == {"voltage", "temp_f", "swr"}

    async def test_names_are_sorted_alphabetically(self, store):
        for name in ["temp_f", "ant_relay_0", "swr", "voltage"]:
            await store.record_sensor(name, 1.0)
        names = await store.get_sensor_names()
        assert names == sorted(names)

    async def test_does_not_include_sensors_from_other_tables(self, store):
        await store.record_device_event("relay_toggle", "coax_switch")
        assert await store.get_sensor_names() == []


# ---------------------------------------------------------------------------
# TelemetryStore - sensor readings
# ---------------------------------------------------------------------------

class TestSensorReadings:

    async def test_record_and_retrieve(self, store):
        await store.record_sensor("swr", 1.8, unit="ratio", source="watt_meter")
        rows = await store.get_sensor_history("swr", since=0)
        assert len(rows) == 1
        assert rows[0].sensor_name == "swr"
        assert rows[0].value == pytest.approx(1.8)
        assert rows[0].unit == "ratio"
        assert rows[0].source == "watt_meter"

    async def test_history_filtered_by_name(self, store):
        await store.record_sensor("swr", 1.8)
        await store.record_sensor("voltage", 13.8)
        rows = await store.get_sensor_history("swr", since=0)
        assert all(r.sensor_name == "swr" for r in rows)

    async def test_history_filtered_by_time(self, store):
        past = time.time() - 10
        await store.record_sensor("swr", 1.8, ts=past)
        await store.record_sensor("swr", 2.0)   # now
        rows = await store.get_sensor_history("swr", since=time.time() - 1)
        assert len(rows) == 1
        assert rows[0].value == pytest.approx(2.0)

    async def test_limit_respected(self, store):
        for i in range(20):
            await store.record_sensor("temp", float(i))
        rows = await store.get_sensor_history("temp", since=0, limit=5)
        assert len(rows) == 5


# ---------------------------------------------------------------------------
# TelemetryStore - device events
# ---------------------------------------------------------------------------

class TestDeviceEvents:

    async def test_record_and_retrieve(self, store):
        await store.record_device_event(
            event_type="relay_toggle",
            device_key="gpio_relay_3",
            old_value="0",
            new_value="1",
            source="automation",
        )
        rows = await store.get_device_events()
        assert len(rows) == 1
        assert rows[0].event_type == "relay_toggle"
        assert rows[0].new_value == "1"

    async def test_filter_by_device_key(self, store):
        await store.record_device_event("relay_toggle", "gpio_relay_1")
        await store.record_device_event("relay_toggle", "gpio_relay_2")
        rows = await store.get_device_events(device_key="gpio_relay_1")
        assert len(rows) == 1
        assert rows[0].device_key == "gpio_relay_1"

    async def test_details_json_round_trip(self, store):
        await store.record_device_event(
            "relay_toggle", "gpio_relay_1",
            details={"reason": "swr_protection", "swr": 3.2},
        )
        rows = await store.get_device_events()
        import json
        details = json.loads(rows[0].details_json)
        assert details["swr"] == pytest.approx(3.2)


# ---------------------------------------------------------------------------
# TelemetryStore - automation events
# ---------------------------------------------------------------------------

class TestAutomationEvents:

    async def test_record_and_retrieve(self, store):
        await store.record_automation_event(
            rule_name="protect_high_swr",
            fired=True,
            tier="protection",
            priority=100,
            trigger_type="sensor_above",
        )
        rows = await store.get_automation_events()
        assert len(rows) == 1
        assert rows[0].rule_name == "protect_high_swr"
        assert rows[0].fired is True
        assert rows[0].tier == "protection"

    async def test_filter_by_rule_name(self, store):
        await store.record_automation_event("rule_a", fired=True)
        await store.record_automation_event("rule_b", fired=True)
        rows = await store.get_automation_events(rule_name="rule_a")
        assert len(rows) == 1

    async def test_context_json_round_trip(self, store):
        await store.record_automation_event(
            "rule_a", fired=True,
            context={"band": "20m", "frequency_hz": 14_225_000},
        )
        rows = await store.get_automation_events()
        import json
        ctx = json.loads(rows[0].context_json)
        assert ctx["band"] == "20m"


# ---------------------------------------------------------------------------
# TelemetryStore - application log
# ---------------------------------------------------------------------------

class TestApplicationLog:

    async def test_record_log(self, store):
        await store.record_log("ERROR", "automation.engine", "Something went wrong")
        # verify via direct query
        from sqlalchemy import select, text
        from telemetry.models import ApplicationLog
        async with store._session() as s:
            result = await s.execute(select(ApplicationLog))
            rows = list(result.scalars())
        assert len(rows) == 1
        assert rows[0].level == "ERROR"
        assert rows[0].logger == "automation.engine"


# ---------------------------------------------------------------------------
# TelemetryStore - prune
# ---------------------------------------------------------------------------

class TestPrune:

    async def test_prune_removes_old_sensor_readings(self, store):
        old_ts = time.time() - 100 * 86400  # 100 days ago
        await store.record_sensor("swr", 1.8, ts=old_ts)
        await store.record_sensor("swr", 2.0)   # recent
        await store.prune(sensor_readings_days=90)
        rows = await store.get_sensor_history("swr", since=0)
        assert len(rows) == 1
        assert rows[0].value == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# SensorRecorder
# ---------------------------------------------------------------------------

class TestSensorRecorder:

    async def test_publishes_to_store(self, store):
        reg = SensorRegistry()
        recorder = SensorRecorder(store, min_interval_s=0.0)
        recorder.attach(reg)
        reg.publish("swr", 1.8, unit="ratio", source="watt_meter")
        await asyncio.sleep(0)   # let create_task run
        rows = await store.get_sensor_history("swr", since=0)
        assert len(rows) == 1
        assert rows[0].value == pytest.approx(1.8)

    async def test_throttle_skips_rapid_publishes(self, store):
        reg = SensorRegistry()
        recorder = SensorRecorder(store, min_interval_s=60.0)
        recorder.attach(reg)
        reg.publish("swr", 1.8)
        reg.publish("swr", 2.0)
        reg.publish("swr", 2.5)
        await asyncio.sleep(0)
        rows = await store.get_sensor_history("swr", since=0)
        assert len(rows) == 1   # only the first write got through

    async def test_exclude_skips_sensor(self, store):
        reg = SensorRegistry()
        recorder = SensorRecorder(store, min_interval_s=0.0, exclude={"debug_temp"})
        recorder.attach(reg)
        reg.publish("debug_temp", 72.0)
        await asyncio.sleep(0)
        rows = await store.get_sensor_history("debug_temp", since=0)
        assert len(rows) == 0

    async def test_min_change_threshold(self, store):
        reg = SensorRegistry()
        recorder = SensorRecorder(store, min_interval_s=0.0, min_change=1.0)
        recorder.attach(reg)
        reg.publish("temp", 72.0)
        await asyncio.sleep(0)
        reg.publish("temp", 72.5)   # delta=0.5 - below threshold, but interval has passed
        await asyncio.sleep(0)
        rows = await store.get_sensor_history("temp", since=0)
        assert len(rows) == 1   # second write blocked by min_change


# ---------------------------------------------------------------------------
# load_telemetry config
# ---------------------------------------------------------------------------

class TestLoadTelemetry:

    def test_defaults(self):
        store, recorder, dcn_logger = load_telemetry()
        assert "station.db" in store._url
        assert recorder._min_interval == pytest.approx(1.0)
        assert dcn_logger is None   # off by default

    def test_custom_config(self):
        store, recorder, dcn_logger = load_telemetry(cfg={
            "telemetry": {
                "database": {"url": "sqlite+aiosqlite:///data/test.db"},
                "sensor_recording": {"min_interval_s": 5.0, "exclude": ["debug"]},
            }
        })
        assert "test.db" in store._url
        assert recorder._min_interval == pytest.approx(5.0)
        assert "debug" in recorder._exclude

    def test_dcn_logging_enabled(self):
        from telemetry.dcn_logger import DCNMessageLogger
        _, _, dcn_logger = load_telemetry(cfg={"telemetry": {"dcn_logging": {"enabled": True}}})
        assert isinstance(dcn_logger, DCNMessageLogger)

    def test_dcn_logging_disabled(self):
        _, _, dcn_logger = load_telemetry(cfg={"telemetry": {"dcn_logging": {"enabled": False}}})
        assert dcn_logger is None

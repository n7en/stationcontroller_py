"""Tests for automation/condition.py and automation/context.py."""
import pytest
from unittest.mock import patch

from automation.bands import BandRegistry
from automation.context import AutomationContext
from automation.condition import (
    Always, Never,
    FrequencyInBand, FrequencyInRange,
    SensorAbove, SensorBelow, SensorBetween, SensorPresent, SensorStale,
    RelayOn, RelayOff,
    RadioConnected, ModeIs, PTTActive,
    PTTDurationAbove, PTTDurationBelow,
    And, Or, Not,
    condition_from_config,
)
from radio.radio_state import RadioState
from sensors.sensor_registry import SensorRegistry


# ---------------------------------------------------------------------------
# Context factory helpers
# ---------------------------------------------------------------------------

def _ctx(
    freq: float = 14_200_000,
    mode: str = "USB",
    ptt: bool = False,
    connected: bool = True,
    sensors: dict | None = None,
) -> AutomationContext:
    from radio.radio_state import RadioMode
    state = RadioState(
        name="test",
        frequency_hz=freq,
        mode=RadioMode.from_str(mode),
        ptt=ptt,
        connected=connected,
    )
    registry = SensorRegistry()
    if sensors:
        for name, value in sensors.items():
            registry.publish(name, value)
    return AutomationContext(
        radio_state=state,
        registry=registry,
        band_registry=BandRegistry.amateur(),
    )


# ---------------------------------------------------------------------------
# AutomationContext
# ---------------------------------------------------------------------------

class TestAutomationContext:

    def test_sensor_returns_value(self):
        ctx = _ctx(sensors={"watt_meter_swr": 2.5})
        assert ctx.sensor("watt_meter_swr") == pytest.approx(2.5)

    def test_sensor_returns_default_when_missing(self):
        ctx = _ctx()
        assert ctx.sensor("missing", default=99.0) == pytest.approx(99.0)

    def test_current_band_name(self):
        ctx = _ctx(freq=14_200_000)
        assert ctx.current_band_name() == "20m"

    def test_current_band_none_when_out_of_band(self):
        ctx = _ctx(freq=10_000_000)
        assert ctx.current_band() is None
        assert ctx.current_band_name() is None

    def test_current_band_none_when_freq_is_none(self):
        state = RadioState(name="test", frequency_hz=None)
        ctx = AutomationContext(
            radio_state=state,
            registry=SensorRegistry(),
            band_registry=BandRegistry.amateur(),
        )
        assert ctx.current_band() is None

    def test_relay_on_true(self):
        ctx = _ctx(sensors={"gpio_relay_3": 1.0})
        assert ctx.relay_on("gpio_relay_3") is True

    def test_relay_on_false(self):
        ctx = _ctx(sensors={"gpio_relay_3": 0.0})
        assert ctx.relay_on("gpio_relay_3") is False

    def test_relay_on_none_when_absent(self):
        ctx = _ctx()
        assert ctx.relay_on("gpio_relay_3") is None


# ---------------------------------------------------------------------------
# Trivial conditions
# ---------------------------------------------------------------------------

class TestTrivialConditions:

    def test_always_true(self):
        assert Always().evaluate(_ctx()) is True

    def test_never_false(self):
        assert Never().evaluate(_ctx()) is False


# ---------------------------------------------------------------------------
# Frequency conditions
# ---------------------------------------------------------------------------

class TestFrequencyConditions:

    def test_frequency_in_band_true(self):
        assert FrequencyInBand("20m").evaluate(_ctx(freq=14_200_000)) is True

    def test_frequency_in_band_false_wrong_band(self):
        assert FrequencyInBand("40m").evaluate(_ctx(freq=14_200_000)) is False

    def test_frequency_in_band_false_out_of_band(self):
        assert FrequencyInBand("20m").evaluate(_ctx(freq=10_000_000)) is False

    def test_frequency_in_band_no_freq(self):
        ctx = AutomationContext(RadioState(name="test"), SensorRegistry(), BandRegistry.amateur())
        assert FrequencyInBand("20m").evaluate(ctx) is False

    def test_frequency_in_range_true(self):
        c = FrequencyInRange(14_000_000, 14_350_000)
        assert c.evaluate(_ctx(freq=14_200_000)) is True

    def test_frequency_in_range_false(self):
        c = FrequencyInRange(14_000_000, 14_350_000)
        assert c.evaluate(_ctx(freq=7_100_000)) is False

    def test_frequency_in_range_edge(self):
        c = FrequencyInRange(14_000_000, 14_350_000)
        assert c.evaluate(_ctx(freq=14_000_000)) is True
        assert c.evaluate(_ctx(freq=14_350_000)) is True


# ---------------------------------------------------------------------------
# Sensor conditions
# ---------------------------------------------------------------------------

class TestSensorConditions:

    def test_sensor_above_true(self):
        ctx = _ctx(sensors={"swr": 3.5})
        assert SensorAbove("swr", 3.0).evaluate(ctx) is True

    def test_sensor_above_false(self):
        ctx = _ctx(sensors={"swr": 2.0})
        assert SensorAbove("swr", 3.0).evaluate(ctx) is False

    def test_sensor_above_absent_sensor_is_0(self):
        ctx = _ctx()
        assert SensorAbove("missing", 0.5).evaluate(ctx) is False

    def test_sensor_below_true(self):
        ctx = _ctx(sensors={"voltage": 11.5})
        assert SensorBelow("voltage", 12.0).evaluate(ctx) is True

    def test_sensor_below_false(self):
        ctx = _ctx(sensors={"voltage": 13.8})
        assert SensorBelow("voltage", 12.0).evaluate(ctx) is False

    def test_sensor_between_true(self):
        ctx = _ctx(sensors={"temp": 75.0})
        assert SensorBetween("temp", 60.0, 80.0).evaluate(ctx) is True

    def test_sensor_between_false_above(self):
        ctx = _ctx(sensors={"temp": 90.0})
        assert SensorBetween("temp", 60.0, 80.0).evaluate(ctx) is False

    def test_sensor_between_false_below(self):
        ctx = _ctx(sensors={"temp": 50.0})
        assert SensorBetween("temp", 60.0, 80.0).evaluate(ctx) is False

    def test_sensor_present_true(self):
        ctx = _ctx(sensors={"swr": 1.5})
        assert SensorPresent("swr").evaluate(ctx) is True

    def test_sensor_present_false(self):
        ctx = _ctx()
        assert SensorPresent("swr").evaluate(ctx) is False

    def test_sensor_stale_absent(self):
        ctx = _ctx()
        assert SensorStale("swr").evaluate(ctx) is True

    def test_sensor_stale_fresh(self):
        ctx = _ctx(sensors={"swr": 2.0})
        assert SensorStale("swr", max_age_s=5.0).evaluate(ctx) is False


# ---------------------------------------------------------------------------
# Relay conditions
# ---------------------------------------------------------------------------

class TestRelayConditions:

    def test_relay_on_true(self):
        ctx = _ctx(sensors={"gpio_relay_3": 1.0})
        assert RelayOn("gpio_relay_3").evaluate(ctx) is True

    def test_relay_on_false_when_off(self):
        ctx = _ctx(sensors={"gpio_relay_3": 0.0})
        assert RelayOn("gpio_relay_3").evaluate(ctx) is False

    def test_relay_on_false_when_absent(self):
        ctx = _ctx()
        assert RelayOn("gpio_relay_3").evaluate(ctx) is False

    def test_relay_off_true(self):
        ctx = _ctx(sensors={"gpio_relay_3": 0.0})
        assert RelayOff("gpio_relay_3").evaluate(ctx) is True

    def test_relay_off_false_when_on(self):
        ctx = _ctx(sensors={"gpio_relay_3": 1.0})
        assert RelayOff("gpio_relay_3").evaluate(ctx) is False

    def test_relay_off_false_when_absent(self):
        ctx = _ctx()
        assert RelayOff("gpio_relay_3").evaluate(ctx) is False


# ---------------------------------------------------------------------------
# Radio state conditions
# ---------------------------------------------------------------------------

class TestRadioConditions:

    def test_radio_connected_true(self):
        assert RadioConnected().evaluate(_ctx(connected=True)) is True

    def test_radio_connected_false(self):
        assert RadioConnected().evaluate(_ctx(connected=False)) is False

    def test_mode_is_true(self):
        assert ModeIs("USB").evaluate(_ctx(mode="USB")) is True

    def test_mode_is_case_insensitive(self):
        assert ModeIs("usb").evaluate(_ctx(mode="USB")) is True

    def test_mode_is_false(self):
        assert ModeIs("CW").evaluate(_ctx(mode="USB")) is False

    def test_ptt_active_true(self):
        assert PTTActive().evaluate(_ctx(ptt=True)) is True

    def test_ptt_active_false(self):
        assert PTTActive().evaluate(_ctx(ptt=False)) is False


# ---------------------------------------------------------------------------
# PTT duration conditions
# ---------------------------------------------------------------------------

class TestPTTDurationConditions:

    def test_duration_above_false_when_ptt_off(self):
        c = PTTDurationAbove(10.0)
        assert c.evaluate(_ctx(ptt=False)) is False

    def test_duration_above_false_on_first_ptt_active_call(self):
        c = PTTDurationAbove(10.0)
        with patch("automation.condition.time") as mock_time:
            mock_time.time.return_value = 100.0
            result = c.evaluate(_ctx(ptt=True))
        assert result is False  # 0 seconds elapsed

    def test_duration_above_true_after_min_seconds(self):
        c = PTTDurationAbove(10.0)
        with patch("automation.condition.time") as mock_time:
            mock_time.time.return_value = 100.0
            c.evaluate(_ctx(ptt=True))   # starts timer
            mock_time.time.return_value = 111.0
            result = c.evaluate(_ctx(ptt=True))
        assert result is True

    def test_duration_above_resets_timer_on_ptt_off(self):
        c = PTTDurationAbove(10.0)
        with patch("automation.condition.time") as mock_time:
            mock_time.time.return_value = 100.0
            c.evaluate(_ctx(ptt=True))
            mock_time.time.return_value = 115.0
            c.evaluate(_ctx(ptt=False))   # PTT off — clears timer
            mock_time.time.return_value = 116.0
            c.evaluate(_ctx(ptt=True))   # PTT on again — timer restarts from 116
            mock_time.time.return_value = 118.0  # only 2s since restart
            result = c.evaluate(_ctx(ptt=True))
        assert result is False

    def test_duration_above_exact_boundary(self):
        c = PTTDurationAbove(10.0)
        with patch("automation.condition.time") as mock_time:
            mock_time.time.return_value = 100.0
            c.evaluate(_ctx(ptt=True))
            mock_time.time.return_value = 110.0  # exactly 10s
            result = c.evaluate(_ctx(ptt=True))
        assert result is True

    def test_duration_above_reset(self):
        c = PTTDurationAbove(10.0)
        with patch("automation.condition.time") as mock_time:
            mock_time.time.return_value = 100.0
            c.evaluate(_ctx(ptt=True))
        c.reset()
        assert c._ptt_active_since is None

    def test_duration_below_false_when_ptt_off(self):
        c = PTTDurationBelow(60.0)
        assert c.evaluate(_ctx(ptt=False)) is False

    def test_duration_below_true_immediately_on_ptt_active(self):
        c = PTTDurationBelow(60.0)
        with patch("automation.condition.time") as mock_time:
            mock_time.time.return_value = 100.0
            result = c.evaluate(_ctx(ptt=True))
        assert result is True  # 0 < 60

    def test_duration_below_false_after_max_seconds(self):
        c = PTTDurationBelow(60.0)
        with patch("automation.condition.time") as mock_time:
            mock_time.time.return_value = 100.0
            c.evaluate(_ctx(ptt=True))
            mock_time.time.return_value = 165.0   # 65s elapsed
            result = c.evaluate(_ctx(ptt=True))
        assert result is False

    def test_duration_below_resets_on_ptt_off(self):
        c = PTTDurationBelow(60.0)
        with patch("automation.condition.time") as mock_time:
            mock_time.time.return_value = 100.0
            c.evaluate(_ctx(ptt=True))
            mock_time.time.return_value = 170.0
            c.evaluate(_ctx(ptt=False))   # reset
            mock_time.time.return_value = 171.0
            result = c.evaluate(_ctx(ptt=True))   # fresh start — only 0s elapsed
        assert result is True

    def test_duration_above_from_config(self):
        c = condition_from_config({"type": "ptt_duration_above", "min_seconds": "10"})
        assert isinstance(c, PTTDurationAbove)
        assert c.min_seconds == pytest.approx(10.0)

    def test_duration_below_from_config(self):
        c = condition_from_config({"type": "ptt_duration_below", "max_seconds": "60"})
        assert isinstance(c, PTTDurationBelow)
        assert c.max_seconds == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# Logical combinators
# ---------------------------------------------------------------------------

class TestLogicalConditions:

    def test_and_both_true(self):
        c = And(Always(), Always())
        assert c.evaluate(_ctx()) is True

    def test_and_one_false(self):
        c = And(Always(), Never())
        assert c.evaluate(_ctx()) is False

    def test_and_short_circuits(self):
        c = And(Never(), Always())
        assert c.evaluate(_ctx()) is False

    def test_or_one_true(self):
        c = Or(Never(), Always())
        assert c.evaluate(_ctx()) is True

    def test_or_both_false(self):
        c = Or(Never(), Never())
        assert c.evaluate(_ctx()) is False

    def test_not_true(self):
        assert Not(Never()).evaluate(_ctx()) is True

    def test_not_false(self):
        assert Not(Always()).evaluate(_ctx()) is False

    def test_operator_and(self):
        c = Always() & Never()
        assert c.evaluate(_ctx()) is False

    def test_operator_or(self):
        c = Always() | Never()
        assert c.evaluate(_ctx()) is True

    def test_operator_invert(self):
        c = ~Never()
        assert c.evaluate(_ctx()) is True

    def test_nested_composition(self):
        # (ptt_active AND swr > 3) OR temp > 150
        c = (PTTActive() & SensorAbove("swr", 3.0)) | SensorAbove("temp", 150.0)
        ctx = _ctx(ptt=True, sensors={"swr": 3.5, "temp": 70.0})
        assert c.evaluate(ctx) is True
        ctx2 = _ctx(ptt=False, sensors={"swr": 3.5, "temp": 70.0})
        assert c.evaluate(ctx2) is False


# ---------------------------------------------------------------------------
# condition_from_config factory
# ---------------------------------------------------------------------------

class TestConditionFromConfig:

    def test_always(self):
        c = condition_from_config({"type": "always"})
        assert c.evaluate(_ctx()) is True

    def test_sensor_above(self):
        c = condition_from_config({"type": "sensor_above", "sensor": "swr", "threshold": "3.0"})
        ctx = _ctx(sensors={"swr": 4.0})
        assert c.evaluate(ctx) is True

    def test_and_compound(self):
        c = condition_from_config({
            "type": "and",
            "conditions": [
                {"type": "always"},
                {"type": "never"},
            ],
        })
        assert c.evaluate(_ctx()) is False

    def test_not_compound(self):
        c = condition_from_config({
            "type": "not",
            "condition": {"type": "always"},
        })
        assert c.evaluate(_ctx()) is False

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown condition type"):
            condition_from_config({"type": "magic_condition"})

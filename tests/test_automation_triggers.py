"""Tests for automation/trigger.py."""
import pytest
from datetime import datetime
from unittest.mock import patch

from automation.bands import BandRegistry
from automation.trigger import (
    SensorAboveTrigger, SensorBelowTrigger, SensorChangedTrigger,
    BandEnteredTrigger, BandExitedTrigger, BandChangedTrigger,
    PTTOnTrigger, PTTOffTrigger,
    RadioConnectedTrigger, RadioDisconnectedTrigger,
    ManualTrigger, TimeTrigger,
    trigger_from_config,
)
from radio.radio_state import RadioState
from sensors.sensor_registry import SensorRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reg(**sensors) -> SensorRegistry:
    r = SensorRegistry()
    for k, v in sensors.items():
        r.publish(k, v)
    return r


def _state(freq=14_200_000, ptt=False, connected=True) -> RadioState:
    return RadioState(name="test", frequency_hz=freq, ptt=ptt, connected=connected)


_bands = BandRegistry.amateur()


def _update(trigger, registry=None, state=None):
    return trigger.update(
        registry or SensorRegistry(),
        state or _state(),
        _bands,
    )


# ---------------------------------------------------------------------------
# SensorAboveTrigger
# ---------------------------------------------------------------------------

class TestSensorAboveTrigger:

    def test_does_not_fire_on_first_call_above(self):
        t = SensorAboveTrigger("swr", 3.0)
        assert _update(t, _reg(swr=4.0)) is None

    def test_does_not_fire_when_staying_above(self):
        t = SensorAboveTrigger("swr", 3.0)
        _update(t, _reg(swr=4.0))   # baseline
        assert _update(t, _reg(swr=5.0)) is None

    def test_fires_on_crossing_above(self):
        t = SensorAboveTrigger("swr", 3.0)
        _update(t, _reg(swr=2.0))   # baseline: below
        td = _update(t, _reg(swr=4.0))
        assert td is not None
        assert td.trigger_type == "sensor_above"
        assert td.sensor_name == "swr"
        assert td.to_value == pytest.approx(4.0)

    def test_does_not_fire_when_below(self):
        t = SensorAboveTrigger("swr", 3.0)
        _update(t, _reg(swr=2.0))
        assert _update(t, _reg(swr=2.5)) is None

    def test_fires_again_after_dip_below(self):
        t = SensorAboveTrigger("swr", 3.0)
        _update(t, _reg(swr=2.0))
        _update(t, _reg(swr=4.0))   # fires
        _update(t, _reg(swr=1.0))   # back below
        td = _update(t, _reg(swr=5.0))   # fires again
        assert td is not None

    def test_missing_sensor_treated_as_below(self):
        t = SensorAboveTrigger("swr", 3.0)
        _update(t, _reg())          # no sensor - baseline = False
        td = _update(t, _reg(swr=5.0))   # now appears above
        assert td is not None

    def test_reset_clears_state(self):
        t = SensorAboveTrigger("swr", 3.0)
        _update(t, _reg(swr=4.0))   # baseline
        t.reset()
        assert _update(t, _reg(swr=4.0)) is None  # re-establishes baseline

    def test_exact_threshold_is_not_above(self):
        t = SensorAboveTrigger("swr", 3.0)
        _update(t, _reg(swr=2.0))
        assert _update(t, _reg(swr=3.0)) is None   # not strictly above


class TestSensorAboveTriggerForSeconds:

    def test_does_not_fire_immediately_on_crossing(self):
        t = SensorAboveTrigger("swr", 3.0, for_seconds=5.0)
        _update(t, _reg(swr=2.0))   # baseline: below
        with patch("automation.trigger.time") as mock_time:
            mock_time.time.return_value = 100.0
            result = _update(t, _reg(swr=4.0))   # crosses above at t=100
        assert result is None

    def test_fires_after_sustained_period(self):
        t = SensorAboveTrigger("swr", 3.0, for_seconds=5.0)
        _update(t, _reg(swr=2.0))   # baseline
        with patch("automation.trigger.time") as mock_time:
            mock_time.time.return_value = 100.0
            _update(t, _reg(swr=4.0))   # crossing at t=100
            mock_time.time.return_value = 106.0  # 6s elapsed
            td = _update(t, _reg(swr=4.0))
        assert td is not None
        assert td.trigger_type == "sensor_above"

    def test_does_not_refire_while_still_above(self):
        t = SensorAboveTrigger("swr", 3.0, for_seconds=5.0)
        _update(t, _reg(swr=2.0))
        with patch("automation.trigger.time") as mock_time:
            mock_time.time.return_value = 100.0
            _update(t, _reg(swr=4.0))   # crossing
            mock_time.time.return_value = 106.0
            _update(t, _reg(swr=4.0))   # fires
            mock_time.time.return_value = 110.0
            result = _update(t, _reg(swr=4.0))  # still above - should not refire
        assert result is None

    def test_resets_timer_on_dip_below(self):
        t = SensorAboveTrigger("swr", 3.0, for_seconds=5.0)
        _update(t, _reg(swr=2.0))   # baseline
        with patch("automation.trigger.time") as mock_time:
            mock_time.time.return_value = 100.0
            _update(t, _reg(swr=4.0))   # crosses at t=100
            mock_time.time.return_value = 103.0
            _update(t, _reg(swr=2.0))   # dips below - timer resets
            mock_time.time.return_value = 104.0
            _update(t, _reg(swr=4.0))   # crosses again at t=104
            mock_time.time.return_value = 108.0  # only 4s since re-crossing
            result = _update(t, _reg(swr=4.0))
        assert result is None

    def test_fires_again_after_dip_and_sustained(self):
        t = SensorAboveTrigger("swr", 3.0, for_seconds=5.0)
        _update(t, _reg(swr=2.0))
        with patch("automation.trigger.time") as mock_time:
            mock_time.time.return_value = 100.0
            _update(t, _reg(swr=4.0))
            mock_time.time.return_value = 106.0
            _update(t, _reg(swr=4.0))   # first fire
            mock_time.time.return_value = 107.0
            _update(t, _reg(swr=2.0))   # dip
            mock_time.time.return_value = 108.0
            _update(t, _reg(swr=4.0))   # re-crossing
            mock_time.time.return_value = 114.0
            td = _update(t, _reg(swr=4.0))  # fires again after 6s sustained
        assert td is not None

    def test_for_seconds_in_config(self):
        t = trigger_from_config({"type": "sensor_above", "sensor": "swr", "threshold": "3.0", "for_seconds": "5.0"})
        assert isinstance(t, SensorAboveTrigger)
        assert t.for_seconds == pytest.approx(5.0)

    def test_for_seconds_defaults_to_zero_in_config(self):
        t = trigger_from_config({"type": "sensor_above", "sensor": "swr", "threshold": "3.0"})
        assert t.for_seconds == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# SensorBelowTrigger
# ---------------------------------------------------------------------------

class TestSensorBelowTrigger:

    def test_does_not_fire_on_first_call(self):
        t = SensorBelowTrigger("voltage", 12.0)
        assert _update(t, _reg(voltage=11.0)) is None

    def test_fires_on_crossing_below(self):
        t = SensorBelowTrigger("voltage", 12.0)
        _update(t, _reg(voltage=13.8))   # baseline: above
        td = _update(t, _reg(voltage=11.5))
        assert td is not None
        assert td.trigger_type == "sensor_below"
        assert td.to_value == pytest.approx(11.5)

    def test_does_not_fire_when_above(self):
        t = SensorBelowTrigger("voltage", 12.0)
        _update(t, _reg(voltage=11.0))
        assert _update(t, _reg(voltage=13.8)) is None

    def test_exact_threshold_is_not_below(self):
        t = SensorBelowTrigger("voltage", 12.0)
        _update(t, _reg(voltage=13.0))
        assert _update(t, _reg(voltage=12.0)) is None


class TestSensorBelowTriggerForSeconds:

    def test_does_not_fire_immediately_on_crossing(self):
        t = SensorBelowTrigger("voltage", 12.0, for_seconds=5.0)
        _update(t, _reg(voltage=13.8))   # baseline: above
        with patch("automation.trigger.time") as mock_time:
            mock_time.time.return_value = 100.0
            result = _update(t, _reg(voltage=11.5))   # crosses below at t=100
        assert result is None

    def test_fires_after_sustained_period(self):
        t = SensorBelowTrigger("voltage", 12.0, for_seconds=5.0)
        _update(t, _reg(voltage=13.8))   # baseline
        with patch("automation.trigger.time") as mock_time:
            mock_time.time.return_value = 100.0
            _update(t, _reg(voltage=11.5))   # crossing at t=100
            mock_time.time.return_value = 106.0
            td = _update(t, _reg(voltage=11.5))
        assert td is not None
        assert td.trigger_type == "sensor_below"

    def test_resets_timer_on_rise_above(self):
        t = SensorBelowTrigger("voltage", 12.0, for_seconds=5.0)
        _update(t, _reg(voltage=13.8))   # baseline
        with patch("automation.trigger.time") as mock_time:
            mock_time.time.return_value = 100.0
            _update(t, _reg(voltage=11.5))   # crosses at t=100
            mock_time.time.return_value = 103.0
            _update(t, _reg(voltage=13.8))   # rises above - resets timer
            mock_time.time.return_value = 104.0
            _update(t, _reg(voltage=11.5))   # crosses again at t=104
            mock_time.time.return_value = 108.0   # only 4s since re-crossing
            result = _update(t, _reg(voltage=11.5))
        assert result is None

    def test_for_seconds_in_config(self):
        t = trigger_from_config({"type": "sensor_below", "sensor": "voltage", "threshold": "12.0", "for_seconds": "5.0"})
        assert isinstance(t, SensorBelowTrigger)
        assert t.for_seconds == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# SensorChangedTrigger
# ---------------------------------------------------------------------------

class TestSensorChangedTrigger:

    def test_does_not_fire_on_first_call(self):
        t = SensorChangedTrigger("temp")
        assert _update(t, _reg(temp=72.0)) is None

    def test_fires_when_value_changes(self):
        t = SensorChangedTrigger("temp")
        _update(t, _reg(temp=72.0))
        td = _update(t, _reg(temp=75.0))
        assert td is not None
        assert td.from_value == pytest.approx(72.0)
        assert td.to_value == pytest.approx(75.0)

    def test_does_not_fire_when_value_unchanged(self):
        t = SensorChangedTrigger("temp")
        _update(t, _reg(temp=72.0))
        assert _update(t, _reg(temp=72.0)) is None

    def test_min_delta_respected(self):
        t = SensorChangedTrigger("temp", min_delta=2.0)
        _update(t, _reg(temp=72.0))
        assert _update(t, _reg(temp=73.0)) is None   # delta=1, below min
        td = _update(t, _reg(temp=75.5))              # delta=2.5, above min
        assert td is not None

    def test_does_not_fire_when_sensor_absent(self):
        t = SensorChangedTrigger("temp")
        assert _update(t, _reg()) is None


# ---------------------------------------------------------------------------
# Band triggers
# ---------------------------------------------------------------------------

class TestBandEnteredTrigger:

    def test_does_not_fire_on_first_call_in_band(self):
        t = BandEnteredTrigger("20m")
        assert _update(t, state=_state(freq=14_200_000)) is None

    def test_fires_on_entering_band(self):
        t = BandEnteredTrigger("20m")
        _update(t, state=_state(freq=7_100_000))    # baseline: 40m
        td = _update(t, state=_state(freq=14_200_000))
        assert td is not None
        assert td.trigger_type == "band_entered"
        assert td.to_band == "20m"

    def test_does_not_fire_when_already_in_band(self):
        t = BandEnteredTrigger("20m")
        _update(t, state=_state(freq=14_200_000))   # baseline
        assert _update(t, state=_state(freq=14_250_000)) is None

    def test_fires_again_after_leaving_and_reentering(self):
        t = BandEnteredTrigger("20m")
        _update(t, state=_state(freq=7_100_000))    # 40m
        _update(t, state=_state(freq=14_200_000))   # enters 20m - fires
        _update(t, state=_state(freq=7_100_000))    # back to 40m
        td = _update(t, state=_state(freq=14_200_000))
        assert td is not None


class TestBandExitedTrigger:

    def test_fires_on_leaving_band(self):
        t = BandExitedTrigger("20m")
        _update(t, state=_state(freq=14_200_000))   # baseline: in 20m
        td = _update(t, state=_state(freq=7_100_000))
        assert td is not None
        assert td.trigger_type == "band_exited"
        assert td.from_band == "20m"

    def test_does_not_fire_when_not_in_band(self):
        t = BandExitedTrigger("20m")
        _update(t, state=_state(freq=7_100_000))   # baseline: 40m, not in 20m
        assert _update(t, state=_state(freq=7_200_000)) is None


class TestBandChangedTrigger:

    def test_does_not_fire_on_first_call(self):
        t = BandChangedTrigger()
        assert _update(t, state=_state(freq=14_200_000)) is None

    def test_fires_on_band_change(self):
        t = BandChangedTrigger()
        _update(t, state=_state(freq=14_200_000))   # baseline: 20m
        td = _update(t, state=_state(freq=7_100_000))
        assert td is not None
        assert td.trigger_type == "band_changed"
        assert td.from_band == "20m"
        assert td.to_band == "40m"

    def test_fires_when_leaving_all_bands(self):
        t = BandChangedTrigger()
        _update(t, state=_state(freq=14_200_000))
        td = _update(t, state=_state(freq=10_500_000))  # no band
        assert td is not None
        assert td.to_band is None

    def test_does_not_fire_within_same_band(self):
        t = BandChangedTrigger()
        _update(t, state=_state(freq=14_000_000))
        assert _update(t, state=_state(freq=14_300_000)) is None


# ---------------------------------------------------------------------------
# PTT triggers
# ---------------------------------------------------------------------------

class TestPTTTriggers:

    def test_ptt_on_fires_on_transition(self):
        t = PTTOnTrigger()
        _update(t, state=_state(ptt=False))
        td = _update(t, state=_state(ptt=True))
        assert td is not None
        assert td.trigger_type == "ptt_on"

    def test_ptt_on_does_not_fire_when_staying_on(self):
        t = PTTOnTrigger()
        _update(t, state=_state(ptt=True))
        assert _update(t, state=_state(ptt=True)) is None

    def test_ptt_off_fires_on_transition(self):
        t = PTTOffTrigger()
        _update(t, state=_state(ptt=True))
        td = _update(t, state=_state(ptt=False))
        assert td is not None
        assert td.trigger_type == "ptt_off"

    def test_ptt_off_first_call_does_not_fire(self):
        t = PTTOffTrigger()
        assert _update(t, state=_state(ptt=False)) is None


# ---------------------------------------------------------------------------
# Radio connected triggers
# ---------------------------------------------------------------------------

class TestRadioConnectionTriggers:

    def test_connected_fires_on_connect(self):
        t = RadioConnectedTrigger()
        _update(t, state=_state(connected=False))
        td = _update(t, state=_state(connected=True))
        assert td is not None
        assert td.trigger_type == "radio_connected"

    def test_disconnected_fires_on_disconnect(self):
        t = RadioDisconnectedTrigger()
        _update(t, state=_state(connected=True))
        td = _update(t, state=_state(connected=False))
        assert td is not None
        assert td.trigger_type == "radio_disconnected"


# ---------------------------------------------------------------------------
# ManualTrigger
# ---------------------------------------------------------------------------

class TestManualTrigger:

    def test_never_fires_from_update(self):
        t = ManualTrigger()
        for _ in range(5):
            assert _update(t) is None


# ---------------------------------------------------------------------------
# trigger_from_config factory
# ---------------------------------------------------------------------------

class TestTriggerFromConfig:

    def test_sensor_above(self):
        t = trigger_from_config({"type": "sensor_above", "sensor": "swr", "threshold": "3.0"})
        assert isinstance(t, SensorAboveTrigger)

    def test_band_entered(self):
        t = trigger_from_config({"type": "band_entered", "band": "40m"})
        assert isinstance(t, BandEnteredTrigger)
        assert t.band_name == "40m"

    def test_manual(self):
        t = trigger_from_config({"type": "manual"})
        assert isinstance(t, ManualTrigger)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown trigger type"):
            trigger_from_config({"type": "magic"})

    def test_time(self):
        t = trigger_from_config({"type": "time", "time": "16:00"})
        assert isinstance(t, TimeTrigger)
        assert t._hour == 16
        assert t._minute == 0

    def test_time_with_days(self):
        t = trigger_from_config({"type": "time", "time": "16:00", "days": ["mon", "wed"]})
        assert t._days == {"mon", "wed"}


# ---------------------------------------------------------------------------
# TimeTrigger
# ---------------------------------------------------------------------------

def _at(dt: datetime):
    """Context manager: freeze automation.trigger.datetime.now() to dt."""
    return patch("automation.trigger.datetime", wraps=datetime.__class__)


class TestTimeTrigger:

    def _update_at(self, trigger, dt: datetime):
        with patch("automation.trigger.datetime") as mock_dt:
            mock_dt.now.return_value = dt
            return trigger.update(SensorRegistry(), None, None)

    def test_does_not_fire_when_hour_differs(self):
        t = TimeTrigger("16:00")
        result = self._update_at(t, datetime(2024, 1, 15, 15, 0, 0))
        assert result is None

    def test_does_not_fire_when_minute_differs(self):
        t = TimeTrigger("16:00")
        result = self._update_at(t, datetime(2024, 1, 15, 16, 1, 0))
        assert result is None

    def test_fires_at_scheduled_time(self):
        t = TimeTrigger("16:00")
        td = self._update_at(t, datetime(2024, 1, 15, 16, 0, 30))
        assert td is not None
        assert td.trigger_type == "time"

    def test_does_not_refire_same_minute(self):
        t = TimeTrigger("16:00")
        self._update_at(t, datetime(2024, 1, 15, 16, 0, 0))   # fires
        result = self._update_at(t, datetime(2024, 1, 15, 16, 0, 45))  # same minute
        assert result is None

    def test_fires_again_next_day(self):
        t = TimeTrigger("16:00")
        self._update_at(t, datetime(2024, 1, 15, 16, 0, 0))   # fires today
        td = self._update_at(t, datetime(2024, 1, 16, 16, 0, 0))  # fires tomorrow
        assert td is not None

    def test_day_filter_fires_on_matching_day(self):
        # 2024-01-15 is a Monday
        t = TimeTrigger("16:00", days=["mon"])
        td = self._update_at(t, datetime(2024, 1, 15, 16, 0, 0))
        assert td is not None

    def test_day_filter_blocks_non_matching_day(self):
        # 2024-01-15 is a Monday - trigger restricted to Wednesday
        t = TimeTrigger("16:00", days=["wed"])
        result = self._update_at(t, datetime(2024, 1, 15, 16, 0, 0))
        assert result is None

    def test_day_filter_case_insensitive(self):
        t = TimeTrigger("16:00", days=["MON", "WED"])
        td = self._update_at(t, datetime(2024, 1, 15, 16, 0, 0))  # Monday
        assert td is not None

    def test_reset_allows_refire(self):
        t = TimeTrigger("16:00")
        self._update_at(t, datetime(2024, 1, 15, 16, 0, 0))   # fires
        t.reset()
        td = self._update_at(t, datetime(2024, 1, 15, 16, 0, 0))  # fires again
        assert td is not None

    def test_no_days_fires_every_day(self):
        t = TimeTrigger("08:00")
        for day in range(15, 22):  # one week
            t.reset()
            td = self._update_at(t, datetime(2024, 1, day, 8, 0, 0))
            assert td is not None, f"should fire on day {day}"

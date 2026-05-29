"""Tests for radio/radio_state.py - RadioState dataclass and RadioMode enum."""
import pytest
from radio.radio_state import RadioMode, RadioState


class TestRadioMode:

    def test_from_str_known_modes(self):
        for mode in RadioMode:
            if mode != RadioMode.UNKNOWN:
                assert RadioMode.from_str(mode.value) == mode

    def test_from_str_case_insensitive(self):
        assert RadioMode.from_str("usb") == RadioMode.USB
        assert RadioMode.from_str("Cw") == RadioMode.CW
        assert RadioMode.from_str("PKTUSB") == RadioMode.PKTUSB

    def test_from_str_unknown_returns_unknown(self):
        assert RadioMode.from_str("INVALID") == RadioMode.UNKNOWN
        assert RadioMode.from_str("") == RadioMode.UNKNOWN
        assert RadioMode.from_str("WSJT") == RadioMode.UNKNOWN

    def test_mode_is_string_enum(self):
        assert RadioMode.USB == "USB"
        assert RadioMode.LSB == "LSB"


class TestRadioStateDefaults:

    def test_required_name(self):
        s = RadioState(name="rig1")
        assert s.name == "rig1"

    def test_numeric_defaults_are_none(self):
        s = RadioState(name="test")
        assert s.frequency_hz is None
        assert s.bandwidth_hz is None
        assert s.signal_strength is None
        assert s.rf_power is None
        assert s.split_freq_hz is None

    def test_bool_defaults(self):
        s = RadioState(name="test")
        assert s.split is False
        assert s.ptt is False
        assert s.connected is False

    def test_string_defaults_are_none(self):
        s = RadioState(name="test")
        assert s.mode is None
        assert s.vfo is None
        assert s.info is None

    def test_updated_at_is_set(self):
        import time
        before = time.time()
        s = RadioState(name="test")
        assert s.updated_at >= before


class TestRadioStateDiff:

    def test_diff_empty_when_equal(self):
        s = RadioState(name="test", frequency_hz=14_200_000.0, ptt=False)
        assert s.diff(s) == {}

    def test_diff_detects_frequency_change(self):
        a = RadioState(name="test", frequency_hz=14_200_000.0)
        b = RadioState(name="test", frequency_hz=7_100_000.0)
        d = a.diff(b)
        assert d == {"frequency_hz": 7_100_000.0}

    def test_diff_detects_mode_change(self):
        a = RadioState(name="test", mode=RadioMode.USB)
        b = RadioState(name="test", mode=RadioMode.LSB)
        d = a.diff(b)
        assert "mode" in d
        assert d["mode"] == RadioMode.LSB

    def test_diff_detects_multiple_changes(self):
        a = RadioState(name="test", frequency_hz=14_200_000.0, ptt=False, connected=True)
        b = RadioState(name="test", frequency_hz=21_300_000.0, ptt=True, connected=True)
        d = a.diff(b)
        assert "frequency_hz" in d
        assert "ptt" in d
        assert "connected" not in d  # unchanged

    def test_diff_does_not_include_unchanged_fields(self):
        a = RadioState(name="test", frequency_hz=14_200_000.0, ptt=False)
        b = RadioState(name="test", frequency_hz=14_200_000.0, ptt=True)
        d = a.diff(b)
        assert "frequency_hz" not in d
        assert d["ptt"] is True

    def test_diff_tracks_connected(self):
        a = RadioState(name="test", connected=True)
        b = RadioState(name="test", connected=False)
        assert a.diff(b) == {"connected": False}

    def test_diff_tracks_rf_power(self):
        a = RadioState(name="test", rf_power=1.0)
        b = RadioState(name="test", rf_power=0.5)
        d = a.diff(b)
        assert d == {"rf_power": 0.5}

    def test_diff_tracks_split(self):
        a = RadioState(name="test", split=False, split_freq_hz=None)
        b = RadioState(name="test", split=True, split_freq_hz=14_225_000.0)
        d = a.diff(b)
        assert "split" in d
        assert "split_freq_hz" in d

    def test_diff_is_asymmetric(self):
        a = RadioState(name="test", frequency_hz=14_200_000.0)
        b = RadioState(name="test", frequency_hz=7_100_000.0)
        d_ab = a.diff(b)
        d_ba = b.diff(a)
        assert d_ab["frequency_hz"] == 7_100_000.0
        assert d_ba["frequency_hz"] == 14_200_000.0


class TestRadioStateCopy:

    def test_copy_is_independent(self):
        s = RadioState(name="test", frequency_hz=14_200_000.0)
        c = s.copy()
        c.frequency_hz = 7_100_000.0
        assert s.frequency_hz == 14_200_000.0

    def test_copy_preserves_all_fields(self):
        s = RadioState(
            name="test",
            frequency_hz=14_200_000.0,
            mode=RadioMode.USB,
            bandwidth_hz=2400.0,
            vfo="VFOA",
            ptt=False,
            split=True,
            split_freq_hz=14_225_000.0,
            signal_strength=-14.0,
            rf_power=0.5,
            connected=True,
            info="IC-7300",
        )
        c = s.copy()
        assert c.frequency_hz == s.frequency_hz
        assert c.mode == s.mode
        assert c.bandwidth_hz == s.bandwidth_hz
        assert c.vfo == s.vfo
        assert c.split is s.split
        assert c.split_freq_hz == s.split_freq_hz
        assert c.signal_strength == s.signal_strength
        assert c.rf_power == s.rf_power
        assert c.connected == s.connected
        assert c.info == s.info

"""
Hardware integration tests for radio control via rigctld.

Prerequisites:
  1. rigctld must be running and connected to a physical radio.
  2. Add a 'radio' section to config/hardware_test_config.yaml (see below).
  3. Run with: pytest --hardware -m hardware

Example hardware_test_config.yaml radio section:

    radio:
      enabled: true
      rigctld_host: localhost
      rigctld_port: 4532
      response_timeout: 5.0
      poll_interval_s: 0.5
      expected_min_freq_hz: 1_000_000       # 1 MHz - basic sanity bound
      expected_max_freq_hz: 30_000_000      # 30 MHz - HF upper bound

CAUTION:
  - These tests never key the transmitter (PTT is never set to True).
  - Frequency is restored to its original value after set_frequency tests.
  - RF power is restored after set_level tests.
"""
import asyncio
import pytest

from radio.backends.base import RadioBackendError
from radio.radio_state import RadioMode


pytestmark = pytest.mark.hardware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _min_freq(cfg: dict) -> float:
    return float(cfg.get("expected_min_freq_hz", 1_000_000))


def _max_freq(cfg: dict) -> float:
    return float(cfg.get("expected_max_freq_hz", 30_000_000_000))


# ---------------------------------------------------------------------------
# Connectivity
# ---------------------------------------------------------------------------

class TestHwConnectivity:

    async def test_connected_after_fixture(self, radio_interface):
        assert radio_interface.state.connected is True

    async def test_get_info_returns_nonempty_string(self, radio_interface):
        info = await radio_interface._backend.get_info()
        assert isinstance(info, str)
        assert len(info) > 0

    async def test_state_has_info_after_connect(self, radio_interface):
        assert radio_interface.state.info is not None
        assert len(radio_interface.state.info) > 0


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------

class TestHwFrequency:

    async def test_get_frequency_returns_plausible_value(
        self, radio_interface, radio_hw_config
    ):
        freq = await radio_interface.get_frequency()
        assert _min_freq(radio_hw_config) <= freq <= _max_freq(radio_hw_config), (
            f"Frequency {freq} Hz is outside expected range"
        )

    async def test_set_get_frequency_round_trip(self, radio_interface):
        original = await radio_interface.get_frequency()
        target = 14_200_000.0
        try:
            await radio_interface.set_frequency(target)
            read_back = await radio_interface.get_frequency()
            assert abs(read_back - target) < 1.0, (
                f"Expected {target} Hz, got {read_back} Hz"
            )
        finally:
            await radio_interface.set_frequency(original)

    async def test_set_frequency_updates_state(self, radio_interface):
        original = await radio_interface.get_frequency()
        target = 7_100_000.0
        try:
            await radio_interface.set_frequency(target)
            assert pytest.approx(radio_interface.state.frequency_hz, abs=1.0) == target
        finally:
            await radio_interface.set_frequency(original)


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------

class TestHwMode:

    async def test_get_mode_returns_known_mode(self, radio_interface):
        mode_str, bw = await radio_interface.get_mode()
        mode = RadioMode.from_str(mode_str)
        assert mode != RadioMode.UNKNOWN, (
            f"Radio returned unrecognised mode string: '{mode_str}'"
        )

    async def test_get_mode_returns_positive_bandwidth(self, radio_interface):
        _mode, bw = await radio_interface.get_mode()
        assert bw >= 0.0


# ---------------------------------------------------------------------------
# PTT - read only (never transmit in automated tests)
# ---------------------------------------------------------------------------

class TestHwPtt:

    async def test_get_ptt_is_false_at_rest(self, radio_interface):
        ptt = await radio_interface.get_ptt()
        assert ptt is False, (
            "Radio is transmitting at test start - aborting for safety"
        )


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

class TestHwLevels:

    async def test_get_signal_strength_returns_number(self, radio_interface):
        try:
            strength = await radio_interface.get_level("STRENGTH")
            assert isinstance(strength, float)
        except RadioBackendError:
            pytest.skip("Radio does not support STRENGTH level")

    async def test_get_rfpower_in_valid_range(self, radio_interface):
        try:
            power = await radio_interface.get_level("RFPOWER")
            assert 0.0 <= power <= 1.0, f"RFPOWER {power} outside [0.0, 1.0]"
        except RadioBackendError:
            pytest.skip("Radio does not support RFPOWER level")

    async def test_set_rfpower_round_trip(self, radio_interface):
        try:
            original = await radio_interface.get_level("RFPOWER")
        except RadioBackendError:
            pytest.skip("Radio does not support RFPOWER level")

        target = max(0.1, original * 0.9)  # slightly below current, never zero
        try:
            await radio_interface.set_level("RFPOWER", target)
            read_back = await radio_interface.get_level("RFPOWER")
            assert abs(read_back - target) < 0.05, (
                f"Expected RFPOWER ~{target:.2f}, got {read_back:.2f}"
            )
        finally:
            await radio_interface.set_level("RFPOWER", original)


# ---------------------------------------------------------------------------
# Poll loop
# ---------------------------------------------------------------------------

class TestHwPollLoop:

    async def test_poll_loop_populates_state(self, radio_interface):
        await radio_interface.start()
        try:
            await asyncio.sleep(1.5)   # two poll cycles at default 0.5 s
            assert radio_interface.state.frequency_hz is not None
            assert radio_interface.state.mode is not None
            assert radio_interface.state.connected is True
        finally:
            await radio_interface.stop()

    async def test_poll_loop_fires_callback(self, radio_interface):
        changes = []
        radio_interface.on_state_change(lambda s, d: changes.append(d))

        await radio_interface.start()
        try:
            await asyncio.sleep(1.5)
        finally:
            await radio_interface.stop()

        assert len(changes) > 0, "No state change callbacks fired during polling"

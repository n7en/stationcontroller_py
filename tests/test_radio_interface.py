"""
Tests for radio/radio_interface.py.

A FakeBackend implements RadioBackend with in-memory state so no TCP
server or hamlib is needed.
"""
import asyncio
from typing import Optional
import pytest

from radio.backends.base import RadioBackend, RadioBackendError
from radio.radio_interface import RadioInterface
from radio.radio_state import RadioMode, RadioState


# ---------------------------------------------------------------------------
# Fake backend
# ---------------------------------------------------------------------------

class FakeBackend(RadioBackend):
    """In-memory RadioBackend for testing."""

    def __init__(self):
        self._connected = False
        self.freq = 14_200_000.0
        self.mode = "USB"
        self.bw = 2400.0
        self.vfo = "VFOA"
        self.ptt = False
        self.split = False
        self.split_freq: Optional[float] = None
        self.levels = {"STRENGTH": -14.0, "RFPOWER": 1.0, "AF": 0.8}
        self.info_str = "Fake Radio"
        self.connect_count = 0

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True
        self.connect_count += 1

    async def disconnect(self) -> None:
        self._connected = False

    async def get_frequency(self) -> float:
        return self.freq

    async def set_frequency(self, hz: float) -> None:
        self.freq = hz

    async def get_mode(self) -> tuple[str, float]:
        return self.mode, self.bw

    async def set_mode(self, mode: str, bandwidth_hz: float = 0) -> None:
        self.mode = mode
        if bandwidth_hz:
            self.bw = bandwidth_hz

    async def get_vfo(self) -> str:
        return self.vfo

    async def set_vfo(self, vfo: str) -> None:
        self.vfo = vfo

    async def get_ptt(self) -> bool:
        return self.ptt

    async def set_ptt(self, transmit: bool) -> None:
        self.ptt = transmit

    async def get_split(self) -> tuple[bool, Optional[float]]:
        return self.split, self.split_freq

    async def set_split(self, active: bool, tx_hz: Optional[float] = None) -> None:
        self.split = active
        self.split_freq = tx_hz

    async def get_level(self, level_name: str) -> float:
        if level_name not in self.levels:
            raise RadioBackendError(f"Unknown level: {level_name}")
        return self.levels[level_name]

    async def set_level(self, level_name: str, value: float) -> None:
        self.levels[level_name] = value

    async def get_info(self) -> str:
        return self.info_str


class _DisconnectingBackend(FakeBackend):
    """Raises RadioBackendError on the next get_full_state call and marks itself disconnected."""

    def __init__(self):
        super().__init__()
        self.fail_once = False

    async def get_full_state(self) -> dict:
        if self.fail_once:
            self.fail_once = False
            self._connected = False
            raise RadioBackendError("simulated connection loss")
        return await super().get_full_state()


def _iface(backend: RadioBackend, poll_s: float = 0.05) -> RadioInterface:
    return RadioInterface("test", backend, poll_interval_s=poll_s, reconnect_delay_s=0.1)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:

    async def test_connect_sets_state_connected(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        assert iface.state.connected is True
        await iface.disconnect()

    async def test_connect_fetches_info(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        assert iface.state.info == "Fake Radio"
        await iface.disconnect()

    async def test_disconnect_sets_state_disconnected(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.disconnect()
        assert iface.state.connected is False

    async def test_start_creates_poll_task(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.start()
        assert iface._task is not None
        assert not iface._task.done()
        await iface.stop()
        await iface.disconnect()

    async def test_stop_cancels_poll_task(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.start()
        await iface.stop()
        assert iface._task is None or iface._task.done()
        await iface.disconnect()

    async def test_context_manager_lifecycle(self):
        b = FakeBackend()
        iface = _iface(b)
        async with iface:
            assert iface.state.connected is True
            assert iface._task is not None
        assert iface.state.connected is False

    async def test_start_twice_creates_only_one_task(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.start()
        task1 = iface._task
        await iface.start()
        assert iface._task is task1
        await iface.stop()
        await iface.disconnect()


# ---------------------------------------------------------------------------
# Poll loop - state updates
# ---------------------------------------------------------------------------

class TestPollLoop:

    async def test_poll_populates_frequency(self):
        b = FakeBackend()
        b.freq = 21_300_000.0
        async with _iface(b):
            await asyncio.sleep(0.15)
            assert pytest.approx(21_300_000.0) == pytest.approx(
                _iface(b).state.frequency_hz or 21_300_000.0
            )

    async def test_poll_updates_state_from_backend(self):
        b = FakeBackend()
        iface = _iface(b)
        async with iface:
            await asyncio.sleep(0.15)
            assert iface.state.frequency_hz == b.freq
            assert iface.state.vfo == b.vfo

    async def test_poll_fires_callback_on_change(self):
        b = FakeBackend()
        iface = _iface(b)
        changes = []
        iface.on_state_change(lambda s, d: changes.append(dict(d)))

        async with iface:
            await asyncio.sleep(0.15)          # let initial poll settle
            b.freq = 7_100_000.0
            await asyncio.sleep(0.15)          # wait for change detection

        freq_diffs = [c for c in changes if "frequency_hz" in c]
        assert len(freq_diffs) >= 1
        assert freq_diffs[-1]["frequency_hz"] == 7_100_000.0

    async def test_poll_does_not_fire_callback_when_nothing_changed(self):
        b = FakeBackend()
        iface = _iface(b)
        changes = []
        iface.on_state_change(lambda s, d: changes.append(dict(d)))

        async with iface:
            await asyncio.sleep(0.15)   # initial poll fires connected=True change
            snapshot = len(changes)
            await asyncio.sleep(0.15)   # nothing changes - no more callbacks
            assert len(changes) == snapshot

    async def test_async_callback_is_awaited(self):
        b = FakeBackend()
        iface = _iface(b)
        results = []

        @iface.on_state_change
        async def handler(state, diff):
            results.append(diff)

        async with iface:
            await asyncio.sleep(0.15)
            b.freq = 3_700_000.0
            await asyncio.sleep(0.15)

        assert any("frequency_hz" in r for r in results)

    async def test_callback_receives_state_reference(self):
        b = FakeBackend()
        iface = _iface(b)
        captured_states = []
        iface.on_state_change(lambda s, d: captured_states.append(s))

        async with iface:
            await asyncio.sleep(0.15)
            b.freq = 14_300_000.0
            await asyncio.sleep(0.15)

        assert captured_states[-1] is iface.state


# ---------------------------------------------------------------------------
# Poll loop - connection loss and reconnect
# ---------------------------------------------------------------------------

class TestReconnect:

    async def test_poll_failure_marks_state_disconnected(self):
        b = _DisconnectingBackend()
        iface = _iface(b, poll_s=0.05)
        changes = []
        iface.on_state_change(lambda s, d: changes.append(dict(d)))

        async with iface:
            b.fail_once = True
            await asyncio.sleep(0.2)

        disconnected_events = [c for c in changes if c.get("connected") is False]
        assert len(disconnected_events) >= 1

    async def test_reconnect_restores_state_connected(self):
        b = _DisconnectingBackend()
        iface = RadioInterface(
            "test", b, poll_interval_s=0.05, reconnect_delay_s=0.05
        )
        async with iface:
            b.fail_once = True
            await asyncio.sleep(0.5)   # time for: fail -> reconnect -> next poll
            assert iface.state.connected is True

    async def test_reconnect_calls_backend_connect_again(self):
        b = _DisconnectingBackend()
        iface = RadioInterface(
            "test", b, poll_interval_s=0.05, reconnect_delay_s=0.05
        )
        initial_connects = b.connect_count
        async with iface:
            b.fail_once = True
            await asyncio.sleep(0.5)
        assert b.connect_count > initial_connects


# ---------------------------------------------------------------------------
# Immediate state update on set_ methods
# ---------------------------------------------------------------------------

class TestSetMethods:

    async def test_set_frequency_updates_state_immediately(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.set_frequency(7_100_000)
        assert iface.state.frequency_hz == 7_100_000.0
        await iface.disconnect()

    async def test_set_mode_updates_state_immediately(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.set_mode("CW", 500)
        assert iface.state.mode == RadioMode.CW
        assert iface.state.bandwidth_hz == 500.0
        await iface.disconnect()

    async def test_set_ptt_updates_state_immediately(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.set_ptt(True)
        assert iface.state.ptt is True
        await iface.set_ptt(False)
        assert iface.state.ptt is False
        await iface.disconnect()

    async def test_set_level_rfpower_updates_rf_power(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.set_level("RFPOWER", 0.5)
        assert iface.state.rf_power == 0.5
        await iface.disconnect()

    async def test_set_level_strength_updates_signal_strength(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.set_level("STRENGTH", -20.0)
        assert iface.state.signal_strength == -20.0
        await iface.disconnect()

    async def test_set_split_updates_state_immediately(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.set_split(True, 14_225_000)
        assert iface.state.split is True
        assert iface.state.split_freq_hz == 14_225_000.0
        await iface.disconnect()

    async def test_set_vfo_updates_state_immediately(self):
        b = FakeBackend()
        iface = _iface(b)
        await iface.connect()
        await iface.set_vfo("VFOB")
        assert iface.state.vfo == "VFOB"
        await iface.disconnect()

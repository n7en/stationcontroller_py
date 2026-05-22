"""
Tests for radio/backends/rigctld.py.

A lightweight in-process TCP server (_FakeRigctld) speaks the rigctld
text protocol so the backend can be exercised without a real radio or
hamlib installation.
"""
import asyncio
import pytest

from radio.backends.base import RadioBackendError
from radio.backends.rigctld import RigctldBackend


# ---------------------------------------------------------------------------
# Fake rigctld server
# ---------------------------------------------------------------------------

class _FakeRigctld:
    """Minimal rigctld-protocol TCP server."""

    def __init__(self):
        self.freq = 14_200_000.0
        self.mode = "USB"
        self.bw = 2400.0
        self.vfo = "VFOA"
        self.ptt = False
        self.split = False
        self.split_freq = 14_225_000.0
        self.levels = {
            "STRENGTH": -14.0,
            "RFPOWER": 1.0,
            "AF": 0.8,
            "SQL": 0.0,
        }
        self.info_str = "Fake Rig v1.0"
        self._server = None
        self.port: int = 0

    async def start(self):
        self._server = await asyncio.start_server(
            self._handle, "127.0.0.1", 0
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                cmd = line.decode().strip()
                response = self._dispatch(cmd)
                writer.write(response.encode())
                await writer.drain()
        except (ConnectionResetError, asyncio.CancelledError, OSError):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    def _dispatch(self, cmd: str) -> str:
        parts = cmd.split()
        if not parts:
            return "RPRT -1\n"
        op = parts[0]

        if op == r"\get_freq":
            return f"{int(self.freq)}\nRPRT 0\n"
        if op == r"\set_freq":
            self.freq = float(parts[1])
            return "RPRT 0\n"
        if op == r"\get_mode":
            return f"{self.mode}\n{int(self.bw)}\nRPRT 0\n"
        if op == r"\set_mode":
            self.mode = parts[1]
            self.bw = float(parts[2]) if len(parts) > 2 else 0.0
            return "RPRT 0\n"
        if op == r"\get_vfo":
            return f"{self.vfo}\nRPRT 0\n"
        if op == r"\set_vfo":
            self.vfo = parts[1]
            return "RPRT 0\n"
        if op == r"\get_ptt":
            return f"{'1' if self.ptt else '0'}\nRPRT 0\n"
        if op == r"\set_ptt":
            self.ptt = parts[1] != "0"
            return "RPRT 0\n"
        if op == r"\get_split_vfo":
            return f"{'1' if self.split else '0'}\nVFOB\nRPRT 0\n"
        if op == r"\set_split_vfo":
            self.split = parts[1] != "0"
            return "RPRT 0\n"
        if op == r"\get_split_freq":
            return f"{int(self.split_freq)}\nRPRT 0\n"
        if op == r"\set_split_freq":
            self.split_freq = float(parts[1])
            return "RPRT 0\n"
        if op == r"\get_level":
            val = self.levels.get(parts[1], 0.0)
            return f"{val}\nRPRT 0\n"
        if op == r"\set_level":
            self.levels[parts[1]] = float(parts[2])
            return "RPRT 0\n"
        if op == r"\get_info":
            return f"{self.info_str}\nRPRT 0\n"
        return "RPRT -1\n"


class _ErrorRigctld(_FakeRigctld):
    """Returns RPRT -1 for every command."""

    def _dispatch(self, cmd: str) -> str:
        return "RPRT -1\n"


class _DropRigctld(_FakeRigctld):
    """Accepts the TCP connection then immediately closes it."""

    async def _handle(self, reader, writer):
        try:
            writer.close()
            await writer.wait_closed()
        except OSError:
            pass


@pytest.fixture
async def rig():
    server = _FakeRigctld()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
async def error_rig():
    server = _ErrorRigctld()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
async def drop_rig():
    server = _DropRigctld()
    await server.start()
    yield server
    await server.stop()


def _make(server: _FakeRigctld) -> RigctldBackend:
    return RigctldBackend(host="127.0.0.1", port=server.port, timeout_s=2.0)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

class TestConnect:

    async def test_connect_sets_connected(self, rig):
        b = _make(rig)
        await b.connect()
        assert b.connected
        await b.disconnect()

    async def test_connect_refused_raises(self):
        b = RigctldBackend(host="127.0.0.1", port=1, timeout_s=1.0)
        with pytest.raises(RadioBackendError, match="Cannot connect"):
            await b.connect()
        assert not b.connected

    async def test_disconnect_clears_connected(self, rig):
        b = _make(rig)
        await b.connect()
        await b.disconnect()
        assert not b.connected

    async def test_disconnect_when_not_connected_is_safe(self):
        b = RigctldBackend(host="127.0.0.1", port=9999, timeout_s=0.1)
        await b.disconnect()  # must not raise


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------

class TestFrequency:

    async def test_get_frequency(self, rig):
        b = _make(rig)
        await b.connect()
        assert await b.get_frequency() == rig.freq
        await b.disconnect()

    async def test_set_frequency_updates_server(self, rig):
        b = _make(rig)
        await b.connect()
        await b.set_frequency(7_100_000)
        assert rig.freq == 7_100_000.0
        await b.disconnect()

    async def test_get_frequency_returns_float(self, rig):
        b = _make(rig)
        await b.connect()
        val = await b.get_frequency()
        assert isinstance(val, float)
        await b.disconnect()


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------

class TestMode:

    async def test_get_mode(self, rig):
        b = _make(rig)
        await b.connect()
        mode, bw = await b.get_mode()
        assert mode == "USB"
        assert bw == 2400.0
        await b.disconnect()

    async def test_set_mode_updates_server(self, rig):
        b = _make(rig)
        await b.connect()
        await b.set_mode("CW", 500)
        assert rig.mode == "CW"
        assert rig.bw == 500.0
        await b.disconnect()

    async def test_set_mode_zero_bandwidth(self, rig):
        b = _make(rig)
        await b.connect()
        await b.set_mode("LSB", 0)
        assert rig.mode == "LSB"
        await b.disconnect()


# ---------------------------------------------------------------------------
# VFO
# ---------------------------------------------------------------------------

class TestVfo:

    async def test_get_vfo(self, rig):
        b = _make(rig)
        await b.connect()
        assert await b.get_vfo() == "VFOA"
        await b.disconnect()

    async def test_set_vfo(self, rig):
        b = _make(rig)
        await b.connect()
        await b.set_vfo("VFOB")
        assert rig.vfo == "VFOB"
        await b.disconnect()


# ---------------------------------------------------------------------------
# PTT
# ---------------------------------------------------------------------------

class TestPtt:

    async def test_get_ptt_default_false(self, rig):
        b = _make(rig)
        await b.connect()
        assert await b.get_ptt() is False
        await b.disconnect()

    async def test_set_ptt_on(self, rig):
        b = _make(rig)
        await b.connect()
        await b.set_ptt(True)
        assert rig.ptt is True
        await b.set_ptt(False)
        await b.disconnect()

    async def test_set_ptt_off(self, rig):
        b = _make(rig)
        await b.connect()
        rig.ptt = True
        await b.set_ptt(False)
        assert rig.ptt is False
        await b.disconnect()


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------

class TestSplit:

    async def test_get_split_inactive(self, rig):
        b = _make(rig)
        await b.connect()
        active, tx_hz = await b.get_split()
        assert active is False
        assert tx_hz is None
        await b.disconnect()

    async def test_get_split_active_returns_freq(self, rig):
        rig.split = True
        rig.split_freq = 14_225_000.0
        b = _make(rig)
        await b.connect()
        active, tx_hz = await b.get_split()
        assert active is True
        assert tx_hz == 14_225_000.0
        await b.disconnect()

    async def test_set_split_enables(self, rig):
        b = _make(rig)
        await b.connect()
        await b.set_split(True, 14_225_000)
        assert rig.split is True
        assert rig.split_freq == 14_225_000.0
        await b.disconnect()

    async def test_set_split_disables(self, rig):
        rig.split = True
        b = _make(rig)
        await b.connect()
        await b.set_split(False)
        assert rig.split is False
        await b.disconnect()


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

class TestLevels:

    async def test_get_level_strength(self, rig):
        b = _make(rig)
        await b.connect()
        val = await b.get_level("STRENGTH")
        assert val == rig.levels["STRENGTH"]
        await b.disconnect()

    async def test_get_level_rfpower(self, rig):
        b = _make(rig)
        await b.connect()
        val = await b.get_level("RFPOWER")
        assert val == rig.levels["RFPOWER"]
        await b.disconnect()

    async def test_set_level_rfpower(self, rig):
        b = _make(rig)
        await b.connect()
        await b.set_level("RFPOWER", 0.5)
        assert rig.levels["RFPOWER"] == 0.5
        await b.disconnect()

    async def test_get_level_unknown_returns_zero(self, rig):
        b = _make(rig)
        await b.connect()
        val = await b.get_level("NOTREAL")
        assert val == 0.0
        await b.disconnect()


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------

class TestInfo:

    async def test_get_info(self, rig):
        b = _make(rig)
        await b.connect()
        info = await b.get_info()
        assert info == "Fake Rig v1.0"
        await b.disconnect()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:

    async def test_rprt_negative_raises(self, error_rig):
        b = _make(error_rig)
        await b.connect()
        with pytest.raises(RadioBackendError, match="RPRT"):
            await b.get_frequency()
        await b.disconnect()

    async def test_command_when_not_connected_raises(self):
        b = RigctldBackend(host="127.0.0.1", port=9999)
        with pytest.raises(RadioBackendError, match="Not connected"):
            await b.get_frequency()

    async def test_connection_drop_raises_and_marks_disconnected(self, drop_rig):
        b = _make(drop_rig)
        await b.connect()
        with pytest.raises(RadioBackendError):
            await b.get_frequency()
        assert not b.connected


# ---------------------------------------------------------------------------
# Full state snapshot
# ---------------------------------------------------------------------------

class TestFullState:

    async def test_get_full_state_returns_all_fields(self, rig):
        b = _make(rig)
        await b.connect()
        state = await b.get_full_state()
        assert "frequency_hz" in state
        assert "mode" in state
        assert "bandwidth_hz" in state
        assert "ptt" in state
        assert "signal_strength" in state
        assert "rf_power" in state
        await b.disconnect()

    async def test_get_full_state_values_match_server(self, rig):
        b = _make(rig)
        await b.connect()
        state = await b.get_full_state()
        assert state["frequency_hz"] == rig.freq
        assert state["mode"] == rig.mode
        assert state["ptt"] is False
        await b.disconnect()

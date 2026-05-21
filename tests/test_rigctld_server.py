"""
Tests for radio/rigctld_server.py — the built-in rigctld-compatible TCP server.

Uses a real asyncio TCP server on a random loopback port paired with a
FakeBackend / RadioInterface so no actual radio hardware is needed.
"""
from __future__ import annotations

import asyncio
import socket
from typing import Optional
import pytest

from radio.backends.base import RadioBackend, RadioBackendError
from radio.radio_interface import RadioInterface
from radio.radio_state import RadioMode
from radio.rigctld_server import RigctldServer, _smeter_to_dbm


# ---------------------------------------------------------------------------
# Fake backend (local copy so this test is self-contained)
# ---------------------------------------------------------------------------

class FakeBackend(RadioBackend):
    def __init__(self):
        self._connected = False
        self.freq       = 14_200_000.0
        self.mode       = "USB"
        self.bw         = 2400.0
        self.vfo        = "VFOA"
        self.ptt        = False
        self.split      = False
        self.split_freq: Optional[float] = None
        self.rf_power   = 1.0
        self.strength   = 120.0   # raw CI-V value ≈ S9
        self.info_str   = "Test Radio"
        self.levels: dict[str, float] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:    self._connected = True
    async def disconnect(self) -> None: self._connected = False

    async def get_frequency(self) -> float: return self.freq
    async def set_frequency(self, hz: float) -> None: self.freq = hz
    async def get_mode(self) -> tuple[str, float]: return self.mode, self.bw
    async def set_mode(self, mode: str, bw: float = 0) -> None:
        self.mode = mode
        if bw: self.bw = bw
    async def get_vfo(self) -> str: return self.vfo
    async def set_vfo(self, vfo: str) -> None: self.vfo = vfo
    async def get_ptt(self) -> bool: return self.ptt
    async def set_ptt(self, tx: bool) -> None: self.ptt = tx
    async def get_split(self) -> tuple[bool, Optional[float]]:
        return self.split, self.split_freq
    async def set_split(self, active: bool, tx_hz: Optional[float] = None) -> None:
        self.split = active
        self.split_freq = tx_hz
    async def get_level(self, name: str) -> float:
        name = name.upper()
        if name == "RFPOWER":  return self.rf_power
        if name == "STRENGTH": return self.strength
        return 0.0
    async def set_level(self, name: str, value: float) -> None:
        self.levels[name.upper()] = value
    async def get_info(self) -> str: return self.info_str


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
async def iface(backend):
    ri = RadioInterface("test", backend, poll_interval_s=0.05, reconnect_delay_s=0.05)
    await ri.connect()
    yield ri
    await ri.disconnect()


@pytest.fixture
async def server(iface):
    port = _free_port()
    srv  = RigctldServer(iface, host="127.0.0.1", port=port)
    task = asyncio.create_task(srv.serve(), name="test_rigctld_server")
    await asyncio.sleep(0.05)   # allow the server socket to open
    yield port
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _transact(port: int, command: str) -> str:
    """Send one command to the server and read back the full response."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(command.encode())
    await writer.drain()
    # Read until we see RPRT or the line is CHKVFO
    buf = b""
    while True:
        chunk = await asyncio.wait_for(reader.read(256), timeout=2.0)
        if not chunk:
            break
        buf += chunk
        text = buf.decode("ascii", errors="replace")
        if "RPRT" in text or "CHKVFO" in text:
            break
    writer.close()
    await writer.wait_closed()
    return buf.decode("ascii", errors="replace")


# ---------------------------------------------------------------------------
# chk_vfo
# ---------------------------------------------------------------------------

class TestChkVfo:

    async def test_chk_vfo_returns_chkvfo_0(self, server):
        r = await _transact(server, "chk_vfo\n")
        assert "CHKVFO 0" in r

    async def test_backslash_chk_vfo(self, server):
        r = await _transact(server, "\\chk_vfo\n")
        assert "CHKVFO 0" in r


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------

class TestFrequency:

    async def test_get_freq_short(self, server, iface):
        iface.state.frequency_hz = 14_225_000.0
        r = await _transact(server, "f\n")
        assert "14225000" in r
        assert "RPRT 0" in r

    async def test_get_freq_long(self, server, iface):
        iface.state.frequency_hz = 7_100_000.0
        r = await _transact(server, "\\get_freq\n")
        assert "7100000" in r
        assert "RPRT 0" in r

    async def test_get_freq_extended_prefix(self, server, iface):
        iface.state.frequency_hz = 3_700_000.0
        r = await _transact(server, "+f\n")
        assert "3700000" in r
        assert "RPRT 0" in r

    async def test_set_freq_short(self, server, iface):
        r = await _transact(server, "F 21300000\n")
        assert "RPRT 0" in r
        await asyncio.sleep(0.05)
        assert iface.state.frequency_hz == pytest.approx(21_300_000.0)

    async def test_set_freq_long(self, server, iface):
        r = await _transact(server, "\\set_freq 10125000\n")
        assert "RPRT 0" in r
        await asyncio.sleep(0.05)
        assert iface.state.frequency_hz == pytest.approx(10_125_000.0)

    async def test_set_freq_disconnected_returns_error(self, server, iface):
        iface.state.connected = False
        r = await _transact(server, "F 14200000\n")
        assert "RPRT -1" in r

    async def test_set_freq_missing_arg_returns_error(self, server):
        r = await _transact(server, "F\n")
        assert "RPRT -1" in r


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------

class TestMode:

    async def test_get_mode_short(self, server, iface):
        iface.state.mode = RadioMode.USB
        iface.state.bandwidth_hz = 2700.0
        r = await _transact(server, "m\n")
        assert "USB" in r
        assert "2700" in r
        assert "RPRT 0" in r

    async def test_get_mode_long(self, server, iface):
        iface.state.mode = RadioMode.CW
        iface.state.bandwidth_hz = 500.0
        r = await _transact(server, "\\get_mode\n")
        assert "CW" in r
        assert "500" in r

    async def test_get_mode_zero_bandwidth_when_unknown(self, server, backend):
        backend.bw = 0.0
        r = await _transact(server, "m\n")
        assert "RPRT 0" in r

    async def test_set_mode_short(self, server, iface, backend):
        r = await _transact(server, "M LSB 2400\n")
        assert "RPRT 0" in r
        await asyncio.sleep(0.05)
        assert iface.state.mode == RadioMode.LSB

    async def test_set_mode_long(self, server, iface):
        r = await _transact(server, "\\set_mode CW 500\n")
        assert "RPRT 0" in r
        await asyncio.sleep(0.05)
        assert iface.state.mode == RadioMode.CW

    async def test_set_mode_without_bandwidth(self, server, iface):
        r = await _transact(server, "M USB\n")
        assert "RPRT 0" in r

    async def test_set_mode_disconnected_returns_error(self, server, iface):
        iface.state.connected = False
        r = await _transact(server, "M USB 2700\n")
        assert "RPRT -1" in r

    async def test_set_mode_missing_arg_returns_error(self, server):
        r = await _transact(server, "M\n")
        assert "RPRT -1" in r


# ---------------------------------------------------------------------------
# VFO
# ---------------------------------------------------------------------------

class TestVfo:

    async def test_get_vfo_returns_vfoa(self, server, backend):
        backend.vfo = "VFOA"
        r = await _transact(server, "v\n")
        assert "VFOA" in r
        assert "RPRT 0" in r

    async def test_get_vfo_long(self, server, iface):
        iface.state.vfo = "VFOB"
        r = await _transact(server, "\\get_vfo\n")
        assert "VFOB" in r

    async def test_set_vfo_short(self, server, iface):
        r = await _transact(server, "V VFOB\n")
        assert "RPRT 0" in r

    async def test_get_vfo_defaults_to_vfoa_when_none(self, server, iface):
        iface.state.vfo = None
        r = await _transact(server, "v\n")
        assert "VFOA" in r


# ---------------------------------------------------------------------------
# PTT
# ---------------------------------------------------------------------------

class TestPtt:

    async def test_get_ptt_false(self, server, backend):
        backend.ptt = False
        r = await _transact(server, "t\n")
        assert "0\n" in r
        assert "RPRT 0" in r

    async def test_get_ptt_true(self, server, iface):
        iface.state.ptt = True
        r = await _transact(server, "t\n")
        assert "1\n" in r
        assert "RPRT 0" in r

    async def test_set_ptt_on(self, server, iface):
        r = await _transact(server, "T 1\n")
        assert "RPRT 0" in r
        await asyncio.sleep(0.05)
        assert iface.state.ptt is True

    async def test_set_ptt_off(self, server, iface):
        iface.state.ptt = True
        r = await _transact(server, "T 0\n")
        assert "RPRT 0" in r
        await asyncio.sleep(0.05)
        assert iface.state.ptt is False

    async def test_set_ptt_disconnected_returns_error(self, server, iface):
        iface.state.connected = False
        r = await _transact(server, "T 1\n")
        assert "RPRT -1" in r


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------

class TestSplit:

    async def test_get_split_vfo_off(self, server, backend):
        backend.split = False
        r = await _transact(server, "s\n")
        assert "0\n" in r
        assert "VFOA" in r
        assert "RPRT 0" in r

    async def test_get_split_vfo_on(self, server, iface):
        iface.state.split = True
        r = await _transact(server, "s\n")
        assert "1\n" in r
        assert "VFOB" in r

    async def test_set_split_vfo(self, server, iface):
        r = await _transact(server, "S 1 VFOB\n")
        assert "RPRT 0" in r

    async def test_set_split_missing_args_returns_error(self, server):
        r = await _transact(server, "S 1\n")
        assert "RPRT -1" in r

    async def test_get_split_freq_no_split(self, server, iface):
        iface.state.frequency_hz = 14_200_000.0
        iface.state.split = False
        iface.state.split_freq_hz = None
        r = await _transact(server, "i\n")
        assert "14200000" in r
        assert "RPRT 0" in r

    async def test_set_split_freq(self, server, iface):
        r = await _transact(server, "I 14225000\n")
        assert "RPRT 0" in r


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

class TestLevels:

    async def test_get_level_rfpower(self, server, iface):
        iface.state.rf_power = 0.75
        r = await _transact(server, "l RFPOWER\n")
        assert "0.75" in r
        assert "RPRT 0" in r

    async def test_get_level_strength_returns_dbm(self, server, iface):
        iface.state.signal_strength = 120.0   # S9 raw value
        r = await _transact(server, "l STRENGTH\n")
        assert "RPRT 0" in r
        # S9 raw=120 should map to -73 dBm
        lines = r.strip().split("\n")
        dbm = float(lines[0])
        assert dbm == pytest.approx(-73.0, abs=1.0)

    async def test_get_level_unknown_returns_zero(self, server):
        r = await _transact(server, "l NOSUCHLEVEL\n")
        assert "0.000000" in r
        assert "RPRT 0" in r

    async def test_set_level_rfpower(self, server, backend):
        r = await _transact(server, "L RFPOWER 0.5\n")
        assert "RPRT 0" in r
        await asyncio.sleep(0.05)
        assert backend.levels.get("RFPOWER") == pytest.approx(0.5)

    async def test_set_level_missing_args_returns_error(self, server):
        r = await _transact(server, "L RFPOWER\n")
        assert "RPRT -1" in r


# ---------------------------------------------------------------------------
# Info and capabilities
# ---------------------------------------------------------------------------

class TestInfo:

    async def test_get_info_returns_info_string(self, server, backend):
        backend.info_str = "IC-7300 @ 192.168.1.50"
        iface_info = backend.info_str
        r = await _transact(server, "_\n")
        assert "RPRT 0" in r

    async def test_get_info_long(self, server):
        r = await _transact(server, "\\get_info\n")
        assert "RPRT 0" in r

    async def test_dump_caps_short(self, server):
        r = await _transact(server, "1\n")
        assert "StationController" in r
        assert "RPRT 0" in r

    async def test_dump_caps_long(self, server):
        r = await _transact(server, "\\dump_caps\n")
        assert "Model name:" in r
        assert "Can set Freq:\tY" in r
        assert "Can get Freq:\tY" in r
        assert "Can set Mode:\tY" in r
        assert "Can set PTT:\tY" in r
        assert "Can set Split VFO:\tY" in r
        assert "RPRT 0" in r

    async def test_dump_state_returns_rprt_ok(self, server):
        r = await _transact(server, "dump_state\n")
        assert "RPRT 0" in r


# ---------------------------------------------------------------------------
# Unknown / unimplemented commands
# ---------------------------------------------------------------------------

class TestUnknownCommands:

    async def test_unknown_command_returns_rprt_enav(self, server):
        r = await _transact(server, "\\zzz_not_a_real_command\n")
        assert "RPRT -11" in r

    async def test_unknown_short_command_returns_rprt_enav(self, server):
        r = await _transact(server, "Z\n")
        assert "RPRT -11" in r


# ---------------------------------------------------------------------------
# Quit
# ---------------------------------------------------------------------------

class TestQuit:

    async def test_quit_short_closes_connection(self, server):
        reader, writer = await asyncio.open_connection("127.0.0.1", server)
        writer.write(b"q\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(128), timeout=2.0)
        # Server closes the connection - EOF or nothing
        assert data == b""
        writer.close()
        await writer.wait_closed()

    async def test_quit_long_closes_connection(self, server):
        reader, writer = await asyncio.open_connection("127.0.0.1", server)
        writer.write(b"\\quit\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(128), timeout=2.0)
        assert data == b""
        writer.close()
        await writer.wait_closed()


# ---------------------------------------------------------------------------
# Multiple concurrent clients
# ---------------------------------------------------------------------------

class TestConcurrentClients:

    async def test_two_clients_simultaneously(self, server, iface):
        iface.state.frequency_hz = 14_200_000.0
        r1, r2 = await asyncio.gather(
            _transact(server, "f\n"),
            _transact(server, "f\n"),
        )
        assert "14200000" in r1
        assert "14200000" in r2
        assert "RPRT 0" in r1
        assert "RPRT 0" in r2

    async def test_second_client_sees_state_change_from_first(self, server, iface):
        await _transact(server, "F 7100000\n")
        await asyncio.sleep(0.05)
        r = await _transact(server, "f\n")
        assert "7100000" in r


# ---------------------------------------------------------------------------
# _smeter_to_dbm unit tests
# ---------------------------------------------------------------------------

class TestSmeterToDbm:

    def test_raw_zero_returns_minimum(self):
        assert _smeter_to_dbm(0.0) == pytest.approx(-127.0)

    def test_raw_120_is_s9(self):
        assert _smeter_to_dbm(120.0) == pytest.approx(-73.0)

    def test_raw_241_is_s9_plus_60(self):
        assert _smeter_to_dbm(241.0) == pytest.approx(-13.0, abs=1.0)

    def test_s9_greater_than_s0(self):
        assert _smeter_to_dbm(120.0) > _smeter_to_dbm(0.0)

    def test_strong_signal_greater_than_s9(self):
        assert _smeter_to_dbm(200.0) > _smeter_to_dbm(120.0)

    def test_negative_input_passes_through(self):
        assert _smeter_to_dbm(-73.0) == pytest.approx(-73.0)

    def test_very_negative_passes_through(self):
        assert _smeter_to_dbm(-120.0) == pytest.approx(-120.0)

    def test_slightly_negative_returns_minimum(self):
        # -5 is not < -10 so it falls through to the raw <= 0 branch
        assert _smeter_to_dbm(-5.0) == pytest.approx(-127.0)

"""
Tests for radio/backends/hamlib_direct.py.

The Hamlib Python bindings are injected via sys.modules so this suite
runs without hamlib installed.
"""
import sys
from unittest.mock import MagicMock, call

import pytest

from radio.backends.base import RadioBackendError
from radio.backends.hamlib_direct import HamlibDirectBackend


# ---------------------------------------------------------------------------
# Hamlib mock helpers
# ---------------------------------------------------------------------------

def _make_hamlib_mock():
    """Return a (mock_module, mock_rig) pair that behaves like the Hamlib API."""
    H = MagicMock(name="Hamlib")

    # Integer constants
    H.RIG_DEBUG_NONE = 0
    H.RIG_VFO_CURR = 0
    H.RIG_VFO_A = 1
    H.RIG_VFO_B = 2
    H.RIG_VFO_MEM = 3
    H.RIG_PTT_OFF = 0
    H.RIG_PTT_ON = 1
    H.RIG_SPLIT_OFF = 0
    H.RIG_SPLIT_ON = 1
    H.RIG_PARITY_NONE = 0
    H.RIG_PARITY_EVEN = 1
    H.RIG_PARITY_ODD = 2
    H.RIG_MODE_USB = 1
    H.RIG_MODE_LSB = 2
    H.RIG_MODE_CW = 3
    H.RIG_LEVEL_STR = 1
    H.RIG_LEVEL_RFPOWER = 2
    H.RIG_LEVEL_AF = 3
    H.RIG_LEVEL_SQL = 4

    # String converters
    H.rig_strrmode.return_value = "USB"
    H.rig_strvfo.return_value = "VFOA"

    # Rig instance
    mock_rig = MagicMock(name="rig")
    mock_rig.get_freq.return_value = 14_200_000.0
    mock_rig.get_mode.return_value = (H.RIG_MODE_USB, 2400)
    mock_rig.get_vfo.return_value = H.RIG_VFO_A
    mock_rig.get_ptt.return_value = H.RIG_PTT_OFF
    mock_rig.get_split_vfo.return_value = (H.RIG_SPLIT_OFF, H.RIG_VFO_B)
    mock_rig.get_split_freq.return_value = 14_225_000.0
    mock_rig.get_level_f.return_value = -14.0
    mock_rig.get_info.return_value = "Mock Rig v1.0"

    H.Rig.return_value = mock_rig
    return H, mock_rig


@pytest.fixture
def hamlib(monkeypatch):
    """Inject mock Hamlib into sys.modules for the duration of the test."""
    H, mock_rig = _make_hamlib_mock()
    monkeypatch.setitem(sys.modules, "Hamlib", H)
    yield H, mock_rig


def _backend(**kwargs) -> HamlibDirectBackend:
    defaults = dict(model_id=1, port="", baud_rate=9600)
    defaults.update(kwargs)
    return HamlibDirectBackend(**defaults)


# ---------------------------------------------------------------------------
# Connect / disconnect
# ---------------------------------------------------------------------------

class TestConnect:

    async def test_connect_opens_rig(self, hamlib):
        H, mock_rig = hamlib
        b = _backend(model_id=351, port="/dev/ttyUSB0", baud_rate=9600)
        await b.connect()
        H.Rig.assert_called_once_with(351)
        mock_rig.open.assert_called_once()
        assert b.connected
        await b.disconnect()

    async def test_connect_configures_port(self, hamlib):
        H, mock_rig = hamlib
        b = _backend(port="/dev/ttyUSB0", baud_rate=9600)
        await b.connect()
        assert mock_rig.state.rigport.pathname == "/dev/ttyUSB0"
        assert mock_rig.state.rigport.parm.serial.rate == 9600
        await b.disconnect()

    async def test_connect_configures_parity_none(self, hamlib):
        H, mock_rig = hamlib
        b = _backend(parity="N")
        await b.connect()
        assert mock_rig.state.rigport.parm.serial.parity == H.RIG_PARITY_NONE
        await b.disconnect()

    async def test_connect_configures_parity_even(self, hamlib):
        H, mock_rig = hamlib
        b = _backend(parity="E")
        await b.connect()
        assert mock_rig.state.rigport.parm.serial.parity == H.RIG_PARITY_EVEN
        await b.disconnect()

    async def test_connect_import_error_raises(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "Hamlib", raising=False)
        b = _backend()
        with pytest.raises(RadioBackendError, match="not installed"):
            await b.connect()
        assert not b.connected

    async def test_connect_rig_open_error_raises(self, hamlib):
        H, mock_rig = hamlib
        mock_rig.open.side_effect = Exception("port busy")
        b = _backend()
        with pytest.raises(RadioBackendError, match="hamlib open failed"):
            await b.connect()
        assert not b.connected

    async def test_disconnect_calls_close(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        await b.disconnect()
        mock_rig.close.assert_called_once()
        assert not b.connected

    async def test_not_connected_raises(self, hamlib):
        b = _backend()
        with pytest.raises(RadioBackendError, match="Not connected"):
            await b.get_frequency()


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------

class TestFrequency:

    async def test_get_frequency(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        val = await b.get_frequency()
        assert val == 14_200_000.0
        mock_rig.get_freq.assert_called_with(H.RIG_VFO_CURR)
        await b.disconnect()

    async def test_set_frequency(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        await b.set_frequency(7_100_000)
        mock_rig.set_freq.assert_called_with(H.RIG_VFO_CURR, 7_100_000)
        await b.disconnect()


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------

class TestMode:

    async def test_get_mode(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        mode, bw = await b.get_mode()
        assert mode == "USB"
        assert bw == 2400.0
        await b.disconnect()

    async def test_set_mode(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        await b.set_mode("USB", 2400)
        mock_rig.set_mode.assert_called_with(H.RIG_VFO_CURR, H.RIG_MODE_USB, 2400)
        await b.disconnect()

    async def test_set_mode_unknown_raises(self, hamlib):
        b = _backend()
        await b.connect()
        with pytest.raises(RadioBackendError, match="Unknown mode"):
            await b.set_mode("INVALID")
        await b.disconnect()


# ---------------------------------------------------------------------------
# VFO
# ---------------------------------------------------------------------------

class TestVfo:

    async def test_get_vfo(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        assert await b.get_vfo() == "VFOA"
        await b.disconnect()

    async def test_set_vfo(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        await b.set_vfo("VFOB")
        mock_rig.set_vfo.assert_called_with(H.RIG_VFO_B)
        await b.disconnect()

    async def test_set_vfo_unknown_raises(self, hamlib):
        b = _backend()
        await b.connect()
        with pytest.raises(RadioBackendError, match="Unknown VFO"):
            await b.set_vfo("VFOX")
        await b.disconnect()


# ---------------------------------------------------------------------------
# PTT
# ---------------------------------------------------------------------------

class TestPtt:

    async def test_get_ptt_false(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        assert await b.get_ptt() is False
        await b.disconnect()

    async def test_get_ptt_true(self, hamlib):
        H, mock_rig = hamlib
        mock_rig.get_ptt.return_value = H.RIG_PTT_ON
        b = _backend()
        await b.connect()
        assert await b.get_ptt() is True
        await b.disconnect()

    async def test_set_ptt_on(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        await b.set_ptt(True)
        mock_rig.set_ptt.assert_called_with(H.RIG_VFO_CURR, H.RIG_PTT_ON)
        await b.disconnect()


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

class TestLevels:

    async def test_get_level_strength(self, hamlib):
        H, mock_rig = hamlib
        mock_rig.get_level_f.return_value = -14.0
        b = _backend()
        await b.connect()
        val = await b.get_level("STRENGTH")
        assert val == -14.0
        mock_rig.get_level_f.assert_called_with(H.RIG_VFO_CURR, H.RIG_LEVEL_STR)
        await b.disconnect()

    async def test_get_level_rfpower(self, hamlib):
        H, mock_rig = hamlib
        mock_rig.get_level_f.return_value = 0.75
        b = _backend()
        await b.connect()
        val = await b.get_level("RFPOWER")
        assert val == 0.75
        mock_rig.get_level_f.assert_called_with(H.RIG_VFO_CURR, H.RIG_LEVEL_RFPOWER)
        await b.disconnect()

    async def test_get_level_unknown_raises(self, hamlib):
        b = _backend()
        await b.connect()
        with pytest.raises(RadioBackendError, match="Unknown level"):
            await b.get_level("NOTREAL")
        await b.disconnect()

    async def test_set_level_rfpower(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        await b.set_level("RFPOWER", 0.5)
        mock_rig.set_level.assert_called_with(H.RIG_VFO_CURR, H.RIG_LEVEL_RFPOWER, 0.5)
        await b.disconnect()

    async def test_set_level_unknown_raises(self, hamlib):
        b = _backend()
        await b.connect()
        with pytest.raises(RadioBackendError, match="Unknown level"):
            await b.set_level("NOTREAL", 1.0)
        await b.disconnect()


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------

class TestInfo:

    async def test_get_info(self, hamlib):
        H, mock_rig = hamlib
        b = _backend()
        await b.connect()
        info = await b.get_info()
        assert info == "Mock Rig v1.0"
        await b.disconnect()

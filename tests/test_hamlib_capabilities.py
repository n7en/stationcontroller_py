"""
Tests for the extended Hamlib capabilities:
  - hamlib_direct.py: RIT/XIT, get_func/set_func, CTCSS, DCS, extra levels
  - rigctld.py: same via rigctld text commands
  - api/routers/hamlib.py: model-list parser
  - automation/action.py: SetFunc, SetRit, SetXit, SetCtcssTone
"""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from radio.backends.base import RadioBackendError


# ---------------------------------------------------------------------------
# Hamlib model-list parser
# ---------------------------------------------------------------------------

class TestHamlibModelParser:
    """Unit-test the fixed-width rigctl -l output parser."""

    def _parse(self, text: str):
        from api.routers.hamlib import _parse_rigctl_list
        return _parse_rigctl_list(text)

    def test_parses_single_model(self):
        # Matches rigctld format: %6d  %-24s  %-24s  %-8s  %s
        line = f"   351  {'ICOM':<24}  {'IC-7300':<24}  {'20200323':<8}  Stable"
        models = self._parse(line)
        assert len(models) == 1
        m = models[0]
        assert m["model_id"] == 351
        assert m["manufacturer"] == "ICOM"
        assert m["model"] == "IC-7300"
        assert m["status"] == "Stable"

    def test_skips_header_lines(self):
        text = (
            "Rig#  Mfg              Model                    Version         Status\n"
            "   1  Hamlib           Dummy                    0.5             Alpha\n"
        )
        models = self._parse(text)
        assert len(models) == 1
        assert models[0]["model_id"] == 1

    def test_parses_multiple_models(self):
        text = (
            "     1  Hamlib           Dummy           0.5          Alpha\n"
            "   135  Yaesu            FT-991A         20200702     Alpha\n"
            "   351  ICOM             IC-7300         20200323     Stable\n"
        )
        models = self._parse(text)
        assert len(models) == 3
        ids = [m["model_id"] for m in models]
        assert 1 in ids and 135 in ids and 351 in ids

    def test_skips_blank_and_garbage_lines(self):
        text = "\n\nnot a model line\n   351  ICOM  IC-7300  20200323  Stable\n"
        models = self._parse(text)
        assert len(models) == 1

    def test_returns_empty_on_empty_input(self):
        assert self._parse("") == []

    def test_skips_model_id_zero(self):
        text = "     0  Hamlib           Dummy           0.5          Alpha\n"
        assert self._parse(text) == []


# ---------------------------------------------------------------------------
# Hamlib direct backend — RIT/XIT, func, CTCSS
# ---------------------------------------------------------------------------

def _make_hamlib_mock():
    """Minimal Hamlib mock with the new constants."""
    H = MagicMock(name="Hamlib")
    H.RIG_DEBUG_NONE = 0
    H.RIG_VFO_CURR   = 0
    H.RIG_VFO_A      = 1
    H.RIG_VFO_B      = 2
    H.RIG_PTT_OFF    = 0
    H.RIG_PTT_ON     = 1
    H.RIG_SPLIT_OFF  = 0
    H.RIG_SPLIT_ON   = 1
    H.RIG_PARITY_NONE = 0
    H.RIG_MODE_USB   = 1
    # Levels
    H.RIG_LEVEL_STRENGTH = 1
    H.RIG_LEVEL_RFPOWER  = 2
    # Functions
    H.RIG_FUNC_NR    = 1
    H.RIG_FUNC_NB    = 2
    H.RIG_FUNC_VOX   = 4
    H.RIG_FUNC_TUNER = 8
    H.rig_strrmode   = MagicMock(return_value="USB")
    H.rig_strvfo     = MagicMock(return_value="VFOA")
    rig = MagicMock(name="rig")
    rig.get_freq.return_value  = 14_200_000.0
    rig.get_mode.return_value  = (H.RIG_MODE_USB, 2400)
    rig.get_vfo.return_value   = H.RIG_VFO_A
    rig.get_ptt.return_value   = H.RIG_PTT_OFF
    rig.get_split_vfo.return_value = (H.RIG_SPLIT_OFF, H.RIG_VFO_B)
    rig.get_split_freq.return_value = 14_225_000.0
    rig.get_level_f.return_value = -14.0
    rig.get_info.return_value   = "Mock Rig"
    rig.get_rit.return_value    = 300
    rig.get_xit.return_value    = -100
    rig.get_func.return_value   = 1
    rig.get_ctcss_tone.return_value = 670
    rig.get_dcs_code.return_value   = 23
    H.Rig.return_value = rig
    return H, rig


@pytest.fixture
def hamlib():
    H, rig = _make_hamlib_mock()
    sys.modules["Hamlib"] = H
    yield H, rig
    sys.modules.pop("Hamlib", None)


def _backend(hamlib):
    from radio.backends.hamlib_direct import HamlibDirectBackend
    return HamlibDirectBackend(model_id=1, port="", baud_rate=9600)


class TestHamlibRit:
    async def test_get_rit_returns_offset(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        val = await b.get_rit()
        assert val == 300
        await b.disconnect()

    async def test_set_rit_calls_rig(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        await b.set_rit(500)
        rig.set_rit.assert_called()
        await b.disconnect()

    async def test_get_xit_returns_offset(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        val = await b.get_xit()
        assert val == -100
        await b.disconnect()

    async def test_set_xit_calls_rig(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        await b.set_xit(-200)
        rig.set_xit.assert_called()
        await b.disconnect()


class TestHamlibFunc:
    async def test_get_func_nr_returns_bool(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        val = await b.get_func("NR")
        assert isinstance(val, bool)
        assert val is True
        await b.disconnect()

    async def test_set_func_nr_calls_rig(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        await b.set_func("NR", True)
        rig.set_func.assert_called()
        await b.disconnect()

    async def test_unknown_func_raises(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        with pytest.raises(RadioBackendError, match="Unknown rig function"):
            await b.get_func("NOSUCHFUNC")
        await b.disconnect()


class TestHamlibCtcss:
    async def test_get_ctcss_tone(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        val = await b.get_ctcss_tone()
        assert val == 670
        await b.disconnect()

    async def test_set_ctcss_tone_calls_rig(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        await b.set_ctcss_tone(670)
        rig.set_ctcss_tone.assert_called()
        await b.disconnect()

    async def test_get_dcs_code(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        val = await b.get_dcs_code()
        assert val == 23
        await b.disconnect()

    async def test_set_dcs_code_calls_rig(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        await b.set_dcs_code(100)
        rig.set_dcs_code.assert_called()
        await b.disconnect()


class TestHamlibExtraLevels:
    async def test_get_preamp_level(self, hamlib):
        H, rig = hamlib
        H.RIG_LEVEL_PREAMP = 10
        rig.get_level_f.return_value = 10.0
        b = _backend(hamlib)
        await b.connect()
        val = await b.get_level("PREAMP")
        assert val == 10.0
        await b.disconnect()

    async def test_unknown_level_raises(self, hamlib):
        H, rig = hamlib
        b = _backend(hamlib)
        await b.connect()
        with pytest.raises(RadioBackendError, match="Unknown level"):
            await b.get_level("NOSUCHLEVEL")
        await b.disconnect()


# ---------------------------------------------------------------------------
# Rigctld backend — new commands via FakeRigctld
# ---------------------------------------------------------------------------

class _ExtendedFakeRigctld:
    """FakeRigctld extended with RIT, XIT, func, CTCSS, DCS commands."""

    def __init__(self):
        self.freq   = 14_200_000.0
        self.mode   = "USB"
        self.bw     = 2400.0
        self.ptt    = False
        self.rit    = 0
        self.xit    = 0
        self.funcs  = {"NR": False, "NB": False, "VOX": False, "TUNER": False}
        self.ctcss  = 0
        self.dcs    = 0
        self._server = None
        self.port: int = 0

    async def start(self):
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader, writer):
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                cmd = line.decode().strip()
                writer.write(self._dispatch(cmd).encode())
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
            self.freq = float(parts[1]); return "RPRT 0\n"
        if op == r"\get_mode":
            return f"{self.mode}\n{int(self.bw)}\nRPRT 0\n"
        if op == r"\set_mode":
            self.mode = parts[1]; return "RPRT 0\n"
        if op == r"\get_vfo":
            return "VFOA\nRPRT 0\n"
        if op == r"\get_ptt":
            return f"{'1' if self.ptt else '0'}\nRPRT 0\n"
        if op == r"\set_ptt":
            self.ptt = parts[1] != "0"; return "RPRT 0\n"
        if op == r"\get_split_vfo":
            return "0\nVFOB\nRPRT 0\n"
        if op == r"\get_level":
            return "0.0\nRPRT 0\n"
        if op == r"\get_info":
            return "Fake Rig\nRPRT 0\n"
        if op == r"\get_rit":
            return f"{self.rit}\nRPRT 0\n"
        if op == r"\set_rit":
            self.rit = int(parts[1]); return "RPRT 0\n"
        if op == r"\get_xit":
            return f"{self.xit}\nRPRT 0\n"
        if op == r"\set_xit":
            self.xit = int(parts[1]); return "RPRT 0\n"
        if op == r"\get_func":
            name = parts[1] if len(parts) > 1 else ""
            val = self.funcs.get(name, False)
            return f"{'1' if val else '0'}\nRPRT 0\n"
        if op == r"\set_func":
            name = parts[1] if len(parts) > 1 else ""
            self.funcs[name] = (parts[2] != "0") if len(parts) > 2 else False
            return "RPRT 0\n"
        if op == r"\get_ctcss_tone":
            return f"{self.ctcss}\nRPRT 0\n"
        if op == r"\set_ctcss_tone":
            self.ctcss = int(parts[1]); return "RPRT 0\n"
        if op == r"\get_dcs_code":
            return f"{self.dcs}\nRPRT 0\n"
        if op == r"\set_dcs_code":
            self.dcs = int(parts[1]); return "RPRT 0\n"
        return "RPRT -1\n"


@pytest.fixture
async def ext_rig():
    server = _ExtendedFakeRigctld()
    await server.start()
    yield server
    await server.stop()


def _rigctld(host, port):
    from radio.backends.rigctld import RigctldBackend
    return RigctldBackend(host=host, port=port, timeout_s=5.0)


class TestRigctldRit:
    async def test_get_rit(self, ext_rig):
        ext_rig.rit = 400
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        assert await b.get_rit() == 400
        await b.disconnect()

    async def test_set_rit(self, ext_rig):
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        await b.set_rit(250)
        assert ext_rig.rit == 250
        await b.disconnect()

    async def test_set_rit_zero_clears(self, ext_rig):
        ext_rig.rit = 500
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        await b.set_rit(0)
        assert ext_rig.rit == 0
        await b.disconnect()


class TestRigctldXit:
    async def test_get_xit(self, ext_rig):
        ext_rig.xit = -300
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        assert await b.get_xit() == -300
        await b.disconnect()

    async def test_set_xit(self, ext_rig):
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        await b.set_xit(-150)
        assert ext_rig.xit == -150
        await b.disconnect()


class TestRigctldFunc:
    async def test_get_func_false_by_default(self, ext_rig):
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        assert await b.get_func("NR") is False
        await b.disconnect()

    async def test_set_func_enables(self, ext_rig):
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        await b.set_func("NR", True)
        assert ext_rig.funcs["NR"] is True
        await b.disconnect()

    async def test_set_func_disables(self, ext_rig):
        ext_rig.funcs["VOX"] = True
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        await b.set_func("VOX", False)
        assert ext_rig.funcs["VOX"] is False
        await b.disconnect()

    async def test_get_func_after_set(self, ext_rig):
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        await b.set_func("NB", True)
        assert await b.get_func("NB") is True
        await b.disconnect()


class TestRigctldCtcss:
    async def test_get_ctcss_tone(self, ext_rig):
        ext_rig.ctcss = 670
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        assert await b.get_ctcss_tone() == 670
        await b.disconnect()

    async def test_set_ctcss_tone(self, ext_rig):
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        await b.set_ctcss_tone(1318)
        assert ext_rig.ctcss == 1318
        await b.disconnect()

    async def test_get_dcs_code(self, ext_rig):
        ext_rig.dcs = 73
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        assert await b.get_dcs_code() == 73
        await b.disconnect()

    async def test_set_dcs_code(self, ext_rig):
        b = _rigctld("127.0.0.1", ext_rig.port)
        await b.connect()
        await b.set_dcs_code(114)
        assert ext_rig.dcs == 114
        await b.disconnect()


# ---------------------------------------------------------------------------
# Automation actions
# ---------------------------------------------------------------------------

def _ctx(iface=None):
    from automation.action import AutomationContext
    ctx = AutomationContext.__new__(AutomationContext)
    ctx.radio_interface  = iface
    ctx.radio_max_power_w = 100.0
    ctx.sensor_registry  = None
    ctx.control_network  = None
    ctx.band_registry    = None
    return ctx


class TestSetFuncAction:
    async def test_set_func_calls_interface(self):
        from automation.action import SetFunc
        iface = MagicMock()
        iface.set_func = AsyncMock()
        ctx = _ctx(iface)
        await SetFunc("NR", True).execute(ctx)
        iface.set_func.assert_awaited_once_with("NR", True)

    async def test_set_func_disable(self):
        from automation.action import SetFunc
        iface = MagicMock()
        iface.set_func = AsyncMock()
        ctx = _ctx(iface)
        await SetFunc("VOX", False).execute(ctx)
        iface.set_func.assert_awaited_once_with("VOX", False)

    async def test_set_func_no_radio_raises(self):
        from automation.action import SetFunc
        with pytest.raises(RuntimeError, match="radio_interface"):
            await SetFunc("NR", True).execute(_ctx(None))

    def test_func_name_uppercased(self):
        from automation.action import SetFunc
        a = SetFunc("nr", True)
        assert a.func == "NR"

    def test_from_config(self):
        from automation.action import action_from_config
        a = action_from_config({"type": "set_func", "func": "TUNER", "value": True})
        from automation.action import SetFunc
        assert isinstance(a, SetFunc)
        assert a.func == "TUNER"
        assert a.value is True

    def test_from_config_default_value_is_true(self):
        from automation.action import action_from_config, SetFunc
        a = action_from_config({"type": "set_func", "func": "NB"})
        assert isinstance(a, SetFunc)
        assert a.value is True


class TestSetRitAction:
    async def test_set_rit_calls_interface(self):
        from automation.action import SetRit
        iface = MagicMock()
        iface.set_rit = AsyncMock()
        ctx = _ctx(iface)
        await SetRit(300).execute(ctx)
        iface.set_rit.assert_awaited_once_with(300)

    async def test_set_rit_zero_off(self):
        from automation.action import SetRit
        iface = MagicMock()
        iface.set_rit = AsyncMock()
        ctx = _ctx(iface)
        await SetRit(0).execute(ctx)
        iface.set_rit.assert_awaited_once_with(0)

    async def test_set_rit_no_radio_raises(self):
        from automation.action import SetRit
        with pytest.raises(RuntimeError, match="radio_interface"):
            await SetRit(100).execute(_ctx(None))

    def test_from_config(self):
        from automation.action import action_from_config, SetRit
        a = action_from_config({"type": "set_rit", "offset_hz": 500})
        assert isinstance(a, SetRit)
        assert a.offset_hz == 500

    def test_from_config_defaults_to_zero(self):
        from automation.action import action_from_config, SetRit
        a = action_from_config({"type": "set_rit"})
        assert isinstance(a, SetRit)
        assert a.offset_hz == 0


class TestSetCtcssToneAction:
    async def test_set_ctcss_calls_interface(self):
        from automation.action import SetCtcssTone
        iface = MagicMock()
        iface.set_ctcss_tone = AsyncMock()
        ctx = _ctx(iface)
        await SetCtcssTone(670).execute(ctx)
        iface.set_ctcss_tone.assert_awaited_once_with(670)

    def test_from_config(self):
        from automation.action import action_from_config, SetCtcssTone
        a = action_from_config({"type": "set_ctcss_tone", "tone": 670})
        assert isinstance(a, SetCtcssTone)
        assert a.tone == 670

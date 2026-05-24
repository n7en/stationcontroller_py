"""
Direct Python hamlib bindings backend.

All blocking hamlib calls run in a thread executor so they do not block
the asyncio event loop.

Requires the hamlib Python bindings (the ``Hamlib`` package).  A missing
library raises RadioBackendError at connect() time, not at import time,
so this module loads cleanly even without hamlib installed.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from .base import RadioBackend, RadioBackendError

log = logging.getLogger(__name__)


# Mode name -> Hamlib constant attribute name
_MODE_TO_HAMLIB: dict[str, str] = {
    "USB":    "RIG_MODE_USB",
    "LSB":    "RIG_MODE_LSB",
    "CW":     "RIG_MODE_CW",
    "CWR":    "RIG_MODE_CWR",
    "AM":     "RIG_MODE_AM",
    "FM":     "RIG_MODE_FM",
    "FMN":    "RIG_MODE_FMN",
    "WFM":    "RIG_MODE_WFM",
    "RTTY":   "RIG_MODE_RTTY",
    "RTTYR":  "RIG_MODE_RTTYR",
    "PKTUSB": "RIG_MODE_PKTUSB",
    "PKTLSB": "RIG_MODE_PKTLSB",
    "PKTFM":  "RIG_MODE_PKTFM",
}

# Level name -> Hamlib constant attribute name
_LEVEL_TO_HAMLIB: dict[str, str] = {
    "STRENGTH":  "RIG_LEVEL_STRENGTH",
    "RFPOWER":   "RIG_LEVEL_RFPOWER",
    "AF":        "RIG_LEVEL_AF",
    "RF":        "RIG_LEVEL_RF",
    "SQL":       "RIG_LEVEL_SQL",
    "MICGAIN":   "RIG_LEVEL_MICGAIN",
    "KEYSPD":    "RIG_LEVEL_KEYSPD",
    "COMP":      "RIG_LEVEL_COMP",
    "AGC":       "RIG_LEVEL_AGC",
    "METER":     "RIG_LEVEL_METER",
    "VOXGAIN":   "RIG_LEVEL_VOXGAIN",
    "SWR":       "RIG_LEVEL_SWR",
    "ALC":       "RIG_LEVEL_ALC",
    # Extended levels
    "PREAMP":    "RIG_LEVEL_PREAMP",
    "ATT":       "RIG_LEVEL_ATT",
    "BALANCE":   "RIG_LEVEL_BALANCE",
    "BKINDL":    "RIG_LEVEL_BKINDL",
    "NOTCHF":    "RIG_LEVEL_NOTCHF",
    "CWPITCH":   "RIG_LEVEL_CWPITCH",
    "VOXDELAY":  "RIG_LEVEL_VOXDELAY",
    "ANTIVOX":   "RIG_LEVEL_ANTIVOX",
    "RAWSTR":    "RIG_LEVEL_RAWSTR",
    "SLOPE_LOW": "RIG_LEVEL_SLOPE_LOW",
    "SLOPE_HIGH":"RIG_LEVEL_SLOPE_HIGH",
}

# Rig function name -> Hamlib constant attribute name
_FUNC_TO_HAMLIB: dict[str, str] = {
    "NB":      "RIG_FUNC_NB",
    "COMP":    "RIG_FUNC_COMP",
    "VOX":     "RIG_FUNC_VOX",
    "TONE":    "RIG_FUNC_TONE",    # CTCSS encode
    "TSQL":    "RIG_FUNC_TSQL",    # CTCSS squelch
    "SBKIN":   "RIG_FUNC_SBKIN",   # Semi-break-in CW
    "FBKIN":   "RIG_FUNC_FBKIN",   # Full break-in CW
    "ANF":     "RIG_FUNC_ANF",     # Automatic Notch Filter
    "NR":      "RIG_FUNC_NR",      # Noise Reduction
    "AIP":     "RIG_FUNC_AIP",
    "APF":     "RIG_FUNC_APF",     # Audio Peak Filter
    "MON":     "RIG_FUNC_MON",     # TX monitor
    "MN":      "RIG_FUNC_MN",      # Manual Notch
    "RF":      "RIG_FUNC_RF",      # RTTY Filter
    "ARO":     "RIG_FUNC_ARO",     # Auto Repeater Offset
    "LOCK":    "RIG_FUNC_LOCK",
    "MUTE":    "RIG_FUNC_MUTE",
    "VSC":     "RIG_FUNC_VSC",
    "REV":     "RIG_FUNC_REV",     # Reverse sideband
    "SQL":     "RIG_FUNC_SQL",
    "ABM":     "RIG_FUNC_ABM",
    "BC":      "RIG_FUNC_BC",
    "MBC":     "RIG_FUNC_MBC",
    "AFC":     "RIG_FUNC_AFC",     # Auto Frequency Control
    "SATMODE": "RIG_FUNC_SATMODE",
    "SCOPE":   "RIG_FUNC_SCOPE",
    "RESUME":  "RIG_FUNC_RESUME",
    "TBURST":  "RIG_FUNC_TBURST",  # 1750 Hz tone burst
    "TUNER":   "RIG_FUNC_TUNER",
    "XIT":     "RIG_FUNC_XIT",
    "NIT":     "RIG_FUNC_NIT",
    "RIT":     "RIG_FUNC_RIT",
    "DSQL":    "RIG_FUNC_DSQL",    # Digital squelch
    "AFLT":    "RIG_FUNC_AFLT",    # AF filter
    "BL":      "RIG_FUNC_BL",      # Beat lock
    "SEND":    "RIG_FUNC_SEND",
    "CATPTT":  "RIG_FUNC_CATPTT",
    "RPTR_SHIFT": "RIG_FUNC_RPTR_SHIFT",
}

_PARITY_TO_HAMLIB: dict[str, str] = {
    "N": "RIG_PARITY_NONE",
    "E": "RIG_PARITY_EVEN",
    "O": "RIG_PARITY_ODD",
}

_VFO_TO_HAMLIB: dict[str, str] = {
    "VFOA": "RIG_VFO_A",
    "VFOB": "RIG_VFO_B",
    "MEM":  "RIG_VFO_MEM",
}


class HamlibDirectBackend(RadioBackend):

    def __init__(
        self,
        model_id: int = 1,       # 1 = RIG_MODEL_DUMMY (safe default for testing)
        port: str = "",
        baud_rate: int = 9600,
        data_bits: int = 8,
        stop_bits: int = 1,
        parity: str = "N",
    ) -> None:
        self._model_id = model_id
        self._port = port
        self._baud_rate = baud_rate
        self._data_bits = data_bits
        self._stop_bits = stop_bits
        self._parity = parity.upper()
        self._rig = None
        self._H = None           # Hamlib module reference
        self._connected = False
        self._rig_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

    def _load_hamlib(self):
        import importlib
        for mod_name in ("Hamlib", "hamlib"):
            try:
                mod = importlib.import_module(mod_name)
                if hasattr(mod, "Rig"):
                    return mod
            except ImportError:
                pass
        raise RadioBackendError(
            "hamlib Python bindings not found or not usable. "
            "Install python3-hamlib and ensure the virtualenv can access system packages "
            "(rebuild with: python3 -m venv --system-site-packages .venv). "
            "Alternatively, use the rigctld backend."
        )

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        def _locked():
            with self._rig_lock:
                return fn(*args)
        return await loop.run_in_executor(None, _locked)

    async def connect(self) -> None:
        log.info(
            "Opening hamlib rig: model=%d port=%r baud=%d data=%d stop=%d parity=%s",
            self._model_id, self._port, self._baud_rate,
            self._data_bits, self._stop_bits, self._parity,
        )
        H = self._load_hamlib()
        self._H = H

        def _open():
            if hasattr(H, 'rig_set_debug') and hasattr(H, 'RIG_DEBUG_NONE'):
                H.rig_set_debug(H.RIG_DEBUG_NONE)
            rig = H.Rig(self._model_id)
            if self._port:
                rig.state.rigport.pathname = self._port
            rig.state.rigport.parm.serial.rate = self._baud_rate
            rig.state.rigport.parm.serial.data_bits = self._data_bits
            rig.state.rigport.parm.serial.stop_bits = self._stop_bits
            parity_attr = _PARITY_TO_HAMLIB.get(self._parity, "RIG_PARITY_NONE")
            rig.state.rigport.parm.serial.parity = getattr(H, parity_attr)
            rig.open()
            return rig

        try:
            self._rig = await self._run(_open)
            self._connected = True
            log.info("Hamlib rig ready: model=%d port=%r", self._model_id, self._port)
        except Exception as exc:
            self._connected = False
            log.error("Hamlib open failed: model=%d port=%r - %s", self._model_id, self._port, exc)
            raise RadioBackendError(f"hamlib open failed: {exc}") from exc

    async def disconnect(self) -> None:
        log.info("Closing hamlib rig: model=%d port=%r", self._model_id, self._port)
        self._connected = False
        if self._rig is not None:
            rig, self._rig = self._rig, None
            try:
                await self._run(rig.close)
            except Exception:
                pass

    def _require(self):
        if self._rig is None or not self._connected:
            raise RadioBackendError("Not connected")
        return self._rig, self._H

    # ------------------------------------------------------------------
    # Frequency
    # ------------------------------------------------------------------

    async def get_frequency(self) -> float:
        rig, H = self._require()
        return float(await self._run(rig.get_freq, H.RIG_VFO_CURR))

    async def set_frequency(self, hz: float) -> None:
        log.debug("set_frequency: %.0f Hz", hz)
        rig, H = self._require()
        await self._run(rig.set_freq, H.RIG_VFO_CURR, int(hz))

    # ------------------------------------------------------------------
    # Mode and filter
    # ------------------------------------------------------------------

    async def get_mode(self) -> tuple[str, float]:
        rig, H = self._require()
        mode_val, bw = await self._run(rig.get_mode, H.RIG_VFO_CURR)
        return H.rig_strrmode(mode_val), float(bw)

    async def set_mode(self, mode: str, bandwidth_hz: float = 0) -> None:
        log.debug("set_mode: %s bw=%d", mode, bandwidth_hz)
        rig, H = self._require()
        attr = _MODE_TO_HAMLIB.get(mode.upper())
        if attr is None:
            raise RadioBackendError(f"Unknown mode: {mode}")
        await self._run(rig.set_mode, H.RIG_VFO_CURR, getattr(H, attr), int(bandwidth_hz))

    # ------------------------------------------------------------------
    # VFO
    # ------------------------------------------------------------------

    async def get_vfo(self) -> str:
        rig, H = self._require()
        vfo_val = await self._run(rig.get_vfo)
        return H.rig_strvfo(vfo_val)

    async def set_vfo(self, vfo: str) -> None:
        rig, H = self._require()
        attr = _VFO_TO_HAMLIB.get(vfo.upper())
        if attr is None:
            raise RadioBackendError(f"Unknown VFO: {vfo}")
        await self._run(rig.set_vfo, getattr(H, attr))

    # ------------------------------------------------------------------
    # PTT
    # ------------------------------------------------------------------

    async def get_ptt(self) -> bool:
        rig, H = self._require()
        ptt_val = await self._run(rig.get_ptt, H.RIG_VFO_CURR)
        return ptt_val != H.RIG_PTT_OFF

    async def set_ptt(self, transmit: bool) -> None:
        log.debug("set_ptt: %s", transmit)
        rig, H = self._require()
        ptt_const = H.RIG_PTT_ON if transmit else H.RIG_PTT_OFF
        await self._run(rig.set_ptt, H.RIG_VFO_CURR, ptt_const)

    # ------------------------------------------------------------------
    # Split
    # ------------------------------------------------------------------

    async def get_split(self) -> tuple[bool, Optional[float]]:
        rig, H = self._require()
        try:
            # pip Hamlib: get_split_vfo(vfo) -> (split, tx_vfo)
            split_val, _tx_vfo = await self._run(rig.get_split_vfo, H.RIG_VFO_CURR)
        except TypeError:
            # system python3-hamlib: get_split_vfo(vfo, tx_vfo) -> (split, tx_vfo)
            split_val, _tx_vfo = await self._run(rig.get_split_vfo, H.RIG_VFO_CURR, H.RIG_VFO_B)
        active = split_val != H.RIG_SPLIT_OFF
        tx_hz: Optional[float] = None
        if active:
            try:
                tx_hz = float(await self._run(rig.get_split_freq, H.RIG_VFO_CURR))
            except Exception:
                pass
        return active, tx_hz

    async def set_split(self, active: bool, tx_hz: Optional[float] = None) -> None:
        rig, H = self._require()
        split_const = H.RIG_SPLIT_ON if active else H.RIG_SPLIT_OFF
        await self._run(rig.set_split_vfo, H.RIG_VFO_CURR, split_const, H.RIG_VFO_B)
        if active and tx_hz is not None:
            await self._run(rig.set_split_freq, H.RIG_VFO_CURR, int(tx_hz))

    # ------------------------------------------------------------------
    # Levels
    # ------------------------------------------------------------------

    async def get_level(self, level_name: str) -> float:
        rig, H = self._require()
        attr = _LEVEL_TO_HAMLIB.get(level_name.upper())
        if attr is None:
            raise RadioBackendError(f"Unknown level: {level_name}")
        const = getattr(H, attr, None)
        if const is None:
            raise RadioBackendError(f"Hamlib has no constant {attr} for level {level_name}")
        # Try all known calling conventions across pip Hamlib and system python3-hamlib:
        #   1. get_level_f(vfo, level)  — pip Hamlib, returns float directly
        #   2. get_level_f(level)       — some system builds omit the VFO arg
        #   3. get_level(vfo, level)    — system hamlib, returns value_t; use .f for float
        #   4. get_level(level)         — system hamlib without VFO arg
        last_exc: Exception = RadioBackendError("no working get_level convention")
        for call in [
            (rig.get_level_f, H.RIG_VFO_CURR, const),
            (rig.get_level_f, const),
            (rig.get_level,   H.RIG_VFO_CURR, const),
            (rig.get_level,   const),
        ]:
            try:
                result = await self._run(*call)
                if hasattr(result, 'f'):
                    return float(result.f)
                return float(result)
            except (TypeError, AttributeError) as exc:
                last_exc = exc
                continue
        raise RadioBackendError(f"get_level failed for {level_name}: {last_exc}")

    async def set_level(self, level_name: str, value: float) -> None:
        rig, H = self._require()
        attr = _LEVEL_TO_HAMLIB.get(level_name.upper())
        if attr is None:
            raise RadioBackendError(f"Unknown level: {level_name}")
        await self._run(rig.set_level, H.RIG_VFO_CURR, getattr(H, attr), value)

    # ------------------------------------------------------------------
    # Sub-receiver / VFO-B
    # ------------------------------------------------------------------

    async def get_sub_state(self) -> dict:
        rig, H = self._require()
        state: dict = {}
        try:
            state["vfob_frequency_hz"] = float(await self._run(rig.get_freq, H.RIG_VFO_B))
        except (TypeError, AttributeError, Exception):
            pass
        try:
            mode_val, bw = await self._run(rig.get_mode, H.RIG_VFO_B)
            state["vfob_mode"] = H.rig_strrmode(mode_val)
            state["vfob_bandwidth_hz"] = float(bw)
        except (TypeError, AttributeError, Exception):
            pass
        try:
            state["sub_frequency_hz"] = float(await self._run(rig.get_freq, H.RIG_VFO_C))
        except (TypeError, AttributeError, Exception):
            pass
        try:
            mode_val, bw = await self._run(rig.get_mode, H.RIG_VFO_C)
            state["sub_mode"] = H.rig_strrmode(mode_val)
            state["sub_bandwidth_hz"] = float(bw)
        except (TypeError, AttributeError, Exception):
            pass
        return state

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    async def get_info(self) -> str:
        rig, _ = self._require()
        return str(await self._run(rig.get_info))

    # ------------------------------------------------------------------
    # RIT / XIT  (Receive / Transmit Incremental Tuning)
    # ------------------------------------------------------------------

    async def get_rit(self) -> int:
        rig, H = self._require()
        try:
            return int(await self._run(rig.get_rit, H.RIG_VFO_CURR))
        except (TypeError, AttributeError):
            return int(await self._run(rig.get_rit))

    async def set_rit(self, offset_hz: int) -> None:
        log.debug("set_rit: %+d Hz", offset_hz)
        rig, H = self._require()
        try:
            await self._run(rig.set_rit, H.RIG_VFO_CURR, int(offset_hz))
        except (TypeError, AttributeError):
            await self._run(rig.set_rit, int(offset_hz))

    async def get_xit(self) -> int:
        rig, H = self._require()
        try:
            return int(await self._run(rig.get_xit, H.RIG_VFO_CURR))
        except (TypeError, AttributeError):
            return int(await self._run(rig.get_xit))

    async def set_xit(self, offset_hz: int) -> None:
        log.debug("set_xit: %+d Hz", offset_hz)
        rig, H = self._require()
        try:
            await self._run(rig.set_xit, H.RIG_VFO_CURR, int(offset_hz))
        except (TypeError, AttributeError):
            await self._run(rig.set_xit, int(offset_hz))

    # ------------------------------------------------------------------
    # Rig functions  (NB, NR, VOX, TUNER, LOCK, …)
    # ------------------------------------------------------------------

    async def get_func(self, func_name: str) -> bool:
        rig, H = self._require()
        attr = _FUNC_TO_HAMLIB.get(func_name.upper())
        if attr is None:
            raise RadioBackendError(f"Unknown rig function: {func_name}")
        const = getattr(H, attr, None)
        if const is None:
            raise RadioBackendError(f"Hamlib has no constant {attr} for function {func_name}")
        for call in [
            (rig.get_func, H.RIG_VFO_CURR, const),
            (rig.get_func, const),
        ]:
            try:
                result = await self._run(*call)
                return bool(result)
            except (TypeError, AttributeError):
                continue
        raise RadioBackendError(f"get_func failed for {func_name}: no working calling convention")

    async def set_func(self, func_name: str, value: bool) -> None:
        log.debug("set_func: %s = %s", func_name, value)
        rig, H = self._require()
        attr = _FUNC_TO_HAMLIB.get(func_name.upper())
        if attr is None:
            raise RadioBackendError(f"Unknown rig function: {func_name}")
        const = getattr(H, attr, None)
        if const is None:
            raise RadioBackendError(f"Hamlib has no constant {attr} for function {func_name}")
        for call in [
            (rig.set_func, H.RIG_VFO_CURR, const, int(value)),
            (rig.set_func, const, int(value)),
        ]:
            try:
                await self._run(*call)
                return
            except (TypeError, AttributeError):
                continue
        raise RadioBackendError(f"set_func failed for {func_name}: no working calling convention")

    # ------------------------------------------------------------------
    # CTCSS / DCS tones
    # ------------------------------------------------------------------

    async def get_ctcss_tone(self) -> int:
        rig, H = self._require()
        try:
            return int(await self._run(rig.get_ctcss_tone, H.RIG_VFO_CURR))
        except (TypeError, AttributeError):
            return int(await self._run(rig.get_ctcss_tone))

    async def set_ctcss_tone(self, tone: int) -> None:
        log.debug("set_ctcss_tone: %d (%.1f Hz)", tone, tone / 10.0)
        rig, H = self._require()
        try:
            await self._run(rig.set_ctcss_tone, H.RIG_VFO_CURR, int(tone))
        except (TypeError, AttributeError):
            await self._run(rig.set_ctcss_tone, int(tone))

    async def get_dcs_code(self) -> int:
        rig, H = self._require()
        try:
            return int(await self._run(rig.get_dcs_code, H.RIG_VFO_CURR))
        except (TypeError, AttributeError):
            return int(await self._run(rig.get_dcs_code))

    async def set_dcs_code(self, code: int) -> None:
        log.debug("set_dcs_code: %d", code)
        rig, H = self._require()
        try:
            await self._run(rig.set_dcs_code, H.RIG_VFO_CURR, int(code))
        except (TypeError, AttributeError):
            await self._run(rig.set_dcs_code, int(code))

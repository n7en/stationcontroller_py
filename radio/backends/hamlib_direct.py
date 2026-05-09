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
    "STRENGTH":  "RIG_LEVEL_STR",
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

    @property
    def connected(self) -> bool:
        return self._connected

    def _load_hamlib(self):
        try:
            import Hamlib
            return Hamlib
        except ImportError as exc:
            raise RadioBackendError(
                "hamlib Python bindings not installed. "
                "Install via your package manager (e.g. python3-hamlib on Linux) "
                "or use the rigctld backend instead."
            ) from exc

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fn, *args)

    async def connect(self) -> None:
        log.info(
            "Opening hamlib rig: model=%d port=%r baud=%d data=%d stop=%d parity=%s",
            self._model_id, self._port, self._baud_rate,
            self._data_bits, self._stop_bits, self._parity,
        )
        H = self._load_hamlib()
        self._H = H

        def _open():
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
        log.debug("Closing hamlib rig: model=%d port=%r", self._model_id, self._port)
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
        split_val, _tx_vfo = await self._run(rig.get_split_vfo, H.RIG_VFO_CURR)
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
        return float(await self._run(rig.get_level_f, H.RIG_VFO_CURR, getattr(H, attr)))

    async def set_level(self, level_name: str, value: float) -> None:
        rig, H = self._require()
        attr = _LEVEL_TO_HAMLIB.get(level_name.upper())
        if attr is None:
            raise RadioBackendError(f"Unknown level: {level_name}")
        await self._run(rig.set_level, H.RIG_VFO_CURR, getattr(H, attr), value)

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    async def get_info(self) -> str:
        rig, _ = self._require()
        return str(await self._run(rig.get_info))

"""
Drop-in fake Hamlib module for hardware-free testing of the hamlib_direct
radio backend.

Activation — add simulator/ to the front of PYTHONPATH before starting
the app so this file shadows the real Hamlib library:

    # Linux / macOS
    PYTHONPATH=simulator .venv/bin/python main.py

    # Windows (PowerShell)
    $env:PYTHONPATH = "simulator"; .venv\\Scripts\\python main.py

Each Rig() instance starts with sensible defaults.  The app drives state
through the normal set_freq / set_mode / set_ptt calls, and get_* calls
return whatever was last set.  Signal-strength readings include a small
noise term so the UI S-meter looks live.

This shim is intentionally self-contained — it has no dependency on the
rest of the simulator package so it can be used without the MQTT stack.
"""

import random

# ---------------------------------------------------------------------------
# Debug levels
# ---------------------------------------------------------------------------
RIG_DEBUG_NONE    = 0
RIG_DEBUG_BUG     = 1
RIG_DEBUG_ERR     = 2
RIG_DEBUG_WARN    = 3
RIG_DEBUG_VERBOSE = 4
RIG_DEBUG_TRACE   = 5


def rig_set_debug(level: int) -> None:  # noqa: ARG001
    pass


# ---------------------------------------------------------------------------
# VFO constants  (real Hamlib bit-field values)
# ---------------------------------------------------------------------------
RIG_VFO_CURR = 0
RIG_VFO_A    = 1 << 0   # 1
RIG_VFO_B    = 1 << 1   # 2
RIG_VFO_C    = 1 << 2   # 4
RIG_VFO_MEM  = 1 << 5   # 32

_VFO_NAMES = {
    RIG_VFO_A:   "VFOA",
    RIG_VFO_B:   "VFOB",
    RIG_VFO_C:   "VFOC",
    RIG_VFO_MEM: "MEM",
    RIG_VFO_CURR: "currVFO",
}


def rig_strvfo(vfo: int) -> str:
    return _VFO_NAMES.get(vfo, f"VFO({vfo})")


# ---------------------------------------------------------------------------
# Mode constants  (real Hamlib bit-field values)
# ---------------------------------------------------------------------------
RIG_MODE_NONE   = 0
RIG_MODE_AM     = 1 << 0    # 1
RIG_MODE_CW     = 1 << 1    # 2
RIG_MODE_USB    = 1 << 2    # 4
RIG_MODE_LSB    = 1 << 3    # 8
RIG_MODE_RTTY   = 1 << 4    # 16
RIG_MODE_FM     = 1 << 5    # 32
RIG_MODE_WFM    = 1 << 6    # 64
RIG_MODE_CWR    = 1 << 7    # 128
RIG_MODE_RTTYR  = 1 << 8    # 256
RIG_MODE_PKTLSB = 1 << 10   # 1024
RIG_MODE_PKTUSB = 1 << 11   # 2048
RIG_MODE_PKTFM  = 1 << 12   # 4096
RIG_MODE_FMN    = 1 << 21   # 2097152

_MODE_NAMES = {
    RIG_MODE_AM:     "AM",
    RIG_MODE_CW:     "CW",
    RIG_MODE_USB:    "USB",
    RIG_MODE_LSB:    "LSB",
    RIG_MODE_RTTY:   "RTTY",
    RIG_MODE_FM:     "FM",
    RIG_MODE_WFM:    "WFM",
    RIG_MODE_CWR:    "CWR",
    RIG_MODE_RTTYR:  "RTTYR",
    RIG_MODE_PKTLSB: "PKTLSB",
    RIG_MODE_PKTUSB: "PKTUSB",
    RIG_MODE_PKTFM:  "PKTFM",
    RIG_MODE_FMN:    "FMN",
}

_MODE_INTS = {v: k for k, v in _MODE_NAMES.items()}


def rig_strrmode(mode: int) -> str:
    return _MODE_NAMES.get(mode, f"MODE({mode})")


# ---------------------------------------------------------------------------
# PTT / Split constants
# ---------------------------------------------------------------------------
RIG_PTT_OFF     = 0
RIG_PTT_ON      = 1
RIG_PTT_ON_MIC  = 2
RIG_PTT_ON_DATA = 3

RIG_SPLIT_OFF = 0
RIG_SPLIT_ON  = 1


# ---------------------------------------------------------------------------
# Parity constants
# ---------------------------------------------------------------------------
RIG_PARITY_NONE  = 0
RIG_PARITY_ODD   = 1
RIG_PARITY_EVEN  = 2
RIG_PARITY_MARK  = 3
RIG_PARITY_SPACE = 4


# ---------------------------------------------------------------------------
# Level constants  (real Hamlib bit-field values, abbreviated)
# ---------------------------------------------------------------------------
RIG_LEVEL_STR     = 1 << 0    # Signal strength (S-meter)
RIG_LEVEL_SQL     = 1 << 2    # Squelch
RIG_LEVEL_AF      = 1 << 4    # AF gain
RIG_LEVEL_RF      = 1 << 5    # RF gain
RIG_LEVEL_AGC     = 1 << 3    # AGC
RIG_LEVEL_RFPOWER = 1 << 11   # TX power (normalised 0.0–1.0)
RIG_LEVEL_MICGAIN = 1 << 12
RIG_LEVEL_KEYSPD  = 1 << 14
RIG_LEVEL_COMP    = 1 << 18
RIG_LEVEL_METER   = 1 << 19
RIG_LEVEL_VOXGAIN = 1 << 21
RIG_LEVEL_SWR     = 1 << 26
RIG_LEVEL_ALC     = 1 << 28


# ---------------------------------------------------------------------------
# Rig state tree (mirrors real Hamlib object hierarchy)
# ---------------------------------------------------------------------------

class _Serial:
    def __init__(self) -> None:
        self.rate      = 9600
        self.data_bits = 8
        self.stop_bits = 1
        self.parity    = RIG_PARITY_NONE


class _Parm:
    def __init__(self) -> None:
        self.serial = _Serial()


class _RigPort:
    def __init__(self) -> None:
        self.pathname = ""
        self.parm     = _Parm()


class _RigState:
    def __init__(self) -> None:
        self.rigport = _RigPort()


# ---------------------------------------------------------------------------
# Rig — the main class the hamlib_direct backend instantiates
# ---------------------------------------------------------------------------

class Rig:
    """Simulated hamlib Rig object."""

    def __init__(self, model_id: int = 1) -> None:
        self._model = model_id
        self.state  = _RigState()

        # Internal radio state
        self._freq        = 14_200_000.0
        self._mode        = RIG_MODE_USB
        self._bw          = 2400
        self._vfo         = RIG_VFO_A
        self._ptt         = RIG_PTT_OFF
        self._split       = RIG_SPLIT_OFF
        self._split_freq  = 14_200_000.0
        self._levels: dict[int, float] = {
            RIG_LEVEL_RFPOWER: 1.0,
            RIG_LEVEL_AF:      0.5,
            RIG_LEVEL_RF:      1.0,
            RIG_LEVEL_SQL:     0.0,
            RIG_LEVEL_STR:     -10.0,
            RIG_LEVEL_SWR:     1.5,
            RIG_LEVEL_ALC:     0.0,
            RIG_LEVEL_AGC:     2.0,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Frequency
    # ------------------------------------------------------------------

    def get_freq(self, vfo: int) -> float:   # noqa: ARG002
        return self._freq

    def set_freq(self, vfo: int, hz: float) -> None:  # noqa: ARG002
        self._freq = float(hz)

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------

    def get_mode(self, vfo: int) -> tuple[int, int]:   # noqa: ARG002
        return (self._mode, self._bw)

    def set_mode(self, vfo: int, mode: int, bw: int) -> None:  # noqa: ARG002
        self._mode = mode
        self._bw   = int(bw)

    # ------------------------------------------------------------------
    # VFO
    # ------------------------------------------------------------------

    def get_vfo(self) -> int:
        return self._vfo

    def set_vfo(self, vfo: int) -> None:
        self._vfo = vfo

    # ------------------------------------------------------------------
    # PTT
    # ------------------------------------------------------------------

    def get_ptt(self, vfo: int) -> int:   # noqa: ARG002
        return self._ptt

    def set_ptt(self, vfo: int, ptt: int) -> None:   # noqa: ARG002
        self._ptt = ptt

    # ------------------------------------------------------------------
    # Split
    # ------------------------------------------------------------------

    def get_split_vfo(self, vfo: int) -> tuple[int, int]:   # noqa: ARG002
        return (self._split, RIG_VFO_B)

    def set_split_vfo(self, vfo: int, split: int, tx_vfo: int) -> None:  # noqa: ARG002
        self._split = split

    def get_split_freq(self, vfo: int) -> float:   # noqa: ARG002
        return self._split_freq

    def set_split_freq(self, vfo: int, hz: float) -> None:   # noqa: ARG002
        self._split_freq = float(hz)

    # ------------------------------------------------------------------
    # Levels
    # ------------------------------------------------------------------

    def get_level_f(self, vfo: int, level: int) -> float:   # noqa: ARG002
        val = self._levels.get(level, 0.0)
        # Add noise to the S-meter so the UI looks alive
        if level == RIG_LEVEL_STR:
            val += random.uniform(-1.5, 1.5)
        return val

    def set_level(self, vfo: int, level: int, value: float) -> None:  # noqa: ARG002
        self._levels[level] = float(value)

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_info(self) -> str:
        return f"SimRig (model_id={self._model})"

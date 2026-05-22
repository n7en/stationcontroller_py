"""
Abstract base class for radio control backends.

Every backend must implement the methods below.  Higher-level code
(RadioInterface) talks only to this interface, making it easy to swap
backends without touching application logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class RadioBackendError(Exception):
    """Raised when a backend operation fails."""


class RadioBackend(ABC):

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection to the radio / daemon."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection cleanly."""

    # ------------------------------------------------------------------
    # Frequency
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_frequency(self) -> float:
        """Return VFO-A frequency in Hz."""

    @abstractmethod
    async def set_frequency(self, hz: float) -> None:
        """Set VFO-A frequency in Hz."""

    # ------------------------------------------------------------------
    # Mode and filter
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_mode(self) -> tuple[str, float]:
        """Return (mode_string, bandwidth_hz) for the current mode."""

    @abstractmethod
    async def set_mode(self, mode: str, bandwidth_hz: float = 0) -> None:
        """Set operating mode and optional filter bandwidth (0 = radio default)."""

    # ------------------------------------------------------------------
    # VFO
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_vfo(self) -> str:
        """Return active VFO name, e.g. 'VFOA'."""

    @abstractmethod
    async def set_vfo(self, vfo: str) -> None:
        """Set active VFO."""

    # ------------------------------------------------------------------
    # PTT
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_ptt(self) -> bool:
        """Return True if the radio is transmitting."""

    @abstractmethod
    async def set_ptt(self, transmit: bool) -> None:
        """Key or un-key the transmitter."""

    # ------------------------------------------------------------------
    # Split
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_split(self) -> tuple[bool, Optional[float]]:
        """Return (split_active, tx_frequency_hz).  tx_freq may be None."""

    @abstractmethod
    async def set_split(self, active: bool, tx_hz: Optional[float] = None) -> None:
        """Enable/disable split; optionally set the TX frequency."""

    # ------------------------------------------------------------------
    # Levels and info
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_level(self, level_name: str) -> float:
        """
        Return a named level value.
        Common level names: STRENGTH (S-meter), RFPOWER, AF, RF, SQL.
        """

    @abstractmethod
    async def set_level(self, level_name: str, value: float) -> None:
        """
        Set a named level value.
        Common level names: RFPOWER (0.0-1.0), AF, RF, SQL, MICGAIN.
        """

    @abstractmethod
    async def get_info(self) -> str:
        """Return a human-readable string identifying the radio model."""

    # ------------------------------------------------------------------
    # Convenience: full state snapshot
    # ------------------------------------------------------------------

    async def get_full_state(self) -> dict:
        """
        Return a dict suitable for updating RadioState fields.
        Default implementation queries each capability individually.
        Subclasses may override with a more efficient batch command.
        """
        state: dict = {}
        try:
            state["frequency_hz"] = await self.get_frequency()
        except (RadioBackendError, TypeError, AttributeError):
            pass
        try:
            mode, bw = await self.get_mode()
            state["mode"] = mode
            state["bandwidth_hz"] = bw
        except (RadioBackendError, TypeError, AttributeError):
            pass
        try:
            state["vfo"] = await self.get_vfo()
        except (RadioBackendError, TypeError, AttributeError):
            pass
        try:
            state["ptt"] = await self.get_ptt()
        except (RadioBackendError, TypeError, AttributeError):
            pass
        try:
            split, tx_hz = await self.get_split()
            state["split"] = split
            state["split_freq_hz"] = tx_hz
        except (RadioBackendError, TypeError, AttributeError):
            pass
        try:
            state["signal_strength"] = await self.get_level("STRENGTH")
        except (RadioBackendError, TypeError, AttributeError):
            pass
        try:
            state["rf_power"] = await self.get_level("RFPOWER")
        except (RadioBackendError, TypeError, AttributeError):
            pass
        try:
            sub = await self.get_sub_state()
            state.update(sub)
        except (RadioBackendError, TypeError, AttributeError):
            pass
        return state

    async def get_sub_state(self) -> dict:
        """Poll VFO-B / sub-receiver state. Override in backends that support it."""
        return {}

    # ------------------------------------------------------------------
    # Optional capabilities — raise NotImplementedError by default so
    # callers can test support with a try/except.  Backends implement
    # whichever subset their hardware or protocol supports.
    # ------------------------------------------------------------------

    async def get_rit(self) -> int:
        """Return RIT (Receive Incremental Tuning) offset in Hz."""
        raise NotImplementedError

    async def set_rit(self, offset_hz: int) -> None:
        """Set RIT offset in Hz (0 to disable)."""
        raise NotImplementedError

    async def get_xit(self) -> int:
        """Return XIT (Transmit Incremental Tuning) offset in Hz."""
        raise NotImplementedError

    async def set_xit(self, offset_hz: int) -> None:
        """Set XIT offset in Hz (0 to disable)."""
        raise NotImplementedError

    async def get_func(self, func_name: str) -> bool:
        """
        Return the state of a named rig function.
        Common names: NB, NR, ANF, VOX, COMP, TUNER, LOCK, MUTE, REV, AFC.
        """
        raise NotImplementedError

    async def set_func(self, func_name: str, value: bool) -> None:
        """Enable or disable a named rig function."""
        raise NotImplementedError

    async def get_ctcss_tone(self) -> int:
        """Return the CTCSS tone code (tenths of Hz, e.g. 670 = 67.0 Hz)."""
        raise NotImplementedError

    async def set_ctcss_tone(self, tone: int) -> None:
        """Set the CTCSS encode tone (tenths of Hz; 0 = off)."""
        raise NotImplementedError

    async def get_dcs_code(self) -> int:
        """Return the DCS (Digital Coded Squelch) code."""
        raise NotImplementedError

    async def set_dcs_code(self, code: int) -> None:
        """Set the DCS code."""
        raise NotImplementedError

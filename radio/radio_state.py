"""
RadioState - snapshot of a single radio's operating parameters.

Fields use SI units throughout (frequency in Hz, bandwidth in Hz).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RadioMode(str, Enum):
    USB    = "USB"
    LSB    = "LSB"
    CW     = "CW"
    CWR    = "CWR"     # CW reverse sideband
    AM     = "AM"
    FM     = "FM"
    FMN    = "FMN"     # Narrow FM
    WFM    = "WFM"     # Wide FM (broadcast)
    RTTY   = "RTTY"
    RTTYR  = "RTTYR"
    PKTUSB = "PKTUSB"  # Digital / data modes
    PKTLSB = "PKTLSB"
    PKTFM  = "PKTFM"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_str(cls, s: str) -> "RadioMode":
        try:
            return cls(s.upper())
        except ValueError:
            return cls.UNKNOWN


@dataclass
class RadioState:
    name: str

    # Operating parameters
    frequency_hz: Optional[float] = None     # VFO-A / main RX frequency
    mode: Optional[RadioMode] = None
    bandwidth_hz: Optional[float] = None     # passband filter width
    vfo: Optional[str] = None                # e.g. "VFOA", "VFOB", "MEM"

    # Split operation
    split: bool = False
    split_freq_hz: Optional[float] = None    # TX frequency when split is on

    # TX state
    ptt: bool = False

    # Signal level (-54 dBm = S0 in hamlib convention, or raw S-meter 0-255)
    signal_strength: Optional[float] = None

    # Transmit power, normalized 0.0–1.0 (hamlib RFPOWER convention)
    rf_power: Optional[float] = None

    # VFO-B (split TX / second VFO)
    vfob_frequency_hz: Optional[float] = None
    vfob_mode: Optional[str] = None
    vfob_bandwidth_hz: Optional[float] = None

    # VFO-C (sub-receiver)
    sub_frequency_hz: Optional[float] = None
    sub_mode: Optional[str] = None
    sub_bandwidth_hz: Optional[float] = None

    # Connection meta
    connected: bool = False
    info: Optional[str] = None               # radio model / firmware string
    updated_at: float = field(default_factory=time.time)

    def diff(self, other: "RadioState") -> dict:
        """Return a dict of fields that differ between self and other."""
        fields = [
            "frequency_hz", "mode", "bandwidth_hz", "vfo",
            "split", "split_freq_hz", "ptt", "signal_strength",
            "rf_power", "connected",
            "vfob_frequency_hz", "vfob_mode", "vfob_bandwidth_hz",
            "sub_frequency_hz", "sub_mode", "sub_bandwidth_hz",
        ]
        return {f: getattr(other, f) for f in fields if getattr(self, f) != getattr(other, f)}

    def copy(self) -> "RadioState":
        import copy
        return copy.copy(self)

"""
QSORecord - a single logged contact from any logging software.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

_band_plan = None


def band_for_freq_hz(freq_hz: Optional[float]) -> Optional[str]:
    """Return the canonical band name ("20m", ...) for a frequency in Hz.

    Fallback for logging software that sends band values we cannot map
    directly.  Uses the amateur band plan from automation.bands.
    """
    if not freq_hz:
        return None
    global _band_plan
    if _band_plan is None:
        from automation.bands import BandPlan
        _band_plan = BandPlan.amateur()
    band = _band_plan.band_for_freq(freq_hz)
    return band.name if band else None


@dataclass
class QSORecord:
    callsign: str                           # DX callsign worked
    band: Optional[str]      = None         # "20m", "40m", …
    mode: Optional[str]      = None         # "USB", "CW", "FT8", …
    frequency_hz: Optional[float] = None    # VFO-A frequency
    timestamp: float         = field(default_factory=time.time)
    my_callsign: Optional[str] = None       # operator callsign
    country: Optional[str]   = None         # DXCC country name
    continent: Optional[str] = None         # "NA", "EU", …
    cq_zone: Optional[int]   = None
    itu_zone: Optional[int]  = None
    dupe: bool               = False
    source: str              = "unknown"    # "n1mm", "n3fjp"
    raw: Optional[dict]      = field(default=None, repr=False)

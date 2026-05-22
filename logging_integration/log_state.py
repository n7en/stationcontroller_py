"""
QSORecord - a single logged contact from any logging software.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


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

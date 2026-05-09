"""
Band plan - amateur radio frequency allocations.

Three levels of detail:

  Band        - the full allocation (40m = 7.000-7.300 MHz)
  BandSegment - a sub-range with characteristic modes (CW, digital, phone)
  Activity    - a specific frequency for a digital mode or calling frequency
                (FT8 @ 14.074.000, WSPR @ 14.095.600)

BandPlan holds a complete named plan (US Extra Class, Canadian Amateur, etc.)
and exposes lookup methods used by the automation engine and its conditions.

Built-in plans
--------------
  BandPlan.us_extra()    - FCC Part 97, Amateur Extra class (default)
  BandPlan.us_general()  - FCC Part 97, General class
  BandPlan.ca_amateur()  - Radio Amateurs of Canada band plan
  BandPlan.itu_region_2() - ITU Region 2 generic (no licence-class splits)
  BandPlan.amateur()     - alias for us_extra(), for backward compatibility

Custom plans can be defined entirely in YAML or loaded via band_plan_from_config().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BandSegment:
    """A portion of a band allocated to a characteristic mode group."""
    name: str               # "cw", "digital", "phone", "beacon", "mixed"
    start_hz: float
    end_hz: float
    modes: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""

    def contains(self, freq_hz: float) -> bool:
        return self.start_hz <= freq_hz <= self.end_hz


@dataclass(frozen=True)
class Activity:
    """A well-known activity frequency within a band (FT8, WSPR, JS8, calling)."""
    name: str               # e.g., "ft8", "wspr", "js8", "cw_calling"
    frequency_hz: float
    mode: str               # e.g., "FT8", "CW", "USB" - informational
    bandwidth_hz: float = 3000.0    # approximate signal bandwidth
    description: str = ""

    def near(self, freq_hz: float, tolerance_hz: float) -> bool:
        return abs(freq_hz - self.frequency_hz) <= tolerance_hz


@dataclass(frozen=True)
class Band:
    """A complete amateur radio band allocation."""
    name: str
    start_hz: float
    end_hz: float
    modes: tuple[str, ...] = field(default_factory=tuple)
    segments: tuple[BandSegment, ...] = field(default_factory=tuple)
    activities: tuple[Activity, ...] = field(default_factory=tuple)

    def contains(self, freq_hz: float) -> bool:
        return self.start_hz <= freq_hz <= self.end_hz

    def segment_for_freq(self, freq_hz: float) -> Optional[BandSegment]:
        """Return the segment containing freq_hz, or None."""
        for seg in self.segments:
            if seg.contains(freq_hz):
                return seg
        return None

    def activity_near(
        self, freq_hz: float, tolerance_hz: float = 500.0
    ) -> Optional[Activity]:
        """Return the nearest activity within tolerance_hz, or None."""
        best: Optional[Activity] = None
        best_dist = float("inf")
        for act in self.activities:
            dist = abs(freq_hz - act.frequency_hz)
            if dist <= tolerance_hz and dist < best_dist:
                best = act
                best_dist = dist
        return best


# ---------------------------------------------------------------------------
# BandPlan
# ---------------------------------------------------------------------------

class BandPlan:
    """
    A complete named band plan - a collection of Band objects with segments
    and activities representing a specific regional or licence-class allocation.
    """

    def __init__(
        self,
        bands: list[Band] | None = None,
        name: str = "",
        country: str = "",
        region: str = "",
    ) -> None:
        self.name = name
        self.country = country
        self.region = region
        self._bands: list[Band] = list(bands or [])
        self._by_name: dict[str, Band] = {b.name: b for b in self._bands}

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def band_for_freq(self, freq_hz: float) -> Optional[Band]:
        for band in self._bands:
            if band.contains(freq_hz):
                return band
        return None

    def band(self, name: str) -> Optional[Band]:
        return self._by_name.get(name)

    def segment_for_freq(self, freq_hz: float) -> Optional[BandSegment]:
        """Return the segment that contains freq_hz across all bands."""
        band = self.band_for_freq(freq_hz)
        if band is None:
            return None
        return band.segment_for_freq(freq_hz)

    def activity_near(
        self, freq_hz: float, tolerance_hz: float = 500.0
    ) -> Optional[Activity]:
        """
        Return the nearest known activity within tolerance_hz of freq_hz,
        searching across all bands.  Returns None if nothing is close enough.
        """
        best: Optional[Activity] = None
        best_dist = float("inf")
        band = self.band_for_freq(freq_hz)
        candidates = band.activities if band else []
        for act in candidates:
            dist = abs(freq_hz - act.frequency_hz)
            if dist <= tolerance_hz and dist < best_dist:
                best = act
                best_dist = dist
        return best

    def names(self) -> list[str]:
        return [b.name for b in self._bands]

    def __len__(self) -> int:
        return len(self._bands)

    # ------------------------------------------------------------------
    # Built-in plans
    # ------------------------------------------------------------------

    @classmethod
    def us_extra(cls) -> "BandPlan":
        """
        FCC Part 97 - Amateur Extra class HF/VHF/UHF privileges.
        Includes standard digital-mode activity frequencies.
        """
        return cls(
            name="US Amateur Extra",
            country="US",
            region="ITU-2",
            bands=_us_extra_bands(),
        )

    @classmethod
    def us_general(cls) -> "BandPlan":
        """
        FCC Part 97 - General class HF privileges.
        General has narrower phone/CW windows on 80, 40, 20, 15 m.
        """
        return cls(
            name="US General",
            country="US",
            region="ITU-2",
            bands=_us_general_bands(),
        )

    @classmethod
    def ca_amateur(cls) -> "BandPlan":
        """
        Radio Amateurs of Canada (RAC) band plan.
        Key difference from US: 40m phone starts at 7.100 MHz (vs US 7.125).
        """
        return cls(
            name="Canadian Amateur",
            country="CA",
            region="ITU-2",
            bands=_ca_bands(),
        )

    @classmethod
    def itu_region_2(cls) -> "BandPlan":
        """
        ITU Region 2 generic allocation (Americas) - no licence-class splits.
        Use as a baseline when no country-specific plan is configured.
        """
        return cls(
            name="ITU Region 2",
            region="ITU-2",
            bands=_itu_r2_bands(),
        )

    @classmethod
    def amateur(cls) -> "BandPlan":
        """Alias for us_extra() - backward compatibility."""
        return cls.us_extra()

    @classmethod
    def from_built_in(cls, name: str) -> "BandPlan":
        factories = {
            "us_extra": cls.us_extra,
            "us_general": cls.us_general,
            "ca_amateur": cls.ca_amateur,
            "itu_region_2": cls.itu_region_2,
            "amateur": cls.amateur,
        }
        key = name.lower().replace(" ", "_").replace("-", "_")
        factory = factories.get(key)
        if factory is None:
            raise ValueError(
                f"Unknown built-in band plan: {name!r}. "
                f"Available: {', '.join(factories)}"
            )
        return factory()


# Backward-compatibility alias
BandRegistry = BandPlan


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------

def band_plan_from_config(cfg: dict) -> BandPlan:
    """
    Build a BandPlan from a config dict.

    Supports:
      built_in: us_extra          # use a named built-in plan
      name: "My Plan"             # optional display name
      bands: [...]                # fully custom band list

    If both built_in and bands are present, the custom bands list is used
    (built_in is ignored - use it OR bands, not both).
    """
    if not cfg:
        return BandPlan.amateur()

    if "bands" in cfg:
        bands = [_band_from_dict(b) for b in cfg["bands"]]
        return BandPlan(
            name=cfg.get("name", "Custom"),
            country=cfg.get("country", ""),
            region=cfg.get("region", ""),
            bands=bands,
        )

    if "built_in" in cfg:
        plan = BandPlan.from_built_in(cfg["built_in"])
        if "name" in cfg:
            plan.name = cfg["name"]
        return plan

    return BandPlan.amateur()


def _band_from_dict(cfg: dict) -> Band:
    segments = tuple(
        BandSegment(
            name=s["name"],
            start_hz=float(s["start_hz"]),
            end_hz=float(s["end_hz"]),
            modes=tuple(s.get("modes", [])),
            description=s.get("description", ""),
        )
        for s in cfg.get("segments", [])
    )
    activities = tuple(
        Activity(
            name=a["name"],
            frequency_hz=float(a["frequency_hz"]),
            mode=a.get("mode", ""),
            bandwidth_hz=float(a.get("bandwidth_hz", 3000.0)),
            description=a.get("description", ""),
        )
        for a in cfg.get("activities", [])
    )
    return Band(
        name=cfg["name"],
        start_hz=float(cfg["start_hz"]),
        end_hz=float(cfg["end_hz"]),
        modes=tuple(cfg.get("modes", [])),
        segments=segments,
        activities=activities,
    )


# ---------------------------------------------------------------------------
# Built-in band data
# ---------------------------------------------------------------------------

def _ft8_activities() -> dict[str, Activity]:
    """FT8 standard operating frequencies (worldwide)."""
    return {
        "160m": Activity("ft8", 1_840_000, "FT8", 50),
        "80m":  Activity("ft8", 3_573_000, "FT8", 50),
        "40m":  Activity("ft8", 7_074_000, "FT8", 50),
        "30m":  Activity("ft8", 10_136_000, "FT8", 50),
        "20m":  Activity("ft8", 14_074_000, "FT8", 50),
        "17m":  Activity("ft8", 18_100_000, "FT8", 50),
        "15m":  Activity("ft8", 21_074_000, "FT8", 50),
        "12m":  Activity("ft8", 24_915_000, "FT8", 50),
        "10m":  Activity("ft8", 28_074_000, "FT8", 50),
        "6m":   Activity("ft8", 50_313_000, "FT8", 50),
    }


def _wspr_activities() -> dict[str, Activity]:
    return {
        "160m": Activity("wspr", 1_836_600,  "WSPR", 6),
        "80m":  Activity("wspr", 3_568_600,  "WSPR", 6),
        "40m":  Activity("wspr", 7_038_600,  "WSPR", 6),
        "30m":  Activity("wspr", 10_138_700, "WSPR", 6),
        "20m":  Activity("wspr", 14_095_600, "WSPR", 6),
        "17m":  Activity("wspr", 18_104_600, "WSPR", 6),
        "15m":  Activity("wspr", 21_094_600, "WSPR", 6),
        "10m":  Activity("wspr", 28_124_600, "WSPR", 6),
    }


def _js8_activities() -> dict[str, Activity]:
    return {
        "80m": Activity("js8", 3_578_000, "JS8", 50),
        "40m": Activity("js8", 7_078_000, "JS8", 50),
        "30m": Activity("js8", 10_130_000, "JS8", 50),
        "20m": Activity("js8", 14_078_000, "JS8", 50),
        "15m": Activity("js8", 21_078_000, "JS8", 50),
        "10m": Activity("js8", 28_078_000, "JS8", 50),
    }


def _ft4_activities() -> dict[str, Activity]:
    return {
        "80m": Activity("ft4", 3_575_000, "FT4", 90),
        "40m": Activity("ft4", 7_047_500, "FT4", 90),
        "30m": Activity("ft4", 10_140_000, "FT4", 90),
        "20m": Activity("ft4", 14_080_000, "FT4", 90),
        "15m": Activity("ft4", 21_140_000, "FT4", 90),
        "10m": Activity("ft4", 28_180_000, "FT4", 90),
    }


def _band_activities(band_name: str) -> tuple[Activity, ...]:
    acts = []
    for d in [_ft8_activities(), _wspr_activities(), _js8_activities(), _ft4_activities()]:
        if band_name in d:
            acts.append(d[band_name])
    return tuple(acts)


def _us_extra_bands() -> list[Band]:
    ft8 = _ft8_activities()
    wspr = _wspr_activities()
    js8 = _js8_activities()
    ft4 = _ft4_activities()

    def acts(*dicts_and_key):
        key = dicts_and_key[-1]
        dicts = dicts_and_key[:-1]
        return tuple(d[key] for d in dicts if key in d)

    return [
        Band("160m", 1_800_000, 2_000_000,
             segments=(
                 BandSegment("cw",      1_800_000, 1_850_000, ("CW",)),
                 BandSegment("digital", 1_838_000, 1_850_000, ("FT8", "WSPR", "PSK31")),
                 BandSegment("phone",   1_850_000, 2_000_000, ("LSB", "AM")),
             ),
             activities=acts(ft8, wspr, "160m")),

        Band("80m", 3_500_000, 4_000_000,
             segments=(
                 BandSegment("cw",      3_500_000, 3_600_000, ("CW",)),
                 BandSegment("digital", 3_570_000, 3_600_000, ("FT8", "WSPR", "JS8", "RTTY")),
                 BandSegment("phone",   3_600_000, 4_000_000, ("LSB", "AM")),
             ),
             activities=acts(ft8, wspr, js8, ft4, "80m")),

        Band("40m", 7_000_000, 7_300_000,
             segments=(
                 BandSegment("cw",      7_000_000, 7_125_000, ("CW",),
                             description="Extra: 7.000-7.125 CW/data"),
                 BandSegment("digital", 7_025_000, 7_125_000, ("FT8", "WSPR", "JS8", "RTTY", "PSK31"),
                             description="Digital sub-band within CW portion"),
                 BandSegment("phone",   7_125_000, 7_300_000, ("LSB",),
                             description="Extra phone: 7.125-7.300"),
             ),
             activities=acts(ft8, wspr, js8, ft4, "40m")),

        Band("30m", 10_100_000, 10_150_000,
             segments=(
                 BandSegment("cw",      10_100_000, 10_130_000, ("CW",)),
                 BandSegment("digital", 10_130_000, 10_150_000, ("FT8", "WSPR", "JS8", "RTTY"),
                             description="No phone on 30m (WARC)"),
             ),
             activities=acts(ft8, wspr, js8, "30m")),

        Band("20m", 14_000_000, 14_350_000,
             segments=(
                 BandSegment("cw",      14_000_000, 14_150_000, ("CW",)),
                 BandSegment("digital", 14_070_000, 14_150_000, ("FT8", "WSPR", "JS8", "RTTY", "PSK31")),
                 BandSegment("phone",   14_150_000, 14_350_000, ("USB",)),
             ),
             activities=acts(ft8, wspr, js8, ft4, "20m")),

        Band("17m", 18_068_000, 18_168_000,
             segments=(
                 BandSegment("cw",      18_068_000, 18_110_000, ("CW",)),
                 BandSegment("digital", 18_095_000, 18_110_000, ("FT8", "WSPR", "RTTY")),
                 BandSegment("phone",   18_110_000, 18_168_000, ("USB",)),
             ),
             activities=acts(ft8, wspr, "17m")),

        Band("15m", 21_000_000, 21_450_000,
             segments=(
                 BandSegment("cw",      21_000_000, 21_200_000, ("CW",)),
                 BandSegment("digital", 21_070_000, 21_200_000, ("FT8", "WSPR", "RTTY", "PSK31")),
                 BandSegment("phone",   21_200_000, 21_450_000, ("USB",)),
             ),
             activities=acts(ft8, wspr, js8, ft4, "15m")),

        Band("12m", 24_890_000, 24_990_000,
             segments=(
                 BandSegment("cw",      24_890_000, 24_930_000, ("CW",)),
                 BandSegment("digital", 24_910_000, 24_930_000, ("FT8", "WSPR", "RTTY")),
                 BandSegment("phone",   24_930_000, 24_990_000, ("USB",)),
             ),
             activities=acts(ft8, wspr, "12m")),

        Band("10m", 28_000_000, 29_700_000,
             segments=(
                 BandSegment("cw",      28_000_000, 28_300_000, ("CW",)),
                 BandSegment("digital", 28_070_000, 28_189_000, ("FT8", "WSPR", "RTTY", "PSK31")),
                 BandSegment("phone",   28_300_000, 29_700_000, ("USB", "AM", "FM")),
             ),
             activities=acts(ft8, wspr, js8, ft4, "10m")),

        Band("6m",   50_000_000,  54_000_000,
             segments=(
                 BandSegment("cw",    50_000_000, 50_100_000, ("CW",)),
                 BandSegment("digital", 50_290_000, 50_320_000, ("FT8",)),
                 BandSegment("phone", 50_100_000, 54_000_000, ("USB", "FM")),
             ),
             activities=(Activity("ft8", 50_313_000, "FT8", 50),)),

        Band("2m",  144_000_000, 148_000_000,
             segments=(
                 BandSegment("cw",    144_000_000, 144_100_000, ("CW",)),
                 BandSegment("digital", 144_100_000, 144_300_000, ("FT8", "WSPR")),
                 BandSegment("phone", 144_200_000, 148_000_000, ("USB", "FM")),
             ),
             activities=(Activity("ft8", 144_174_000, "FT8", 50),)),

        Band("1.25m", 222_000_000, 225_000_000),
        Band("70cm",  420_000_000, 450_000_000),
    ]


def _us_general_bands() -> list[Band]:
    """
    US General class - narrower phone windows on 80/40/20/15m.
    Non-General portions are still listed as segments with a note.
    """
    ft8 = _ft8_activities()
    wspr = _wspr_activities()
    js8 = _js8_activities()
    ft4 = _ft4_activities()

    def acts(*dicts_and_key):
        key = dicts_and_key[-1]
        dicts = dicts_and_key[:-1]
        return tuple(d[key] for d in dicts if key in d)

    return [
        Band("160m", 1_800_000, 2_000_000,
             segments=(
                 BandSegment("cw",      1_800_000, 1_850_000, ("CW",)),
                 BandSegment("digital", 1_838_000, 1_850_000, ("FT8", "WSPR")),
                 BandSegment("phone",   1_850_000, 2_000_000, ("LSB",)),
             ),
             activities=acts(ft8, wspr, "160m")),

        Band("80m", 3_500_000, 4_000_000,
             segments=(
                 BandSegment("cw",      3_525_000, 3_600_000, ("CW",),
                             description="General CW: 3.525-3.600"),
                 BandSegment("digital", 3_570_000, 3_600_000, ("FT8", "WSPR", "RTTY")),
                 BandSegment("phone",   3_800_000, 4_000_000, ("LSB",),
                             description="General phone: 3.800-4.000"),
             ),
             activities=acts(ft8, wspr, js8, ft4, "80m")),

        Band("40m", 7_000_000, 7_300_000,
             segments=(
                 BandSegment("cw",      7_025_000, 7_125_000, ("CW",),
                             description="General CW: 7.025-7.125"),
                 BandSegment("digital", 7_025_000, 7_125_000, ("FT8", "WSPR", "JS8", "RTTY")),
                 BandSegment("phone",   7_175_000, 7_300_000, ("LSB",),
                             description="General phone: 7.175-7.300"),
             ),
             activities=acts(ft8, wspr, js8, ft4, "40m")),

        Band("30m",  10_100_000, 10_150_000,
             activities=acts(ft8, wspr, js8, "30m")),

        Band("20m", 14_000_000, 14_350_000,
             segments=(
                 BandSegment("cw",      14_025_000, 14_150_000, ("CW",),
                             description="General CW: 14.025-14.150"),
                 BandSegment("digital", 14_070_000, 14_150_000, ("FT8", "WSPR", "RTTY")),
                 BandSegment("phone",   14_225_000, 14_350_000, ("USB",),
                             description="General phone: 14.225-14.350"),
             ),
             activities=acts(ft8, wspr, js8, ft4, "20m")),

        Band("17m",  18_068_000, 18_168_000,
             activities=acts(ft8, wspr, "17m")),

        Band("15m", 21_000_000, 21_450_000,
             segments=(
                 BandSegment("cw",      21_025_000, 21_200_000, ("CW",)),
                 BandSegment("digital", 21_070_000, 21_200_000, ("FT8", "WSPR", "RTTY")),
                 BandSegment("phone",   21_275_000, 21_450_000, ("USB",),
                             description="General phone: 21.275-21.450"),
             ),
             activities=acts(ft8, wspr, js8, ft4, "15m")),

        Band("12m",  24_890_000, 24_990_000,
             activities=acts(ft8, wspr, "12m")),
        Band("10m",  28_000_000, 29_700_000,
             activities=acts(ft8, wspr, js8, ft4, "10m")),
        Band("6m",   50_000_000,  54_000_000),
        Band("2m",  144_000_000, 148_000_000),
        Band("1.25m", 222_000_000, 225_000_000),
        Band("70cm",  420_000_000, 450_000_000),
    ]


def _ca_bands() -> list[Band]:
    """
    Canadian Amateur band plan (Advanced/Basic with Honours).
    Key difference from US on 40m: phone allowed from 7.100 MHz
    (vs US Extra 7.125, US General 7.175).
    """
    ft8 = _ft8_activities()
    wspr = _wspr_activities()
    js8 = _js8_activities()

    def acts(*dicts_and_key):
        key = dicts_and_key[-1]
        dicts = dicts_and_key[:-1]
        return tuple(d[key] for d in dicts if key in d)

    return [
        Band("160m", 1_800_000, 2_000_000,
             activities=acts(ft8, wspr, "160m")),

        Band("80m", 3_500_000, 4_000_000,
             segments=(
                 BandSegment("cw",      3_500_000, 3_600_000, ("CW",)),
                 BandSegment("digital", 3_570_000, 3_600_000, ("FT8", "WSPR", "RTTY")),
                 BandSegment("phone",   3_600_000, 4_000_000, ("LSB",)),
             ),
             activities=acts(ft8, wspr, js8, "80m")),

        Band("40m", 7_000_000, 7_300_000,
             segments=(
                 BandSegment("cw",      7_000_000, 7_100_000, ("CW",),
                             description="Canada CW: 7.000-7.100 (vs US 7.125)"),
                 BandSegment("digital", 7_025_000, 7_100_000, ("FT8", "WSPR", "JS8", "RTTY")),
                 BandSegment("phone",   7_100_000, 7_300_000, ("LSB",),
                             description="Canada phone: 7.100-7.300 (vs US Extra 7.125)"),
             ),
             activities=acts(ft8, wspr, js8, "40m")),

        Band("30m",  10_100_000, 10_150_000,
             activities=acts(ft8, wspr, "30m")),

        Band("20m", 14_000_000, 14_350_000,
             segments=(
                 BandSegment("cw",      14_000_000, 14_150_000, ("CW",)),
                 BandSegment("digital", 14_070_000, 14_150_000, ("FT8", "WSPR", "RTTY")),
                 BandSegment("phone",   14_150_000, 14_350_000, ("USB",)),
             ),
             activities=acts(ft8, wspr, js8, "20m")),

        Band("17m",  18_068_000, 18_168_000,
             activities=acts(ft8, wspr, "17m")),

        Band("15m", 21_000_000, 21_450_000,
             activities=acts(ft8, wspr, js8, "15m")),

        Band("12m",  24_890_000, 24_990_000),
        Band("10m",  28_000_000, 29_700_000,
             activities=acts(ft8, wspr, "10m")),
        Band("6m",   50_000_000,  54_000_000),
        Band("2m",  144_000_000, 148_000_000),
        Band("1.25m", 220_000_000, 225_000_000,
             description="Canada 1.25m: 220-225 MHz (vs US 222-225)"),
        Band("70cm",  430_000_000, 450_000_000,
             description="Canada 70cm: 430-450 MHz (vs US 420-450)"),
    ]


def _itu_r2_bands() -> list[Band]:
    """
    ITU Region 2 generic HF allocations - Americas, no licence-class splits.
    Includes digital activity frequencies without mode-segment detail.
    """
    ft8 = _ft8_activities()
    wspr = _wspr_activities()

    def acts(*dicts_and_key):
        key = dicts_and_key[-1]
        dicts = dicts_and_key[:-1]
        return tuple(d[key] for d in dicts if key in d)

    return [
        Band("160m",  1_800_000,   2_000_000, activities=acts(ft8, wspr, "160m")),
        Band("80m",   3_500_000,   4_000_000, activities=acts(ft8, wspr, "80m")),
        Band("40m",   7_000_000,   7_300_000, activities=acts(ft8, wspr, "40m")),
        Band("30m",  10_100_000,  10_150_000, activities=acts(ft8, wspr, "30m")),
        Band("20m",  14_000_000,  14_350_000, activities=acts(ft8, wspr, "20m")),
        Band("17m",  18_068_000,  18_168_000, activities=acts(ft8, wspr, "17m")),
        Band("15m",  21_000_000,  21_450_000, activities=acts(ft8, wspr, "15m")),
        Band("12m",  24_890_000,  24_990_000),
        Band("10m",  28_000_000,  29_700_000, activities=acts(ft8, wspr, "10m")),
        Band("6m",   50_000_000,  54_000_000),
        Band("2m",  144_000_000, 148_000_000),
        Band("70cm", 420_000_000, 450_000_000),
    ]

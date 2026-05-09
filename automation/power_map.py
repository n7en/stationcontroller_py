"""
Power maps: translate between radio drive power and antenna/output power.

Three implementations:
  IdentityPowerMap   - 1:1, no gain or loss
  LinearPowerMap     - fixed dB gain/loss (e.g. amplifier with known gain)
  LookupPowerMap     - user-measured [(radio_w, antenna_w)] points, linearly
                       interpolated; extrapolates at boundaries

All maps expose forward(radio_w) -> antenna_w and inverse(antenna_w) -> radio_w.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod


class PowerMap(ABC):
    @abstractmethod
    def forward(self, radio_w: float) -> float:
        """Translate radio drive watts to antenna/output watts."""

    @abstractmethod
    def inverse(self, antenna_w: float) -> float:
        """Translate desired antenna/output watts to required radio drive watts."""


class IdentityPowerMap(PowerMap):
    def forward(self, radio_w: float) -> float:
        return radio_w

    def inverse(self, antenna_w: float) -> float:
        return antenna_w


class LinearPowerMap(PowerMap):
    """
    Fixed gain expressed in dB.

    gain_db > 0 -> amplification (e.g. amp with 20 dB gain)
    gain_db < 0 -> attenuation/loss (e.g. long feedline)
    """

    def __init__(self, gain_db: float) -> None:
        self.gain_db = gain_db
        self._ratio = 10.0 ** (gain_db / 10.0)

    def forward(self, radio_w: float) -> float:
        return radio_w * self._ratio

    def inverse(self, antenna_w: float) -> float:
        return antenna_w / self._ratio


class LookupPowerMap(PowerMap):
    """
    Piecewise-linear map from user-measured [(radio_w, antenna_w)] pairs.

    Points need not be sorted; the constructor sorts them by radio_w.
    Extrapolates linearly beyond the measured range using the slope of
    the nearest segment.
    """

    def __init__(self, points: list[tuple[float, float]]) -> None:
        if len(points) < 2:
            raise ValueError("LookupPowerMap requires at least 2 points")
        self._fwd = sorted(points, key=lambda p: p[0])
        self._inv = sorted(points, key=lambda p: p[1])

    def forward(self, radio_w: float) -> float:
        return self._interpolate(radio_w, self._fwd, x_idx=0, y_idx=1)

    def inverse(self, antenna_w: float) -> float:
        return self._interpolate(antenna_w, self._inv, x_idx=1, y_idx=0)

    @staticmethod
    def _interpolate(
        x: float,
        points: list[tuple[float, float]],
        x_idx: int,
        y_idx: int,
    ) -> float:
        xs = [p[x_idx] for p in points]
        ys = [p[y_idx] for p in points]

        if x <= xs[0]:
            if xs[1] == xs[0]:
                return ys[0]
            slope = (ys[1] - ys[0]) / (xs[1] - xs[0])
            return ys[0] + slope * (x - xs[0])

        if x >= xs[-1]:
            if xs[-1] == xs[-2]:
                return ys[-1]
            slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
            return ys[-1] + slope * (x - xs[-1])

        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                span = xs[i + 1] - xs[i]
                if span == 0:
                    return ys[i]
                t = (x - xs[i]) / span
                return ys[i] + t * (ys[i + 1] - ys[i])

        return ys[-1]


def power_map_from_config(cfg: dict) -> PowerMap:
    """
    Construct a PowerMap from a config dict.

    Supported types:
      {"type": "identity"}
      {"type": "linear", "gain_db": 20.0}
      {"type": "lookup", "points": [[5, 600], [4, 450], [3, 300]]}
    """
    kind = cfg.get("type", "identity")
    if kind == "identity":
        return IdentityPowerMap()
    if kind == "linear":
        return LinearPowerMap(float(cfg["gain_db"]))
    if kind == "lookup":
        points = [tuple(p) for p in cfg["points"]]
        return LookupPowerMap(points)
    raise ValueError(f"Unknown power_map type: {kind!r}")

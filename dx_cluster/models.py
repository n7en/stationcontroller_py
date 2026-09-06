"""
DX Cluster data models mirroring the Spothole API schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DXSpot:
    id: str
    dx_call: str
    freq: float                         # Hz
    band: Optional[str]        = None   # "20m", "40m", …
    mode: Optional[str]        = None   # "SSB", "CW", "FT8", …
    mode_type: Optional[str]   = None   # "PHONE", "CW", "DATA"
    time: Optional[float]      = None   # Unix epoch (UTC)
    comment: Optional[str]     = None
    source: Optional[str]      = None   # "Cluster", "POTA", …
    sig: Optional[str]         = None   # "POTA", "SOTA", …
    dx_country: Optional[str]  = None
    dx_flag: Optional[str]     = None
    dx_continent: Optional[str] = None
    dx_dxcc_id: Optional[int]  = None
    dx_cq_zone: Optional[int]  = None
    de_call: Optional[str]     = None   # spotter callsign
    dx_grid: Optional[str]     = None
    dx_latitude: Optional[float] = None
    dx_longitude: Optional[float] = None
    qrt: bool = False

    @classmethod
    def from_api(cls, d: dict) -> "DXSpot":
        return cls(
            id           = d.get("id", ""),
            dx_call      = d.get("dx_call", ""),
            freq         = float(d.get("freq") or 0),
            band         = d.get("band"),
            mode         = d.get("mode"),
            mode_type    = d.get("mode_type"),
            time         = d.get("time"),
            comment      = d.get("comment"),
            source       = d.get("source"),
            sig          = d.get("sig"),
            dx_country   = d.get("dx_country"),
            dx_flag      = d.get("dx_flag"),
            dx_continent = d.get("dx_continent"),
            dx_dxcc_id   = d.get("dx_dxcc_id"),
            dx_cq_zone   = d.get("dx_cq_zone"),
            de_call      = d.get("de_call"),
            dx_grid      = d.get("dx_grid"),
            dx_latitude  = d.get("dx_latitude"),
            dx_longitude = d.get("dx_longitude"),
            qrt          = bool(d.get("qrt", False)),
        )

    def as_dict(self) -> dict:
        return {
            "id":           self.id,
            "dx_call":      self.dx_call,
            "freq":         self.freq,
            "band":         self.band,
            "mode":         self.mode,
            "mode_type":    self.mode_type,
            "time":         self.time,
            "comment":      self.comment,
            "source":       self.source,
            "sig":          self.sig,
            "dx_country":   self.dx_country,
            "dx_flag":      self.dx_flag,
            "dx_continent": self.dx_continent,
            "dx_dxcc_id":   self.dx_dxcc_id,
            "dx_cq_zone":   self.dx_cq_zone,
            "de_call":      self.de_call,
            "dx_grid":      self.dx_grid,
            "dx_latitude":  self.dx_latitude,
            "dx_longitude": self.dx_longitude,
            "qrt":          self.qrt,
        }


@dataclass
class SolarConditions:
    updated: Optional[float]     = None
    sfi: Optional[int]           = None   # Solar Flux Index
    a_index: Optional[int]       = None
    k_index: Optional[int]       = None
    xray: Optional[str]          = None
    sunspots: Optional[int]      = None
    solar_wind: Optional[float]  = None
    geomag_field: Optional[str]  = None
    geomag_storm_scale: Optional[int]  = None
    geomag_storm_desc: Optional[str]   = None
    radio_blackout_scale: Optional[int] = None
    xray_desc: Optional[str]     = None
    band_conditions_desc: Optional[str] = None
    hf_conditions: dict          = field(default_factory=dict)
    vhf_conditions: dict         = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict) -> "SolarConditions":
        return cls(
            updated              = d.get("updated"),
            sfi                  = d.get("sfi"),
            a_index              = d.get("a_index"),
            k_index              = d.get("k_index"),
            xray                 = d.get("xray"),
            sunspots             = d.get("sunspots"),
            solar_wind           = d.get("solar_wind"),
            geomag_field         = d.get("geomag_field"),
            geomag_storm_scale   = d.get("geomag_storm_scale"),
            geomag_storm_desc    = d.get("geomag_storm_desc"),
            radio_blackout_scale = d.get("radio_blackout_scale"),
            xray_desc            = d.get("xray_desc"),
            band_conditions_desc = d.get("band_conditions_desc"),
            hf_conditions        = d.get("hf_conditions") or {},
            vhf_conditions       = d.get("vhf_conditions") or {},
        )

    def as_dict(self) -> dict:
        return {
            "updated":              self.updated,
            "sfi":                  self.sfi,
            "a_index":              self.a_index,
            "k_index":              self.k_index,
            "xray":                 self.xray,
            "sunspots":             self.sunspots,
            "solar_wind":           self.solar_wind,
            "geomag_field":         self.geomag_field,
            "geomag_storm_scale":   self.geomag_storm_scale,
            "geomag_storm_desc":    self.geomag_storm_desc,
            "radio_blackout_scale": self.radio_blackout_scale,
            "xray_desc":            self.xray_desc,
            "band_conditions_desc": self.band_conditions_desc,
            "hf_conditions":        self.hf_conditions,
            "vhf_conditions":       self.vhf_conditions,
        }

"""
N1MM+ UDP listener.

N1MM+ broadcasts XML packets on UDP port 12060 (configurable).
We listen for <ContactInfo> packets and convert them to QSORecords.

Frequency note: N1MM+ transmits rxfreq / txfreq in units of 10 Hz.
Multiply by 10 to get Hz (e.g. 1420050 → 14,200,500 Hz = 14.200 MHz).
"""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Callable, Optional

from .log_state import QSORecord, band_for_freq_hz

log = logging.getLogger(__name__)

QSOCallback = Callable[[QSORecord], None]

# Map N1MM band strings to canonical band names.  N1MM normally sends the
# band as its MHz value ("14" = 20m, "3.5" = 80m); meters strings are kept
# for older versions.  Ambiguous values ("10" = 30m in MHz but 10m in
# meters) are resolved by preferring the frequency-derived band in
# _parse_contact - this map is only the fallback.
_BAND_MAP: dict[str, str] = {
    # MHz values (current N1MM+ ContactInfo format)
    "1.8": "160m", "3.5": "80m", "5.3": "60m", "7": "40m",
    "14": "20m",   "18": "17m",  "21": "15m",
    "24": "12m",   "28": "10m",  "50": "6m",   "144": "2m",
    "420": "70cm", "902": "33cm",
    # meters strings (legacy)
    "160": "160m", "80": "80m", "60": "60m", "40": "40m",
    "30": "30m",   "20": "20m", "17": "17m", "15": "15m",
    "12": "12m",   "10": "10m", "6": "6m",   "2": "2m",
    "222": "1.25m","432": "70cm","1296": "23cm",
}


def _parse_contact(root: ET.Element) -> Optional[QSORecord]:
    """Parse a <ContactInfo> XML element into a QSORecord."""
    def _t(tag: str) -> str:
        el = root.find(tag)
        return (el.text or "").strip() if el is not None else ""

    callsign = _t("call")
    if not callsign:
        return None

    # Frequency: rxfreq is in 10 Hz units
    freq_hz: Optional[float] = None
    raw_freq = _t("rxfreq")
    if raw_freq:
        try:
            freq_hz = float(raw_freq) * 10.0
        except ValueError:
            pass

    # Band: derive from frequency when possible (unambiguous), fall back to
    # the band string (MHz value or meters, varies by N1MM version).
    band: Optional[str] = band_for_freq_hz(freq_hz)
    raw_band = _t("band")
    if band is None and raw_band:
        band = _BAND_MAP.get(raw_band)
        if band is None:
            band = _BAND_MAP.get(raw_band.replace("M", "").replace("m", ""))

    cq_zone = itu_zone = None
    try:
        cq_zone = int(_t("cqzone")) if _t("cqzone") else None
    except ValueError:
        pass
    try:
        itu_zone = int(_t("ituzone")) if _t("ituzone") else None
    except ValueError:
        pass

    return QSORecord(
        callsign=callsign,
        band=band,
        mode=_t("mode") or None,
        frequency_hz=freq_hz,
        my_callsign=_t("mycall") or None,
        country=_t("countryprefix") or None,
        continent=_t("continent") or None,
        cq_zone=cq_zone,
        itu_zone=itu_zone,
        dupe=_t("dupe") == "1",
        source="n1mm",
        raw={child.tag: child.text for child in root},
    )


class _N1MMProtocol(asyncio.DatagramProtocol):
    def __init__(self, callbacks: list[QSOCallback]) -> None:
        self._callbacks = callbacks

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            root = ET.fromstring(data.decode("utf-8", errors="replace"))
        except ET.ParseError:
            return

        if root.tag != "ContactInfo":
            return

        record = _parse_contact(root)
        if record is None:
            return

        log.info("N1MM+ logged: %s on %s %s from %s", record.callsign, record.band, record.mode, addr)
        for cb in self._callbacks:
            try:
                cb(record)
            except Exception:
                log.exception("N1MM+ QSO callback raised")

    def error_received(self, exc: Exception) -> None:
        log.warning("N1MM+ UDP error: %s", exc)


class N1MMListener:
    """
    Async UDP listener for N1MM+ contact broadcasts.

    N1MM+ must have "Broadcast contacts to network" enabled in its config
    (Tools → Configure Ports → Network → Enable).
    """

    name = "n1mm"

    def __init__(self, host: str = "0.0.0.0", port: int = 12060) -> None:
        self._host = host
        self._port = port
        self._callbacks: list[QSOCallback] = []
        self._transport: Optional[asyncio.DatagramTransport] = None

    @property
    def connected(self) -> bool:
        """True while the UDP listener socket is open."""
        return self._transport is not None

    def status(self) -> dict:
        return {
            "backend":   self.name,
            "connected": self.connected,
            "detail":    f"UDP {self._host}:{self._port}",
        }

    def on_qso(self, cb: QSOCallback) -> None:
        self._callbacks.append(cb)

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _N1MMProtocol(self._callbacks),
            local_addr=(self._host, self._port),
        )
        log.info("N1MM+ listener started on UDP %s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._transport:
            self._transport.close()
            self._transport = None
        log.info("N1MM+ listener stopped")

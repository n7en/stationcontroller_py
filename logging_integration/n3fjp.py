"""
N3FJP TCP poller.

N3FJP logging software (Amateur Contact Log, etc.) opens a TCP server on
port 1100.  We connect as a client, load the full log on startup, then
poll GetCurrentQSOData periodically to detect new contacts.

Commands are plain-text XML terminated with \\r\\n.
Responses are XML wrapped in <response>...</response>.
"""
from __future__ import annotations

import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Callable, Optional

from .log_state import QSORecord, band_for_freq_hz

log = logging.getLogger(__name__)

QSOCallback = Callable[[QSORecord], None]

# N3FJP sends band as "20M", "40M", etc.
_BAND_MAP: dict[str, str] = {
    "160M": "160m", "80M": "80m", "60M": "60m", "40M": "40m",
    "30M":  "30m",  "20M": "20m", "17M": "17m", "15M": "15m",
    "12M":  "12m",  "10M": "10m", "6M":  "6m",  "2M":  "2m",
    "222":  "1.25m","432": "70cm","1296": "23cm",
}


def _parse_timestamp(date_str: str, time_str: str) -> Optional[float]:
    """Parse N3FJP date/time strings (e.g. "2026/07/03" + "14:22") to epoch."""
    if not date_str:
        return None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(f"{date_str} {time_str}".strip(), fmt).timestamp()
        except ValueError:
            continue
    return None


def _parse_qso_element(el: ET.Element, source: str = "n3fjp") -> Optional[QSORecord]:
    def _t(*tags: str) -> str:
        for tag in tags:
            child = el.find(tag)
            if child is not None and child.text and child.text.strip():
                return child.text.strip()
        return ""

    callsign = _t("Call", "call", "fldCall")
    if not callsign:
        return None

    freq_hz: Optional[float] = None
    raw_freq = _t("Freq", "RxFreq", "freq", "fldFreq")
    if raw_freq:
        try:
            freq_hz = float(raw_freq) * 1000.0  # kHz → Hz
        except ValueError:
            pass

    raw_band = _t("Band", "band", "fldBand")
    band = (
        _BAND_MAP.get(raw_band.upper())
        or band_for_freq_hz(freq_hz)
        or (raw_band.lower() if raw_band else None)
    )

    ts = _parse_timestamp(
        _t("Date", "date", "fldDateStr"),
        _t("TimeOn", "timeon", "fldTimeOnStr"),
    )

    return QSORecord(
        callsign=callsign,
        band=band,
        mode=_t("Mode", "mode", "fldMode") or None,
        frequency_hz=freq_hz,
        timestamp=ts if ts is not None else time.time(),
        my_callsign=_t("MyCall", "mycall") or None,
        country=_t("Country", "country", "fldCountryWorked") or None,
        continent=None,
        dupe=False,
        source=source,
        raw={child.tag: child.text for child in el},
    )


class N3FJPPoller:
    """
    Async TCP client that polls N3FJP for logged contacts.

    On start: loads all existing QSOs via GetAllQSOData.
    While running: polls GetCurrentQSOData every poll_interval_s seconds
    and fires the callback when a new callsign is seen.
    """

    name = "n3fjp"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1100,
        poll_interval_s: float = 5.0,
        reconnect_delay_s: float = 15.0,
    ) -> None:
        self._host = host
        self._port = port
        self._poll_interval = poll_interval_s
        self._reconnect_delay = reconnect_delay_s
        self._callbacks: list[QSOCallback] = []
        self._task: Optional[asyncio.Task] = None
        self._seen_calls: set[str] = set()   # de-dupe on (call, band, mode)
        self._connected = False

    @property
    def connected(self) -> bool:
        """True while a TCP session with N3FJP is established."""
        return self._connected

    def status(self) -> dict:
        return {
            "backend":   self.name,
            "connected": self._connected,
            "detail":    f"TCP {self._host}:{self._port}",
        }

    def on_qso(self, cb: QSOCallback) -> None:
        self._callbacks.append(cb)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="n3fjp_poller")
        log.info("N3FJP poller started (%s:%d)", self._host, self._port)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("N3FJP poller stopped")

    async def _run(self) -> None:
        while True:
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("N3FJP connection lost (%s) - reconnecting in %.0fs", exc, self._reconnect_delay)
            await asyncio.sleep(self._reconnect_delay)

    async def _session(self) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port),
            timeout=10.0,
        )
        log.info("N3FJP connected at %s:%d", self._host, self._port)
        self._connected = True
        try:
            # Load full log on connect
            await self._load_all(reader, writer)
            # Poll for new contacts
            while True:
                await asyncio.sleep(self._poll_interval)
                await self._poll_current(reader, writer)
        finally:
            self._connected = False
            writer.close()

    async def _send_cmd(self, writer: asyncio.StreamWriter, cmd: str) -> None:
        writer.write(f"{cmd}\r\n".encode())
        await writer.drain()

    async def _read_response(self, reader: asyncio.StreamReader) -> Optional[ET.Element]:
        buf = b""
        try:
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=5.0)
                if not chunk:
                    break
                buf += chunk
                if b"</response>" in buf:
                    break
        except asyncio.TimeoutError:
            pass
        if not buf:
            return None
        try:
            return ET.fromstring(buf.decode("utf-8", errors="replace"))
        except ET.ParseError:
            return None

    async def _load_all(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await self._send_cmd(writer, "<cmd>GetAllQSOData</cmd>")
        root = await self._read_response(reader)
        if root is None:
            return
        count = 0
        for qso_el in root.iter():
            if qso_el.tag in ("QSOData", "CurrentQSOData"):
                record = _parse_qso_element(qso_el)
                if record:
                    key = (record.callsign, record.band, record.mode)
                    if key in self._seen_calls:
                        continue
                    self._seen_calls.add(key)
                    count += 1
                    # Feed existing QSOs to the manager so worked() queries
                    # cover the whole log, not just this session's contacts.
                    for cb in self._callbacks:
                        try:
                            cb(record)
                        except Exception:
                            log.exception("N3FJP QSO callback raised")
        log.info("N3FJP: loaded %d existing QSOs", count)

    async def _poll_current(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await self._send_cmd(writer, "<cmd>GetCurrentQSOData</cmd>")
        root = await self._read_response(reader)
        if root is None:
            return
        for qso_el in root.iter():
            if qso_el.tag in ("QSOData", "CurrentQSOData"):
                record = _parse_qso_element(qso_el)
                if record:
                    key = (record.callsign, record.band, record.mode)
                    if key not in self._seen_calls:
                        self._seen_calls.add(key)
                        log.info("N3FJP logged: %s on %s %s", record.callsign, record.band, record.mode)
                        for cb in self._callbacks:
                            try:
                                cb(record)
                            except Exception:
                                log.exception("N3FJP QSO callback raised")

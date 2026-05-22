"""
LogbookManager - holds all logging backends and a unified QSO store.

Usage::

    mgr = LogbookManager.from_config(cfg)
    await mgr.start()
    contacts = mgr.contacts()           # all QSOs seen so far
    in_log   = mgr.worked(callsign)     # True/False
    on_band  = mgr.worked_on_band(callsign, "20m")
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Optional

from .log_state import QSORecord
from .n1mm import N1MMListener
from .n3fjp import N3FJPPoller

log = logging.getLogger(__name__)

_MAX_RECORDS = 10_000   # cap in-memory log


class LogbookManager:

    def __init__(self) -> None:
        self._backends: list = []           # N1MMListener | N3FJPPoller
        self._records: deque[QSORecord] = deque(maxlen=_MAX_RECORDS)
        # Index for fast lookup: callsign -> set of (band, mode) tuples
        self._index: dict[str, set[tuple[Optional[str], Optional[str]]]] = {}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: dict) -> "LogbookManager":
        mgr = cls()

        n1mm_cfg = cfg.get("n1mm", {})
        if n1mm_cfg.get("enabled", False):
            listener = N1MMListener(
                host=n1mm_cfg.get("host", "0.0.0.0"),
                port=int(n1mm_cfg.get("port", 12060)),
            )
            listener.on_qso(mgr._on_qso)
            mgr._backends.append(listener)
            log.info("Logbook: N1MM+ listener enabled on UDP port %d", n1mm_cfg.get("port", 12060))

        n3fjp_cfg = cfg.get("n3fjp", {})
        if n3fjp_cfg.get("enabled", False):
            poller = N3FJPPoller(
                host=n3fjp_cfg.get("host", "localhost"),
                port=int(n3fjp_cfg.get("port", 1100)),
                poll_interval_s=float(n3fjp_cfg.get("poll_interval_s", 5.0)),
                reconnect_delay_s=float(n3fjp_cfg.get("reconnect_delay_s", 15.0)),
            )
            poller.on_qso(mgr._on_qso)
            mgr._backends.append(poller)
            log.info("Logbook: N3FJP poller enabled at %s:%d", n3fjp_cfg.get("host", "localhost"), n3fjp_cfg.get("port", 1100))

        return mgr

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        for backend in self._backends:
            try:
                await backend.start()
            except Exception:
                log.exception("Failed to start logbook backend %s", backend)

    async def stop(self) -> None:
        for backend in self._backends:
            try:
                await backend.stop()
            except Exception:
                log.exception("Failed to stop logbook backend %s", backend)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_qso(self, record: QSORecord) -> None:
        self._records.append(record)
        key = record.callsign.upper()
        if key not in self._index:
            self._index[key] = set()
        self._index[key].add((record.band, record.mode))

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def contacts(self, limit: int = 200) -> list[QSORecord]:
        """Return the most recent *limit* contacts (newest first)."""
        recs = list(self._records)
        return list(reversed(recs))[:limit]

    def worked(self, callsign: str) -> bool:
        """True if we have any logged QSO with this callsign."""
        return callsign.upper() in self._index

    def worked_on_band(self, callsign: str, band: str) -> bool:
        """True if we worked this callsign on the specified band."""
        entries = self._index.get(callsign.upper())
        if not entries:
            return False
        return any(b == band for b, _ in entries)

    def worked_on_band_mode(self, callsign: str, band: str, mode: str) -> bool:
        """True if we worked this callsign on this band + mode combination."""
        entries = self._index.get(callsign.upper())
        if not entries:
            return False
        return (band, mode) in entries

    @property
    def total_contacts(self) -> int:
        return len(self._records)

    @property
    def enabled(self) -> bool:
        return bool(self._backends)

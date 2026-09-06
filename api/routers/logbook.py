"""
GET  /api/logbook/contacts  - recent logged contacts
GET  /api/logbook/status    - backend connection status
GET  /api/logbook/worked    - check if a callsign is in the log
POST /api/logbook/qso       - push a single QSO (remote logging modules)
POST /api/logbook/qsos      - push a batch of QSOs (initial sync)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import AppState, get_state

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/logbook", tags=["logbook"])


@router.get("/status")
async def logbook_status(state: AppState = Depends(get_state)) -> dict:
    mgr = state.logbook_manager
    if mgr is None:
        return {"enabled": False, "backends": [], "total_contacts": 0}
    return {
        "enabled": mgr.enabled,
        "backends": mgr.backend_status(),
        "total_contacts": mgr.total_contacts,
    }


@router.get("/contacts")
async def list_contacts(
    limit: int = Query(default=100, ge=1, le=1000),
    state: AppState = Depends(get_state),
) -> dict:
    mgr = state.logbook_manager
    if mgr is None:
        return {"contacts": []}
    contacts = mgr.contacts(limit=limit)
    return {
        "contacts": [
            {
                "callsign":     c.callsign,
                "band":         c.band,
                "mode":         c.mode,
                "frequency_hz": c.frequency_hz,
                "timestamp":    c.timestamp,
                "my_callsign":  c.my_callsign,
                "country":      c.country,
                "continent":    c.continent,
                "cq_zone":      c.cq_zone,
                "dupe":         c.dupe,
                "source":       c.source,
            }
            for c in contacts
        ]
    }


class QSOIn(BaseModel):
    """A QSO pushed by a remote logging module."""
    callsign: str = Field(min_length=1, max_length=32)
    band: Optional[str] = None            # "20m" - derived from frequency if omitted
    mode: Optional[str] = None            # "USB", "CW", "FT8", ...
    frequency_hz: Optional[float] = Field(default=None, ge=0)
    timestamp: Optional[float] = None     # epoch seconds; defaults to now
    my_callsign: Optional[str] = None
    country: Optional[str] = None
    continent: Optional[str] = None
    cq_zone: Optional[int] = None
    itu_zone: Optional[int] = None
    dupe: bool = False
    source: str = "api"                   # identifies the remote module


def _to_record(q: QSOIn):
    from logging_integration.log_state import QSORecord
    import time as _time
    return QSORecord(
        callsign=q.callsign,
        band=q.band,
        mode=q.mode,
        frequency_hz=q.frequency_hz,
        timestamp=q.timestamp if q.timestamp is not None else _time.time(),
        my_callsign=q.my_callsign,
        country=q.country,
        continent=q.continent,
        cq_zone=q.cq_zone,
        itu_zone=q.itu_zone,
        dupe=q.dupe,
        source=q.source or "api",
    )


def _require_manager(state: AppState):
    mgr = state.logbook_manager
    if mgr is None:
        raise HTTPException(status_code=503, detail="Logbook manager not running")
    return mgr


@router.post("/qso")
async def add_qso(body: QSOIn, state: AppState = Depends(get_state)) -> dict:
    """Add a single QSO from a remote logging module."""
    mgr = _require_manager(state)
    rec = mgr.add_qso(_to_record(body))
    log.info("Logbook API: %s logged %s on %s %s",
             rec.source, rec.callsign, rec.band, rec.mode)
    return {
        "ok": True,
        "callsign": rec.callsign,
        "band": rec.band,
        "total_contacts": mgr.total_contacts,
    }


@router.post("/qsos")
async def add_qsos(body: list[QSOIn], state: AppState = Depends(get_state)) -> dict:
    """Add a batch of QSOs (e.g. a remote module syncing its log on startup)."""
    mgr = _require_manager(state)
    if len(body) > 10_000:
        raise HTTPException(status_code=422, detail="Batch too large (max 10000)")
    for q in body:
        mgr.add_qso(_to_record(q))
    log.info("Logbook API: batch of %d QSOs added (total %d)", len(body), mgr.total_contacts)
    return {"ok": True, "added": len(body), "total_contacts": mgr.total_contacts}


@router.get("/worked")
async def check_worked(
    call: str = Query(..., description="Callsign to check"),
    band: Optional[str] = Query(default=None, description="Optional band filter (e.g. '20m')"),
    state: AppState = Depends(get_state),
) -> dict:
    mgr = state.logbook_manager
    if mgr is None:
        return {"call": call, "worked": False, "worked_on_band": False}
    worked = mgr.worked(call)
    worked_band = mgr.worked_on_band(call, band) if band else False
    return {"call": call, "worked": worked, "worked_on_band": worked_band, "band": band}

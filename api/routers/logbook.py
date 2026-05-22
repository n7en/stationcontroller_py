"""
GET  /api/logbook/contacts  - recent logged contacts
GET  /api/logbook/status    - backend connection status
GET  /api/logbook/worked    - check if a callsign is in the log
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import AppState, get_state

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/logbook", tags=["logbook"])


@router.get("/status")
async def logbook_status(state: AppState = Depends(get_state)) -> dict:
    mgr = state.logbook_manager
    if mgr is None or not mgr.enabled:
        return {"enabled": False, "backends": [], "total_contacts": 0}
    return {
        "enabled": True,
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

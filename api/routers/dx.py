"""
GET  /api/dx/spots   - recent DX cluster spots
GET  /api/dx/solar   - solar and propagation conditions
POST /api/dx/tune    - tune radio to a spot's frequency and mode
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import AppState, get_state

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dx", tags=["dx"])


@router.get("/spots")
async def list_spots(
    limit: int = Query(default=100, ge=1, le=500),
    band: Optional[str] = Query(default=None, description="Filter by band, e.g. '20m'"),
    mode: Optional[str] = Query(default=None, description="Filter by mode, e.g. 'CW'"),
    continent: Optional[str] = Query(default=None, description="Filter by DX continent, e.g. 'AF'"),
    state: AppState = Depends(get_state),
) -> dict:
    mgr = state.dx_manager
    if mgr is None:
        return {"spots": [], "enabled": False}

    spots = mgr.spots(limit=500)   # fetch all then filter

    if band:
        spots = [s for s in spots if s.get("band") == band]
    if mode:
        m = mode.upper()
        spots = [s for s in spots if (s.get("mode") or "").upper() == m
                 or (s.get("mode_type") or "").upper() == m]
    if continent:
        spots = [s for s in spots if s.get("dx_continent") == continent]

    return {"spots": spots[:limit], "enabled": True, "total": len(spots)}


@router.get("/solar")
async def get_solar(state: AppState = Depends(get_state)) -> dict:
    mgr = state.dx_manager
    if mgr is None:
        return {"enabled": False, "solar": None}
    return {"enabled": True, "solar": mgr.solar()}


class TuneRequest(BaseModel):
    freq: float                         # Hz
    mode: Optional[str] = None          # e.g. "USB", "CW"


@router.post("/tune")
async def tune_to_spot(body: TuneRequest, state: AppState = Depends(get_state)) -> dict:
    """Tune the radio to the given frequency (and optionally mode) from a DX spot."""
    iface = state.radio_interface
    if iface is None:
        raise HTTPException(status_code=503, detail="No radio connected")
    if not iface.state.connected:
        raise HTTPException(status_code=503, detail="Radio is not connected")

    await iface.set_frequency(body.freq)
    if body.mode:
        try:
            await iface.set_mode(body.mode)
        except Exception as exc:
            log.warning("tune: set_mode(%s) failed: %s", body.mode, exc)

    log.info("Tuned to %.0f Hz %s (from DX spot)", body.freq, body.mode or "")
    return {"ok": True, "freq": body.freq, "mode": body.mode}

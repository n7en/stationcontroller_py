"""GET /api/history/sensors and /api/history/devices - telemetry query endpoints."""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import AppState, get_state

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/sensors/names")
async def get_sensor_names(state: AppState = Depends(get_state)) -> list[str]:
    if state.telemetry is None:
        return []
    return await state.telemetry.get_sensor_names()


@router.get("/sensors")
async def get_sensor_history(
    name:  str,
    since: float,
    until: Optional[float] = None,
    limit: int = Query(default=3000, ge=1, le=10000),
    state: AppState = Depends(get_state),
) -> list[dict]:
    if state.telemetry is None:
        return []
    now = time.time()
    if since > now:
        raise HTTPException(status_code=400, detail="'since' must be a past timestamp")
    readings = await state.telemetry.get_sensor_history(name, since, until or now, limit)
    return [{"ts": r.ts, "value": r.value, "unit": r.unit} for r in readings]


@router.get("/devices")
async def get_device_events(
    device_key: Optional[str] = None,
    since: Optional[float] = None,
    limit: int = Query(default=500, ge=1, le=5000),
    state: AppState = Depends(get_state),
) -> list[dict]:
    if state.telemetry is None:
        return []
    since = since or (time.time() - 86400)
    events = await state.telemetry.get_device_events(device_key, since, limit)
    return [
        {
            "ts":          e.ts,
            "event_type":  e.event_type,
            "device_key":  e.device_key,
            "device_name": e.device_name,
            "old_value":   e.old_value,
            "new_value":   e.new_value,
        }
        for e in events
    ]

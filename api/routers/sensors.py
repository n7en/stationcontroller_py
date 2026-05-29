"""GET /api/sensors - current sensor snapshot."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import AppState, get_state

router = APIRouter(prefix="/api/sensors", tags=["sensors"])


@router.get("")
async def get_sensors(state: AppState = Depends(get_state)) -> dict:
    if state.sensor_registry is None:
        return {}
    return {
        name: {
            "value": m.value,
            "unit": m.unit,
            "source": m.source,
            "ts": m.timestamp,
            "age_s": m.age_s(),
        }
        for name, m in state.sensor_registry.snapshot().items()
    }


@router.get("/{name}")
async def get_sensor(name: str, state: AppState = Depends(get_state)) -> dict:
    if state.sensor_registry is None:
        return {}
    m = state.sensor_registry.get(name)
    if m is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Sensor {name!r} not found")
    return {
        "name": m.name,
        "value": m.value,
        "unit": m.unit,
        "source": m.source,
        "ts": m.timestamp,
        "age_s": m.age_s(),
    }

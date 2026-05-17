"""
GET  /api/relays          - list known relay states from sensor registry
POST /api/relays/{key}    - send relay command over DCN
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import AppState, get_state

router = APIRouter(prefix="/api/relays", tags=["relays"])


@router.get("")
async def get_relays(state: AppState = Depends(get_state)) -> dict:
    """Return all sensors whose names start with 'relay_' or contain '_relay_'."""
    if state.sensor_registry is None:
        return {}
    return {
        name: {"value": int(m.value), "source": m.source, "ts": m.timestamp}
        for name, m in state.sensor_registry.snapshot().items()
        if "relay" in name.lower()
    }


class RelayCommand(BaseModel):
    state: int          # 0 or 1
    device_addr: str    # DCN address e.g. "01"
    relay_num: int      # 1-indexed relay on that device


@router.post("/{key}")
async def set_relay(
    key: str,
    cmd: RelayCommand,
    state: AppState = Depends(get_state),
) -> dict:
    if cmd.state not in (0, 1):
        raise HTTPException(status_code=422, detail="state must be 0 or 1")
    network = state.network_for_addr(cmd.device_addr)
    if network is None:
        raise HTTPException(status_code=503, detail="No DCN network connected")
    await network.send(cmd.device_addr, f"RY{cmd.relay_num},{cmd.state}")
    return {"ok": True, "key": key, "state": cmd.state}

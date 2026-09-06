"""GET/PUT /api/streamdeck — Stream Deck config and status."""
from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException

from ..deps import AppState, get_state

router = APIRouter(prefix="/api/streamdeck", tags=["streamdeck"])

_CFG_PATH = Path(__file__).parents[2] / "config" / "streamdeck_config.yaml"
_EXAMPLE  = Path(__file__).parents[2] / "config" / "streamdeck_config.yaml.example"


def _read_cfg() -> dict:
    if _CFG_PATH.exists():
        with open(_CFG_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    if _EXAMPLE.exists():
        with open(_EXAMPLE, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {"streamdeck": {"enabled": False, "brightness": 70, "buttons": []}}


@router.get("/status")
async def get_status(state: AppState = Depends(get_state)) -> dict:
    """Return device connection status."""
    mgr = getattr(state, "streamdeck_manager", None)
    if mgr is None:
        return {"connected": False, "available": False}
    info = mgr.device_info
    info["available"] = True
    return info


@router.get("/config")
async def get_config() -> dict:
    return _read_cfg()


@router.put("/config")
async def put_config(body: dict, state: AppState = Depends(get_state)) -> dict:
    """Save config and hot-reload the running manager."""
    _CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CFG_PATH, "w", encoding="utf-8") as fh:
        yaml.dump(body, fh, default_flow_style=False, allow_unicode=True)

    mgr = getattr(state, "streamdeck_manager", None)
    if mgr is not None:
        sd_cfg = body.get("streamdeck", {})
        mgr.reload_config(sd_cfg)

    return {"ok": True}

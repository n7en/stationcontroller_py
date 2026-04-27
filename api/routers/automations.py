"""
GET  /api/automations         — list all automations + enabled state
GET  /api/automations/config  — raw YAML of the automation config file
PUT  /api/automations/config  — save and reload automation config
POST /api/automations/{name}/trigger — manually fire an automation
POST /api/automations/{name}/enable  — enable / disable
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import AppState, get_state

AUTOMATION_CONFIG = Path("config/automation_config.yaml")
log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/automations", tags=["automations"])


@router.get("")
async def list_automations(state: AppState = Depends(get_state)) -> list[dict]:
    if state.engine is None:
        return []
    return [
        {
            "name": a.name,
            "tier": a.tier.value,
            "priority": a.priority,
            "enabled": a.enabled,
            "mode": a.mode.value,
            "description": getattr(a, "description", ""),
        }
        for a in state.engine.automations()
    ]


@router.get("/config")
async def get_automation_config() -> dict:
    if not AUTOMATION_CONFIG.exists():
        return {"yaml": ""}
    return {"yaml": AUTOMATION_CONFIG.read_text(encoding="utf-8")}


class ConfigSave(BaseModel):
    yaml: str


@router.put("/config")
async def save_automation_config(
    body: ConfigSave,
    state: AppState = Depends(get_state),
) -> dict:
    try:
        parsed = yaml.safe_load(body.yaml)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=422, detail=f"YAML parse error: {e}")
    if parsed is not None and not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="Automation config must be a YAML mapping")
    AUTOMATION_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    AUTOMATION_CONFIG.write_text(body.yaml, encoding="utf-8", newline="\n")

    # Reload into live engine if available
    if state.engine is not None and parsed:
        try:
            from automation.config import load_automations
            load_automations(state.engine, parsed, state.band_registry)
        except Exception as e:
            log.exception("Failed to reload automations")
            raise HTTPException(status_code=422, detail=f"Reload error: {e}")

    return {"ok": True}


class TriggerRequest(BaseModel):
    bypass_conditions: bool = False


@router.post("/{name}/trigger")
async def manual_trigger(
    name: str,
    req: TriggerRequest,
    state: AppState = Depends(get_state),
) -> dict:
    if state.engine is None:
        raise HTTPException(status_code=503, detail="Automation engine not running")
    from automation.context import AutomationContext
    from sensors.sensor_registry import SensorRegistry
    from radio.radio_state import RadioState
    from automation.bands import BandRegistry

    ctx = AutomationContext(
        radio_state=state.radio_state or RadioState(name=""),
        registry=state.sensor_registry or SensorRegistry(),
        band_registry=state.band_registry or BandRegistry.amateur(),
        radio_interface=state.radio_interface,
        control_network=state.control_network,
    )
    try:
        fired = await state.engine.trigger(
            name, ctx, bypass_conditions=req.bypass_conditions
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Automation {name!r} not found")
    return {"ok": True, "fired": fired}


class EnableRequest(BaseModel):
    enabled: bool


@router.post("/{name}/enable")
async def set_enabled(
    name: str,
    req: EnableRequest,
    state: AppState = Depends(get_state),
) -> dict:
    if state.engine is None:
        raise HTTPException(status_code=503, detail="Automation engine not running")
    a = state.engine.get_automation(name)
    if a is None:
        raise HTTPException(status_code=404, detail=f"Automation {name!r} not found")
    a.enabled = req.enabled
    return {"ok": True, "name": name, "enabled": req.enabled}

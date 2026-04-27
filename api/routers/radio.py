"""Radio state and configuration endpoints."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import AppState, get_state

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/radio", tags=["radio"])

RADIO_CFG = Path("config/radio_config.yaml")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RIGCTLD_KEYS      = {"name", "backend", "host", "port", "poll_interval_s", "reconnect_delay_s"}
_HAMLIB_KEYS       = {"name", "backend", "model_id", "port", "baud_rate",
                      "data_bits", "stop_bits", "parity", "poll_interval_s", "reconnect_delay_s"}
_COMMON_DEFAULTS   = {"poll_interval_s": 0.5, "reconnect_delay_s": 5.0}
_RIGCTLD_DEFAULTS  = {"host": "localhost", "port": 4532}
_HAMLIB_DEFAULTS   = {"model_id": 1, "baud_rate": 9600, "data_bits": 8, "stop_bits": 1, "parity": "N"}


def _clean_radio_entry(entry: dict) -> dict:
    """Strip keys irrelevant to the chosen backend and fill in missing defaults."""
    backend = entry.get("backend", "rigctld")
    allowed = _RIGCTLD_KEYS if backend == "rigctld" else _HAMLIB_KEYS
    cleaned = {k: v for k, v in entry.items() if k in allowed}
    defaults = {**_COMMON_DEFAULTS, **(
        _RIGCTLD_DEFAULTS if backend == "rigctld" else _HAMLIB_DEFAULTS
    )}
    for k, v in defaults.items():
        cleaned.setdefault(k, v)
    return cleaned


async def _rebuild_radio(state: AppState) -> bool:
    """Stop the current radio interface and start a fresh one from the saved config."""
    from radio.radio_manager import RadioManager

    if state.radio_interface is not None:
        try:
            await state.radio_interface.stop()
            await state.radio_interface.disconnect()
        except Exception:
            pass

    try:
        manager = RadioManager.from_config(str(RADIO_CFG))
        if not manager.names():
            return False

        iface = manager[manager.names()[0]]

        if state.ws_hub is not None:
            ws_hub = state.ws_hub

            async def _on_change(rs, _diff):
                await ws_hub.broadcast_radio(rs)

            iface.on_state_change(_on_change)

        state.radio_interface = iface
        state.radio_state     = iface.state

        await iface.connect()
        await iface.start()
        return True

    except Exception:
        log.exception("Radio rebuild failed")
        return False


@router.get("")
async def get_radio(state: AppState = Depends(get_state)) -> dict:
    rs = state.radio_state
    if rs is None:
        return {"connected": False}
    return {
        "connected": rs.connected,
        "frequency_hz": rs.frequency_hz,
        "mode": getattr(rs, "mode", None),
        "ptt": rs.ptt,
    }


class TuneRequest(BaseModel):
    frequency_hz: float | None = None
    mode: str | None = None
    bandwidth_hz: float = 0


@router.post("/tune")
async def tune_radio(req: TuneRequest, state: AppState = Depends(get_state)) -> dict:
    if state.radio_interface is None:
        raise HTTPException(status_code=503, detail="Radio interface not connected")
    if req.frequency_hz is not None:
        await state.radio_interface.set_frequency(req.frequency_hz)
    if req.mode is not None:
        await state.radio_interface.set_mode(req.mode, req.bandwidth_hz)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Config read / write / reconnect
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_radio_config() -> dict:
    if not RADIO_CFG.exists():
        return {"radios": []}
    try:
        with open(RADIO_CFG, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return {"radios": data.get("radios", [])}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class RadioConfigBody(BaseModel):
    radios: list[dict[str, Any]]


@router.put("/config")
async def save_radio_config(
    body: RadioConfigBody,
    state: AppState = Depends(get_state),
) -> dict:
    if not body.radios:
        raise HTTPException(status_code=422, detail="'radios' must be a non-empty list")

    cleaned_radios = [_clean_radio_entry(r) for r in body.radios]
    RADIO_CFG.parent.mkdir(parents=True, exist_ok=True)
    with open(RADIO_CFG, "w", encoding="utf-8", newline="\n") as fh:
        yaml.dump({"radios": cleaned_radios}, fh, default_flow_style=False, allow_unicode=True)

    reconnected = await _rebuild_radio(state)
    return {"ok": True, "reconnected": reconnected}


@router.post("/reconnect")
async def reconnect_radio(state: AppState = Depends(get_state)) -> dict:
    if state.radio_interface is None:
        raise HTTPException(status_code=503, detail="No radio interface configured")
    try:
        await state.radio_interface.stop()
        await state.radio_interface.disconnect()
    except Exception:
        pass
    try:
        await state.radio_interface.connect()
        await state.radio_interface.start()
        return {"ok": True, "connected": state.radio_interface.state.connected}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

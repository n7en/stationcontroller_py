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

_RIGCTLD_KEYS  = {"name", "backend", "enabled", "host", "port", "timeout_s",
                   "poll_interval_s", "reconnect_delay_s",
                   "init_raw_cmds", "init_cmds"}
_MANAGED_KEYS  = {"name", "backend", "enabled", "model_id", "serial_port", "serial_baud",
                   "host", "port", "timeout_s", "startup_timeout_s",
                   "serial_timeout_ms", "poll_interval_s", "reconnect_delay_s",
                   "init_raw_cmds", "init_cmds"}
_HAMLIB_KEYS   = {"name", "backend", "enabled", "model_id", "port", "baud_rate",
                   "data_bits", "stop_bits", "parity", "poll_interval_s", "reconnect_delay_s"}
_K4_KEYS       = {"name", "backend", "enabled", "transport",
                   "port", "baud_rate",
                   "host", "tcp_port", "password",
                   "timeout_s", "max_power_w", "power_range",
                   "poll_interval_s", "reconnect_delay_s"}
_ICOM_LAN_KEYS = {"name", "backend", "enabled", "host", "port",
                   "username", "password", "model", "timeout_s",
                   "poll_interval_s", "reconnect_delay_s"}

_COMMON_DEFAULTS    = {"enabled": True, "poll_interval_s": 1.0, "reconnect_delay_s": 5.0}
_RIGCTLD_DEFAULTS   = {"host": "localhost", "port": 4532, "timeout_s": 15.0}
_MANAGED_DEFAULTS   = {"host": "127.0.0.1", "port": 0, "serial_baud": 9600,
                        "timeout_s": 15.0, "startup_timeout_s": 10.0,
                        "serial_timeout_ms": 500}
_HAMLIB_DEFAULTS    = {"model_id": 1, "baud_rate": 9600, "data_bits": 8,
                        "stop_bits": 1, "parity": "N"}
_K4_DEFAULTS        = {"baud_rate": 38400, "timeout_s": 5.0,
                        "max_power_w": 100, "power_range": "H"}
_ICOM_LAN_DEFAULTS  = {"port": 50001, "username": "", "password": "",
                        "model": "", "timeout_s": 15.0}


def _clean_radio_entry(entry: dict) -> dict:
    """Strip keys irrelevant to the chosen backend and fill in missing defaults."""
    backend = entry.get("backend", "rigctld")
    if backend == "managed_rigctld":
        allowed, defaults = _MANAGED_KEYS,  {**_COMMON_DEFAULTS, **_MANAGED_DEFAULTS}
    elif backend == "hamlib_direct":
        allowed, defaults = _HAMLIB_KEYS,   {**_COMMON_DEFAULTS, **_HAMLIB_DEFAULTS}
    elif backend == "elecraft_k4":
        allowed, defaults = _K4_KEYS,       {**_COMMON_DEFAULTS, **_K4_DEFAULTS}
    elif backend == "icom_lan":
        allowed, defaults = _ICOM_LAN_KEYS, {**_COMMON_DEFAULTS, **_ICOM_LAN_DEFAULTS}
    else:
        allowed, defaults = _RIGCTLD_KEYS,  {**_COMMON_DEFAULTS, **_RIGCTLD_DEFAULTS}
    cleaned = {k: v for k, v in entry.items() if k in allowed}
    for k, v in defaults.items():
        cleaned.setdefault(k, v)
    return cleaned


async def _rebuild_radio(state: AppState) -> bool:
    """Stop all current radio interfaces and start fresh ones from the saved config."""
    from radio.radio_manager import RadioManager

    # Stop everything managed by the old manager
    if state.radio_manager is not None:
        try:
            await state.radio_manager.stop_all()
        except Exception:
            pass
    elif state.radio_interface is not None:
        try:
            await state.radio_interface.stop()
            await state.radio_interface.disconnect()
        except Exception:
            pass

    # Give the serial port (and any external rigctld) time to flush before
    # opening a new connection.  Without this, mid-transaction bytes left in
    # the OS serial buffer cause every subsequent read to return stale data.
    await asyncio.sleep(2.0)

    try:
        manager = RadioManager.from_config(str(RADIO_CFG))
        if not manager.names():
            return False

        ws_hub = state.ws_hub

        for iface in manager:
            if ws_hub is not None:
                async def _on_change(rs, _diff, _hub=ws_hub, _name=iface.name):
                    await _hub.broadcast_radio(_name, rs)
                iface.on_state_change(_on_change)
            try:
                await iface.connect()
            except Exception:
                log.warning("Radio '%s' connect failed - poll loop will retry", iface.name)
            await iface.start()

        primary = manager[manager.names()[0]]
        state.radio_manager   = manager
        state.radio_interface = primary
        state.radio_state     = primary.state
        return True

    except Exception:
        log.exception("Radio rebuild failed")
        return False


@router.get("/serial-ports")
async def list_serial_ports() -> dict:
    """Return serial ports currently visible to the OS."""
    try:
        from serial.tools import list_ports
        ports = [
            {"port": p.device, "description": p.description or p.device}
            for p in sorted(list_ports.comports(), key=lambda p: p.device)
        ]
    except ImportError:
        ports = []
    return {"ports": ports}


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

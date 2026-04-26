"""WebSocket endpoint — /ws"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..deps import AppState, get_state
from . import update as _update_mod

log = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, state: AppState = Depends(get_state)):
    hub = state.ws_hub
    await hub.connect(ws)
    try:
        await hub.send_snapshot(
            ws, state.sensor_registry, state.radio_state, state.label_registry,
            update_result=_update_mod._cached_result,
        )
        async for raw in ws.iter_text():
            await _handle_client_message(raw, state)
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)


async def _handle_client_message(raw: str, state: AppState) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("WS: invalid JSON from client: %r", raw[:200])
        return

    kind = msg.get("type")

    if kind == "relay_cmd":
        if state.control_network is None:
            log.warning("WS relay_cmd: no control_network configured")
            return
        key: str = msg.get("key", "")
        relay_num: int = int(msg.get("relay_num", 0))
        relay_state: int = int(msg.get("state", 0))
        device_addr = key.split("_")[1] if "_" in key else msg.get("device_addr", "01")
        await state.control_network.send(device_addr, f"RY{relay_num},{relay_state}")
        await state.ws_hub.broadcast_relay(key, relay_state)

    elif kind == "coax_select":
        if state.control_network is None:
            log.warning("WS coax_select: no control_network configured")
            return
        device_addr: str = msg.get("device_addr", "02")
        port: int = int(msg.get("port", 0))
        await state.control_network.send(device_addr, f"CX,{port}")

    elif kind == "radio_tune":
        if state.radio_interface is None:
            log.warning("WS radio_tune: no radio_interface configured")
            return
        if freq := msg.get("frequency_hz"):
            await state.radio_interface.set_frequency(float(freq))
        if mode := msg.get("mode"):
            bw = float(msg.get("bandwidth_hz", 0))
            await state.radio_interface.set_mode(mode, bw)

    else:
        log.debug("WS: unknown message type %r", kind)

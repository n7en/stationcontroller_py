"""WebSocket endpoint - /ws"""
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
            ws, state.sensor_registry, state.radio_manager, state.label_registry,
            update_result=_update_mod._cached_result,
        )
        if state.log_buffer is not None:
            logs = state.log_buffer.recent_general()
            if logs:
                await hub.send(ws, {"type": "log_history", "entries": logs})
            dcns = state.log_buffer.recent_dcn()
            if dcns:
                await hub.send(ws, {"type": "dcn_history", "entries": dcns})
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
        key: str = msg.get("key", "")
        relay_num: int = int(msg.get("relay_num", 0))   # 0-based from client
        relay_state: int = int(msg.get("state", 0))
        device_addr = msg.get("device_addr", "01")
        bus: str = msg.get("bus", "")
        network = state.network_for_addr(device_addr, bus=bus or None)
        if network is None:
            log.warning("WS relay_cmd: no network for device addr %s", device_addr)
            return
        await network.send(device_addr, f"RY{relay_num},{relay_state}")

    elif kind == "coax_select":
        device_addr: str = msg.get("device_addr", "02")
        port: int = int(msg.get("port", 0))   # 0-indexed port number
        bus: str = msg.get("bus", "")
        # Optimistic update: find the device on the correct bus so we don't
        # highlight the wrong coax switch when multiple buses share the same address.
        for dev in state.devices.values():
            if getattr(dev, "address", None) == device_addr and hasattr(dev, "optimistic_select"):
                if not bus or getattr(dev, "bus", None) == bus:
                    dev.optimistic_select(port)
                    break
        network = state.network_for_addr(device_addr, bus=bus or None)
        if network is None:
            log.warning("WS coax_select: no network for device addr %s", device_addr)
            return
        await network.send(device_addr, f"CX,{port}")

    elif kind == "pos_select":
        device_addr: str = msg.get("device_addr", "06")
        position: int = int(msg.get("position", 0))   # 0-based from client
        bus: str = msg.get("bus", "")
        for dev in state.devices.values():
            if getattr(dev, "address", None) == device_addr and hasattr(dev, "optimistic_select_position"):
                if not bus or getattr(dev, "bus", None) == bus:
                    dev.optimistic_select_position(position)   # 0-based
                    break
        network = state.network_for_addr(device_addr, bus=bus or None)
        if network is None:
            log.warning("WS pos_select: no network for device addr %s", device_addr)
            return
        await network.send(device_addr, f"POS,{position}")

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

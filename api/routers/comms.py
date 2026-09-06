"""
GET  /api/comms/buses    - list live DCN bus names
POST /api/comms/discover - broadcast PING on a bus and return responding devices
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import AppState, get_state

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comms", tags=["comms"])

# Maps UPDATE packet type token → device config type string
_TYPE_MAP: dict[str, str] = {
    "GPIO1": "gpio",
    "ARC1":  "antenna_relay",
    "CX1":   "coax_switch",
    "CX2":   "vhf_coax_relay",
    "WM1":   "watt_meter",
}


@router.get("/buses")
async def list_buses(state: AppState = Depends(get_state)) -> dict:
    """Return names of all live DCN buses."""
    return {"buses": sorted(state.networks.keys())}


@router.post("/discover")
async def discover_devices(
    bus: str = Query(default="control", description="Bus name to scan"),
    timeout: float = Query(default=3.0, ge=0.5, le=15.0, description="Scan duration in seconds"),
    state: AppState = Depends(get_state),
) -> dict:
    """
    Broadcast a PING on the named bus and collect UPDATE responses.

    Returns a list of discovered devices with their address and inferred type.
    Devices that respond with an unknown UPDATE type are included with
    device_type=null so the UI can still show them.
    """
    network = state.networks.get(bus) if state.networks else None
    if network is None:
        # Fall back to control network if the named bus isn't found
        network = state.control_network
    if network is None:
        raise HTTPException(status_code=503, detail="No DCN networks are connected")

    found: dict[str, dict] = {}   # addr -> device info
    active = True

    async def capture(pkt, _transport_name: str) -> None:
        if not active:
            return
        if pkt.command != "UPDATE" or pkt.broadcast:
            return
        addr = pkt.from_addr
        if not addr or addr in found:
            return
        args = pkt.args
        raw_type = args[0] if args else ""
        device_type = _TYPE_MAP.get(raw_type)
        found[addr] = {
            "address":     addr,
            "device_type": device_type,
            "raw_type":    raw_type,
        }
        log.debug("Discover: found %s (%s) on bus %s", addr, raw_type, bus)

    network.on_packet(capture)
    try:
        await network.broadcast("PING")
        await asyncio.sleep(timeout)
    finally:
        active = False
        try:
            network._handlers.remove(capture)
        except ValueError:
            pass

    devices = sorted(found.values(), key=lambda d: d["address"])
    log.info("DCN discover on bus '%s': %d device(s) found", bus, len(devices))
    return {"bus": bus, "devices": devices}

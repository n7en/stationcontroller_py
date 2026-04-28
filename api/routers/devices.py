"""GET /api/devices -- device topology with sensor schemas for the UI."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..deps import AppState, get_state

router = APIRouter(prefix="/api", tags=["devices"])


def _device_schema(dev: Any) -> dict:
    from devices.gpio_module    import GPIOModule
    from devices.coax_switch    import CoaxSwitch
    from devices.watt_meter     import WattMeter
    from devices.vhf_coax_relay import VHFCoaxRelay
    from devices.antenna_relay  import AntennaRelayModule

    name = dev.name
    pfx  = name
    addr = getattr(dev, "address", "??")

    if isinstance(dev, GPIOModule):
        return {
            "name": name, "type": "gpio", "address": addr,
            "sensors": (
                [{"key": f"{pfx}_relay_{i}",     "role": "relay",         "relay_num":     i} for i in range(1, 9)] +
                [{"key": f"{pfx}_input_{i}",     "role": "digital_input", "input_num":     i} for i in range(1, 5)] +
                [{"key": f"{pfx}_voltmeter_{i}", "role": "voltmeter",     "voltmeter_num": i} for i in range(1, 5)] +
                [{"key": f"{pfx}_temp_1_f",      "role": "temperature",   "probe_num":     1},
                 {"key": f"{pfx}_temp_2_f",      "role": "temperature",   "probe_num":     2}]
            ),
        }

    if isinstance(dev, CoaxSwitch):
        return {
            "name": name, "type": "coax_switch", "address": addr, "n_ports": 4,
            "sensors": (
                [{"key": f"{pfx}_active_port", "role": "active_port"}] +
                [{"key": f"{pfx}_port_{i}",    "role": "port", "port": i} for i in range(1, 5)]
            ),
        }

    if isinstance(dev, WattMeter):
        return {
            "name": name, "type": "watt_meter", "address": addr,
            "sensors": [
                {"key": f"{pfx}_forward_power_w",        "role": "forward_power"},
                {"key": f"{pfx}_reflected_power_w",      "role": "reflected_power"},
                {"key": f"{pfx}_swr",                    "role": "swr"},
                {"key": f"{pfx}_reflection_coefficient", "role": "reflection_coefficient"},
                {"key": f"{pfx}_return_loss_db",         "role": "return_loss"},
                {"key": f"{pfx}_mismatch_loss_db",       "role": "mismatch_loss"},
            ],
        }

    if isinstance(dev, VHFCoaxRelay):
        return {
            "name": name, "type": "vhf_relay", "address": addr,
            "sensors": [
                {"key": f"{pfx}_relay", "role": "relay",   "relay_num": 1},
                {"key": f"{pfx}_nc",    "role": "nc_port"},
                {"key": f"{pfx}_no",    "role": "no_port"},
            ],
        }

    if isinstance(dev, AntennaRelayModule):
        n = dev.n_relays
        return {
            "name":         name,
            "type":         "antenna_relay",
            "address":      addr,
            "persona":      dev.persona,
            "persona_label": dev.persona_label,
            "n_relays":     n,
            "mode":         dev.mode,
            "sensors": [
                {"key": f"{pfx}_relay_{i}", "role": "relay", "relay_num": i}
                for i in range(1, n + 1)
            ],
        }

    return {"name": name, "type": "unknown", "address": addr, "sensors": []}


@router.get("/devices")
async def get_devices(state: AppState = Depends(get_state)) -> dict:
    if not state.devices:
        return {"devices": []}
    return {"devices": [_device_schema(dev) for dev in state.devices.values()]}

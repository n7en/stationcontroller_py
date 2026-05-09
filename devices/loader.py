"""
Load device instances from comms_config.yaml.

Reads the 'devices:' section, instantiates each device module, and attaches
it to the DCN bus named in the config.  Returns a dict of device instances
(keyed by device name) and a mapping from DCN address to bus name used by
the API layer to route outbound commands to the right network.

Usage::

    networks = DCNNetwork.buses_from_config(COMMS_CFG)
    devices, addr_bus = load_devices(COMMS_CFG, sensor_registry, networks)

    # Route a command to whichever bus owns address "02":
    bus = addr_bus.get("02", "control")
    await networks[bus].send("02", "CX,3")
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from comms.config import load_config
from comms.dcn_network import DCNNetwork
from sensors.sensor_registry import SensorRegistry

log = logging.getLogger(__name__)


def _device_registry() -> dict[str, type]:
    from devices.gpio_module    import GPIOModule
    from devices.coax_switch    import CoaxSwitch
    from devices.watt_meter     import WattMeter
    from devices.vhf_coax_relay import VHFCoaxRelay
    from devices.antenna_relay  import AntennaRelayModule

    return {
        "gpio":           GPIOModule,
        "coax_switch":    CoaxSwitch,
        "watt_meter":     WattMeter,
        "vhf_relay":      VHFCoaxRelay,
        "antenna_relay":  AntennaRelayModule,
    }


def load_devices(
    config_path: str | Path,
    registry: SensorRegistry,
    networks: dict[str, DCNNetwork],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Instantiate and attach all devices declared in *config_path*.

    Returns:
        devices     — dict[name → device instance]
        addr_bus    — dict[address → bus_name] for API routing
                      When the same address appears on multiple buses (e.g.
                      two streaming watt meters) the first entry wins for
                      backward-compat routing; explicit bus selection
                      overrides this.
    """
    cfg = load_config(config_path)
    dev_registry = _device_registry()

    devices: dict[str, Any] = {}
    addr_bus: dict[str, str] = {}

    for dev_cfg in cfg.get("devices", []):
        device_type = dev_cfg.get("type", "")
        device_cls = dev_registry.get(device_type)
        if device_cls is None:
            log.warning("Unknown device type '%s' - skipping", device_type)
            continue

        name    = dev_cfg.get("name") or device_type
        address = str(dev_cfg.get("address", ""))
        bus_name = dev_cfg.get("bus", "control")

        if name in devices:
            log.warning("Duplicate device name '%s' - skipping second definition", name)
            continue

        try:
            kwargs: dict = {}
            if device_type == "antenna_relay":
                persona = dev_cfg.get("persona")
                if persona:
                    kwargs["persona"] = persona
            device = device_cls(name=name, address=address, registry=registry, **kwargs)
        except Exception:
            log.exception("Failed to create device '%s' (type=%s)", name, device_type)
            continue

        network = networks.get(bus_name)
        if network is not None:
            device.attach(network)
            log.debug("Device '%s' (%s addr=%s) attached to bus '%s'",
                      name, device_type, address, bus_name)
        else:
            log.warning(
                "Device '%s': bus '%s' not found in loaded networks — "
                "device will not receive packets",
                name, bus_name,
            )

        devices[name] = device
        if address and address not in addr_bus:
            addr_bus[address] = bus_name

    return devices, addr_bus

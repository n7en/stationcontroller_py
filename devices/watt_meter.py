"""
DCN Watt Meter (#335) device module.

Subscribes to UPDATE,WM1 packets from the DCN network, computes the full
set of RF power metrics from the raw forward/reflected power readings, and
publishes everything to a SensorRegistry.

RF metric ownership lives here - the automation engine and any other consumer
reads named values from the registry and has no knowledge of the formulas.

DCN packet format (UPDATE,WM1):
    args[0]  WM1              module type identifier
    args[1]  <port>           antenna/port selection (string)
    args[2]  <forward_w>      forward power in watts (float)
    args[3]  <reflected_w>    reflected power in watts (float)
    args[4+] reserved / firmware-dependent
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

from comms.dcn_network import DCNNetwork
from comms.dcn_packet import DCNPacket
from sensors.sensor_registry import SensorRegistry


# ---------------------------------------------------------------------------
# RF metric calculations - public so other modules can reuse them
# ---------------------------------------------------------------------------

def compute_rf_metrics(forward_w: float, reflected_w: float) -> dict:
    """
    Compute derived RF power metrics from forward and reflected power.

    Returns a dict with keys:
        swr                  - voltage standing wave ratio (1.0 = perfect match)
        reflection_coefficient - magnitude of Γ (0.0–1.0)
        return_loss_db       - return loss in dB (positive = loss)
        mismatch_loss_db     - power lost to mismatch in dB

    All values are None when forward_w <= 0 (transmitter off / no signal).
    reflected_w is clamped to [0, forward_w] before computation to guard
    against meter offsets that produce physically impossible readings.
    """
    if forward_w <= 0.0:
        return {
            "swr": None,
            "reflection_coefficient": None,
            "return_loss_db": None,
            "mismatch_loss_db": None,
        }

    # Clamp ratio to [0, 1) - reflected can never exceed forward physically
    ratio = min(max(reflected_w / forward_w, 0.0), 0.9999)
    gamma = math.sqrt(ratio)

    swr = (1.0 + gamma) / (1.0 - gamma)
    return_loss_db = -10.0 * math.log10(ratio) if ratio > 0.0 else float("inf")
    mismatch_loss_db = -10.0 * math.log10(1.0 - ratio)

    return {
        "swr": round(swr, 4),
        "reflection_coefficient": round(gamma, 6),
        "return_loss_db": round(return_loss_db, 3),
        "mismatch_loss_db": round(mismatch_loss_db, 4),
    }


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------

@dataclass
class WattMeterState:
    name: str
    address: str

    port: Optional[str] = None

    # Raw readings from DCN
    forward_power_w: Optional[float] = None
    reflected_power_w: Optional[float] = None

    # Derived RF metrics
    swr: Optional[float] = None
    reflection_coefficient: Optional[float] = None
    return_loss_db: Optional[float] = None
    mismatch_loss_db: Optional[float] = None

    updated_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class WattMeter:
    """
    DCN Watt Meter (#335) device module.

    Attaches to a DCNNetwork and listens for UPDATE,WM1 packets from the
    configured device address.  On each packet it updates its state and
    publishes all values to the SensorRegistry under keys prefixed with
    the instance name (e.g. "main_forward_power_w", "main_swr", ...).

    Usage::

        registry = SensorRegistry()
        meter = WattMeter(name="main", address="03", registry=registry)
        meter.attach(network)

        # Later:
        print(meter.state.swr)
        print(registry.value("main_swr"))
    """

    def __init__(
        self,
        name: str,
        address: str,
        registry: SensorRegistry,
        n_ports: int = 2,
    ) -> None:
        self.name = name
        self.address = address
        self._registry = registry
        self.n_ports = n_ports
        self.state = WattMeterState(name=name, address=address)
        src = f"watt_meter:{name}"
        for _port in range(n_ports):
            _pfx = f"{name}_port_{_port}"
            registry.publish(f"{_pfx}_forward_power_w",        0.0, "W",  src)
            registry.publish(f"{_pfx}_reflected_power_w",      0.0, "W",  src)
            registry.publish(f"{_pfx}_swr",                    0.0, "",   src)
            registry.publish(f"{_pfx}_reflection_coefficient", 0.0, "",   src)
            registry.publish(f"{_pfx}_return_loss_db",         0.0, "dB", src)
            registry.publish(f"{_pfx}_mismatch_loss_db",       0.0, "dB", src)

    def attach(self, network: DCNNetwork) -> None:
        """Register the packet handler with a DCN network."""
        network.on_packet(self._handle_packet)

    async def _handle_packet(self, packet: DCNPacket, transport_name: str) -> None:
        if packet.from_addr != self.address:
            return
        if packet.command != "UPDATE":
            return
        args = packet.args
        if not args or args[0] != "WM1":
            return
        self._parse_and_publish(args)

    def _parse_and_publish(self, args: list[str]) -> None:
        try:
            port_str   = args[1] if len(args) > 1 else "0"
            port       = int(port_str) if port_str.strip().isdigit() else 0
            forward_w  = float(args[2]) if len(args) > 2 else 0.0
            reflected_w = float(args[3]) if len(args) > 3 else 0.0
        except (ValueError, IndexError):
            return

        metrics = compute_rf_metrics(forward_w, reflected_w)

        # Keep backward-compat state attributes for the most-recent reading
        self.state.port              = port_str
        self.state.forward_power_w   = forward_w
        self.state.reflected_power_w = reflected_w
        self.state.swr               = metrics["swr"]
        self.state.reflection_coefficient = metrics["reflection_coefficient"]
        self.state.return_loss_db    = metrics["return_loss_db"]
        self.state.mismatch_loss_db  = metrics["mismatch_loss_db"]
        self.state.updated_at        = time.time()

        src  = f"watt_meter:{self.name}"
        pfx  = f"{self.name}_port_{port}"
        self._registry.publish(f"{pfx}_forward_power_w",   forward_w,   "W",  src)
        self._registry.publish(f"{pfx}_reflected_power_w", reflected_w, "W",  src)
        self._registry.publish(f"{pfx}_swr",
            metrics["swr"]                    if metrics["swr"]                    is not None else 0.0, "", src)
        self._registry.publish(f"{pfx}_reflection_coefficient",
            metrics["reflection_coefficient"] if metrics["reflection_coefficient"] is not None else 0.0, "", src)
        self._registry.publish(f"{pfx}_return_loss_db",
            metrics["return_loss_db"]         if metrics["return_loss_db"]         is not None else 0.0, "dB", src)
        self._registry.publish(f"{pfx}_mismatch_loss_db",
            metrics["mismatch_loss_db"]       if metrics["mismatch_loss_db"]       is not None else 0.0, "dB", src)


# ---------------------------------------------------------------------------
# Standalone packet parser (for use in tests / hardware conftest)
# ---------------------------------------------------------------------------

def parse_wm1_update(packet: DCNPacket) -> dict:
    """
    Parse an UPDATE,WM1 DCNPacket into a structured dict.

    Returns keys: module_type, port, forward_power_w, reflected_power_w,
    plus all RF metrics from compute_rf_metrics().
    """
    args = packet.args
    result: dict = {"module_type": args[0] if args else None}

    try:
        result["port"] = args[1] if len(args) > 1 else None
        forward_w = float(args[2]) if len(args) > 2 else 0.0
        reflected_w = float(args[3]) if len(args) > 3 else 0.0
        result["forward_power_w"] = forward_w
        result["reflected_power_w"] = reflected_w
        result.update(compute_rf_metrics(forward_w, reflected_w))
    except (ValueError, IndexError):
        pass

    return result

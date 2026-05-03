"""
DCN hardware simulator — publishes realistic device UPDATE packets over MQTT,
and responds to commands (relay set, coax select, etc.) exactly as firmware would.

Packet format mirrors the nodered_mqtt transport:
  topic_rx  — simulator PUBLISHES here  (Python receives these as device responses)
  topic_tx  — simulator SUBSCRIBES here (Python sends commands here)

Run:  python -m simulator [config.yaml]  (default: simulator/sim_config.yaml)
"""

import asyncio
import logging
import math
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import paho.mqtt.client as mqtt
import yaml

logger = logging.getLogger("dcn_sim")

# ---------------------------------------------------------------------------
# Packet helpers
# ---------------------------------------------------------------------------

_UNICAST_RE  = re.compile(r'^/(.{2})(.{2}):([^:]+):([^:]+)\r?$')
_BROADCAST_RE = re.compile(r'^//([^:]+):([^:]+)\r?$')


def _build(from_addr: str, to_addr: str, payload: str) -> str:
    return f"/{from_addr}{to_addr}:{payload}:XX"


def _parse(raw: str) -> Optional[tuple]:
    """Return (to_addr, command, args) or None.  to_addr='' for broadcasts."""
    raw = raw.strip()
    if raw.startswith("//"):
        m = _BROADCAST_RE.match(raw)
        if not m:
            return None
        parts = m.group(1).split(",")
        return "", parts[0], parts[1:]
    m = _UNICAST_RE.match(raw)
    if not m:
        return None
    _from, to_addr, payload, _crc = m.groups()
    parts = payload.split(",")
    return to_addr, parts[0], parts[1:]


# ---------------------------------------------------------------------------
# Simulated device base
# ---------------------------------------------------------------------------

class _SimDevice:
    address: str = ""
    master: str = "00"
    interval: float = 1.0

    def update_packet(self) -> str:
        raise NotImplementedError

    def handle(self, cmd: str, args: list) -> None:
        pass

    def _pkt(self, payload: str) -> str:
        return _build(self.address, self.master, payload)


# ---------------------------------------------------------------------------
# GPIO module (#321)  — relays, digital I/O, voltmeters, temps
# ---------------------------------------------------------------------------

class SimGPIO(_SimDevice):
    def __init__(self, cfg: dict, master: str) -> None:
        self.address  = cfg["address"]
        self.master   = master
        self.interval = float(cfg.get("update_interval_s", 1.0))
        raw = cfg.get("relay_states", "00000000")
        self._relays  = list(str(raw).ljust(8, "0")[:8])
        self._v       = [12.0, 13.8, 5.0, 3.3]
        self._temps   = [72.0, 74.0]

    def handle(self, cmd: str, args: list) -> None:
        m = re.match(r"^RY(\d)$", cmd)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < 8 and args:
                v = args[0]
                if   v == "1": self._relays[idx] = "1"
                elif v == "0": self._relays[idx] = "0"
                elif v == "T": self._relays[idx] = str(1 - int(self._relays[idx]))
            return
        if cmd == "RY":
            if not args:
                self._relays = ["0"] * 8
            elif len(args) == 1 and len(args[0]) == 8:
                for i, c in enumerate(args[0]):
                    if c in "01":
                        self._relays[i] = c

    def update_packet(self) -> str:
        for i in range(4):
            self._v[i] = max(0.0, self._v[i] + random.uniform(-0.005, 0.005))
        for i in range(2):
            self._temps[i] += random.uniform(-0.05, 0.05)
        v = ",".join(f"{x:.3f}" for x in self._v)
        t = ",".join(f"{x:.2f}" for x in self._temps)
        relay_str = "".join(self._relays)
        return self._pkt(f"UPDATE,GPIO1,{relay_str},0000,{v},{t}")


# ---------------------------------------------------------------------------
# Coax switch (#331 CX-1) — selects one of 4 antenna ports
# ---------------------------------------------------------------------------

class SimCoaxSwitch(_SimDevice):
    def __init__(self, cfg: dict, master: str) -> None:
        self.address     = cfg["address"]
        self.master      = master
        self.interval    = float(cfg.get("update_interval_s", 1.0))
        self._port       = int(cfg.get("active_port", 1))

    def handle(self, cmd: str, args: list) -> None:
        if cmd == "CX" and args:
            try:
                self._port = int(args[0])
            except ValueError:
                pass

    def update_packet(self) -> str:
        return self._pkt(f"UPDATE,CX1,{self._port}")


# ---------------------------------------------------------------------------
# Watt meter (#351) — RF forward/reflected power at configurable rate
# ---------------------------------------------------------------------------

class SimWattMeter(_SimDevice):
    def __init__(self, cfg: dict, master: str) -> None:
        self.address    = cfg["address"]
        self.master     = master
        self.interval   = float(cfg.get("update_interval_s", 0.1))
        self.tx_enabled = bool(cfg.get("tx_enabled", False))
        self._fwd_nom   = float(cfg.get("forward_power_w", 100.0))
        self._ref_nom   = float(cfg.get("reflected_power_w", 2.0))
        self._t         = 0.0

    def update_packet(self) -> str:
        self._t += self.interval
        if self.tx_enabled:
            # Slight ripple to simulate real RF envelope
            fwd = self._fwd_nom * (1 + 0.015 * math.sin(self._t * 2 * math.pi))
            fwd = max(0.0, fwd + random.uniform(-0.3, 0.3))
            ref = max(0.0, min(
                self._ref_nom + random.uniform(-0.05, 0.05),
                fwd * 0.9,
            ))
        else:
            fwd = ref = 0.0
        return self._pkt(f"UPDATE,WM1,1,{fwd:.3f},{ref:.3f}")


# ---------------------------------------------------------------------------
# VHF coax relay (#332 CX-2) — single SPDT relay
# ---------------------------------------------------------------------------

class SimVHFRelay(_SimDevice):
    def __init__(self, cfg: dict, master: str) -> None:
        self.address  = cfg["address"]
        self.master   = master
        self.interval = float(cfg.get("update_interval_s", 1.0))
        self._state   = int(cfg.get("relay_state", 0))

    def handle(self, cmd: str, args: list) -> None:
        if cmd == "RY1" and args:
            v = args[0]
            if   v == "1": self._state = 1
            elif v == "0": self._state = 0
            elif v == "T": self._state ^= 1

    def update_packet(self) -> str:
        return self._pkt(f"UPDATE,CX2,{self._state}")


# ---------------------------------------------------------------------------
# Antenna relay module (#361) — 8-relay bank
# ---------------------------------------------------------------------------

class SimAntennaRelay(_SimDevice):
    def __init__(self, cfg: dict, master: str) -> None:
        self.address  = cfg["address"]
        self.master   = master
        self.interval = float(cfg.get("update_interval_s", 1.0))
        raw = cfg.get("relay_states", "00000000")
        self._relays  = list(str(raw).ljust(8, "0")[:8])
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def handle(self, cmd: str, args: list) -> None:
        m = re.match(r"^RY(\d)$", cmd)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < 8 and args:
                v = args[0]
                if   v == "1": self._relays[idx] = "1"
                elif v == "0": self._relays[idx] = "0"
                elif v == "T": self._relays[idx] = str(1 - int(self._relays[idx]))
                elif v == "P" and self._loop:
                    dur = float(args[1]) if len(args) > 1 else 0.5
                    asyncio.run_coroutine_threadsafe(self._pulse(idx, dur), self._loop)
            return
        if cmd == "RY":
            if not args:
                self._relays = ["0"] * 8
            elif len(args) == 1 and len(args[0]) == 8:
                for i, c in enumerate(args[0]):
                    if c in "01":
                        self._relays[i] = c
            return
        if cmd == "POS" and args:
            try:
                pos = int(args[0]) - 1
                self._relays = ["0"] * 8
                if 0 <= pos < 8:
                    self._relays[pos] = "1"
            except ValueError:
                pass

    async def _pulse(self, idx: int, duration: float) -> None:
        self._relays[idx] = "1"
        await asyncio.sleep(duration)
        self._relays[idx] = "0"

    def update_packet(self) -> str:
        return self._pkt(f"UPDATE,ARC1,{''.join(self._relays)}")


# ---------------------------------------------------------------------------
# Device registry
# ---------------------------------------------------------------------------

_DEVICE_CLASSES = {
    "gpio":           SimGPIO,
    "coax_switch":    SimCoaxSwitch,
    "watt_meter":     SimWattMeter,
    "vhf_relay":      SimVHFRelay,
    "antenna_relay":  SimAntennaRelay,
}


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class DCNSimulator:
    def __init__(self, config: dict) -> None:
        mqtt_cfg = config.get("mqtt", {})
        self._broker    = mqtt_cfg.get("broker", "localhost")
        self._port      = int(mqtt_cfg.get("port", 1883))
        self._username  = mqtt_cfg.get("username") or None
        self._password  = mqtt_cfg.get("password") or None
        self._topic_rx  = config.get("topic_rx", "dcn/control/rx")
        self._topic_tx  = config.get("topic_tx", "dcn/control/tx")
        self._master    = config.get("master_addr", "00")
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._devices: dict[str, _SimDevice] = {}
        for dev_cfg in config.get("devices", []):
            cls = _DEVICE_CLASSES.get(dev_cfg.get("type", ""))
            if cls is None:
                logger.warning("Unknown device type '%s' — skipped", dev_cfg.get("type"))
                continue
            dev = cls(dev_cfg, self._master)
            self._devices[dev.address] = dev
            logger.info("  [%s] %s  (every %.3fs)", dev.address, dev_cfg["type"], dev.interval)

        # Radio simulator (rigctld)
        self._rigctld: Optional[object] = None
        rig_cfg = config.get("radio", {}).get("rigctld", {})
        if rig_cfg.get("enabled", False):
            from simulator.radio_sim import SimRadioState, SimRigctld
            state = SimRadioState.from_config(rig_cfg.get("initial", {}))
            self._rigctld = SimRigctld(
                state,
                host=rig_cfg.get("host", "127.0.0.1"),
                port=int(rig_cfg.get("port", 4532)),
            )
            logger.info("  rigctld  %s:%s", rig_cfg.get("host", "127.0.0.1"),
                        rig_cfg.get("port", 4532))

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
            client_id="dcn-simulator",
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        if self._username:
            self._client.username_pw_set(self._username, self._password)

    # ------------------------------------------------------------------
    # MQTT callbacks (called from paho thread)
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            logger.error("MQTT connect failed (rc=%s)", rc)
            return
        logger.info("MQTT connected to %s:%s", self._broker, self._port)
        client.subscribe(self._topic_tx)
        logger.info("Subscribed to TX topic: %s", self._topic_tx)
        logger.info("Publishing UPDATE packets to RX topic: %s", self._topic_rx)

    def _on_message(self, client, userdata, msg) -> None:
        raw = msg.payload.decode("ascii", errors="replace")
        parsed = _parse(raw)
        if parsed is None:
            return
        to_addr, cmd, args = parsed
        logger.debug("CMD  to=%-4s  %s %s", to_addr or "ALL", cmd, args)

        if to_addr == "":
            for dev in self._devices.values():
                dev.handle(cmd, args)
        else:
            dev = self._devices.get(to_addr)
            if dev:
                dev.handle(cmd, args)

    # ------------------------------------------------------------------
    # Async device loops
    # ------------------------------------------------------------------

    async def _device_loop(self, dev: _SimDevice) -> None:
        while True:
            try:
                pkt = dev.update_packet()
                self._client.publish(self._topic_rx, pkt)
                logger.debug("TX   %s", pkt)
            except Exception as exc:
                logger.warning("Device %s update error: %s", dev.address, exc)
            await asyncio.sleep(dev.interval)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        for dev in self._devices.values():
            if hasattr(dev, "attach_loop"):
                dev.attach_loop(self._loop)

        if self._rigctld:
            await self._rigctld.start()

        self._client.connect_async(self._broker, self._port, keepalive=60)
        self._client.loop_start()

        logger.info("DCN simulator starting — %d device(s)", len(self._devices))
        tasks = [
            asyncio.create_task(self._device_loop(dev), name=f"sim-{dev.address}")
            for dev in self._devices.values()
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            for t in tasks:
                t.cancel()
            if self._rigctld:
                await self._rigctld.stop()
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("DCN simulator stopped")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="DCN hardware simulator — publishes device packets over MQTT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  python -m simulator\n  python -m simulator simulator/sim_config.yaml -v",
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="simulator/sim_config.yaml",
        help="Path to YAML config (default: simulator/sim_config.yaml)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        logger.error("Config not found: %s", cfg_path)
        sys.exit(1)

    with cfg_path.open(encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    sim = DCNSimulator(config)
    try:
        asyncio.run(sim.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

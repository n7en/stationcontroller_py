"""
WSHub - WebSocket connection manager and broadcaster.

Maintains the set of active browser connections and fans out JSON messages
to all of them.  Wires into SensorRegistry.on_any() and RadioState changes
so the browser receives live updates without polling.

Message types (server -> client):
  sensor_update    - one sensor value changed
  relay_state      - a relay was toggled
  radio_state      - frequency / mode / PTT / connected changed
  automation_fired - an automation executed
  full_snapshot    - complete current state, sent once on connect

Message types (client -> server, handled in ws router):
  relay_cmd        - toggle a relay
  radio_tune       - set frequency / mode
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Optional

from fastapi import WebSocket

if TYPE_CHECKING:
    from sensors.sensor_registry import Measurement, SensorRegistry
    from radio.radio_state import RadioState
    from radio.radio_manager import RadioManager

log = logging.getLogger(__name__)


class WSHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        log.info("WS client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        log.info("WS client disconnected (%d remaining)", len(self._connections))

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast(self, message: dict) -> None:
        if not self._connections:
            return
        text = json.dumps(message)
        dead: set[WebSocket] = set()
        for ws in list(self._connections):
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send(self, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            self.disconnect(ws)

    # ------------------------------------------------------------------
    # Typed message helpers
    # ------------------------------------------------------------------

    async def broadcast_sensor(self, m: "Measurement") -> None:
        await self.broadcast({
            "type": "sensor_update",
            "name": m.name,
            "value": m.value,
            "unit": m.unit,
            "source": m.source,
            "ts": m.timestamp,
        })

    async def broadcast_relay(self, key: str, state: int, name: str = "") -> None:
        await self.broadcast({
            "type": "relay_state",
            "key": key,
            "state": state,
            "name": name,
        })

    async def broadcast_radio(self, name: str, rs: "RadioState") -> None:
        mode = rs.mode
        mode_str = mode.value if mode is not None else None
        await self.broadcast({
            "type":            "radio_state",
            "name":            name,
            "frequency_hz":    rs.frequency_hz,
            "mode":            mode_str,
            "bandwidth_hz":    rs.bandwidth_hz,
            "vfo":             rs.vfo,
            "ptt":             rs.ptt,
            "signal_strength": rs.signal_strength,
            "rf_power":        rs.rf_power,
            "connected":       rs.connected,
            "info":            rs.info,
            "vfob_frequency_hz":  rs.vfob_frequency_hz,
            "vfob_mode":          rs.vfob_mode,
            "vfob_bandwidth_hz":  rs.vfob_bandwidth_hz,
            "sub_frequency_hz":   rs.sub_frequency_hz,
            "sub_mode":           rs.sub_mode,
            "sub_bandwidth_hz":   rs.sub_bandwidth_hz,
        })

    async def broadcast_automation(self, name: str, tier: str = "") -> None:
        await self.broadcast({
            "type": "automation_fired",
            "name": name,
            "tier": tier,
            "ts": time.time(),
        })

    async def broadcast_labels(self, labels: dict[str, str]) -> None:
        await self.broadcast({"type": "labels_update", "labels": labels})

    async def broadcast_update_available(self, result: dict) -> None:
        await self.broadcast({
            "type":           "update_available",
            "latest_version": result.get("latest_version"),
            "release_url":    result.get("release_url", ""),
            "published_at":   result.get("published_at", ""),
        })

    # ------------------------------------------------------------------
    # Full snapshot - sent to a newly connected client
    # ------------------------------------------------------------------

    async def send_snapshot(
        self,
        ws: WebSocket,
        sensor_registry: Optional["SensorRegistry"] = None,
        radio_manager: Optional["RadioManager"] = None,
        label_registry: Optional[Any] = None,
        update_result: Optional[dict] = None,
    ) -> None:
        sensors = {}
        if sensor_registry is not None:
            for name, m in sensor_registry.snapshot().items():
                sensors[name] = {
                    "value": m.value,
                    "unit": m.unit,
                    "source": m.source,
                    "ts": m.timestamp,
                }

        radios: dict = {}
        if radio_manager is not None:
            for iface in radio_manager:
                rs = iface.state
                mode = rs.mode
                radios[iface.name] = {
                    "frequency_hz":    rs.frequency_hz,
                    "mode":            mode.value if mode is not None else None,
                    "bandwidth_hz":    rs.bandwidth_hz,
                    "vfo":             rs.vfo,
                    "ptt":             rs.ptt,
                    "signal_strength": rs.signal_strength,
                    "rf_power":        rs.rf_power,
                    "connected":       rs.connected,
                    "info":            rs.info,
                    "vfob_frequency_hz":  rs.vfob_frequency_hz,
                    "vfob_mode":          rs.vfob_mode,
                    "vfob_bandwidth_hz":  rs.vfob_bandwidth_hz,
                    "sub_frequency_hz":   rs.sub_frequency_hz,
                    "sub_mode":           rs.sub_mode,
                    "sub_bandwidth_hz":   rs.sub_bandwidth_hz,
                }

        labels = label_registry.all() if label_registry is not None else {}

        update = None
        if update_result and update_result.get("update_available"):
            update = {
                "latest_version": update_result.get("latest_version"),
                "release_url":    update_result.get("release_url", ""),
                "published_at":   update_result.get("published_at", ""),
            }

        await self.send(ws, {
            "type":    "full_snapshot",
            "sensors": sensors,
            "radios":  radios,
            "labels":  labels,
            "update":  update,
            "ts":      time.time(),
        })

    # ------------------------------------------------------------------
    # Wiring helpers - call these at startup
    # ------------------------------------------------------------------

    def attach_sensor_registry(self, registry: "SensorRegistry") -> None:
        """Push every sensor update to all connected browsers."""
        def _on_measurement(m: "Measurement") -> None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self.broadcast_sensor(m),
                    name=f"ws.sensor.{m.name}",
                )
            except RuntimeError:
                pass

        registry.on_any(_on_measurement)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

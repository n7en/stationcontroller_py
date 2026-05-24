"""
Node-RED MQTT bridge transport.

This transport connects to an MQTT broker to exchange DCN packets with a
Node-RED flow running on the same or a remote device.

Node-RED flow direction:
  Serial IN  -> validate -> MQTT publish  -> topic_rx  (Node-RED -> Python)
  topic_tx   -> MQTT subscribe -> Serial OUT          (Python -> Node-RED)

Import nodered/dcn_mqtt_bridge_flow.json into Node-RED to set up the other end.

Config keys:
  broker    - MQTT broker hostname or IP, default "localhost"
  port      - MQTT broker port, default 1883
  topic_rx  - topic Node-RED publishes DCN packets to, default "dcn/<name>/rx"
  topic_tx  - topic Python publishes commands to, default "dcn/<name>/tx"
  username  - optional broker username
  password  - optional broker password
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import paho.mqtt.client as mqtt

from .base import DCNTransport
from ..dcn_packet import DCNPacket, parse_packet

logger = logging.getLogger(__name__)


_CONNECT_TIMEOUT_S = 10   # seconds before logging an error for unreachable broker


class NodeRedMQTTTransport(DCNTransport):

    def __init__(self, name: str, config: dict) -> None:
        super().__init__(name, config)
        self._client: Optional[mqtt.Client] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._broker_host: str = ""
        self._broker_port: int = 1883

    @property
    def _topic_rx(self) -> str:
        return self._config.get("topic_rx", f"dcn/{self.name}/rx")

    @property
    def _topic_tx(self) -> str:
        return self._config.get("topic_tx", f"dcn/{self.name}/tx")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self._loop = asyncio.get_event_loop()
        broker = self._config.get("broker", "localhost")
        port = int(self._config.get("port", 1883))
        username = self._config.get("username", "")
        password = self._config.get("password", "")

        self._broker_host = broker
        self._broker_port = port

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
            client_id=f"dcn-{self.name}",
            clean_session=True,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        if username:
            self._client.username_pw_set(username, password or None)

        self._client.connect_async(broker, port, keepalive=60)
        self._client.loop_start()
        logger.info(
            "MQTT '%s' connecting to %s:%d (rx=%s, tx=%s)",
            self.name, broker, port, self._topic_rx, self._topic_tx,
        )

        self._watchdog_task = self._loop.create_task(
            self._connection_watchdog(), name=f"mqtt-watchdog-{self.name}"
        )

    async def disconnect(self) -> None:
        self._connected = False
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
        logger.info("MQTT transport '%s' disconnected", self.name)

    async def send(self, packet: DCNPacket) -> None:
        if not self._connected or not self._client:
            logger.warning("MQTT '%s': send skipped - not connected", self.name)
            return
        payload = str(packet)
        self._client.publish(self._topic_tx, payload, qos=0)
        logger.debug("MQTT '%s' TX [%s]: %s", self.name, self._topic_tx, payload)

    # ------------------------------------------------------------------
    # paho-mqtt callbacks (run in paho's network thread)
    # ------------------------------------------------------------------

    async def _connection_watchdog(self) -> None:
        await asyncio.sleep(_CONNECT_TIMEOUT_S)
        if not self._connected:
            logger.error(
                "MQTT '%s': no connection to broker %s:%d after %ds - "
                "check the broker is running and the address is correct",
                self.name, self._broker_host, self._broker_port, _CONNECT_TIMEOUT_S,
            )

    def _on_connect(self, client: mqtt.Client, userdata, flags, rc: int) -> None:
        if rc == 0:
            self._connected = True
            if self._watchdog_task is not None:
                self._watchdog_task.cancel()
                self._watchdog_task = None
            client.subscribe(self._topic_rx, qos=0)
            logger.info(
                "MQTT '%s' connected, subscribed to %s", self.name, self._topic_rx
            )
        else:
            logger.error("MQTT '%s' broker refused connection, rc=%d", self.name, rc)

    def _on_disconnect(self, client: mqtt.Client, userdata, rc: int) -> None:
        self._connected = False
        if rc != 0:
            logger.warning(
                "MQTT '%s' unexpected disconnect rc=%d - paho will reconnect",
                self.name, rc,
            )

    def _on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        try:
            raw = msg.payload.decode("ascii", errors="replace").strip()
            logger.debug("MQTT '%s' RX [%s]: %s", self.name, msg.topic, raw)
            packet = parse_packet(raw)
            if packet and self._loop and not self._loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self._dispatch(packet), self._loop
                )
        except Exception:
            logger.exception("MQTT '%s' error processing message", self.name)

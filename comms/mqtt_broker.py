"""
Embedded MQTT broker (amqtt) — optional, started when mqtt_broker.enabled = true
in comms_config.yaml.

Lifecycle:
    broker = EmbeddedMQTTBroker.from_config(cfg)
    await broker.start()
    ...
    await broker.stop()
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

log = logging.getLogger("mqtt_broker")


class EmbeddedMQTTBroker:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        allow_anonymous: bool = True,
        users: Optional[list[dict]] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._allow_anonymous = allow_anonymous
        self._users = users or []
        self._broker = None
        self._passwd_file: Optional[str] = None

    @classmethod
    def from_config(cls, cfg: dict) -> "EmbeddedMQTTBroker":
        return cls(
            host=cfg.get("host", "127.0.0.1"),
            port=int(cfg.get("port", 1883)),
            allow_anonymous=cfg.get("allow_anonymous", True),
            users=cfg.get("users") or [],
        )

    async def start(self) -> None:
        from amqtt.broker import Broker

        bind = f"{self._host}:{self._port}"

        if self._users:
            fd, path = tempfile.mkstemp(suffix=".passwd", prefix="mqtt_")
            with os.fdopen(fd, "w") as fh:
                for user in self._users:
                    fh.write(f"{user['username']}:{user['password']}\n")
            self._passwd_file = path

            auth_cfg = {
                "allow-anonymous": self._allow_anonymous,
                "plugins": ["auth.file"],
                "password-file": path,
            }
        else:
            auth_cfg = {"allow-anonymous": True}

        amqtt_config = {
            "listeners": {
                "default": {
                    "type": "tcp",
                    "bind": bind,
                    "max_connections": 50,
                }
            },
            "sys_interval": 0,
            "auth": auth_cfg,
            "topic-check": {"enabled": False},
        }

        self._broker = Broker(amqtt_config)
        await self._broker.start()
        log.info(
            "Embedded MQTT broker listening on %s (anonymous=%s, users=%d)",
            bind, self._allow_anonymous, len(self._users),
        )

    async def stop(self) -> None:
        if self._broker is not None:
            await self._broker.shutdown()
            log.info("Embedded MQTT broker stopped")
            self._broker = None
        if self._passwd_file is not None:
            try:
                os.unlink(self._passwd_file)
            except OSError:
                pass
            self._passwd_file = None

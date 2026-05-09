"""
ManagedRigctldBackend — launches and manages a rigctld subprocess, then
connects to it exactly like a regular RigctldBackend.

Use this backend when you want the Station Controller to own the rigctld
process lifecycle instead of requiring you to start it manually.

Config keys (in radio_config.yaml):
    model_id          — Hamlib rig model number (required)
                        Common values: 3073 = IC-7300, 2014 = TS-2000,
                                       135  = FT-991A, 122 = FT-817,
                                       1    = Dummy (no radio attached)
    serial_port       — Serial device (required): /dev/ttyUSB0 or COM3
    serial_baud       — CAT baud rate (default 9600)
    host              — rigctld listen address (default 127.0.0.1)
    port              — rigctld TCP port; 0 = auto-select (default 0)
    timeout_s         — per-command TCP timeout in seconds (default 15.0)
    startup_timeout_s — seconds to wait for rigctld to become ready (default 10.0)
"""
from __future__ import annotations

import logging

from .base import RadioBackendError
from .rigctld import RigctldBackend
from ..rigctld_launcher import RigctldLauncher

log = logging.getLogger(__name__)


class ManagedRigctldBackend(RigctldBackend):

    def __init__(
        self,
        model_id: int,
        serial_port: str,
        serial_baud: int = 9600,
        host: str = "127.0.0.1",
        port: int = 0,
        timeout_s: float = 15.0,
        startup_timeout_s: float = 10.0,
        serial_timeout_ms: int = 500,
    ) -> None:
        self._launcher = RigctldLauncher(
            model_id=model_id,
            serial_port=serial_port,
            baud_rate=serial_baud,
            listen_host=host,
            port=port,  # launcher picks a free port when port=0
            serial_timeout_ms=serial_timeout_ms,
        )
        self._startup_timeout = startup_timeout_s
        # Initialise the TCP backend with the port the launcher resolved
        super().__init__(host=host, port=self._launcher.port, timeout_s=timeout_s)

    async def connect(self) -> None:
        log.debug(
            "ManagedRigctld connect: model=%d serial=%s baud=%d host=%s port=%d",
            self._launcher.model_id, self._launcher.serial_port,
            self._launcher.baud_rate, self._launcher.listen_host, self._launcher.port,
        )
        try:
            await self._launcher.start(startup_timeout=self._startup_timeout)
        except Exception as exc:
            log.error("Failed to start managed rigctld: %s", exc)
            raise RadioBackendError(f"Failed to start rigctld: {exc}") from exc
        self._port = self._launcher.port  # keep in sync
        await super().connect()

    async def disconnect(self) -> None:
        log.debug("ManagedRigctld disconnect (port %d)", self._launcher.port)
        await super().disconnect()
        await self._launcher.stop()

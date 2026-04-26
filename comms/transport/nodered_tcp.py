"""
Node-RED TCP bridge transport.

Python acts as a TCP server; the Node-RED flow connects as a TCP client.
A single persistent connection carries DCN packets in both directions,
CR-delimited, over plain ASCII.

Only one client connection is tracked at a time.  If Node-RED reconnects,
the old connection is cleanly replaced.

Import nodered/dcn_tcp_bridge_flow.json into Node-RED to set up the other end.

Config keys:
  host  - interface to listen on, default "0.0.0.0"
  port  - TCP port, default 4880
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .base import DCNTransport
from ..dcn_packet import DCNPacket, parse_packet

logger = logging.getLogger(__name__)


class NodeRedTCPTransport(DCNTransport):

    def __init__(self, name: str, config: dict) -> None:
        super().__init__(name, config)
        self._host: str = config.get("host", "0.0.0.0")
        self._port: int = int(config.get("port", 4880))
        self._server: Optional[asyncio.Server] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )
        self._connected = True
        logger.info(
            "TCP '%s' listening on %s:%d — waiting for Node-RED client",
            self.name, self._host, self._port,
        )

    async def disconnect(self) -> None:
        self._connected = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        logger.info("TCP '%s' stopped", self.name)

    async def send(self, packet: DCNPacket) -> None:
        if not self._writer:
            logger.warning("TCP '%s': send skipped — no client connected", self.name)
            return
        try:
            self._writer.write(packet.encode())
            await self._writer.drain()
            logger.debug("TCP '%s' TX: %s", self.name, packet)
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            logger.warning("TCP '%s': send failed (%s), dropping client", self.name, exc)
            self._writer = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        addr = writer.get_extra_info("peername")
        logger.info("TCP '%s': client connected from %s", self.name, addr)

        if self._writer:
            logger.info("TCP '%s': replacing previous client", self.name)
            try:
                self._writer.close()
            except Exception:
                pass

        self._writer = writer
        buf = ""

        try:
            while True:
                data = await reader.read(256)
                if not data:
                    break
                buf += data.decode("ascii", errors="replace")
                while "\r" in buf:
                    line, buf = buf.split("\r", 1)
                    line = line.strip()
                    if not line:
                        continue
                    packet = parse_packet(line)
                    if packet:
                        logger.debug("TCP '%s' RX: %s", self.name, packet)
                        await self._dispatch(packet)
                    else:
                        logger.debug("TCP '%s' ignored non-packet: %r", self.name, line)
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        except Exception:
            logger.exception("TCP '%s' client handler error", self.name)
        finally:
            logger.info("TCP '%s': client %s disconnected", self.name, addr)
            if self._writer is writer:
                self._writer = None
            try:
                writer.close()
            except Exception:
                pass

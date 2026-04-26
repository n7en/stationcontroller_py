"""
DCNNetwork — manages one or more DCN transports as a unified network.

Usage (from config file):

    network = DCNNetwork.from_config("config/comms_config.yaml")

    @network.on_packet
    async def handle(packet, transport_name):
        print(f"[{transport_name}] {packet}")

    async with network:
        await network.send("01", "STATE")          # query GPIO module
        await network.broadcast("PING")            # ping all devices

Usage (manual):

    network = DCNNetwork()
    network.add_transport(RS485Transport("control", {"port": "/dev/ttyUSB0"}))
    network.add_transport(RS485Transport("power",   {"port": "/dev/ttyUSB1", "baud_rate": 115200}))
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable, Awaitable, Optional, Union

from .config import load_config, get_buses, get_networks
from .dcn_packet import DCNPacket, build_packet, build_broadcast, MASTER_ADDR
from .transport.base import DCNTransport, PacketHandler
from .transport.rs485 import RS485Transport
from .transport.nodered_mqtt import NodeRedMQTTTransport
from .transport.nodered_tcp import NodeRedTCPTransport

logger = logging.getLogger(__name__)

_TRANSPORT_REGISTRY: dict[str, type[DCNTransport]] = {
    "rs485": RS485Transport,
    "nodered_mqtt": NodeRedMQTTTransport,
    "nodered_tcp": NodeRedTCPTransport,
}


class DCNNetwork:

    def __init__(self, master_addr: str = MASTER_ADDR) -> None:
        self.master_addr = master_addr
        self._transports: dict[str, DCNTransport] = {}
        self._handlers: list[PacketHandler] = []
        self._tx_handlers: list[PacketHandler] = []

    # ------------------------------------------------------------------
    # Transport management
    # ------------------------------------------------------------------

    def add_transport(self, transport: DCNTransport) -> None:
        """Register a transport. Packets received on it are forwarded to
        all handlers registered with on_packet()."""
        if transport.name in self._transports:
            raise ValueError(f"Transport name '{transport.name}' already registered")
        self._transports[transport.name] = transport
        transport.on_packet(self._route_packet)
        logger.debug("Registered transport '%s' (%s)", transport.name, type(transport).__name__)

    def transport(self, name: str) -> Optional[DCNTransport]:
        return self._transports.get(name)

    @property
    def transports(self) -> dict[str, DCNTransport]:
        return dict(self._transports)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect_all(self) -> None:
        """Connect every registered transport concurrently."""
        results = await asyncio.gather(
            *[t.connect() for t in self._transports.values()],
            return_exceptions=True,
        )
        for transport, result in zip(self._transports.values(), results):
            if isinstance(result, Exception):
                logger.error(
                    "Transport '%s' failed to connect: %s", transport.name, result
                )

    async def disconnect_all(self) -> None:
        """Disconnect all transports."""
        await asyncio.gather(
            *[t.disconnect() for t in self._transports.values()],
            return_exceptions=True,
        )

    # asyncio context manager support
    async def __aenter__(self) -> "DCNNetwork":
        await self.connect_all()
        return self

    async def __aexit__(self, *_) -> None:
        await self.disconnect_all()

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send(
        self,
        to_addr: str,
        payload: str,
        from_addr: Optional[str] = None,
        transport_name: Optional[str] = None,
    ) -> None:
        """Build and send a unicast DCN packet.

        If transport_name is specified, the packet is sent only on that
        transport.  Otherwise it is sent on all connected transports.
        """
        packet = build_packet(to_addr, payload, from_addr or self.master_addr)
        await self._transmit(packet, transport_name)

    async def broadcast(
        self,
        payload: str,
        transport_name: Optional[str] = None,
    ) -> None:
        """Build and send a broadcast DCN packet (//)."""
        packet = build_broadcast(payload)
        await self._transmit(packet, transport_name)

    async def send_packet(
        self,
        packet: DCNPacket,
        transport_name: Optional[str] = None,
    ) -> None:
        """Send a pre-built DCNPacket."""
        await self._transmit(packet, transport_name)

    async def _transmit(
        self, packet: DCNPacket, transport_name: Optional[str]
    ) -> None:
        targets = (
            [self._transports[transport_name]]
            if transport_name and transport_name in self._transports
            else [t for t in self._transports.values() if t.connected]
        )
        if not targets:
            logger.warning("No connected transports available to send: %s", packet)
            return
        for t in targets:
            for handler in self._tx_handlers:
                try:
                    result = handler(packet, t.name)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("Unhandled exception in transmit handler")
        await asyncio.gather(
            *[t.send(packet) for t in targets],
            return_exceptions=True,
        )

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def on_packet(
        self,
        handler: Optional[PacketHandler] = None,
    ) -> Callable:
        """Register a handler for received packets (decorator or direct call).

        Signature: handler(packet: DCNPacket, transport_name: str) -> None
        """
        if handler is not None:
            self._handlers.append(handler)
            return handler

        def decorator(fn: PacketHandler) -> PacketHandler:
            self._handlers.append(fn)
            return fn

        return decorator

    def on_transmit(
        self,
        handler: Optional[PacketHandler] = None,
    ) -> Callable:
        """Register a handler called for every transmitted packet (decorator or direct call).

        Signature: handler(packet: DCNPacket, transport_name: str) -> None
        Called once per target transport before the packet is sent.
        """
        if handler is not None:
            self._tx_handlers.append(handler)
            return handler

        def decorator(fn: PacketHandler) -> PacketHandler:
            self._tx_handlers.append(fn)
            return fn

        return decorator

    async def _route_packet(self, packet: DCNPacket, transport_name: str) -> None:
        for handler in self._handlers:
            try:
                result = handler(packet, transport_name)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Unhandled exception in packet handler")

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        config_path: str | Path,
        master_addr: str = MASTER_ADDR,
    ) -> "DCNNetwork":
        """Create a DCNNetwork from a YAML config file.

        Only network entries whose type matches a registered transport are
        loaded; unknown types are logged and skipped.
        """
        config = load_config(config_path)
        network = cls(master_addr=master_addr)

        for net_cfg in get_networks(config):
            transport_type = net_cfg.get("type")
            transport_cls = _TRANSPORT_REGISTRY.get(transport_type)
            if transport_cls is None:
                logger.warning(
                    "Unknown transport type '%s' — skipping entry '%s'",
                    transport_type, net_cfg.get("name", "?"),
                )
                continue
            name = net_cfg.get("name") or transport_type
            try:
                transport = transport_cls(name=name, config=net_cfg)
                network.add_transport(transport)
                logger.debug("Loaded transport '%s' (%s)", name, transport_type)
            except Exception:
                logger.exception("Failed to create transport '%s'", name)

        return network

    @classmethod
    def buses_from_config(
        cls,
        config_path: str | Path,
        master_addr: str = MASTER_ADDR,
    ) -> "dict[str, DCNNetwork]":
        """Create one DCNNetwork per bus entry in the 'buses:' config schema.

        Returns a dict keyed by bus name so callers can attach devices to
        specific buses by name::

            networks = DCNNetwork.buses_from_config("config/comms_config.yaml")
            gpio.attach(networks["control"])
            watt_meter.attach(networks["power"])
        """
        config = load_config(config_path)
        buses: dict[str, DCNNetwork] = {}

        for bus_cfg in get_buses(config):
            bus_name = bus_cfg.get("name") or f"bus_{len(buses)}"
            network = cls(master_addr=master_addr)

            for transport_cfg in bus_cfg.get("transports", []):
                transport_type = transport_cfg.get("type")
                transport_cls = _TRANSPORT_REGISTRY.get(transport_type)
                if transport_cls is None:
                    logger.warning(
                        "Unknown transport type '%s' in bus '%s' — skipping",
                        transport_type, bus_name,
                    )
                    continue
                t_name = transport_cfg.get("name") or transport_type
                try:
                    transport = transport_cls(name=t_name, config=transport_cfg)
                    network.add_transport(transport)
                    logger.debug(
                        "Bus '%s': loaded transport '%s' (%s)",
                        bus_name, t_name, transport_type,
                    )
                except Exception:
                    logger.exception(
                        "Failed to create transport '%s' in bus '%s'", t_name, bus_name
                    )

            buses[bus_name] = network

        return buses

    def __repr__(self) -> str:
        names = list(self._transports.keys())
        return f"<DCNNetwork master={self.master_addr!r} transports={names}>"

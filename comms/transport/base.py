from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Union

from ..dcn_packet import DCNPacket

logger = logging.getLogger(__name__)

PacketHandler = Callable[[DCNPacket, str], Union[None, Awaitable[None]]]


class DCNTransport(ABC):
    """
    Abstract base for all DCN transport adapters.

    Subclasses implement connect/disconnect/send for a specific physical or
    virtual medium (RS-485, MQTT, TCP).  Received packets are dispatched to
    all registered handlers via on_packet().
    """

    def __init__(self, name: str, config: dict) -> None:
        self.name = name
        self._config = config
        self._connected = False
        self._handlers: list[PacketHandler] = []

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def baud_rate(self) -> int:
        return int(self._config.get("baud_rate", 9600))

    @property
    def description(self) -> str:
        return self._config.get("description", "")

    @abstractmethod
    async def connect(self) -> None:
        """Open the transport and begin receiving packets."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the transport cleanly."""

    @abstractmethod
    async def send(self, packet: DCNPacket) -> None:
        """Transmit a DCN packet."""

    def on_packet(self, handler: PacketHandler) -> None:
        """Register a callback invoked for every received DCNPacket."""
        self._handlers.append(handler)

    async def _dispatch(self, packet: DCNPacket) -> None:
        """Invoke all registered handlers with the received packet."""
        for handler in self._handlers:
            try:
                result = handler(packet, self.name)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Error in packet handler for transport '%s'", self.name)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} connected={self.connected}>"

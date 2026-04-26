"""
DCNMessageLogger — logs every received and transmitted DCN packet to the database.

Attach to a DCNNetwork at startup:

    dcn_logger = DCNMessageLogger(store)
    dcn_logger.attach(network)

Both RX (on_packet) and TX (on_transmit) are captured.
Records are pruned to 24 hours by TelemetryStore.prune().
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from comms.dcn_packet import DCNPacket

if TYPE_CHECKING:
    from comms.dcn_network import DCNNetwork
    from .store import TelemetryStore

log = logging.getLogger(__name__)


class DCNMessageLogger:
    def __init__(self, store: "TelemetryStore") -> None:
        self._store = store

    def attach(self, network: "DCNNetwork") -> None:
        network.on_packet(self._on_rx)
        network.on_transmit(self._on_tx)

    async def _on_rx(self, packet: DCNPacket, transport_name: str) -> None:
        try:
            await self._store.record_dcn_message(
                direction="rx",
                payload=packet.payload,
                from_addr=packet.from_addr,
                to_addr=packet.to_addr,
                broadcast=packet.broadcast,
                transport=transport_name,
                raw=packet.raw or str(packet),
            )
        except Exception:
            log.exception("DCNMessageLogger: failed to record RX packet")

    async def _on_tx(self, packet: DCNPacket, transport_name: str) -> None:
        try:
            await self._store.record_dcn_message(
                direction="tx",
                payload=packet.payload,
                from_addr=packet.from_addr,
                to_addr=packet.to_addr,
                broadcast=packet.broadcast,
                transport=transport_name,
                raw=packet.raw or str(packet),
            )
        except Exception:
            log.exception("DCNMessageLogger: failed to record TX packet")

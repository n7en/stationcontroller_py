"""
DCN packet definition, builder, and parser.

Packet format (normal):   /FFTT:PAYLOAD:CRC<CR>
Packet format (broadcast): //PAYLOAD:CRC<CR>

  /   - start of packet
  FF  - from address (2 printable chars, typically "00" for master)
  TT  - to address   (2 printable chars)
  :   - delimiter (may not appear in payload)
  CRC - "XX" placeholder (full CRC/LRC not yet implemented in most firmware)
  <CR>- end of packet (ASCII 13)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

CRC_PLACEHOLDER = "XX"
MASTER_ADDR = "00"
END_OF_PACKET = "\r"


@dataclass
class DCNPacket:
    from_addr: str
    to_addr: str
    payload: str
    crc: str = CRC_PLACEHOLDER
    broadcast: bool = False
    raw: str = field(default="", repr=False)

    @property
    def command(self) -> str:
        """First comma-delimited field of the payload, uppercased."""
        return self.payload.split(",")[0].upper()

    @property
    def args(self) -> list[str]:
        """Remaining comma-delimited fields after the command."""
        parts = self.payload.split(",")
        return parts[1:] if len(parts) > 1 else []

    def build(self) -> str:
        if self.broadcast:
            return f"//{self.payload}:{self.crc}{END_OF_PACKET}"
        return f"/{self.from_addr}{self.to_addr}:{self.payload}:{self.crc}{END_OF_PACKET}"

    def encode(self) -> bytes:
        return self.build().encode("ascii")

    def __str__(self) -> str:
        return self.build().rstrip(END_OF_PACKET)


def build_packet(
    to_addr: str,
    payload: str,
    from_addr: str = MASTER_ADDR,
    crc: str = CRC_PLACEHOLDER,
) -> DCNPacket:
    return DCNPacket(from_addr=from_addr, to_addr=to_addr, payload=payload, crc=crc)


def build_broadcast(payload: str, crc: str = CRC_PLACEHOLDER) -> DCNPacket:
    return DCNPacket(from_addr="", to_addr="", payload=payload, crc=crc, broadcast=True)


def parse_packet(raw: str) -> Optional[DCNPacket]:
    """
    Parse a raw DCN packet string into a DCNPacket.
    Returns None if the string is not a valid DCN packet.
    """
    raw = raw.strip()
    if not raw.startswith("/"):
        return None

    if raw.startswith("//"):
        # Broadcast: //PAYLOAD[:CRC]
        content = raw[2:]
        parts = content.split(":")
        payload = parts[0]
        crc = parts[1] if len(parts) > 1 else CRC_PLACEHOLDER
        if not payload:
            return None
        return DCNPacket(
            from_addr="", to_addr="", payload=payload,
            crc=crc, broadcast=True, raw=raw,
        )

    # Normal: /FFTT:PAYLOAD:CRC
    content = raw[1:]
    parts = content.split(":")
    if len(parts) < 2:
        return None
    header = parts[0]
    if len(header) < 4:
        return None
    from_addr = header[:2]
    to_addr = header[2:4]
    payload = parts[1]
    crc = parts[2] if len(parts) > 2 else CRC_PLACEHOLDER
    if not payload:
        return None
    return DCNPacket(
        from_addr=from_addr, to_addr=to_addr,
        payload=payload, crc=crc, raw=raw,
    )

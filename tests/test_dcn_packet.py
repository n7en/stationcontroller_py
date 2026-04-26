"""
Tests for comms/dcn_packet.py — packet parsing, building, and properties.
No I/O or mocking required; all pure logic.
"""
import pytest

from comms.dcn_packet import (
    DCNPacket,
    parse_packet,
    build_packet,
    build_broadcast,
    CRC_PLACEHOLDER,
    MASTER_ADDR,
)


# ---------------------------------------------------------------------------
# parse_packet — valid inputs
# ---------------------------------------------------------------------------

class TestParsePacketValid:

    def test_simple_command(self):
        p = parse_packet("/0001:STATE:XX")
        assert p is not None
        assert p.from_addr == "00"
        assert p.to_addr == "01"
        assert p.payload == "STATE"
        assert p.crc == "XX"
        assert not p.broadcast

    def test_command_with_single_arg(self):
        p = parse_packet("/0001:RY3,1:XX")
        assert p is not None
        assert p.payload == "RY3,1"
        assert p.command == "RY3"
        assert p.args == ["1"]

    def test_command_with_multiple_args(self):
        p = parse_packet("/0001:RY,01000000:XX")
        assert p is not None
        assert p.command == "RY"
        assert p.args == ["01000000"]

    def test_update_packet_from_docs(self):
        # Real-world example from the DCN manual
        raw = "/0100:UPDATE,GPIO1,01000000,0110,12.000,13.700,13.850,4.950,72.00,74.00:XX"
        p = parse_packet(raw)
        assert p is not None
        assert p.from_addr == "01"
        assert p.to_addr == "00"
        assert p.command == "UPDATE"
        assert p.args[0] == "GPIO1"
        assert p.args[1] == "01000000"   # relay states 1-8
        assert p.args[2] == "0110"       # digital inputs 1-4
        assert p.args[3] == "12.000"     # voltmeter 1
        assert p.args[7] == "72.00"      # temp probe 1
        assert p.args[8] == "74.00"      # temp probe 2

    def test_strips_leading_trailing_whitespace(self):
        p = parse_packet("  /0001:STATE:XX  ")
        assert p is not None
        assert p.from_addr == "00"

    def test_strips_trailing_cr(self):
        p = parse_packet("/0001:STATE:XX\r")
        assert p is not None
        assert p.payload == "STATE"

    def test_missing_crc_uses_placeholder(self):
        p = parse_packet("/0001:STATE")
        assert p is not None
        assert p.crc == CRC_PLACEHOLDER

    def test_raw_preserved(self):
        raw = "/0001:STATE:XX"
        p = parse_packet(raw)
        assert p.raw == raw

    def test_non_numeric_addresses(self):
        # Spec allows any printable char as address
        p = parse_packet("/AABB:PING:XX")
        assert p is not None
        assert p.from_addr == "AA"
        assert p.to_addr == "BB"

    def test_broadcast_with_crc(self):
        p = parse_packet("//PING:XX")
        assert p is not None
        assert p.broadcast
        assert p.payload == "PING"
        assert p.crc == "XX"
        assert p.from_addr == ""
        assert p.to_addr == ""

    def test_broadcast_without_crc(self):
        # Many real broadcast examples in docs omit CRC
        p = parse_packet("//REBOOT")
        assert p is not None
        assert p.broadcast
        assert p.payload == "REBOOT"
        assert p.crc == CRC_PLACEHOLDER

    def test_broadcast_with_args(self):
        p = parse_packet("//SETADDR,5:XX")
        assert p is not None
        assert p.broadcast
        assert p.command == "SETADDR"
        assert p.args == ["5"]

    def test_broadcast_with_cr(self):
        p = parse_packet("//PING:XX\r")
        assert p is not None
        assert p.payload == "PING"


# ---------------------------------------------------------------------------
# parse_packet — invalid inputs → should return None
# ---------------------------------------------------------------------------

class TestParsePacketInvalid:

    def test_empty_string(self):
        assert parse_packet("") is None

    def test_no_leading_slash(self):
        assert parse_packet("0001:STATE:XX") is None

    def test_address_too_short(self):
        # Only 3 address chars — need 4
        assert parse_packet("/001:STATE:XX") is None

    def test_no_delimiter(self):
        assert parse_packet("/0001STATE") is None

    def test_empty_payload(self):
        assert parse_packet("/0001::XX") is None

    def test_empty_broadcast_payload(self):
        assert parse_packet("//") is None

    def test_whitespace_only(self):
        assert parse_packet("   ") is None

    def test_random_garbage(self):
        assert parse_packet("hello world") is None


# ---------------------------------------------------------------------------
# build_packet
# ---------------------------------------------------------------------------

class TestBuildPacket:

    def test_default_from_addr_is_master(self):
        p = build_packet("01", "STATE")
        assert p.from_addr == MASTER_ADDR
        assert p.to_addr == "01"

    def test_custom_from_addr(self):
        p = build_packet("01", "STATE", from_addr="05")
        assert p.from_addr == "05"

    def test_payload_preserved(self):
        p = build_packet("01", "RY3,1")
        assert p.payload == "RY3,1"

    def test_crc_default(self):
        p = build_packet("01", "STATE")
        assert p.crc == CRC_PLACEHOLDER

    def test_not_broadcast(self):
        p = build_packet("01", "STATE")
        assert not p.broadcast

    def test_build_string_format(self):
        p = build_packet("01", "STATE")
        assert p.build() == "/0001:STATE:XX\r"

    def test_encode_returns_ascii_bytes(self):
        p = build_packet("01", "STATE")
        assert p.encode() == b"/0001:STATE:XX\r"

    def test_str_has_no_trailing_cr(self):
        p = build_packet("01", "STATE")
        assert str(p) == "/0001:STATE:XX"
        assert not str(p).endswith("\r")


# ---------------------------------------------------------------------------
# build_broadcast
# ---------------------------------------------------------------------------

class TestBuildBroadcast:

    def test_is_broadcast(self):
        p = build_broadcast("PING")
        assert p.broadcast

    def test_build_string_format(self):
        assert build_broadcast("PING").build() == "//PING:XX\r"

    def test_with_args(self):
        p = build_broadcast("SETADDR,5")
        assert p.build() == "//SETADDR,5:XX\r"

    def test_encode_bytes(self):
        assert build_broadcast("PING").encode() == b"//PING:XX\r"


# ---------------------------------------------------------------------------
# DCNPacket properties
# ---------------------------------------------------------------------------

class TestDCNPacketProperties:

    def test_command_uppercased(self):
        p = DCNPacket("00", "01", "state")
        assert p.command == "STATE"

    def test_command_already_upper(self):
        p = DCNPacket("00", "01", "STATE")
        assert p.command == "STATE"

    def test_args_empty_for_command_only_payload(self):
        p = DCNPacket("00", "01", "STATE")
        assert p.args == []

    def test_args_single(self):
        p = DCNPacket("00", "01", "RY1,1")
        assert p.args == ["1"]

    def test_args_multiple(self):
        p = DCNPacket("00", "01", "UPDATE,GPIO1,01000000")
        assert p.args == ["GPIO1", "01000000"]

    def test_str_is_packet_without_cr(self):
        p = build_packet("01", "STATE")
        s = str(p)
        assert s == "/0001:STATE:XX"
        assert "\r" not in s


# ---------------------------------------------------------------------------
# Round-trip: parse then build should reproduce the original string
# ---------------------------------------------------------------------------

class TestRoundTrip:

    @pytest.mark.parametrize("raw", [
        "/0001:STATE:XX",
        "/0001:RY3,1:XX",
        "/0001:RY,01000000:XX",
        "/0100:UPDATE,GPIO1,01000000,0110,12.000,13.700,13.850,4.950,72.00,74.00:XX",
        "//PING:XX",
        "//SETADDR,5:XX",
        "//REBOOT:XX",
    ])
    def test_round_trip(self, raw):
        packet = parse_packet(raw)
        assert packet is not None, f"Failed to parse: {raw!r}"
        assert str(packet) == raw

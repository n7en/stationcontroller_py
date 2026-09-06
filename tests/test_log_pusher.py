"""
Tests for tools/log_pusher.py - the standalone remote log pusher.
"""
from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from tools.log_pusher import (
    Pusher,
    StationClient,
    _N1MMProtocol,
    dedupe_key,
    parse_n1mm_contact,
    parse_n3fjp_qso,
)


def _n1mm_xml(**overrides) -> bytes:
    fields = {
        "call": "JA1XYZ", "rxfreq": "1420050", "mode": "USB",
        "mycall": "N7EN", "countryprefix": "JA", "continent": "AS",
        "cqzone": "25", "ituzone": "45", "dupe": "0",
        "timestamp": "2026-07-04 18:22:33",
    }
    fields.update(overrides)
    inner = "".join(f"<{k}>{v}</{k}>" for k, v in fields.items())
    return f"<ContactInfo>{inner}</ContactInfo>".encode()


class TestParseN1MM:

    def test_full_payload(self):
        p = parse_n1mm_contact(_n1mm_xml(), source="shack")
        assert p["callsign"] == "JA1XYZ"
        assert p["frequency_hz"] == pytest.approx(14_200_500.0)
        assert p["mode"] == "USB"
        assert p["my_callsign"] == "N7EN"
        assert p["country"] == "JA"
        assert p["continent"] == "AS"
        assert p["cq_zone"] == 25
        assert p["itu_zone"] == 45
        assert p["source"] == "shack"
        assert "timestamp" in p
        assert "band" not in p          # server derives band from frequency
        assert "dupe" not in p          # only sent when true

    def test_dupe_flag(self):
        p = parse_n1mm_contact(_n1mm_xml(dupe="1"), source="s")
        assert p["dupe"] is True

    def test_rejects_non_contactinfo(self):
        assert parse_n1mm_contact(b"<RadioInfo/>", "s") is None
        assert parse_n1mm_contact(b"garbage", "s") is None
        assert parse_n1mm_contact(_n1mm_xml(call=""), "s") is None

    def test_bad_optional_fields_tolerated(self):
        p = parse_n1mm_contact(
            _n1mm_xml(rxfreq="xx", cqzone="yy", timestamp="zz"), source="s")
        assert p["callsign"] == "JA1XYZ"
        assert "frequency_hz" not in p
        assert "cq_zone" not in p
        assert "timestamp" not in p


class TestParseN3FJP:

    def test_full_payload(self):
        el = ET.fromstring(
            "<QSOData><Call>VE3ABC</Call><Freq>14025.5</Freq><Mode>CW</Mode>"
            "<MyCall>N7EN</MyCall><Country>Canada</Country>"
            "<Date>2026/07/01</Date><TimeOn>14:22</TimeOn></QSOData>")
        p = parse_n3fjp_qso(el, source="shack")
        assert p["callsign"] == "VE3ABC"
        assert p["frequency_hz"] == pytest.approx(14_025_500.0)
        assert p["mode"] == "CW"
        assert p["country"] == "Canada"
        assert "timestamp" in p

    def test_missing_call(self):
        assert parse_n3fjp_qso(ET.fromstring("<QSOData/>"), "s") is None


class TestDedupe:

    def test_protocol_suppresses_duplicate_broadcasts(self):
        pusher = MagicMock()
        proto = _N1MMProtocol(pusher, source="s")
        proto.datagram_received(_n1mm_xml(), ("127.0.0.1", 1))
        proto.datagram_received(_n1mm_xml(), ("127.0.0.1", 2))  # rebroadcast
        assert pusher.enqueue.call_count == 1

    def test_different_qsos_pass(self):
        pusher = MagicMock()
        proto = _N1MMProtocol(pusher, source="s")
        proto.datagram_received(_n1mm_xml(), ("", 1))
        proto.datagram_received(_n1mm_xml(call="W1AW"), ("", 1))
        assert pusher.enqueue.call_count == 2


class TestPusher:

    async def test_pushes_queued_payloads(self):
        client = MagicMock()
        client.push = MagicMock(return_value=True)
        pusher = Pusher(client)
        pusher.enqueue({"callsign": "K1AAA"})
        pusher.enqueue({"callsign": "K2BBB"})

        task = asyncio.create_task(pusher.run())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        client.push.assert_called_once_with(
            [{"callsign": "K1AAA"}, {"callsign": "K2BBB"}])

    async def test_requeues_on_failure_preserving_order(self):
        client = MagicMock()
        client.push = MagicMock(side_effect=[False, True])
        pusher = Pusher(client)
        pusher.enqueue({"callsign": "K1AAA"})
        pusher.enqueue({"callsign": "K2BBB"})

        with patch("tools.log_pusher.RETRY_MIN_S", 0.01):
            task = asyncio.create_task(pusher.run())
            await asyncio.sleep(0.2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert client.push.call_count == 2
        # Second attempt must resend the same batch in the same order
        assert client.push.call_args_list[1].args[0] == [
            {"callsign": "K1AAA"}, {"callsign": "K2BBB"}]


class TestStationClient:

    def test_single_vs_batch_endpoint(self):
        client = StationClient("https://x")
        with patch.object(client, "_post", return_value=(200, {})) as post:
            client.push([{"callsign": "K1AAA"}])
            assert post.call_args.args[0] == "/api/logbook/qso"
            client.push([{"callsign": "K1AAA"}, {"callsign": "K2BBB"}])
            assert post.call_args.args[0] == "/api/logbook/qsos"

    def test_relogin_on_401(self):
        client = StationClient("https://x", username="admin", password="pw")
        responses = [(401, {}), (200, {}), (200, {})]
        with patch.object(client, "_post", side_effect=responses) as post:
            ok = client.push([{"callsign": "K1AAA"}])
        assert ok is True
        # push -> 401, login -> 200, retry push -> 200
        assert [c.args[0] for c in post.call_args_list] == [
            "/api/logbook/qso", "/api/auth/login", "/api/logbook/qso"]

    def test_failure_without_auth_returns_false(self):
        client = StationClient("https://x")
        with patch.object(client, "_post", return_value=(503, {"detail": "down"})):
            assert client.push([{"callsign": "K1AAA"}]) is False

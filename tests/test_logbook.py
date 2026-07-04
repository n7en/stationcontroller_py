"""
Tests for logging_integration/ - N1MM+ listener, N3FJP poller, LogbookManager.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock

import pytest

from logging_integration.log_state import QSORecord, band_for_freq_hz
from logging_integration.manager import LogbookManager
from logging_integration.n1mm import N1MMListener, _N1MMProtocol, _parse_contact
from logging_integration.n3fjp import N3FJPPoller, _parse_qso_element, _parse_timestamp


# ---------------------------------------------------------------------------
# band_for_freq_hz
# ---------------------------------------------------------------------------

class TestBandForFreq:

    def test_common_bands(self):
        assert band_for_freq_hz(14_200_500) == "20m"
        assert band_for_freq_hz(7_150_000) == "40m"
        assert band_for_freq_hz(3_800_000) == "80m"
        assert band_for_freq_hz(146_520_000) == "2m"

    def test_out_of_band_returns_none(self):
        assert band_for_freq_hz(13_000_000) is None

    def test_none_and_zero(self):
        assert band_for_freq_hz(None) is None
        assert band_for_freq_hz(0) is None


# ---------------------------------------------------------------------------
# N1MM+ ContactInfo parsing
# ---------------------------------------------------------------------------

def _n1mm_xml(**overrides) -> str:
    fields = {
        "call": "JA1XYZ", "band": "14", "rxfreq": "1420050", "mode": "USB",
        "mycall": "N7EN", "countryprefix": "JA", "continent": "AS",
        "cqzone": "25", "ituzone": "45", "dupe": "0",
    }
    fields.update(overrides)
    inner = "".join(f"<{k}>{v}</{k}>" for k, v in fields.items())
    return f"<ContactInfo>{inner}</ContactInfo>"


class TestN1MMParse:

    def test_full_contact(self):
        rec = _parse_contact(ET.fromstring(_n1mm_xml()))
        assert rec is not None
        assert rec.callsign == "JA1XYZ"
        assert rec.frequency_hz == pytest.approx(14_200_500.0)  # rxfreq x10
        assert rec.band == "20m"
        assert rec.mode == "USB"
        assert rec.my_callsign == "N7EN"
        assert rec.country == "JA"
        assert rec.continent == "AS"
        assert rec.cq_zone == 25
        assert rec.itu_zone == 45
        assert rec.dupe is False
        assert rec.source == "n1mm"

    def test_band_derived_from_frequency_beats_band_string(self):
        # Ambiguous band string "10" (30m in MHz, 10m in meters) - the
        # frequency decides: 10.12 MHz is 30m.
        rec = _parse_contact(ET.fromstring(_n1mm_xml(band="10", rxfreq="1012000")))
        assert rec.band == "30m"

    def test_mhz_band_string_without_frequency(self):
        rec = _parse_contact(ET.fromstring(_n1mm_xml(band="3.5", rxfreq="")))
        assert rec.band == "80m"

    def test_meters_band_string_without_frequency(self):
        rec = _parse_contact(ET.fromstring(_n1mm_xml(band="40", rxfreq="")))
        assert rec.band == "40m"

    def test_dupe_flag(self):
        rec = _parse_contact(ET.fromstring(_n1mm_xml(dupe="1")))
        assert rec.dupe is True

    def test_missing_call_returns_none(self):
        assert _parse_contact(ET.fromstring(_n1mm_xml(call=""))) is None

    def test_bad_zone_values_tolerated(self):
        rec = _parse_contact(ET.fromstring(_n1mm_xml(cqzone="xx", ituzone="")))
        assert rec.cq_zone is None
        assert rec.itu_zone is None


class TestN1MMProtocol:

    def test_datagram_fires_callback(self):
        received = []
        proto = _N1MMProtocol([received.append])
        proto.datagram_received(_n1mm_xml().encode(), ("127.0.0.1", 12060))
        assert len(received) == 1
        assert received[0].callsign == "JA1XYZ"

    def test_non_contactinfo_ignored(self):
        received = []
        proto = _N1MMProtocol([received.append])
        proto.datagram_received(b"<RadioInfo><Freq>14200</Freq></RadioInfo>", ("", 0))
        assert received == []

    def test_invalid_xml_ignored(self):
        received = []
        proto = _N1MMProtocol([received.append])
        proto.datagram_received(b"not xml at all", ("", 0))
        assert received == []

    def test_callback_exception_does_not_break_others(self):
        received = []

        def _bad(_rec):
            raise RuntimeError("boom")

        proto = _N1MMProtocol([_bad, received.append])
        proto.datagram_received(_n1mm_xml().encode(), ("", 0))
        assert len(received) == 1


class TestN1MMListener:

    async def test_start_stop_and_status(self):
        listener = N1MMListener(host="127.0.0.1", port=0)
        assert listener.connected is False
        await listener.start()
        assert listener.connected is True
        st = listener.status()
        assert st["backend"] == "n1mm"
        assert st["connected"] is True
        await listener.stop()
        assert listener.connected is False


# ---------------------------------------------------------------------------
# N3FJP parsing
# ---------------------------------------------------------------------------

def _n3fjp_xml(**overrides) -> str:
    fields = {
        "Call": "VE3ABC", "Band": "20M", "Mode": "CW", "Freq": "14025.5",
        "MyCall": "N7EN", "Country": "Canada",
    }
    fields.update(overrides)
    inner = "".join(f"<{k}>{v}</{k}>" for k, v in fields.items())
    return f"<QSOData>{inner}</QSOData>"


class TestN3FJPParse:

    def test_full_qso(self):
        rec = _parse_qso_element(ET.fromstring(_n3fjp_xml()))
        assert rec is not None
        assert rec.callsign == "VE3ABC"
        assert rec.band == "20m"
        assert rec.mode == "CW"
        assert rec.frequency_hz == pytest.approx(14_025_500.0)  # kHz -> Hz
        assert rec.my_callsign == "N7EN"
        assert rec.country == "Canada"
        assert rec.source == "n3fjp"

    def test_band_derived_from_frequency_when_band_missing(self):
        rec = _parse_qso_element(ET.fromstring(_n3fjp_xml(Band="", Freq="7040")))
        assert rec.band == "40m"

    def test_fld_prefixed_tags(self):
        xml = ("<QSOData><fldCall>W1AW</fldCall><fldBand>40M</fldBand>"
               "<fldMode>SSB</fldMode></QSOData>")
        rec = _parse_qso_element(ET.fromstring(xml))
        assert rec.callsign == "W1AW"
        assert rec.band == "40m"
        assert rec.mode == "SSB"

    def test_missing_call_returns_none(self):
        assert _parse_qso_element(ET.fromstring("<QSOData><Band>20M</Band></QSOData>")) is None

    def test_timestamp_from_date_fields(self):
        rec = _parse_qso_element(ET.fromstring(
            _n3fjp_xml(Date="2026/07/01", TimeOn="14:22")
        ))
        import datetime as _dt
        expected = _dt.datetime(2026, 7, 1, 14, 22).timestamp()
        assert rec.timestamp == pytest.approx(expected)


class TestN3FJPTimestamp:

    def test_formats(self):
        assert _parse_timestamp("2026/07/01", "14:22") is not None
        assert _parse_timestamp("2026-07-01", "14:22:33") is not None
        assert _parse_timestamp("2026/07/01", "") is not None
        assert _parse_timestamp("", "14:22") is None
        assert _parse_timestamp("garbage", "date") is None


class TestN3FJPLoadAll:

    async def test_load_all_feeds_callbacks(self):
        """Existing QSOs from GetAllQSOData must reach the manager."""
        poller = N3FJPPoller()
        received = []
        poller.on_qso(received.append)

        response = (
            "<response>"
            + _n3fjp_xml(Call="K1AAA")
            + _n3fjp_xml(Call="K2BBB", Band="40M", Freq="7040")
            + _n3fjp_xml(Call="K1AAA")   # duplicate - must not double-fire
            + "</response>"
        ).encode()

        reader = MagicMock()
        reader.read = AsyncMock(side_effect=[response, b""])
        writer = MagicMock()
        writer.drain = AsyncMock()

        await poller._load_all(reader, writer)

        assert [r.callsign for r in received] == ["K1AAA", "K2BBB"]
        writer.write.assert_called_once_with(b"<cmd>GetAllQSOData</cmd>\r\n")

    async def test_poll_current_only_fires_new(self):
        poller = N3FJPPoller()
        received = []
        poller.on_qso(received.append)

        response = ("<response>" + _n3fjp_xml() + "</response>").encode()
        reader = MagicMock()
        reader.read = AsyncMock(side_effect=[response, b"", response, b""])
        writer = MagicMock()
        writer.drain = AsyncMock()

        await poller._poll_current(reader, writer)
        assert len(received) == 1
        # Same QSO polled again - deduplicated
        await poller._poll_current(reader, writer)
        assert len(received) == 1


# ---------------------------------------------------------------------------
# LogbookManager
# ---------------------------------------------------------------------------

class TestLogbookManager:

    def _mgr_with(self, *records: QSORecord) -> LogbookManager:
        mgr = LogbookManager()
        for r in records:
            mgr._on_qso(r)
        return mgr

    def test_worked_case_insensitive(self):
        mgr = self._mgr_with(QSORecord(callsign="ja1xyz", band="20m", mode="CW"))
        assert mgr.worked("JA1XYZ") is True
        assert mgr.worked("W1AW") is False

    def test_worked_on_band(self):
        mgr = self._mgr_with(QSORecord(callsign="JA1XYZ", band="20m", mode="CW"))
        assert mgr.worked_on_band("JA1XYZ", "20m") is True
        assert mgr.worked_on_band("JA1XYZ", "40m") is False

    def test_worked_on_band_mode(self):
        mgr = self._mgr_with(QSORecord(callsign="JA1XYZ", band="20m", mode="CW"))
        assert mgr.worked_on_band_mode("JA1XYZ", "20m", "CW") is True
        assert mgr.worked_on_band_mode("JA1XYZ", "20m", "SSB") is False

    def test_contacts_newest_first_with_limit(self):
        mgr = self._mgr_with(
            QSORecord(callsign="K1AAA"),
            QSORecord(callsign="K2BBB"),
            QSORecord(callsign="K3CCC"),
        )
        recent = mgr.contacts(limit=2)
        assert [r.callsign for r in recent] == ["K3CCC", "K2BBB"]
        assert mgr.total_contacts == 3

    def test_from_config_disabled_backends(self):
        mgr = LogbookManager.from_config({"n1mm": {"enabled": False},
                                          "n3fjp": {"enabled": False}})
        assert mgr.enabled is False
        assert mgr.backend_status() == []

    def test_from_config_enabled_backends(self):
        mgr = LogbookManager.from_config({
            "n1mm":  {"enabled": True, "port": 12060},
            "n3fjp": {"enabled": True, "host": "localhost", "port": 1100},
        })
        assert mgr.enabled is True
        status = mgr.backend_status()
        assert [s["backend"] for s in status] == ["n1mm", "n3fjp"]
        assert all(s["connected"] is False for s in status)

    def test_add_qso_normalises_and_indexes(self):
        mgr = LogbookManager()
        rec = mgr.add_qso(QSORecord(callsign=" ja1xyz ", band="20M", mode="CW"))
        assert rec.callsign == "JA1XYZ"
        assert rec.band == "20m"
        assert mgr.worked("JA1XYZ") is True
        assert mgr.worked_on_band("JA1XYZ", "20m") is True

    def test_add_qso_derives_band_from_frequency(self):
        mgr = LogbookManager()
        rec = mgr.add_qso(QSORecord(callsign="W1AW", frequency_hz=7_074_000))
        assert rec.band == "40m"


# ---------------------------------------------------------------------------
# REST API - POST /api/logbook/qso(s)
# ---------------------------------------------------------------------------

class TestLogbookApi:

    @pytest.fixture
    async def client(self):
        from httpx import ASGITransport, AsyncClient
        from api.app import create_app
        from api.deps import AppState, _state

        fresh = AppState()
        for attr in vars(fresh):
            setattr(_state, attr, getattr(fresh, attr))

        s = AppState()
        s.logbook_manager = LogbookManager()
        app = create_app(s)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    async def test_post_single_qso(self, client):
        r = await client.post("/api/logbook/qso", json={
            "callsign": "ja1xyz", "frequency_hz": 14_025_000,
            "mode": "CW", "source": "remote_ft8",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["callsign"] == "JA1XYZ"
        assert d["band"] == "20m"
        assert d["total_contacts"] == 1

        r2 = await client.get("/api/logbook/worked", params={"call": "JA1XYZ", "band": "20m"})
        assert r2.json()["worked"] is True
        assert r2.json()["worked_on_band"] is True

        r3 = await client.get("/api/logbook/contacts")
        contacts = r3.json()["contacts"]
        assert len(contacts) == 1
        assert contacts[0]["source"] == "remote_ft8"

    async def test_post_batch(self, client):
        batch = [
            {"callsign": "K1AAA", "band": "20m", "mode": "SSB"},
            {"callsign": "K2BBB", "frequency_hz": 7_040_000, "mode": "CW"},
        ]
        r = await client.post("/api/logbook/qsos", json=batch)
        assert r.status_code == 200
        assert r.json()["added"] == 2
        assert r.json()["total_contacts"] == 2

    async def test_post_empty_callsign_rejected(self, client):
        r = await client.post("/api/logbook/qso", json={"callsign": ""})
        assert r.status_code == 422

    async def test_status_reports_api_fed_contacts(self, client):
        await client.post("/api/logbook/qso", json={"callsign": "K1AAA"})
        r = await client.get("/api/logbook/status")
        d = r.json()
        # No listener backends configured, but the count must be real
        assert d["enabled"] is False
        assert d["total_contacts"] == 1

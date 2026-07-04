#!/usr/bin/env python3
"""
StationController remote log pusher.

Runs on the machine where your logging software lives (e.g. the shack PC
running N1MM+ or N3FJP) and forwards logged QSOs to a StationController
instance over HTTPS using POST /api/logbook/qso(s).

Use this when the logging PC and StationController are on different
machines/subnets where N1MM+ UDP broadcasts or the N3FJP TCP port cannot
reach StationController directly - outbound HTTPS is all that is needed.

Standalone by design: one file, Python 3.9+ standard library only.
Copy it anywhere and run it - no repo checkout or pip installs required.

Sources:
  N1MM+  - listens for ContactInfo UDP broadcasts on this machine.
           N1MM+: Config -> Configure Ports... -> Broadcast Data tab ->
           enable "Contacts", target 127.0.0.1:12060 (default).
  N3FJP  - polls the local N3FJP TCP API (Settings -> Application Program
           Interface -> enable, default port 1100).  The full local log is
           batch-synced to StationController on startup/reconnect.

Usage:
    python log_pusher.py --server https://station.local:8080
    python log_pusher.py --server https://192.168.1.50:8080 \\
        --username admin --password secret \\
        --n3fjp-host localhost --source shack_pc

Notes:
  - StationController generates a self-signed TLS certificate, so
    certificate verification is OFF by default; pass --verify if you have
    installed a real certificate.
  - QSOs are queued in memory and retried with backoff while the server is
    unreachable (queue capped at 10,000 - oldest dropped first).
"""
from __future__ import annotations

import argparse
import asyncio
import http.cookiejar
import json
import logging
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime
from typing import Optional

log = logging.getLogger("log_pusher")

QUEUE_MAX     = 10_000
BATCH_MAX     = 500     # max QSOs per /qsos request
RETRY_MIN_S   = 5.0
RETRY_MAX_S   = 60.0


# ---------------------------------------------------------------------------
# QSO parsing - N1MM+ ContactInfo
# ---------------------------------------------------------------------------

def parse_n1mm_contact(data: bytes, source: str) -> Optional[dict]:
    """Parse an N1MM+ ContactInfo UDP datagram into a /api/logbook/qso payload.

    Band is intentionally omitted - StationController derives it from the
    frequency, which avoids the ambiguity of N1MM's band strings.
    """
    try:
        root = ET.fromstring(data.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return None
    if root.tag != "ContactInfo":
        return None

    def _t(tag: str) -> str:
        el = root.find(tag)
        return (el.text or "").strip() if el is not None else ""

    callsign = _t("call")
    if not callsign:
        return None

    payload: dict = {"callsign": callsign, "source": source}

    raw_freq = _t("rxfreq")           # N1MM+ sends 10 Hz units
    if raw_freq:
        try:
            payload["frequency_hz"] = float(raw_freq) * 10.0
        except ValueError:
            pass

    ts = _parse_n1mm_timestamp(_t("timestamp"))
    if ts is not None:
        payload["timestamp"] = ts

    for key, tag in (("mode", "mode"), ("my_callsign", "mycall"),
                     ("country", "countryprefix"), ("continent", "continent")):
        val = _t(tag)
        if val:
            payload[key] = val
    for key, tag in (("cq_zone", "cqzone"), ("itu_zone", "ituzone")):
        val = _t(tag)
        if val:
            try:
                payload[key] = int(val)
            except ValueError:
                pass
    if _t("dupe") == "1":
        payload["dupe"] = True
    return payload


def _parse_n1mm_timestamp(raw: str) -> Optional[float]:
    """N1MM+ timestamps are local PC time, "YYYY-MM-DD HH:MM:SS"."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).timestamp()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# QSO parsing - N3FJP QSOData
# ---------------------------------------------------------------------------

def parse_n3fjp_qso(el: ET.Element, source: str) -> Optional[dict]:
    """Parse one N3FJP QSOData/CurrentQSOData element into a payload dict."""
    def _t(*tags: str) -> str:
        for tag in tags:
            child = el.find(tag)
            if child is not None and child.text and child.text.strip():
                return child.text.strip()
        return ""

    callsign = _t("Call", "call", "fldCall")
    if not callsign:
        return None

    payload: dict = {"callsign": callsign, "source": source}

    raw_freq = _t("Freq", "RxFreq", "freq", "fldFreq")   # kHz
    if raw_freq:
        try:
            payload["frequency_hz"] = float(raw_freq) * 1000.0
        except ValueError:
            pass

    mode = _t("Mode", "mode", "fldMode")
    if mode:
        payload["mode"] = mode
    mycall = _t("MyCall", "mycall")
    if mycall:
        payload["my_callsign"] = mycall
    country = _t("Country", "country", "fldCountryWorked")
    if country:
        payload["country"] = country

    date_s = _t("Date", "date", "fldDateStr")
    time_s = _t("TimeOn", "timeon", "fldTimeOnStr")
    if date_s:
        for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M", "%Y/%m/%d", "%Y-%m-%d"):
            try:
                payload["timestamp"] = datetime.strptime(
                    f"{date_s} {time_s}".strip(), fmt).timestamp()
                break
            except ValueError:
                continue
    return payload


def dedupe_key(payload: dict) -> tuple:
    return (
        payload.get("callsign", "").upper(),
        payload.get("frequency_hz"),
        payload.get("mode"),
        payload.get("timestamp"),
    )


# ---------------------------------------------------------------------------
# StationController HTTP client (urllib, blocking - called via to_thread)
# ---------------------------------------------------------------------------

class StationClient:
    def __init__(self, server: str, username: str = "", password: str = "",
                 verify_tls: bool = False) -> None:
        self.server   = server.rstrip("/")
        self.username = username
        self.password = password

        ctx = ssl.create_default_context()
        if not verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )

    def _post(self, path: str, body) -> tuple[int, dict]:
        req = urllib.request.Request(
            f"{self.server}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode() or "{}")
            except Exception:
                detail = {}
            return e.code, detail

    def login(self) -> bool:
        if not self.username:
            return True
        status, _ = self._post("/api/auth/login",
                               {"username": self.username, "password": self.password})
        if status == 200:
            log.info("Logged in to %s as %s", self.server, self.username)
            return True
        log.error("Login failed (HTTP %d)", status)
        return False

    def push(self, payloads: list[dict]) -> bool:
        """Send one or more QSOs; True on success. Re-logins once on 401."""
        path, body = ("/api/logbook/qso", payloads[0]) if len(payloads) == 1 \
            else ("/api/logbook/qsos", payloads)
        status, detail = self._post(path, body)
        if status == 401 and self.username:
            if self.login():
                status, detail = self._post(path, body)
        if status == 200:
            return True
        log.warning("Push failed: HTTP %d %s", status, detail.get("detail", ""))
        return False


# ---------------------------------------------------------------------------
# Pusher - queue + retry loop
# ---------------------------------------------------------------------------

class Pusher:
    def __init__(self, client: StationClient) -> None:
        self._client = client
        self._queue: deque[dict] = deque(maxlen=QUEUE_MAX)
        self._event = asyncio.Event()
        self._pushed = 0

    def enqueue(self, payload: dict) -> None:
        self._queue.append(payload)
        self._event.set()

    def enqueue_batch(self, payloads: list[dict]) -> None:
        self._queue.extend(payloads)
        self._event.set()

    async def run(self) -> None:
        backoff = RETRY_MIN_S
        while True:
            await self._event.wait()
            self._event.clear()
            while self._queue:
                batch = [self._queue.popleft()
                         for _ in range(min(len(self._queue), BATCH_MAX))]
                ok = await asyncio.to_thread(self._client.push, batch)
                if ok:
                    self._pushed += len(batch)
                    backoff = RETRY_MIN_S
                    log.info("Pushed %d QSO(s)  (%d total this session)",
                             len(batch), self._pushed)
                else:
                    # Put the batch back in order and retry later
                    self._queue.extendleft(reversed(batch))
                    log.info("Server unreachable - %d queued, retrying in %.0fs",
                             len(self._queue), backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, RETRY_MAX_S)
                    self._event.set()
                    break


# ---------------------------------------------------------------------------
# N1MM+ UDP source
# ---------------------------------------------------------------------------

class _N1MMProtocol(asyncio.DatagramProtocol):
    def __init__(self, pusher: Pusher, source: str) -> None:
        self._pusher = pusher
        self._source = source
        self._seen: deque[tuple] = deque(maxlen=200)

    def datagram_received(self, data: bytes, addr) -> None:
        payload = parse_n1mm_contact(data, self._source)
        if payload is None:
            return
        key = dedupe_key(payload)
        if key in self._seen:     # N1MM+ can broadcast to multiple targets
            return
        self._seen.append(key)
        log.info("N1MM+ QSO: %s %s", payload["callsign"], payload.get("mode", ""))
        self._pusher.enqueue(payload)


async def run_n1mm(pusher: Pusher, host: str, port: int, source: str) -> None:
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(
        lambda: _N1MMProtocol(pusher, source),
        local_addr=(host, port),
    )
    log.info("Listening for N1MM+ broadcasts on UDP %s:%d", host, port)


# ---------------------------------------------------------------------------
# N3FJP TCP source
# ---------------------------------------------------------------------------

async def run_n3fjp(pusher: Pusher, host: str, port: int,
                    poll_s: float, source: str) -> None:
    seen: set[tuple] = set()
    while True:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=10.0)
            log.info("N3FJP connected at %s:%d", host, port)
            try:
                # Initial full-log sync
                batch = await _n3fjp_query(reader, writer, "GetAllQSOData",
                                           seen, source)
                if batch:
                    log.info("N3FJP: syncing %d existing QSOs", len(batch))
                    pusher.enqueue_batch(batch)
                # Poll for new contacts
                while True:
                    await asyncio.sleep(poll_s)
                    for payload in await _n3fjp_query(
                            reader, writer, "GetCurrentQSOData", seen, source):
                        log.info("N3FJP QSO: %s %s",
                                 payload["callsign"], payload.get("mode", ""))
                        pusher.enqueue(payload)
            finally:
                writer.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("N3FJP connection lost (%s) - retrying in 15s", exc)
        await asyncio.sleep(15.0)


async def _n3fjp_query(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                       cmd: str, seen: set, source: str) -> list[dict]:
    writer.write(f"<cmd>{cmd}</cmd>\r\n".encode())
    await writer.drain()
    buf = b""
    try:
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=5.0)
            if not chunk:
                break
            buf += chunk
            if b"</response>" in buf:
                break
    except asyncio.TimeoutError:
        pass
    if not buf:
        return []
    try:
        root = ET.fromstring(buf.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return []
    out: list[dict] = []
    for el in root.iter():
        if el.tag in ("QSOData", "CurrentQSOData"):
            payload = parse_n3fjp_qso(el, source)
            if payload:
                key = dedupe_key(payload)
                if key not in seen:
                    seen.add(key)
                    out.append(payload)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Forward QSOs from local logging software to StationController.")
    p.add_argument("--server", required=True,
                   help="StationController base URL, e.g. https://192.168.1.50:8080")
    p.add_argument("--source", default=socket.gethostname().lower(),
                   help="Source name recorded with each QSO (default: hostname)")
    p.add_argument("--username", default="", help="StationController username (if auth enabled)")
    p.add_argument("--password", default="", help="StationController password")
    p.add_argument("--verify", action="store_true",
                   help="Verify the server TLS certificate (off by default - "
                        "StationController uses a self-signed cert)")
    p.add_argument("--no-n1mm", action="store_true", help="Disable the N1MM+ UDP listener")
    p.add_argument("--n1mm-host", default="0.0.0.0", help="N1MM+ listen interface")
    p.add_argument("--n1mm-port", type=int, default=12060, help="N1MM+ UDP port")
    p.add_argument("--n3fjp-host", default="",
                   help="Enable N3FJP polling by giving its host (e.g. localhost)")
    p.add_argument("--n3fjp-port", type=int, default=1100, help="N3FJP TCP API port")
    p.add_argument("--n3fjp-poll", type=float, default=5.0, help="N3FJP poll interval (s)")
    return p


async def amain(args: argparse.Namespace) -> None:
    client = StationClient(args.server, args.username, args.password,
                           verify_tls=args.verify)
    if args.username and not await asyncio.to_thread(client.login):
        sys.exit(1)

    pusher = Pusher(client)
    tasks = [asyncio.create_task(pusher.run(), name="pusher")]

    if not args.no_n1mm:
        await run_n1mm(pusher, args.n1mm_host, args.n1mm_port, args.source)
    if args.n3fjp_host:
        tasks.append(asyncio.create_task(
            run_n3fjp(pusher, args.n3fjp_host, args.n3fjp_port,
                      args.n3fjp_poll, args.source),
            name="n3fjp",
        ))
    if args.no_n1mm and not args.n3fjp_host:
        log.error("All sources disabled - enable N1MM+ or pass --n3fjp-host")
        sys.exit(1)

    log.info("Forwarding QSOs to %s (source=%s)", args.server, args.source)
    await asyncio.gather(*tasks)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    args = build_arg_parser().parse_args()
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()

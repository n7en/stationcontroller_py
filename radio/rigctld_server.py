"""
radio/rigctld_server.py — rigctld-compatible TCP server (Hamlib network protocol).

Exposes a RadioInterface as a rigctld daemon so any Hamlib-compatible
application (WSJT-X, JS8Call, Winlink, fldigi, flrig, etc.) can connect and
control the radio using its existing rigctld support — no separate rigctld
process required.

Protocol: Hamlib network rig-control protocol over TCP (newline-delimited).
VFO mode: CHKVFO 0 (VFO not included in commands — maximum app compatibility).
Default port: 4532 (same as stock rigctld).

Implemented commands
--------------------
  f / get_freq             get current VFO-A frequency (Hz)
  F / set_freq <hz>        set VFO-A frequency
  m / get_mode             get mode + passband (Hz)
  M / set_mode <mode> <bw> set mode and optional passband
  v / get_vfo              get active VFO name
  V / set_vfo <vfo>        set active VFO
  t / get_ptt              get PTT state (0/1)
  T / set_ptt <0|1>        key / unkey PTT
  s / get_split_vfo        get split state + TX VFO
  S / set_split_vfo <s> <v> enable/disable split
  i / get_split_freq       get TX (VFO-B) frequency
  I / set_split_freq <hz>  set TX frequency (enables split)
  l / get_level <name>     get RFPOWER (0-1) or STRENGTH (dBm)
  L / set_level <name> <v> set RFPOWER level
  _ / get_info             get radio model/info string
  1 / dump_caps            capability report for client auto-detection
  chk_vfo                  report CHKVFO 0 (no VFO in commands)
  q / Q / quit             close connection

Config (radio_config.yaml):
    rigctld_server:
      enabled: true
      host: "0.0.0.0"   # listen interface
      port: 4532         # TCP port (default = same as stock rigctld)
      radio: "radio"     # radio name to expose (defaults to first configured)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)

RPRT_OK   = "RPRT 0\n"
RPRT_ERR  = "RPRT -1\n"    # generic error
RPRT_ENAV = "RPRT -11\n"   # command not available / not implemented

# Minimum dump_caps that lets WSJT-X, JS8Call, fldigi etc. auto-detect capabilities.
_DUMP_CAPS = """\
Caps dump for model:\t1
Model name:\tStationController
Mfg name:\tStationController
Backend version:\t0.1
Backend copyright:\tLGPL
Backend status:\tAlpha
Rig type:\tTransceiver
PTT type:\tRig CAT
DCD type:\tNone
Port type:\tNetwork
Write delay:\t0ms
Post write delay:\t0ms
Has targetable VFO:\tN
Has transceive:\tN
Frequency range 1 for VFO(s) VFOA:
\t1 Hz - 2000000000 Hz
Mode list:\tAM CW CWR USB LSB RTTY RTTYR FM WFM PKTUSB PKTLSB
VFO list:\tVFOA VFOB
VFO ops:\tTOGGLE
Scan ops:\tNONE
Number of channels:\t0
Max RIT:\t0 Hz
Max XIT:\t0 Hz
Max IF-SHIFT:\t0 Hz
Preamp step:\tNone
Attenuator step:\tNone
Tuning steps:\tAny/1 Hz
Can set Conf:\tN
Can get Conf:\tN
Can set Freq:\tY
Can get Freq:\tY
Can set Mode:\tY
Can get Mode:\tY
Can set VFO:\tY
Can get VFO:\tY
Can set PTT:\tY
Can get PTT:\tY
Can get DCD:\tN
Can set Rptr Shift:\tN
Can get Rptr Shift:\tN
Can set Rptr Offs:\tN
Can get Rptr Offs:\tN
Can set Split Freq:\tY
Can get Split Freq:\tY
Can set Split Mode:\tN
Can get Split Mode:\tN
Can set Split VFO:\tY
Can get Split VFO:\tY
Can set Tuning Step:\tN
Can get Tuning Step:\tN
Can set RIT:\tN
Can get RIT:\tN
Can set XIT:\tN
Can get XIT:\tN
Can get IF-shift:\tN
Can set Ext Lev:\tN
Can get Ext Lev:\tN
Can set Ext Parm:\tN
Can get Ext Parm:\tN
Can set CTCSS:\tN
Can get CTCSS:\tN
Can set DCS:\tN
Can get DCS:\tN
Can set CTCSS squelch:\tN
Can get CTCSS squelch:\tN
Can set DCS squelch:\tN
Can get DCS squelch:\tN
Can set Power Stat:\tN
Can get Power Stat:\tN
Can Reset:\tN
Can get Ant:\tN
Can set Ant:\tN
Can set Transceive:\tN
Can get Transceive:\tN
Can set Func:\tN
Can get Func:\tN
Can set Level:\tY
Can get Level:\tY
Can set Param:\tN
Can get Param:\tN
Can send DTMF:\tN
Can recv DTMF:\tN
Can send Morse:\tN
Can send Voice Mem:\tN
"""


class RigctldServer:
    """
    asyncio TCP server implementing the Hamlib rigctld network protocol.

    Multiple clients may connect simultaneously; each gets an independent
    command loop.  All commands delegate to the supplied RadioInterface —
    state is shared across all clients because they all talk to the same radio.
    """

    def __init__(
        self,
        radio_interface,        # RadioInterface instance
        host: str = "0.0.0.0",
        port: int = 4532,
    ) -> None:
        self._radio = radio_interface
        self._host  = host
        self._port  = port
        self._server: Optional[asyncio.AbstractServer] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def serve(self) -> None:
        """Start the server and run until the task is cancelled."""
        self._server = await asyncio.start_server(
            self._handle_client,
            host=self._host,
            port=self._port,
        )
        addrs = ", ".join(str(s.getsockname()) for s in self._server.sockets)
        log.info("rigctld server listening on %s  (radio: %s)", addrs, self._radio.name)
        try:
            async with self._server:
                await self._server.serve_forever()
        except asyncio.CancelledError:
            log.info("rigctld server stopped")
            raise

    # ------------------------------------------------------------------
    # Per-client handler
    # ------------------------------------------------------------------

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername", "?")
        log.info("rigctld: client connected from %s", peer)
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(reader.readline(), timeout=120.0)
                except asyncio.TimeoutError:
                    break
                if not raw:
                    break   # client closed the connection
                line = raw.decode("ascii", errors="replace").strip()
                if not line:
                    continue
                response = await self._dispatch(line)
                if response is None:
                    break   # quit command
                writer.write(response.encode("ascii"))
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        except Exception:
            log.exception("rigctld: unexpected error for client %s", peer)
        finally:
            log.info("rigctld: client disconnected: %s", peer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, line: str) -> Optional[str]:
        """Parse one rigctld command line, execute it, return the response."""
        # Strip the extended-response prefix (+) — we reply in standard format.
        if line.startswith("+"):
            line = line[1:]

        if line.startswith("\\"):
            # Long form: \command [args...]
            parts = line[1:].split()
            cmd   = parts[0].lower() if parts else ""
            args  = parts[1:]
        else:
            # Short form: X [args...]
            parts = line.split()
            cmd   = parts[0] if parts else ""
            args  = parts[1:]

        try:
            return await self._execute(cmd, args)
        except Exception as exc:
            log.warning("rigctld: error executing %r: %s", cmd, exc)
            return RPRT_ERR

    async def _execute(self, cmd: str, args: list[str]) -> Optional[str]:
        """Execute a parsed command and return its response string."""
        rs = self._radio.state

        # ── Quit ──────────────────────────────────────────────────────────
        if cmd in ("q", "Q", "quit"):
            return None

        # ── VFO check — tells client we do NOT include VFO in commands ────
        if cmd == "chk_vfo":
            return "CHKVFO 0\n"

        # ── Frequency ─────────────────────────────────────────────────────
        if cmd in ("f", "get_freq"):
            hz = rs.frequency_hz or 0.0
            return f"{int(hz)}\n{RPRT_OK}"

        if cmd in ("F", "set_freq"):
            if not args:
                return RPRT_ERR
            if not rs.connected:
                return RPRT_ERR
            await self._radio.set_frequency(float(args[0]))
            return RPRT_OK

        # ── Mode ──────────────────────────────────────────────────────────
        if cmd in ("m", "get_mode"):
            mode = rs.mode.value if rs.mode else "USB"
            bw   = int(rs.bandwidth_hz) if rs.bandwidth_hz else 0
            return f"{mode}\n{bw}\n{RPRT_OK}"

        if cmd in ("M", "set_mode"):
            if not args:
                return RPRT_ERR
            if not rs.connected:
                return RPRT_ERR
            mode = args[0]
            bw   = float(args[1]) if len(args) > 1 else 0
            await self._radio.set_mode(mode, bw)
            return RPRT_OK

        # ── VFO ───────────────────────────────────────────────────────────
        if cmd in ("v", "get_vfo"):
            return f"{rs.vfo or 'VFOA'}\n{RPRT_OK}"

        if cmd in ("V", "set_vfo"):
            if not args:
                return RPRT_ERR
            if rs.connected:
                await self._radio.set_vfo(args[0])
            return RPRT_OK

        # ── PTT ───────────────────────────────────────────────────────────
        if cmd in ("t", "get_ptt"):
            return f"{1 if rs.ptt else 0}\n{RPRT_OK}"

        if cmd in ("T", "set_ptt"):
            if not args:
                return RPRT_ERR
            if not rs.connected:
                return RPRT_ERR
            await self._radio.set_ptt(args[0] != "0")
            return RPRT_OK

        # ── Split VFO ─────────────────────────────────────────────────────
        if cmd in ("s", "get_split_vfo"):
            split  = 1 if rs.split else 0
            tx_vfo = "VFOB" if rs.split else "VFOA"
            return f"{split}\n{tx_vfo}\n{RPRT_OK}"

        if cmd in ("S", "set_split_vfo"):
            if len(args) < 2:
                return RPRT_ERR
            if rs.connected:
                active = args[0] != "0"
                tx_hz  = rs.vfob_frequency_hz if active else None
                await self._radio.set_split(active, tx_hz)
            return RPRT_OK

        # ── Split frequency ───────────────────────────────────────────────
        if cmd in ("i", "get_split_freq"):
            hz = rs.split_freq_hz or rs.vfob_frequency_hz or rs.frequency_hz or 0
            return f"{int(hz)}\n{RPRT_OK}"

        if cmd in ("I", "set_split_freq"):
            if not args:
                return RPRT_ERR
            if rs.connected:
                hz = float(args[0])
                await self._radio.set_split(True, hz)
            return RPRT_OK

        # ── Levels ────────────────────────────────────────────────────────
        if cmd in ("l", "get_level"):
            name = (args[0].upper() if args else "STRENGTH")
            if name == "STRENGTH":
                dbm = _smeter_to_dbm(rs.signal_strength or 0.0)
                return f"{dbm:.6f}\n{RPRT_OK}"
            if name in ("RFPOWER", "RFPOWER_METER"):
                return f"{rs.rf_power or 0.0:.6f}\n{RPRT_OK}"
            return f"0.000000\n{RPRT_OK}"

        if cmd in ("L", "set_level"):
            if len(args) < 2:
                return RPRT_ERR
            if rs.connected:
                await self._radio.set_level(args[0].upper(), float(args[1]))
            return RPRT_OK

        # ── Info ──────────────────────────────────────────────────────────
        if cmd in ("_", "get_info"):
            info = rs.info or f"StationController ({self._radio.name})"
            return f"{info}\n{RPRT_OK}"

        # ── Capability dump ───────────────────────────────────────────────
        if cmd in ("1", "dump_caps"):
            return _DUMP_CAPS + RPRT_OK

        # ── dump_state (legacy capability check) ─────────────────────────
        if cmd == "dump_state":
            return _dump_state()

        # ── Unimplemented ─────────────────────────────────────────────────
        log.debug("rigctld: unimplemented command %r (args=%r)", cmd, args)
        return RPRT_ENAV


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _smeter_to_dbm(raw: float) -> float:
    """Convert a raw S-meter reading to dBm (Hamlib convention).

    Hamlib uses -54 dBm = S0, -73 dBm = S9 (yes, S9 is *lower* in dBm
    because it's signal power — the convention is odd but it's what apps
    expect).  Icom CI-V raw value: 0=S0, 120=S9, 241=S9+60dB.

    If the value is already in a plausible dBm range (negative and < -10),
    pass it through unchanged so back-ends that return real dBm work too.
    """
    if raw < -10:
        return raw                               # already a dBm value
    if raw <= 0:
        return -127.0                            # S0 ≈ -127 dBm (no signal)
    if raw <= 120:
        return -127.0 + (raw / 120.0) * 54.0   # 0 → -127, 120 → -73 (S9)
    return -73.0 + ((raw - 120) / 121.0) * 60.0 # 120 → -73, 241 → -13 (S9+60)


def _dump_state() -> str:
    """Return a minimal dump_state response (legacy capability bitmap format)."""
    return (
        "0\n"
        "2\n"                              # rig type: transceiver
        "2\n"                              # port type: network
        "1 2000000000 0x1ff -1 -1 0x10000003 0x3\n"  # RX range
        "0 0 0 0 0 0 0\n"
        "1 2000000000 0x1ff -1 -1 0x10000003 0x3\n"  # TX range
        "0 0 0 0 0 0 0\n"
        "0 0\n"                            # tuning steps sentinel
        "0 0\n"                            # filter sentinel
        "0\n"                              # max_rit
        "0\n"                              # max_xit
        "0\n"                              # max_ifshift
        "0\n"                              # announces
        f"{RPRT_OK}"
    )

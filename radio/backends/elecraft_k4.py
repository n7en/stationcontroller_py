"""
Elecraft K4 direct CAT backend - serial and TCP transports.

Communicates with the K4 using its native semicolon-terminated command
protocol over either:
  serial - USB virtual COM port or RS232 DE9 connector
  tcp    - Ethernet TCP socket (same CAT protocol over the network)

No Hamlib or rigctld required.

Protocol summary:
  GET  - send "<CMD>;"          -> radio replies "<CMD><value>;"
  SET  - send "<CMD><value>;"   -> radio executes silently (no ACK)
  ERR  - malformed command echoed back as "<CMD>?;"

PTT state is tracked locally because TX/RX are write-only commands.
Signal strength (SMH) is returned in dBm and converted to Hamlib
convention (0 = S9, ±6 dB per S-unit, -54 = S0).

Config keys (in radio_config.yaml):

  Serial transport (transport: serial):
    port              - Serial device (required): /dev/ttyACM0  or  COM3
    baud_rate         - Baud rate, 4800–115200 (default 38400)

  TCP transport (transport: tcp):
    host              - K4 hostname or IP address (required)
    tcp_port          - TCP port configured on the K4 (default 9204)
    password          - Remote access password, if RRP is set on the K4 (optional)

  Shared:
    timeout_s         - Per-command timeout in seconds (default 5.0)
    max_power_w       - Radio's max TX power for normalisation (default 100)
    power_range       - PC command power range: H=high/100W, L=QRP/10W (default H)
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from .base import RadioBackend, RadioBackendError

log = logging.getLogger(__name__)

# K4 mode number -> string (matches Hamlib naming conventions)
_K4_MODE: dict[int, str] = {
    1: "LSB",
    2: "USB",
    3: "CW",
    4: "FM",
    5: "AM",
    6: "PKTUSB",   # DATA-A / AFSK-A
    7: "CWR",
    9: "PKTLSB",   # DATA REV
}
_MODE_TO_K4: dict[str, int] = {v: k for k, v in _K4_MODE.items()}
_MODE_TO_K4["DATA"] = 6       # convenience alias used by some loggers

# Absolute dBm value that corresponds to S9 on HF (IARU standard)
_S9_DBM = -73


class ElecraftK4Backend(RadioBackend):
    """
    Direct CAT control for the Elecraft K4 transceiver.

    Supports two transports:
      serial - pyserial over USB/RS232; blocking calls run in a thread-pool
               executor so they do not block the asyncio event loop.
      tcp    - asyncio StreamReader/StreamWriter over the K4 Ethernet port;
               fully async, no thread executor needed.
    """

    def __init__(
        self,
        transport: str = "serial",
        # Serial params
        port: str = "",
        baud_rate: int = 38400,
        # TCP params
        host: str = "",
        tcp_port: int = 9204,
        password: str = "",
        # Shared params
        timeout_s: float = 5.0,
        max_power_w: int = 100,
        power_range: str = "H",
    ) -> None:
        self._transport   = transport.lower()
        # serial
        self._port        = port
        self._baud_rate   = baud_rate
        self._ser         = None
        self._lock        = threading.Lock()
        # tcp
        self._host        = host
        self._tcp_port    = tcp_port
        self._password    = password
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        # shared
        self._timeout     = timeout_s
        self._max_power   = max(1, max_power_w)
        self._power_range = power_range.upper()
        self._connected   = False
        self._ptt         = False    # tracked locally; TX/RX are write-only

    @property
    def connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        if self._transport == "tcp":
            await self._connect_tcp()
        else:
            await self._connect_serial()

    async def _connect_serial(self) -> None:
        log.info(
            "Opening K4 on %s @ %d baud (timeout=%.1fs)",
            self._port, self._baud_rate, self._timeout,
        )
        try:
            import serial as _serial   # noqa: F401 - verify import before opening
        except ImportError as exc:
            raise RadioBackendError(
                "pyserial not installed.  Run:  pip install pyserial"
            ) from exc

        def _open():
            import serial as _s
            return _s.Serial(
                port=self._port,
                baudrate=self._baud_rate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=self._timeout,
                write_timeout=self._timeout,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )

        try:
            self._ser = await self._run(_open)
            self._connected = True
            self._ptt = False
            log.info("K4 connected on %s", self._port)
        except Exception as exc:
            self._connected = False
            log.error("K4 connect failed on %s: %s", self._port, exc)
            raise RadioBackendError(
                f"Cannot open K4 serial port {self._port}: {exc}"
            ) from exc

    async def _connect_tcp(self) -> None:
        log.info(
            "Connecting K4 via TCP %s:%d (timeout=%.1fs)",
            self._host, self._tcp_port, self._timeout,
        )
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._tcp_port),
                timeout=self._timeout,
            )
            # Authenticate if a password is configured (K4 RRP command).
            # Send the RRT connection request; the K4 does not ACK it formally.
            if self._password:
                self._writer.write(
                    f"RRT{self._host}:{self._tcp_port}?{self._password};".encode()
                )
                await self._writer.drain()
                try:
                    await asyncio.wait_for(self._tcp_read_until_semi(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
            self._connected = True
            self._ptt = False
            log.info("K4 connected via TCP %s:%d", self._host, self._tcp_port)
        except RadioBackendError:
            raise
        except Exception as exc:
            self._connected = False
            log.error("K4 TCP connect failed %s:%d: %s", self._host, self._tcp_port, exc)
            raise RadioBackendError(
                f"Cannot connect to K4 at {self._host}:{self._tcp_port}: {exc}"
            ) from exc

    async def disconnect(self) -> None:
        log.debug("Closing K4 (%s)", self._transport)
        self._connected = False
        self._ptt = False
        if self._transport == "tcp":
            if self._writer is not None:
                writer, self._writer = self._writer, None
                self._reader = None
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
        else:
            if self._ser is not None:
                ser, self._ser = self._ser, None
                try:
                    await self._run(ser.close)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Async/sync bridge (serial only)
    # ------------------------------------------------------------------

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fn, *args)

    # ------------------------------------------------------------------
    # TCP low-level I/O (fully async)
    # ------------------------------------------------------------------

    async def _tcp_read_until_semi(self) -> str:
        """Read bytes from the TCP stream until ';', return decoded string."""
        buf = bytearray()
        while True:
            c = await self._reader.read(1)
            if not c:
                raise RadioBackendError("K4 TCP connection closed unexpectedly")
            if c == b";":
                break
            buf += c
        return buf.decode(errors="replace")

    async def _tcp_transact(self, cmd: str) -> str:
        """Send a GET command over TCP and return the response body."""
        if self._writer is None or self._reader is None:
            raise RadioBackendError("Not connected to K4 (TCP)")
        self._writer.write((cmd + ";").encode())
        await self._writer.drain()
        resp = await self._tcp_read_until_semi()
        if resp.endswith("?"):
            raise RadioBackendError(f"K4 rejected command '{cmd}': {resp}")
        return resp

    async def _tcp_send_set(self, cmd: str) -> None:
        """Send a SET command over TCP (no response expected)."""
        if self._writer is None:
            raise RadioBackendError("Not connected to K4 (TCP)")
        self._writer.write((cmd + ";").encode())
        await self._writer.drain()

    # ------------------------------------------------------------------
    # Serial low-level I/O (blocking - call via _run)
    # ------------------------------------------------------------------

    def _read_until_semi(self) -> str:
        """Read bytes until ';', return decoded string without the semicolon."""
        buf = b""
        while True:
            c = self._ser.read(1)
            if not c:
                raise RadioBackendError("K4 serial read timeout")
            if c == b";":
                break
            buf += c
        return buf.decode(errors="replace")

    def _transact(self, cmd: str) -> str:
        """Send a GET command and return the response body.  Blocking."""
        if not self._ser or not self._ser.is_open:
            raise RadioBackendError("Not connected to K4")
        with self._lock:
            self._ser.reset_input_buffer()
            self._ser.write((cmd + ";").encode())
            self._ser.flush()
            resp = self._read_until_semi()
        if resp.endswith("?"):
            raise RadioBackendError(f"K4 rejected command '{cmd}': {resp}")
        return resp

    def _send_set(self, cmd: str) -> None:
        """Send a SET command (no response expected).  Blocking."""
        if not self._ser or not self._ser.is_open:
            raise RadioBackendError("Not connected to K4")
        with self._lock:
            self._ser.write((cmd + ";").encode())
            self._ser.flush()

    # ------------------------------------------------------------------
    # Async wrappers - dispatch to TCP or serial
    # ------------------------------------------------------------------

    async def _query(self, cmd: str) -> str:
        """Send a GET command, return response string."""
        log.debug("K4 query: %s", cmd)
        try:
            if self._transport == "tcp":
                coro = self._tcp_transact(cmd)
            else:
                coro = self._run(self._transact, cmd)
            return await asyncio.wait_for(coro, timeout=self._timeout + 1.0)
        except asyncio.TimeoutError as exc:
            self._connected = False
            raise RadioBackendError(f"K4 timeout on query '{cmd}'") from exc
        except RadioBackendError:
            raise
        except Exception as exc:
            self._connected = False
            raise RadioBackendError(f"K4 error on '{cmd}': {exc}") from exc

    async def _write(self, cmd: str) -> None:
        """Send a SET command."""
        log.debug("K4 set: %s", cmd)
        try:
            if self._transport == "tcp":
                coro = self._tcp_send_set(cmd)
            else:
                coro = self._run(self._send_set, cmd)
            await asyncio.wait_for(coro, timeout=self._timeout + 1.0)
        except asyncio.TimeoutError as exc:
            self._connected = False
            raise RadioBackendError(f"K4 timeout sending '{cmd}'") from exc
        except RadioBackendError:
            raise
        except Exception as exc:
            self._connected = False
            raise RadioBackendError(f"K4 error sending '{cmd}': {exc}") from exc

    # ------------------------------------------------------------------
    # Frequency  (FA = VFO A, FB = VFO B)
    # ------------------------------------------------------------------

    async def get_frequency(self) -> float:
        resp = await self._query("FA")
        # Response: FA00014200000  (11-digit Hz value)
        try:
            return float(resp[2:])
        except (ValueError, IndexError) as exc:
            raise RadioBackendError(f"Unexpected FA response: {resp!r}") from exc

    async def set_frequency(self, hz: float) -> None:
        log.debug("set_frequency: %.0f Hz", hz)
        await self._write(f"FA{int(hz):011d}")

    # ------------------------------------------------------------------
    # Mode  (MD command; K4 uses numeric codes)
    # ------------------------------------------------------------------

    async def get_mode(self) -> tuple[str, float]:
        resp = await self._query("MD")
        # Response: MD2  (single digit)
        try:
            mode_str = _K4_MODE.get(int(resp[2]), "UNKNOWN")
            return mode_str, 0.0
        except (ValueError, IndexError) as exc:
            raise RadioBackendError(f"Unexpected MD response: {resp!r}") from exc

    async def set_mode(self, mode: str, bandwidth_hz: float = 0) -> None:
        log.debug("set_mode: %s", mode)
        k4_mode = _MODE_TO_K4.get(mode.upper())
        if k4_mode is None:
            raise RadioBackendError(f"Mode not supported by K4: {mode}")
        await self._write(f"MD{k4_mode}")

    # ------------------------------------------------------------------
    # VFO  (K4 always uses VFO A as main; no Hamlib-style swap)
    # ------------------------------------------------------------------

    async def get_vfo(self) -> str:
        return "VFOA"

    async def set_vfo(self, vfo: str) -> None:
        pass   # K4 VFO selection is implicit via FA/FB frequency commands

    # ------------------------------------------------------------------
    # PTT  (TX/RX are write-only; state tracked locally)
    # ------------------------------------------------------------------

    async def get_ptt(self) -> bool:
        return self._ptt

    async def set_ptt(self, transmit: bool) -> None:
        log.debug("set_ptt: %s", transmit)
        await self._write("TX" if transmit else "RX")
        self._ptt = transmit

    # ------------------------------------------------------------------
    # Split  (FT = split on/off, FB = VFO B frequency)
    # ------------------------------------------------------------------

    async def get_split(self) -> tuple[bool, Optional[float]]:
        resp = await self._query("FT")
        # Response: FT0 or FT1
        try:
            active = resp[2] == "1"
        except IndexError as exc:
            raise RadioBackendError(f"Unexpected FT response: {resp!r}") from exc
        tx_hz: Optional[float] = None
        if active:
            try:
                resp_b = await self._query("FB")
                tx_hz = float(resp_b[2:])
            except (RadioBackendError, ValueError):
                pass
        return active, tx_hz

    async def set_split(self, active: bool, tx_hz: Optional[float] = None) -> None:
        await self._write(f"FT{'1' if active else '0'}")
        if active and tx_hz is not None:
            await self._write(f"FB{int(tx_hz):011d}")

    # ------------------------------------------------------------------
    # Levels
    # ------------------------------------------------------------------

    async def get_level(self, level_name: str) -> float:
        name = level_name.upper()

        if name == "STRENGTH":
            resp = await self._query("SMH")
            # Response: SMH+042 or SMH-073  (absolute dBm, signed)
            try:
                dbm = float(resp[3:])
                # Convert absolute dBm to Hamlib convention:
                #   0 = S9 (-73 dBm), -54 = S0 (-127 dBm), +60 = S9+60dB (-13 dBm)
                return dbm - _S9_DBM
            except (ValueError, IndexError) as exc:
                raise RadioBackendError(f"Unexpected SMH response: {resp!r}") from exc

        if name == "RFPOWER":
            resp = await self._query("PO")
            # Response: POnnnn  (tenths of a watt, e.g. PO1000 = 100.0 W)
            try:
                watts = int(resp[2:]) / 10.0
                return min(1.0, watts / self._max_power)
            except (ValueError, IndexError) as exc:
                raise RadioBackendError(f"Unexpected PO response: {resp!r}") from exc

        raise RadioBackendError(f"Level not supported by K4 backend: {level_name}")

    async def set_level(self, level_name: str, value: float) -> None:
        if level_name.upper() == "RFPOWER":
            # PC command: PCnnnR where nnn = watts, R = H (high/100W) or L (QRP/10W)
            watts = max(1, int(value * self._max_power))
            await self._write(f"PC{watts:03d}{self._power_range}")
            return
        raise RadioBackendError(f"Level not supported by K4 backend: {level_name}")

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    async def get_info(self) -> str:
        try:
            # RVM = Rig Version Message (firmware string), common on Elecraft rigs
            resp = await self._query("RVM")
            return f"Elecraft K4 FW:{resp[3:]}"
        except RadioBackendError:
            return "Elecraft K4"

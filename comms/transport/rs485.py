"""
RS-485 serial transport.

Each instance owns one serial port at a configurable baud rate.
A background daemon thread reads bytes, assembles lines on CR boundaries,
and dispatches parsed DCNPackets back on the asyncio event loop.

Automatic reconnection is attempted every RECONNECT_DELAY seconds if the
port is lost (e.g. USB dongle unplugged).

Config keys:
  port       - serial port path, e.g. /dev/ttyUSB0 or COM3
  baud_rate  - 9600 (control) or 115200 (power meter), default 9600
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

import serial

from .base import DCNTransport
from ..dcn_packet import DCNPacket, parse_packet

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 5.0   # seconds between reconnect attempts
RECONNECT_LOG_EVERY = 12  # log a reminder every N retries (~60 s at 5 s delay)


class RS485Transport(DCNTransport):

    def __init__(self, name: str, config: dict) -> None:
        super().__init__(name, config)
        self._serial: Optional[serial.Serial] = None
        self._read_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()
        self._buffer = ""
        self._reconnect_attempts = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._stop_event.clear()
        self._buffer = ""
        self._open_port()
        self._connected = self._serial is not None and self._serial.is_open
        self._read_thread = threading.Thread(
            target=self._read_loop,
            daemon=True,
            name=f"rs485-{self.name}",
        )
        self._read_thread.start()
        if self._connected:
            logger.info(
                "RS-485 '%s' connected on %s @ %d baud",
                self.name, self._config["port"], self.baud_rate,
            )
        else:
            logger.error(
                "RS-485 '%s' could not open %s - will retry every %.0fs",
                self.name, self._config.get("port", ""), RECONNECT_DELAY,
            )

    async def disconnect(self) -> None:
        self._connected = False
        self._stop_event.set()
        if self._serial and self._serial.is_open:
            try:
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                self._serial.close()
            except Exception:
                pass
        if self._read_thread and self._read_thread.is_alive():
            await asyncio.to_thread(self._read_thread.join, 1.0)
        logger.info("RS-485 '%s' disconnected", self.name)

    async def send(self, packet: DCNPacket) -> None:
        if not self._connected or not self._serial or not self._serial.is_open:
            logger.warning("RS-485 '%s': send skipped - not connected", self.name)
            return
        try:
            self._serial.write(packet.encode())
            logger.debug("RS-485 '%s' TX: %s", self.name, packet)
        except serial.SerialException as exc:
            logger.error("RS-485 '%s' write error: %s", self.name, exc)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open_port(self) -> None:
        port = self._config.get("port", "")
        try:
            # Open with port=None to defer the actual open() call so we can
            # suppress the modem-control ioctls (TIOCMBIS/TIOCMBIC) that
            # pyserial issues unconditionally in _update_dtr_state /
            # _update_rts_state.  USB RS-485 adapters have no DTR/RTS lines
            # and reject those ioctls with Errno 5 (EIO).
            # Setting _dtr_state/rts_state to None is NOT sufficient because
            # pyserial treats None as falsy and still calls _set_dtr_state(False).
            # Overriding the update methods as no-ops on the instance is the
            # only reliable way to skip the ioctl entirely.
            ser = serial.Serial(
                port=None,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                dsrdtr=False,
                rtscts=False,
                xonxoff=False,
            )
            ser._update_dtr_state = lambda: None   # suppress TIOCMBIC/TIOCMBIS
            ser._update_rts_state = lambda: None
            ser.port = port
            ser.open()
            # Clear HUPCL so the kernel does not assert a hangup (de-assert
            # DTR/RTS) when the port is closed.  Without this, many USB RS-485
            # adapters do a firmware reset on close and spend ~500 ms
            # re-enumerating, causing the next open to fail on service restart.
            try:
                import termios
                attrs = termios.tcgetattr(ser.fd)
                attrs[2] &= ~termios.HUPCL   # cflag
                termios.tcsetattr(ser.fd, termios.TCSANOW, attrs)
            except Exception:
                pass  # not available on Windows
            self._serial = ser
        except (serial.SerialException, OSError) as exc:
            if self._reconnect_attempts == 0:
                logger.error("RS-485 '%s' cannot open %s: %s", self.name, port, exc)
            self._serial = None

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._serial or not self._serial.is_open:
                time.sleep(RECONNECT_DELAY)
                self._reconnect_attempts += 1
                self._open_port()
                if self._serial and self._serial.is_open:
                    self._connected = True
                    self._reconnect_attempts = 0
                    logger.info("RS-485 '%s': reconnected on %s",
                                self.name, self._config.get("port", ""))
                else:
                    if self._reconnect_attempts % RECONNECT_LOG_EVERY == 0:
                        logger.error(
                            "RS-485 '%s': still cannot open %s (%d attempts)",
                            self.name, self._config.get("port", ""),
                            self._reconnect_attempts,
                        )
                continue

            try:
                waiting = self._serial.in_waiting
                data = self._serial.read(waiting or 1)
                if data:
                    self._buffer += data.decode("ascii", errors="replace")
                    self._process_buffer()
            except serial.SerialException as exc:
                logger.error("RS-485 '%s' read error: %s - will reconnect", self.name, exc)
                self._connected = False
                try:
                    self._serial.close()
                except Exception:
                    pass

    def _process_buffer(self) -> None:
        # Split on CR, LF, or CRLF — devices at different baud rates use different terminators
        while True:
            cr = self._buffer.find("\r")
            lf = self._buffer.find("\n")
            if cr == -1 and lf == -1:
                break
            if cr == -1:
                pos = lf
            elif lf == -1:
                pos = cr
            else:
                pos = min(cr, lf)
            line = self._buffer[:pos].strip()
            # skip the terminator (and consume CRLF as a single delimiter)
            rest = self._buffer[pos + 1:]
            if rest.startswith("\n") and pos == cr:
                rest = rest[1:]
            self._buffer = rest
            if not line:
                continue
            packet = parse_packet(line)
            if packet:
                logger.debug("RS-485 '%s' RX: %s", self.name, packet)
                if self._loop and not self._loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        self._dispatch(packet), self._loop
                    )
            else:
                logger.info("RS-485 '%s' ignored non-packet line: %r", self.name, line)

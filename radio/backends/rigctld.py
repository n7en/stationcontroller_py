"""
Rigctld TCP backend.

Connects to a running rigctld daemon (hamlib) over TCP.
Works identically for local (127.0.0.1:4532) and remote (host:4532) daemons.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .base import RadioBackend, RadioBackendError

log = logging.getLogger(__name__)


class RigctldBackend(RadioBackend):

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4532,
        timeout_s: float = 15.0,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout_s
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        log.debug("Connecting to rigctld at %s:%d (timeout=%.1fs)", self._host, self._port, self._timeout)
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
            self._connected = True
            log.info("Connected to rigctld at %s:%d", self._host, self._port)
        except (OSError, asyncio.TimeoutError) as exc:
            self._connected = False
            log.debug("rigctld connect failed at %s:%d: %s", self._host, self._port, exc)
            raise RadioBackendError(
                f"Cannot connect to rigctld at {self._host}:{self._port}: {exc}"
            ) from exc

    async def disconnect(self) -> None:
        log.debug("Disconnecting from rigctld at %s:%d", self._host, self._port)
        self._connected = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            self._writer = None
            self._reader = None

    # ------------------------------------------------------------------
    # Low-level command exchange
    # ------------------------------------------------------------------

    def _drop_connection(self) -> None:
        """Mark disconnected and close the underlying socket so rigctld frees the slot."""
        log.warning("rigctld connection dropped (%s:%d)", self._host, self._port)
        self._connected = False
        self._reader = None
        if self._writer is not None:
            try:
                self._writer.close()
            except OSError:
                pass
            self._writer = None

    async def _cmd(self, command: str) -> list[str]:
        """
        Send one extended-mode command, return response lines excluding RPRT.
        Raises RadioBackendError on RPRT < 0 or connection loss.
        """
        if not self._connected or self._writer is None:
            raise RadioBackendError("Not connected to rigctld")

        log.debug("rigctld cmd: %s", command)
        async with self._lock:
            try:
                self._writer.write((command + "\n").encode())
                await self._writer.drain()
                return await asyncio.wait_for(
                    self._read_response(), timeout=self._timeout
                )
            except (OSError, ConnectionResetError) as exc:
                self._drop_connection()
                raise RadioBackendError(f"rigctld connection lost: {exc}") from exc
            except asyncio.TimeoutError as exc:
                self._drop_connection()
                raise RadioBackendError("rigctld response timed out") from exc

    async def _read_response(self) -> list[str]:
        lines: list[str] = []
        while True:
            raw = await self._reader.readline()
            if not raw:
                raise ConnectionResetError("rigctld closed the connection")
            line = raw.decode().rstrip("\n\r")
            if line.startswith("RPRT "):
                code = int(line.split()[1])
                if code < 0:
                    raise RadioBackendError(f"rigctld error RPRT {code}")
                return lines
            lines.append(line)

    # ------------------------------------------------------------------
    # Frequency
    # ------------------------------------------------------------------

    async def get_frequency(self) -> float:
        lines = await self._cmd(r"\get_freq")
        try:
            return float(lines[0])
        except (IndexError, ValueError) as exc:
            raise RadioBackendError(f"Unexpected get_freq response: {lines}") from exc

    async def set_frequency(self, hz: float) -> None:
        log.debug("set_frequency: %.0f Hz", hz)
        await self._cmd(rf"\set_freq {int(hz)}")

    # ------------------------------------------------------------------
    # Mode and filter
    # ------------------------------------------------------------------

    async def get_mode(self) -> tuple[str, float]:
        lines = await self._cmd(r"\get_mode")
        try:
            mode = lines[0]
            bw = float(lines[1]) if len(lines) > 1 else 0.0
            return mode, bw
        except (IndexError, ValueError) as exc:
            raise RadioBackendError(f"Unexpected get_mode response: {lines}") from exc

    async def set_mode(self, mode: str, bandwidth_hz: float = 0) -> None:
        log.debug("set_mode: %s bw=%d", mode, bandwidth_hz)
        await self._cmd(rf"\set_mode {mode} {int(bandwidth_hz)}")

    # ------------------------------------------------------------------
    # VFO
    # ------------------------------------------------------------------

    async def get_vfo(self) -> str:
        lines = await self._cmd(r"\get_vfo")
        try:
            return lines[0]
        except IndexError as exc:
            raise RadioBackendError(f"Unexpected get_vfo response: {lines}") from exc

    async def set_vfo(self, vfo: str) -> None:
        await self._cmd(rf"\set_vfo {vfo}")

    # ------------------------------------------------------------------
    # PTT
    # ------------------------------------------------------------------

    async def get_ptt(self) -> bool:
        lines = await self._cmd(r"\get_ptt")
        try:
            return lines[0].strip() != "0"
        except IndexError as exc:
            raise RadioBackendError(f"Unexpected get_ptt response: {lines}") from exc

    async def set_ptt(self, transmit: bool) -> None:
        log.debug("set_ptt: %s", transmit)
        await self._cmd(rf"\set_ptt {1 if transmit else 0}")

    # ------------------------------------------------------------------
    # Split
    # ------------------------------------------------------------------

    async def get_split(self) -> tuple[bool, Optional[float]]:
        vfo_lines = await self._cmd(r"\get_split_vfo")
        try:
            active = vfo_lines[0].strip() != "0"
        except IndexError as exc:
            raise RadioBackendError(f"Unexpected get_split_vfo response: {vfo_lines}") from exc
        tx_hz: Optional[float] = None
        if active:
            try:
                freq_lines = await self._cmd(r"\get_split_freq")
                tx_hz = float(freq_lines[0])
            except (RadioBackendError, IndexError, ValueError):
                pass
        return active, tx_hz

    async def set_split(self, active: bool, tx_hz: Optional[float] = None) -> None:
        await self._cmd(rf"\set_split_vfo {1 if active else 0} VFOB")
        if active and tx_hz is not None:
            await self._cmd(rf"\set_split_freq {int(tx_hz)}")

    # ------------------------------------------------------------------
    # Levels
    # ------------------------------------------------------------------

    async def get_level(self, level_name: str) -> float:
        lines = await self._cmd(rf"\get_level {level_name}")
        try:
            return float(lines[0])
        except (IndexError, ValueError) as exc:
            raise RadioBackendError(f"Unexpected get_level response for {level_name}: {lines}") from exc

    async def set_level(self, level_name: str, value: float) -> None:
        await self._cmd(rf"\set_level {level_name} {value}")

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    async def get_info(self) -> str:
        lines = await self._cmd(r"\get_info")
        try:
            return lines[0] if lines else ""
        except IndexError:
            return ""

    # ------------------------------------------------------------------
    # Full-state override — polls only stable commands
    # ------------------------------------------------------------------

    async def get_full_state(self) -> dict:
        """
        Poll freq, mode, and PTT.  Skips get_vfo, get_split, and get_level because
        all issue additional sub-commands or level queries that cause some radios
        (e.g. TS-2000) to return RPRT errors that prompt rigctld to close the
        TCP socket, breaking subsequent commands in the same poll.  If a connection
        drop is detected mid-poll, raise immediately so the caller can reconnect.
        """
        state: dict = {}

        try:
            state["frequency_hz"] = await self.get_frequency()
        except RadioBackendError:
            if not self._connected:
                raise
        try:
            mode, bw = await self.get_mode()
            state["mode"] = mode
            state["bandwidth_hz"] = bw
        except RadioBackendError:
            if not self._connected:
                raise
        try:
            state["ptt"] = await self.get_ptt()
        except RadioBackendError:
            if not self._connected:
                raise
        return state

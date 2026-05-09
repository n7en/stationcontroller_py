"""
RigctldLauncher - manages a rigctld subprocess.

Finds a free TCP port (or uses a fixed one), spawns rigctld with the
specified rig model and serial port, waits until the port accepts
connections, and tears down cleanly on stop().
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import socket
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


def _find_free_port(start: int = 4532, stop: int = 4600) -> int:
    """Return the first available TCP port in [start, stop)."""
    for port in range(start, stop):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free TCP port available in range {start}-{stop - 1}")


class RigctldLauncher:
    """
    Manages one rigctld process.

    Attributes:
        port  - the resolved TCP port (set at construction; read after __init__)
    """

    def __init__(
        self,
        model_id: int,
        serial_port: str,
        baud_rate: int = 9600,
        listen_host: str = "127.0.0.1",
        port: int = 0,
        serial_timeout_ms: int = 500,
        extra_args: Optional[list[str]] = None,
    ) -> None:
        self.model_id          = model_id
        self.serial_port       = serial_port
        self.baud_rate         = baud_rate
        self.listen_host       = listen_host
        self.serial_timeout_ms = serial_timeout_ms
        # Resolve the port now so callers can read it before start()
        self.port        = port if port > 0 else _find_free_port()
        self.extra_args  = extra_args or []
        self._proc: Optional[asyncio.subprocess.Process] = None
        # PID file lets us kill a leftover process from a previous app run.
        # Keyed on serial_port so it survives port-number changes between restarts.
        _safe = serial_port.replace("/", "_").replace("\\", "_").replace(":", "_")
        self._pid_file = os.path.join(tempfile.gettempdir(), f"sc_rigctld_{_safe}.pid")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, startup_timeout: float = 10.0) -> None:
        """Spawn rigctld and block until its TCP port is accepting connections."""
        if self._proc is not None and self._proc.returncode is None:
            return  # already running

        # Kill any rigctld left over from a previous app run on this serial port.
        self._kill_stale()

        exe = shutil.which("rigctld")
        if exe is None:
            raise RuntimeError(
                "rigctld not found on PATH.  Install hamlib: "
                "apt install hamlib | brew install hamlib | "
                "https://github.com/Hamlib/Hamlib/releases"
            )

        cmd = [
            exe,
            "-m", str(self.model_id),
            "-r", self.serial_port,
            "-s", str(self.baud_rate),
            "-T", self.listen_host,
            "-t", str(self.port),
            "-o", f"timeout={self.serial_timeout_ms}",
            *self.extra_args,
        ]
        logger.info("Starting rigctld: %s", " ".join(cmd))

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        # Drain stderr in the background so the pipe never fills up
        loop = asyncio.get_running_loop()
        loop.create_task(
            self._drain_stderr(), name=f"rigctld-stderr-{self.port}"
        )

        # Poll until the port is reachable or we give up
        deadline = loop.time() + startup_timeout
        while loop.time() < deadline:
            if self._proc.returncode is not None:
                raise RuntimeError(
                    f"rigctld exited prematurely with code {self._proc.returncode}"
                )
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.listen_host, self.port),
                    timeout=0.5,
                )
                writer.close()
                await writer.wait_closed()
                logger.info(
                    "rigctld ready on %s:%d  (pid %d, model %d, port %s @ %d baud)",
                    self.listen_host, self.port, self._proc.pid,
                    self.model_id, self.serial_port, self.baud_rate,
                )
                self._write_pid(self._proc.pid)
                return
            except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
                await asyncio.sleep(0.2)

        raise RuntimeError(
            f"rigctld did not become ready on {self.listen_host}:{self.port} "
            f"within {startup_timeout:.0f}s"
        )

    async def stop(self) -> None:
        """Terminate the rigctld process gracefully, then forcibly if needed."""
        if self._proc is None or self._proc.returncode is not None:
            self._remove_pid()
            return
        logger.info("Stopping rigctld (pid %d)", self._proc.pid)
        self._proc.terminate()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("rigctld (pid %d) did not exit - killing", self._proc.pid)
            self._proc.kill()
            await self._proc.wait()
        self._proc = None
        self._remove_pid()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    # ------------------------------------------------------------------
    # PID-file helpers - survive app restarts on the same serial port
    # ------------------------------------------------------------------

    def _write_pid(self, pid: int) -> None:
        try:
            with open(self._pid_file, "w") as fh:
                fh.write(str(pid))
        except OSError as exc:
            logger.debug("Could not write PID file %s: %s", self._pid_file, exc)

    def _remove_pid(self) -> None:
        try:
            os.unlink(self._pid_file)
        except OSError:
            pass

    def _kill_stale(self) -> None:
        """Kill a rigctld left over from a previous run, if the PID file exists."""
        try:
            with open(self._pid_file) as fh:
                pid = int(fh.read().strip())
        except (OSError, ValueError):
            return
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("Sent SIGTERM to stale rigctld (pid %d, port %s)", pid, self.serial_port)
        except (ProcessLookupError, OSError):
            pass  # already gone
        self._remove_pid()

    # ------------------------------------------------------------------

    async def _drain_stderr(self) -> None:
        if self._proc is None or self._proc.stderr is None:
            return
        try:
            async for raw in self._proc.stderr:
                line = raw.decode(errors="replace").rstrip()
                if line:
                    logger.debug("rigctld[%d]: %s", self.port, line)
        except Exception:
            pass

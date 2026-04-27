"""
Simulated rigctld daemon for hardware-free radio testing.

SimRigctld is an async TCP server that speaks the rigctld extended protocol.
The app's rigctld backend connects to it exactly as it would a real rigctld
process — no changes to the app or radio config needed beyond pointing host/port
at the simulator.

Integrated into DCNSimulator via the radio.rigctld section of sim_config.yaml.
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field

logger = logging.getLogger("dcn_sim.radio")

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

@dataclass
class SimRadioState:
    frequency_hz: float  = 14_200_000.0
    mode: str            = "USB"
    bandwidth_hz: int    = 2400
    vfo: str             = "VFOA"
    ptt: bool            = False
    split: bool          = False
    split_freq_hz: float = 14_200_000.0
    rf_power: float      = 1.0        # normalised 0.0–1.0
    af_gain: float       = 0.5
    signal_strength: float = -10.0   # dBm (approx S3)
    info: str            = "SimRig"

    @classmethod
    def from_config(cls, cfg: dict) -> "SimRadioState":
        return cls(
            frequency_hz   = float(cfg.get("frequency_hz",    14_200_000)),
            mode           = str(cfg.get("mode",           "USB")),
            bandwidth_hz   = int(cfg.get("bandwidth_hz",   2400)),
            vfo            = str(cfg.get("vfo",            "VFOA")),
            ptt            = bool(cfg.get("ptt",           False)),
            split          = bool(cfg.get("split",         False)),
            split_freq_hz  = float(cfg.get("split_freq_hz", 14_200_000)),
            rf_power       = float(cfg.get("rf_power",     1.0)),
            af_gain        = float(cfg.get("af_gain",      0.5)),
            signal_strength= float(cfg.get("signal_strength", -10.0)),
            info           = str(cfg.get("info",           "SimRig")),
        )


# ---------------------------------------------------------------------------
# rigctld TCP server
# ---------------------------------------------------------------------------

class SimRigctld:
    """
    Async TCP server speaking the rigctld extended (backslash) protocol.

    Handles every command the rigctld backend uses:
      \\get_freq / \\set_freq
      \\get_mode / \\set_mode
      \\get_vfo  / \\set_vfo
      \\get_ptt  / \\set_ptt
      \\get_split_vfo  / \\set_split_vfo
      \\get_split_freq / \\set_split_freq
      \\get_level / \\set_level  (RFPOWER, AF, STRENGTH)
      \\get_info
    """

    def __init__(self, state: SimRadioState, host: str = "127.0.0.1", port: int = 4532) -> None:
        self.state = state
        self.host  = host
        self.port  = port
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port,
        )
        addr = self._server.sockets[0].getsockname()
        logger.info("rigctld simulator listening on %s:%s", addr[0], addr[1])

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("rigctld simulator stopped")

    # ------------------------------------------------------------------
    # Client handler
    # ------------------------------------------------------------------

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        logger.debug("rigctld: client connected %s", peer)
        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break
                cmd = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not cmd:
                    continue
                response = self._dispatch(cmd)
                writer.write(response.encode("utf-8"))
                await writer.drain()
                logger.debug("rigctld  %r  ->  %r", cmd, response.rstrip("\n"))
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logger.debug("rigctld: client disconnected %s", peer)

    # ------------------------------------------------------------------
    # Protocol dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, cmd: str) -> str:
        s = self.state
        parts = cmd.split()
        if not parts:
            return "RPRT -1\n"
        op   = parts[0]
        args = parts[1:]

        # Frequency
        if op == r"\get_freq":
            return f"{int(s.frequency_hz)}\nRPRT 0\n"
        if op == r"\set_freq" and args:
            s.frequency_hz = float(args[0])
            return "RPRT 0\n"

        # Mode
        if op == r"\get_mode":
            return f"{s.mode}\n{s.bandwidth_hz}\nRPRT 0\n"
        if op == r"\set_mode" and len(args) >= 2:
            s.mode = args[0]
            s.bandwidth_hz = int(args[1])
            return "RPRT 0\n"

        # VFO
        if op == r"\get_vfo":
            return f"{s.vfo}\nRPRT 0\n"
        if op == r"\set_vfo" and args:
            s.vfo = args[0]
            return "RPRT 0\n"

        # PTT
        if op == r"\get_ptt":
            return f"{1 if s.ptt else 0}\nRPRT 0\n"
        if op == r"\set_ptt" and args:
            s.ptt = args[0] != "0"
            logger.info("rigctld: PTT %s", "ON" if s.ptt else "OFF")
            return "RPRT 0\n"

        # Split VFO
        if op == r"\get_split_vfo":
            return f"{1 if s.split else 0}\nVFOB\nRPRT 0\n"
        if op == r"\set_split_vfo" and args:
            s.split = args[0] != "0"
            return "RPRT 0\n"

        # Split frequency
        if op == r"\get_split_freq":
            return f"{int(s.split_freq_hz)}\nRPRT 0\n"
        if op == r"\set_split_freq" and args:
            s.split_freq_hz = float(args[0])
            return "RPRT 0\n"

        # Levels
        if op == r"\get_level" and args:
            return self._get_level(args[0])
        if op == r"\set_level" and len(args) >= 2:
            return self._set_level(args[0], args[1])

        # Info
        if op == r"\get_info":
            return f"{s.info}\nRPRT 0\n"

        logger.debug("rigctld: unrecognised command %r", op)
        return "RPRT -1\n"

    def _get_level(self, name: str) -> str:
        s = self.state
        if name == "RFPOWER":
            return f"{s.rf_power:.6f}\nRPRT 0\n"
        if name == "AF":
            return f"{s.af_gain:.6f}\nRPRT 0\n"
        if name in ("STRENGTH", "STR"):
            # Small noise so the S-meter looks live
            val = s.signal_strength + random.uniform(-1.5, 1.5)
            return f"{val:.1f}\nRPRT 0\n"
        return "0.000000\nRPRT 0\n"

    def _set_level(self, name: str, raw: str) -> str:
        try:
            value = float(raw)
        except ValueError:
            return "RPRT -1\n"
        s = self.state
        if name == "RFPOWER":
            s.rf_power = max(0.0, min(1.0, value))
        elif name == "AF":
            s.af_gain = max(0.0, min(1.0, value))
        return "RPRT 0\n"

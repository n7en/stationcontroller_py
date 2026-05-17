"""
Icom LAN backend — native CI-V over UDP via rigplane-core.

Speaks the Icom RS-BA1/wfview UDP protocol directly; no rigctld or wfview
required.  Wraps rigplane's ``Radio`` API and maps it to the StationController
``RadioBackend`` interface.

Install rigplane before enabling this backend:
    pip install git+https://github.com/rigplane/rigplane-core.git

Config keys (radio_config.yaml):
    backend:       icom_lan
    host:          "192.168.1.50"   # radio IP address
    port:          50001             # control port (default 50001)
    username:      ""                # LAN login username if set on radio
    password:      ""                # LAN login password if set on radio
    model:         "IC-7300"         # optional model hint for sub-rx routing
    timeout_s:     15.0
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .base import RadioBackend, RadioBackendError

log = logging.getLogger(__name__)

# Mode string mapping: StationController/hamlib names → rigplane Mode enum names.
# rigplane enum names match CI-V mode bytes and are already uppercase.
_TO_RIGPLANE: dict[str, str] = {
    "LSB":      "LSB",
    "USB":      "USB",
    "AM":       "AM",
    "FM":       "FM",
    "CW":       "CW",
    "CWR":      "CWR",
    "RTTY":     "RTTY",
    "RTTYR":    "RTTYR",
    "DV":       "DV",
    "DD":       "DD",
    "WFM":      "WFM",
    "DATA-LSB": "LSB",
    "DATA-USB": "USB",
}

_INSTALL_HINT = (
    "rigplane is not installed.\n"
    "Install with: pip install git+https://github.com/rigplane/rigplane-core.git"
)


class IcomLanBackend(RadioBackend):
    """Radio backend for Icom transceivers connected via Ethernet/LAN.

    Uses the rigplane library which implements the native Icom UDP protocol
    (the same protocol used by RS-BA1 and wfview) directly in Python.
    Supports all Icom LAN-capable HF/VHF transceivers including IC-7300,
    IC-7610, IC-9700, IC-705, and others.

    rigplane handles its own auto-reconnect loop, so transient disconnections
    (e.g. radio power cycle) are recovered automatically without intervention
    from RadioInterface.
    """

    def __init__(
        self,
        host: str,
        port: int = 50001,
        username: str = "",
        password: str = "",
        timeout_s: float = 15.0,
        model: str = "",
        **_kwargs,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._timeout = timeout_s
        self._model = model
        self._radio = None  # rigplane Radio instance, set on connect()

    # ------------------------------------------------------------------
    # Connection state
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        if self._radio is None:
            return False
        try:
            from rigplane.runtime._connection_state import RadioConnectionState
            state = self._radio.connection_state
            # Report True during RECONNECTING so RadioInterface's reconnect
            # loop doesn't race against rigplane's own reconnect logic.
            return state in (
                RadioConnectionState.CONNECTED,
                RadioConnectionState.RECONNECTING,
            )
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            from rigplane import create_radio, LanBackendConfig
        except ImportError as exc:
            raise RadioBackendError(_INSTALL_HINT) from exc

        # Disconnect any stale instance before creating a new one.
        if self._radio is not None:
            try:
                await self._radio.disconnect()
            except Exception:
                pass
            self._radio = None

        try:
            cfg = LanBackendConfig(
                host=self._host,
                port=self._port,
                username=self._username or "",
                password=self._password or "",
                auto_reconnect=True,
                **({"model": self._model} if self._model else {}),
            )
            radio = create_radio(cfg)
            await asyncio.wait_for(radio.connect(), timeout=self._timeout)
            self._radio = radio
            log.info("Icom LAN connected: %s:%d", self._host, self._port)
        except asyncio.TimeoutError as exc:
            raise RadioBackendError(
                f"Icom LAN connect timed out ({self._timeout}s) for {self._host}:{self._port}"
            ) from exc
        except RadioBackendError:
            raise
        except Exception as exc:
            raise RadioBackendError(
                f"Icom LAN connect failed for {self._host}:{self._port}: {exc}"
            ) from exc

    async def disconnect(self) -> None:
        if self._radio is not None:
            try:
                await self._radio.disconnect()
            except Exception:
                pass
            self._radio = None

    # ------------------------------------------------------------------
    # Frequency
    # ------------------------------------------------------------------

    async def get_frequency(self) -> float:
        self._require()
        try:
            return float(await asyncio.wait_for(
                self._radio.get_freq(), timeout=self._timeout
            ))
        except Exception as exc:
            raise RadioBackendError(f"get_frequency: {exc}") from exc

    async def set_frequency(self, hz: float) -> None:
        self._require()
        try:
            await asyncio.wait_for(
                self._radio.set_freq(int(hz)), timeout=self._timeout
            )
        except Exception as exc:
            raise RadioBackendError(f"set_frequency: {exc}") from exc

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------

    async def get_mode(self) -> tuple[str, float]:
        self._require()
        try:
            mode_enum, fw = await asyncio.wait_for(
                self._radio.get_mode_info(), timeout=self._timeout
            )
            return mode_enum.name, float(fw or 0)
        except Exception as exc:
            raise RadioBackendError(f"get_mode: {exc}") from exc

    async def set_mode(self, mode: str, bandwidth_hz: float = 0) -> None:
        self._require()
        try:
            from rigplane import Mode
            rp_name = _TO_RIGPLANE.get(mode.upper(), mode.upper())
            rp_mode = Mode[rp_name]
            fw = int(bandwidth_hz) if bandwidth_hz else None
            await asyncio.wait_for(
                self._radio.set_mode(rp_mode, filter_width=fw),
                timeout=self._timeout,
            )
        except KeyError:
            raise RadioBackendError(f"Unknown or unsupported mode: {mode!r}")
        except Exception as exc:
            raise RadioBackendError(f"set_mode: {exc}") from exc

    # ------------------------------------------------------------------
    # VFO
    # ------------------------------------------------------------------

    async def get_vfo(self) -> str:
        if self._radio is None:
            return "VFOA"
        try:
            slot = getattr(self._radio.state.main, "active_slot", "A")
            return f"VFO{slot}"
        except Exception:
            return "VFOA"

    async def set_vfo(self, vfo: str) -> None:
        # VFO swap via CI-V 0x07 could be added if needed
        pass

    # ------------------------------------------------------------------
    # PTT
    # ------------------------------------------------------------------

    async def get_ptt(self) -> bool:
        if self._radio is None:
            return False
        try:
            return bool(self._radio.state.ptt)
        except Exception:
            return False

    async def set_ptt(self, transmit: bool) -> None:
        self._require()
        try:
            await asyncio.wait_for(
                self._radio.set_ptt(transmit), timeout=self._timeout
            )
        except Exception as exc:
            raise RadioBackendError(f"set_ptt: {exc}") from exc

    # ------------------------------------------------------------------
    # Split
    # ------------------------------------------------------------------

    async def get_split(self) -> tuple[bool, Optional[float]]:
        if self._radio is None:
            return False, None
        try:
            split = bool(self._radio.state.split)
            tx_hz: Optional[float] = None
            if split:
                try:
                    vfob = self._radio.state.main.vfo_b.freq_hz
                    if vfob:
                        tx_hz = float(vfob)
                except Exception:
                    pass
            return split, tx_hz
        except Exception:
            return False, None

    async def set_split(self, active: bool, tx_hz: Optional[float] = None) -> None:
        if self._radio is None:
            return
        try:
            # CI-V 0x0F: split on (0x01) / off (0x00)
            await self._radio.send_civ(0x0F, sub=0x01 if active else 0x00)
            if active and tx_hz is not None:
                # Set VFO-B (receiver=1) to the TX frequency
                await self._radio.set_freq(int(tx_hz), receiver=1)
        except Exception as exc:
            raise RadioBackendError(f"set_split: {exc}") from exc

    # ------------------------------------------------------------------
    # Levels
    # ------------------------------------------------------------------

    async def get_level(self, level_name: str) -> float:
        if self._radio is None:
            return 0.0
        name = level_name.upper()
        try:
            if name == "STRENGTH":
                raw = self._radio.state.main.s_meter  # 0–255 raw CI-V value
                return float(raw) if raw is not None else 0.0
            if name == "RFPOWER":
                val = await asyncio.wait_for(
                    self._radio.get_rf_power(), timeout=self._timeout
                )
                return float(val) / 255.0  # normalise to 0.0–1.0
        except Exception:
            pass
        return 0.0

    async def set_level(self, level_name: str, value: float) -> None:
        # Extendable via send_civ for AF/RF/SQL/MICGAIN etc.
        pass

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    async def get_info(self) -> str:
        if self._radio is None:
            return f"Icom LAN @ {self._host}:{self._port}"
        try:
            profile = getattr(self._radio, "profile", None)
            if profile:
                model = getattr(profile, "model", "") or getattr(profile, "name", "")
                if model:
                    return f"{model} @ {self._host}"
        except Exception:
            pass
        return f"Icom LAN @ {self._host}:{self._port}"

    # ------------------------------------------------------------------
    # Full-state override — reads from rigplane's in-process state cache.
    # No network round-trip; rigplane keeps state current via its own CI-V
    # receive loop, so this is always fresh without us polling the radio.
    # ------------------------------------------------------------------

    async def get_full_state(self) -> dict:
        if self._radio is None or not self.connected:
            return {}

        result: dict = {}
        try:
            rs = self._radio.state
            main = rs.main

            # Frequency (active VFO slot, Hz)
            freq = main.freq
            if freq:
                result["frequency_hz"] = float(freq)

            # Mode (already a string, e.g. "LSB", "USB")
            mode = main.mode
            if mode:
                result["mode"] = str(mode)

            # Filter bandwidth in Hz (None when unknown)
            fw = getattr(main, "filter_width", None)
            if fw:
                result["bandwidth_hz"] = float(fw)

            # VFO A / B frequencies for split display
            try:
                vfob_hz = main.vfo_b.freq_hz
                if vfob_hz:
                    result["vfob_frequency_hz"] = float(vfob_hz)
                    result["vfob_mode"] = str(main.vfo_b.mode or "")
            except Exception:
                pass

            # Global RadioState fields
            result["ptt"]   = bool(rs.ptt)
            result["split"] = bool(rs.split)

            # S-meter (0–255 raw CI-V; 0 = S0, 120 = S9, 241 = S9+60dB)
            s = getattr(main, "s_meter", None)
            if s is not None:
                result["signal_strength"] = float(s)


            # Sub-receiver state (dual-watch radios: IC-7610, IC-9700)
            try:
                sub = rs.sub
                sub_freq = sub.freq
                if sub_freq:
                    result["sub_frequency_hz"] = float(sub_freq)
                    result["sub_mode"] = str(sub.mode or "")
                    sub_fw = getattr(sub, "filter_width", None)
                    if sub_fw:
                        result["sub_bandwidth_hz"] = float(sub_fw)
            except Exception:
                pass

        except Exception as exc:
            log.debug("get_full_state: %s", exc)

        # RF power is not in the rigplane state cache — query it directly.
        try:
            result["rf_power"] = await self.get_level("RFPOWER")
        except Exception:
            pass

        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require(self) -> None:
        if self._radio is None or not self.connected:
            raise RadioBackendError("Icom LAN radio not connected")

"""
RadioInterface - wraps a single backend, owns the poll loop, and maintains RadioState.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional, Union

from .backends.base import RadioBackend, RadioBackendError
from .radio_state import RadioMode, RadioState

logger = logging.getLogger(__name__)

StateCallback = Callable[["RadioState", dict], Union[None, Awaitable[None]]]


class RadioInterface:
    """
    Wraps a RadioBackend.  Polls the radio at a configurable interval,
    keeps a RadioState snapshot up to date, and notifies registered
    callbacks whenever any field changes.

    Can be used standalone or managed by RadioManager.

    Usage::

        async with RadioInterface("ic7300", RigctldBackend()) as radio:
            await radio.set_frequency(14_200_000)
            print(radio.state.frequency_hz)
    """

    def __init__(
        self,
        name: str,
        backend: RadioBackend,
        poll_interval_s: float = 0.5,
        reconnect_delay_s: float = 5.0,
    ) -> None:
        self.name = name
        self._backend = backend
        self._poll_interval = poll_interval_s
        self._reconnect_delay = reconnect_delay_s
        self.state = RadioState(name=name)
        self._callbacks: list[StateCallback] = []
        self._task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        await self._backend.connect()
        try:
            self.state.info = await self._backend.get_info()
        except RadioBackendError:
            pass
        self.state.connected = True

    async def disconnect(self) -> None:
        await self._backend.disconnect()
        self.state.connected = False

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(
            self._poll_loop(), name=f"radio-poll-{self.name}"
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def __aenter__(self) -> "RadioInterface":
        await self.connect()
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()
        await self.disconnect()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_state_change(self, callback: StateCallback) -> StateCallback:
        """Register a state-change callback.  Works as a decorator or plain call.

        The callback receives ``(state, diff)`` where ``diff`` is a dict of
        only the fields that changed.
        """
        self._callbacks.append(callback)
        return callback

    async def _fire(self, diff: dict) -> None:
        for cb in self._callbacks:
            try:
                result = cb(self.state, diff)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("State change callback raised an exception")

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while True:
            try:
                if not self._backend.connected:
                    await self._reconnect()
                else:
                    await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in radio poll loop for %s", self.name)
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        try:
            raw = await self._backend.get_full_state()
        except RadioBackendError as exc:
            logger.warning("Poll failed for %s: %s", self.name, exc)
            if self.state.connected:
                self.state.connected = False
                await self._fire({"connected": False})
            return

        prev = self.state.copy()
        _apply_raw_state(self.state, raw)
        self.state.connected = self._backend.connected

        diff = prev.diff(self.state)
        if diff:
            await self._fire(diff)

    async def _reconnect(self) -> None:
        await asyncio.sleep(self._reconnect_delay)
        try:
            await self._backend.connect()
            self._reconnect_attempts = 0
            # Don't broadcast "connected" here - wait for the first successful
            # poll to confirm the radio is actually responding before the UI
            # flips back to "online".
            logger.info("Reconnected %s - awaiting first poll", self.name)
        except RadioBackendError as exc:
            self._reconnect_attempts += 1
            if self._reconnect_attempts == 1:
                logger.error("Radio '%s' cannot connect: %s", self.name, exc)
            elif self._reconnect_attempts % 12 == 0:
                logger.error(
                    "Radio '%s' still not connected after %d attempts",
                    self.name, self._reconnect_attempts,
                )

    # ------------------------------------------------------------------
    # Radio control - delegate to backend, update state immediately
    # ------------------------------------------------------------------

    async def get_frequency(self) -> float:
        val = await self._backend.get_frequency()
        self.state.frequency_hz = val
        return val

    async def set_frequency(self, hz: float) -> None:
        await self._backend.set_frequency(hz)
        self.state.frequency_hz = hz

    async def get_mode(self) -> tuple[str, float]:
        mode_str, bw = await self._backend.get_mode()
        self.state.mode = RadioMode.from_str(mode_str)
        self.state.bandwidth_hz = bw
        return mode_str, bw

    async def set_mode(self, mode: str, bandwidth_hz: float = 0) -> None:
        await self._backend.set_mode(mode, bandwidth_hz)
        self.state.mode = RadioMode.from_str(mode)
        if bandwidth_hz:
            self.state.bandwidth_hz = bandwidth_hz

    async def get_vfo(self) -> str:
        val = await self._backend.get_vfo()
        self.state.vfo = val
        return val

    async def set_vfo(self, vfo: str) -> None:
        await self._backend.set_vfo(vfo)
        self.state.vfo = vfo

    async def get_ptt(self) -> bool:
        val = await self._backend.get_ptt()
        self.state.ptt = val
        return val

    async def set_ptt(self, transmit: bool) -> None:
        await self._backend.set_ptt(transmit)
        self.state.ptt = transmit

    async def get_split(self) -> tuple[bool, Optional[float]]:
        active, tx_hz = await self._backend.get_split()
        self.state.split = active
        self.state.split_freq_hz = tx_hz
        return active, tx_hz

    async def set_split(self, active: bool, tx_hz: Optional[float] = None) -> None:
        await self._backend.set_split(active, tx_hz)
        self.state.split = active
        if tx_hz is not None:
            self.state.split_freq_hz = tx_hz

    async def get_level(self, level_name: str) -> float:
        val = await self._backend.get_level(level_name)
        _apply_level(self.state, level_name, val)
        return val

    async def set_level(self, level_name: str, value: float) -> None:
        await self._backend.set_level(level_name, value)
        _apply_level(self.state, level_name, value)

    # ------------------------------------------------------------------
    # Optional capabilities — delegate to backend; caller handles
    # NotImplementedError when the backend does not support the feature.
    # ------------------------------------------------------------------

    async def get_rit(self) -> int:
        return await self._backend.get_rit()

    async def set_rit(self, offset_hz: int) -> None:
        await self._backend.set_rit(offset_hz)

    async def get_xit(self) -> int:
        return await self._backend.get_xit()

    async def set_xit(self, offset_hz: int) -> None:
        await self._backend.set_xit(offset_hz)

    async def get_func(self, func_name: str) -> bool:
        return await self._backend.get_func(func_name)

    async def set_func(self, func_name: str, value: bool) -> None:
        await self._backend.set_func(func_name, value)

    async def get_ctcss_tone(self) -> int:
        return await self._backend.get_ctcss_tone()

    async def set_ctcss_tone(self, tone: int) -> None:
        await self._backend.set_ctcss_tone(tone)

    async def get_dcs_code(self) -> int:
        return await self._backend.get_dcs_code()

    async def set_dcs_code(self, code: int) -> None:
        await self._backend.set_dcs_code(code)


# ------------------------------------------------------------------
# Helpers (module-level to keep the class lean)
# ------------------------------------------------------------------

def _apply_raw_state(state: RadioState, raw: dict) -> None:
    if "frequency_hz" in raw:
        state.frequency_hz = raw["frequency_hz"]
    if "mode" in raw:
        state.mode = RadioMode.from_str(raw["mode"])
    if "bandwidth_hz" in raw:
        state.bandwidth_hz = raw["bandwidth_hz"]
    if "vfo" in raw:
        state.vfo = raw["vfo"]
    if "ptt" in raw:
        state.ptt = raw["ptt"]
    if "split" in raw:
        state.split = raw["split"]
    if "split_freq_hz" in raw:
        state.split_freq_hz = raw["split_freq_hz"]
    if "signal_strength" in raw:
        state.signal_strength = raw["signal_strength"]
    if "rf_power" in raw:
        state.rf_power = raw["rf_power"]
    if "vfob_frequency_hz" in raw:
        state.vfob_frequency_hz = raw["vfob_frequency_hz"]
    if "vfob_mode" in raw:
        state.vfob_mode = raw["vfob_mode"]
    if "vfob_bandwidth_hz" in raw:
        state.vfob_bandwidth_hz = raw["vfob_bandwidth_hz"]
    if "sub_frequency_hz" in raw:
        state.sub_frequency_hz = raw["sub_frequency_hz"]
    if "sub_mode" in raw:
        state.sub_mode = raw["sub_mode"]
    if "sub_bandwidth_hz" in raw:
        state.sub_bandwidth_hz = raw["sub_bandwidth_hz"]


def _apply_level(state: RadioState, level_name: str, value: float) -> None:
    name = level_name.upper()
    if name == "RFPOWER":
        state.rf_power = value
    elif name == "STRENGTH":
        state.signal_strength = value

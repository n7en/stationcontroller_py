"""
Action hierarchy for the automation engine.

All actions implement execute(ctx) as a coroutine.
Actions are composable: Sequence, Conditional.

Hardware actions (SetRadioPower, SetRelay) require the relevant interface to
be set on the AutomationContext; they raise RuntimeError if called without it.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from .context import AutomationContext

if TYPE_CHECKING:
    from .condition import Condition

log = logging.getLogger(__name__)


class Action(ABC):
    @abstractmethod
    async def execute(self, ctx: AutomationContext) -> None: ...


# ---------------------------------------------------------------------------
# Trivial / utility
# ---------------------------------------------------------------------------

class NoOp(Action):
    async def execute(self, ctx: AutomationContext) -> None:
        pass


class Log(Action):
    def __init__(self, message: str, level: str = "INFO") -> None:
        self.message = message
        self._level = getattr(logging, level.upper(), logging.INFO)

    async def execute(self, ctx: AutomationContext) -> None:
        log.log(self._level, self.message)


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------

class Sequence(Action):
    def __init__(self, *actions: Action) -> None:
        self.actions = actions

    async def execute(self, ctx: AutomationContext) -> None:
        for action in self.actions:
            await action.execute(ctx)


class Conditional(Action):
    """Execute if_true when condition holds, otherwise if_false (if provided)."""

    def __init__(
        self,
        condition: "Condition",
        if_true: Action,
        if_false: Optional[Action] = None,
    ) -> None:
        self.condition = condition
        self.if_true = if_true
        self.if_false = if_false

    async def execute(self, ctx: AutomationContext) -> None:
        if self.condition.evaluate(ctx):
            await self.if_true.execute(ctx)
        elif self.if_false is not None:
            await self.if_false.execute(ctx)


# ---------------------------------------------------------------------------
# Hardware actions
# ---------------------------------------------------------------------------

class SetRadioPower(Action):
    """
    Set the radio transmit power.

    watts - desired output power in watts.
    ctx.radio_interface must be set and ctx.radio_max_power_w must be provided
    so the engine can normalise watts -> 0.0–1.0 for the backend.
    """

    def __init__(self, watts: float) -> None:
        self.watts = watts

    async def execute(self, ctx: AutomationContext) -> None:
        if ctx.radio_interface is None:
            raise RuntimeError(
                "SetRadioPower requires radio_interface on AutomationContext"
            )
        if ctx.radio_max_power_w is None or ctx.radio_max_power_w <= 0:
            raise RuntimeError(
                "SetRadioPower requires radio_max_power_w on AutomationContext"
            )
        normalized = max(0.0, min(1.0, self.watts / ctx.radio_max_power_w))
        await ctx.radio_interface.set_level("RFPOWER", normalized)
        log.info("SetRadioPower: %.1f W (%.3f normalized)", self.watts, normalized)


class SetFrequency(Action):
    """Set the radio's VFO frequency via the radio interface."""

    def __init__(self, hz: float) -> None:
        self.hz = hz

    async def execute(self, ctx: AutomationContext) -> None:
        if ctx.radio_interface is None:
            raise RuntimeError(
                "SetFrequency requires radio_interface on AutomationContext"
            )
        await ctx.radio_interface.set_frequency(self.hz)
        log.info("SetFrequency: %.0f Hz", self.hz)


class SetMode(Action):
    """Set the radio's operating mode (e.g. USB, LSB, CW) via the radio interface."""

    def __init__(self, mode: str, bandwidth_hz: float = 0) -> None:
        self.mode = mode
        self.bandwidth_hz = bandwidth_hz

    async def execute(self, ctx: AutomationContext) -> None:
        if ctx.radio_interface is None:
            raise RuntimeError(
                "SetMode requires radio_interface on AutomationContext"
            )
        await ctx.radio_interface.set_mode(self.mode, self.bandwidth_hz)
        log.info("SetMode: %s  bw=%.0f Hz", self.mode, self.bandwidth_hz)


class TuneRadio(Action):
    """
    Set frequency and optionally mode in one step.

    Equivalent to SetFrequency followed by SetMode, but expressed as a single
    config block - useful for automation rules like "tune to the 20m net freq".
    """

    def __init__(
        self,
        frequency_hz: float,
        mode: str | None = None,
        bandwidth_hz: float = 0,
    ) -> None:
        self.frequency_hz = frequency_hz
        self.mode = mode
        self.bandwidth_hz = bandwidth_hz

    async def execute(self, ctx: AutomationContext) -> None:
        if ctx.radio_interface is None:
            raise RuntimeError(
                "TuneRadio requires radio_interface on AutomationContext"
            )
        await ctx.radio_interface.set_frequency(self.frequency_hz)
        if self.mode is not None:
            await ctx.radio_interface.set_mode(self.mode, self.bandwidth_hz)
        log.info(
            "TuneRadio: %.0f Hz%s",
            self.frequency_hz,
            f"  mode={self.mode}" if self.mode else "",
        )


class SetRelay(Action):
    """
    Send a relay command over the DCN control network.

    relay_num  - 1-indexed relay number on the GPIO module
    state      - 1 (on) or 0 (off)
    dcn_address - target device DCN address string (e.g. "01")

    ctx.control_network must be a connected DCNNetwork.
    """

    def __init__(self, dcn_address: str, relay_num: int, state: int) -> None:
        if state not in (0, 1):
            raise ValueError(f"relay state must be 0 or 1, got {state}")
        self.dcn_address = dcn_address
        self.relay_num = relay_num
        self.state = state

    async def execute(self, ctx: AutomationContext) -> None:
        if ctx.control_network is None:
            raise RuntimeError(
                "SetRelay requires control_network on AutomationContext"
            )
        cmd = f"RY{self.relay_num},{self.state}"
        await ctx.control_network.send(self.dcn_address, cmd)
        log.info(
            "SetRelay: addr=%s relay=%d state=%d",
            self.dcn_address, self.relay_num, self.state,
        )


class SetFunc(Action):
    """Enable or disable a named rig function (NB, NR, VOX, TUNER, LOCK, …)."""

    def __init__(self, func: str, value: bool) -> None:
        self.func  = func.upper()
        self.value = value

    async def execute(self, ctx: AutomationContext) -> None:
        if ctx.radio_interface is None:
            raise RuntimeError("SetFunc requires radio_interface on AutomationContext")
        await ctx.radio_interface.set_func(self.func, self.value)
        log.info("SetFunc: %s = %s", self.func, self.value)


class SetRit(Action):
    """Set the RIT (Receive Incremental Tuning) offset in Hz.  0 = off."""

    def __init__(self, offset_hz: int) -> None:
        self.offset_hz = int(offset_hz)

    async def execute(self, ctx: AutomationContext) -> None:
        if ctx.radio_interface is None:
            raise RuntimeError("SetRit requires radio_interface on AutomationContext")
        await ctx.radio_interface.set_rit(self.offset_hz)
        log.info("SetRit: %+d Hz", self.offset_hz)


class SetXit(Action):
    """Set the XIT (Transmit Incremental Tuning) offset in Hz.  0 = off."""

    def __init__(self, offset_hz: int) -> None:
        self.offset_hz = int(offset_hz)

    async def execute(self, ctx: AutomationContext) -> None:
        if ctx.radio_interface is None:
            raise RuntimeError("SetXit requires radio_interface on AutomationContext")
        await ctx.radio_interface.set_xit(self.offset_hz)
        log.info("SetXit: %+d Hz", self.offset_hz)


class SetCtcssTone(Action):
    """Set the CTCSS encode tone.  Tone is in tenths of Hz (e.g. 670 = 67.0 Hz); 0 = off."""

    def __init__(self, tone: int) -> None:
        self.tone = int(tone)

    async def execute(self, ctx: AutomationContext) -> None:
        if ctx.radio_interface is None:
            raise RuntimeError("SetCtcssTone requires radio_interface on AutomationContext")
        await ctx.radio_interface.set_ctcss_tone(self.tone)
        log.info("SetCtcssTone: %d (%.1f Hz)", self.tone, self.tone / 10.0)


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------

def action_from_config(cfg: dict) -> Action:
    """
    Build an Action from a config dict.

    The 'type' key selects the action class; remaining keys are arguments.
    """
    from .condition import condition_from_config  # avoid circular at module level

    kind = cfg.get("type", "")
    if kind == "noop":
        return NoOp()
    if kind == "log":
        return Log(cfg["message"], cfg.get("level", "INFO"))
    if kind == "sequence":
        return Sequence(*(action_from_config(a) for a in cfg["actions"]))
    if kind == "conditional":
        return Conditional(
            condition_from_config(cfg["condition"]),
            action_from_config(cfg["if_true"]),
            action_from_config(cfg["if_false"]) if cfg.get("if_false") else None,
        )
    if kind == "set_radio_power":
        return SetRadioPower(float(cfg["watts"]))
    if kind == "set_frequency":
        return SetFrequency(float(cfg["frequency_hz"]))
    if kind == "set_mode":
        return SetMode(str(cfg["mode"]), float(cfg.get("bandwidth_hz", 0)))
    if kind == "tune_radio":
        return TuneRadio(
            float(cfg["frequency_hz"]),
            str(cfg["mode"]) if "mode" in cfg else None,
            float(cfg.get("bandwidth_hz", 0)),
        )
    if kind == "set_relay":
        return SetRelay(
            str(cfg["dcn_address"]),
            int(cfg["relay_num"]),
            int(cfg["state"]),
        )
    if kind == "set_func":
        return SetFunc(str(cfg["func"]), bool(cfg.get("value", True)))
    if kind == "set_rit":
        return SetRit(int(cfg.get("offset_hz", 0)))
    if kind == "set_xit":
        return SetXit(int(cfg.get("offset_hz", 0)))
    if kind == "set_ctcss_tone":
        return SetCtcssTone(int(cfg.get("tone", 0)))
    raise ValueError(f"Unknown action type: {kind!r}")

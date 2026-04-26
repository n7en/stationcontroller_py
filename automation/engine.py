"""
AutomationEngine — Home Assistant-style Trigger → Condition → Action engine.

Call process(ctx) whenever sensor or radio state changes.  The engine
updates every trigger; automations whose triggers detect a transition have
their conditions checked and, if all pass, their action executed.

Manual testing
--------------
Call engine.trigger(name, ctx) to fire an automation by name without waiting
for its real trigger condition.  Conditions are still evaluated (unless
bypass_conditions=True is passed).

Execution modes (AutomationMode)
---------------------------------
SINGLE   — skip if the automation's action is already running (default)
RESTART  — cancel the running action and start fresh
QUEUED   — queue up to 10 executions; drain in order after current finishes
PARALLEL — always run; no concurrency tracking
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from typing import Optional

from .automation import Automation, AutomationMode, AutomationTier
from .context import AutomationContext
from .trigger import TriggerData

log = logging.getLogger(__name__)


class AutomationEngine:
    def __init__(self) -> None:
        self._automations: list[Automation] = []
        self._executing: set[str] = set()       # names currently awaiting their action
        self._tasks: dict[str, asyncio.Task] = {}   # for RESTART cancellation only
        self._queues: dict[str, deque] = {}

    # ------------------------------------------------------------------
    # Automation management
    # ------------------------------------------------------------------

    def add_automation(self, automation: Automation) -> None:
        if any(a.name == automation.name for a in self._automations):
            raise ValueError(f"Automation {automation.name!r} already exists")
        self._automations.append(automation)
        self._sort()

    def remove_automation(self, name: str) -> None:
        before = len(self._automations)
        self._automations = [a for a in self._automations if a.name != name]
        if len(self._automations) == before:
            raise KeyError(f"Automation {name!r} not found")
        self._executing.discard(name)
        self._tasks.pop(name, None)
        self._queues.pop(name, None)

    def get_automation(self, name: str) -> Optional[Automation]:
        return next((a for a in self._automations if a.name == name), None)

    def automations(self, tier: Optional[AutomationTier] = None) -> list[Automation]:
        if tier is None:
            return list(self._automations)
        return [a for a in self._automations if a.tier == tier]

    def _sort(self) -> None:
        self._automations.sort(key=lambda a: (a.tier.order, -a.priority))

    # ------------------------------------------------------------------
    # Normal processing (called on every state change)
    # ------------------------------------------------------------------

    async def process(self, ctx: AutomationContext) -> list[str]:
        """
        Update all triggers and execute automations whose triggers fired.
        Returns the names of automations whose actions ran this cycle.
        """
        fired: list[str] = []
        for automation in self._automations:
            if not automation.enabled:
                continue
            for trigger in automation.triggers:
                td = trigger.update(
                    ctx.registry, ctx.radio_state, ctx.band_registry
                )
                if td is not None:
                    td.automation_name = automation.name
                    ran = await self._run(automation, td, ctx)
                    if ran:
                        fired.append(automation.name)
                    break   # first firing trigger is enough
        return fired

    # ------------------------------------------------------------------
    # Manual trigger — for testing
    # ------------------------------------------------------------------

    async def trigger(
        self,
        name: str,
        ctx: AutomationContext,
        bypass_conditions: bool = False,
    ) -> bool:
        """
        Manually fire an automation by name.

        Bypasses trigger evaluation — useful for testing rules without
        waiting for real hardware events.  Conditions are still evaluated
        unless bypass_conditions=True.

        Returns True if the action ran, False if conditions blocked it or
        the automation is disabled.
        """
        automation = self.get_automation(name)
        if automation is None:
            raise KeyError(f"Automation {name!r} not found")
        if not automation.enabled:
            log.warning("Automation %r is disabled — manual trigger ignored", name)
            return False
        td = TriggerData(
            trigger_type="manual",
            manual=True,
            automation_name=name,
        )
        return await self._run(automation, td, ctx, bypass_conditions=bypass_conditions)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _run(
        self,
        automation: Automation,
        trigger_data: TriggerData,
        ctx: AutomationContext,
        bypass_conditions: bool = False,
    ) -> bool:
        name = automation.name
        mode = automation.mode

        # Execution mode gate
        if name in self._executing:
            if mode == AutomationMode.SINGLE:
                log.debug("Automation %r: skipped (already running, mode=single)", name)
                return False

            if mode == AutomationMode.QUEUED:
                q = self._queues.setdefault(name, deque(maxlen=10))
                q.append((trigger_data, ctx))
                log.debug("Automation %r queued (%d pending)", name, len(q))
                return False

            if mode == AutomationMode.RESTART:
                task = self._tasks.get(name)
                if task and not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
            # PARALLEL: fall through — no concurrency gate

        # Conditions — all must pass
        if not bypass_conditions and automation.conditions:
            if not all(c.evaluate(ctx) for c in automation.conditions):
                log.debug(
                    "Automation %r: conditions not met (trigger=%s)",
                    name, trigger_data.trigger_type,
                )
                return False

        log.info(
            "Automation fired: %s  tier=%s  trigger=%s%s",
            name,
            automation.tier.value,
            trigger_data.trigger_type,
            "  [manual]" if trigger_data.manual else "",
        )

        if mode == AutomationMode.RESTART:
            # Use a task so we can cancel it on re-trigger
            self._executing.add(name)
            task = asyncio.create_task(self._execute_bare(automation, ctx))
            self._tasks[name] = task
            try:
                await task
            except asyncio.CancelledError:
                return False
            finally:
                self._executing.discard(name)
                self._drain_queue(name)
            return True

        if mode == AutomationMode.PARALLEL:
            # No concurrency tracking — always run
            await self._execute_bare(automation, ctx)
            return True

        # SINGLE and QUEUED: direct await with _executing tracking
        # _executing.add is synchronous so any concurrent coroutine that checks
        # before the first yield will see the name and skip/queue correctly.
        self._executing.add(name)
        try:
            await self._execute_bare(automation, ctx)
        finally:
            self._executing.discard(name)
            self._drain_queue(name)
        return True

    async def _execute_bare(self, automation: Automation, ctx: AutomationContext) -> None:
        try:
            await automation.action.execute(ctx)
        except asyncio.CancelledError:
            log.debug("Automation %r cancelled", automation.name)
            raise
        except Exception:
            log.exception("Error executing automation %r", automation.name)

    def _drain_queue(self, name: str) -> None:
        q = self._queues.get(name)
        if q:
            trigger_data, ctx = q.popleft()
            automation = self.get_automation(name)
            if automation:
                asyncio.create_task(self._run(automation, trigger_data, ctx))
